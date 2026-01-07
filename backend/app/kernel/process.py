"""Kernel process implementation."""
import asyncio
from multiprocessing import Queue
from typing import Dict
from .types import ExecuteRequest
from ..core.ast_parser import extract_python_dependencies, extract_sql_dependencies
from ..core.graph import DependencyGraph, CycleDetectedError
from ..core.executor import PythonExecutor, SQLExecutor


def kernel_main(input_queue: Queue, output_queue: Queue):
    """
    Main loop for kernel process.

    Runs in a separate process and handles execution requests.
    """
    # Initialize kernel state
    python_executor = PythonExecutor()
    sql_executor = SQLExecutor()
    graph = DependencyGraph()
    cell_registry: Dict[str, tuple[str, str]] = {}  # cell_id → (code, cell_type)
    has_run: Dict[str, bool] = {}  # cell_id → has executed successfully

    print("[Kernel] Started")

    while True:
        # Wait for request (blocking)
        request_data = input_queue.get()

        # Check for shutdown
        if request_data.get('type') == 'shutdown':
            print("[Kernel] Shutting down")
            break

        # Check for register_cell request
        if request_data.get('type') == 'register_cell':
            try:
                from .types import RegisterCellRequest, CellNotification, CellOutput, CellChannel
                register_req = RegisterCellRequest(**request_data)

                # Extract dependencies
                if register_req.cell_type == 'python':
                    reads, writes = extract_python_dependencies(register_req.code)
                else:  # sql
                    reads = extract_sql_dependencies(register_req.code)
                    writes = set()

                # Update graph - REJECT if cycle detected
                try:
                    graph.update_cell(register_req.cell_id, reads, writes)

                    # Store cell code for future execution only if registration succeeds
                    cell_registry[register_req.cell_id] = (register_req.code, register_req.cell_type)

                    # Invalidate has_run for this cell
                    has_run[register_req.cell_id] = False

                    # Invalidate all descendants (they depend on this cell's output)
                    import networkx as nx
                    try:
                        if graph._graph.has_node(register_req.cell_id):
                            for descendant in nx.descendants(graph._graph, register_req.cell_id):
                                has_run[descendant] = False
                    except nx.NetworkXError:
                        pass  # No descendants or graph issue

                    # Send metadata notification
                    output_queue.put(CellNotification(
                        cell_id=register_req.cell_id,
                        output=CellOutput(
                            channel=CellChannel.METADATA,
                            mimetype="application/json",
                            data={"reads": list(reads), "writes": list(writes)}
                        )
                    ).model_dump())

                    # Send status notification
                    output_queue.put(CellNotification(
                        cell_id=register_req.cell_id,
                        output=CellOutput(
                            channel=CellChannel.STATUS,
                            mimetype="application/json",
                            data={"status": "idle"}
                        )
                    ).model_dump())

                except CycleDetectedError as e:
                    # Send error notification
                    output_queue.put(CellNotification(
                        cell_id=register_req.cell_id,
                        output=CellOutput(
                            channel=CellChannel.ERROR,
                            mimetype="application/json",
                            data={
                                "error_type": "CycleDetectedError",
                                "message": str(e)
                            }
                        )
                    ).model_dump())

                    # Send blocked status
                    output_queue.put(CellNotification(
                        cell_id=register_req.cell_id,
                        output=CellOutput(
                            channel=CellChannel.STATUS,
                            mimetype="application/json",
                            data={"status": "blocked"}
                        )
                    ).model_dump())

                continue
            except Exception as e:
                print(f"[Kernel] Invalid register request: {e}")
                continue

        # Handle database configuration
        if request_data.get('type') == 'set_database_config':
            try:
                from .types import SetDatabaseConfigRequest, CellNotification, CellOutput, CellChannel

                config_req = SetDatabaseConfigRequest(**request_data)

                # Configure SQL executor
                sql_executor.set_connection_string(config_req.connection_string)

                print(f"[Kernel] Database configured: {config_req.connection_string}")

                # Send status notification (use special "__system__" cell_id for non-cell messages)
                output_queue.put(CellNotification(
                    cell_id="__system__",
                    output=CellOutput(
                        channel=CellChannel.STATUS,
                        mimetype="application/json",
                        data={"status": "db_configured"}
                    )
                ).model_dump())

            except Exception as e:
                # Send error notification
                output_queue.put(CellNotification(
                    cell_id="__system__",
                    output=CellOutput(
                        channel=CellChannel.ERROR,
                        mimetype="application/json",
                        data={
                            "error_type": "DatabaseConfigError",
                            "message": str(e)
                        }
                    )
                ).model_dump())

            continue

        # Handle execute request (make explicit instead of fallthrough)
        if request_data.get('type') == 'execute' or 'cell_id' in request_data:
            try:
                from .types import CellNotification, CellOutput, CellChannel
                request = ExecuteRequest(**request_data)
            except Exception as e:
                print(f"[Kernel] Invalid execute request: {e}")
                continue

            # Verify cell is registered
            if request.cell_id not in cell_registry:
                # Check if cell exists in graph but failed registration (blocked due to cycle)
                # If so, silently skip to avoid duplicate error messages
                if graph._graph.has_node(request.cell_id):
                    # Cell is in graph but blocked - error already sent during registration
                    continue

                # Cell doesn't exist at all - this is unexpected, send error
                error_msg = (
                    f"Cell {request.cell_id} not registered. "
                    "Cells must be registered via RegisterCellRequest before execution."
                )
                output_queue.put(CellNotification(
                    cell_id=request.cell_id,
                    output=CellOutput(
                        channel=CellChannel.ERROR,
                        mimetype="application/json",
                        data={
                            "error_type": "CellNotRegistered",
                            "message": error_msg
                        }
                    )
                ).model_dump())
                continue

            # Get execution order with only STALE ancestors
            # (ancestors that haven't been executed yet or have changed since last execution)
            import networkx as nx

            if graph._graph.has_node(request.cell_id):
                # Get all ancestors
                all_ancestors = set(nx.ancestors(graph._graph, request.cell_id))

                # Filter to only stale ancestors (not yet run)
                stale_ancestors = {a for a in all_ancestors if not has_run.get(a, False)}

                # Get descendants (for reactive cascade)
                descendants = set(nx.descendants(graph._graph, request.cell_id))

                # Combine: stale ancestors + self + descendants
                affected = stale_ancestors | {request.cell_id} | descendants

                # Topological sort
                subgraph = graph._graph.subgraph(affected)
                try:
                    cells_to_run = list(nx.topological_sort(subgraph))
                except nx.NetworkXError:
                    cells_to_run = [request.cell_id]
            else:
                # Cell not registered yet in graph, just run it
                cells_to_run = [request.cell_id]


            # Execute all affected cells in topological order
            for cell_id in cells_to_run:
                if cell_id not in cell_registry:
                    # Cell hasn't been registered yet (shouldn't happen)
                    continue

                cell_code, cell_type = cell_registry[cell_id]

                # Send status: running
                output_queue.put(CellNotification(
                    cell_id=cell_id,
                    output=CellOutput(
                        channel=CellChannel.STATUS,
                        mimetype="application/json",
                        data={"status": "running"}
                    )
                ).model_dump())

                # Execute
                if cell_type == 'python':
                    exec_result = python_executor.execute(cell_code)
                    cell_reads, cell_writes = extract_python_dependencies(cell_code)
                else:
                    # SQL execution (async)
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        exec_result = loop.run_until_complete(
                            sql_executor.execute(cell_code, python_executor.globals_dict)
                        )
                    finally:
                        loop.close()
                    cell_reads = extract_sql_dependencies(cell_code)
                    cell_writes = set()

                # Send stdout (if any)
                if exec_result.stdout:
                    output_queue.put(CellNotification(
                        cell_id=cell_id,
                        output=CellOutput(
                            channel=CellChannel.STDOUT,
                            mimetype="text/plain",
                            data=exec_result.stdout
                        )
                    ).model_dump())

                # Send outputs (plots, tables, etc.)
                for output in exec_result.outputs:
                    output_queue.put(CellNotification(
                        cell_id=cell_id,
                        output=CellOutput(
                            channel=CellChannel.OUTPUT,
                            mimetype=output.mime_type,
                            data=output.data
                        )
                    ).model_dump())

                # Send status: success or error
                status = "success" if exec_result.status == "success" else "error"
                output_queue.put(CellNotification(
                    cell_id=cell_id,
                    output=CellOutput(
                        channel=CellChannel.STATUS,
                        mimetype="application/json",
                        data={"status": status}
                    )
                ).model_dump())

                # Mark cell as successfully run if execution succeeded
                if status == "success":
                    has_run[cell_id] = True

                # Send error details (if any)
                if exec_result.error:
                    output_queue.put(CellNotification(
                        cell_id=cell_id,
                        output=CellOutput(
                            channel=CellChannel.ERROR,
                            mimetype="application/json",
                            data={
                                "error_type": "RuntimeError",
                                "message": exec_result.error
                            }
                        )
                    ).model_dump())

                # Send metadata (dependency info)
                output_queue.put(CellNotification(
                    cell_id=cell_id,
                    output=CellOutput(
                        channel=CellChannel.METADATA,
                        mimetype="application/json",
                        data={
                            "reads": list(cell_reads),
                            "writes": list(cell_writes)
                        }
                    )
                ).model_dump())
