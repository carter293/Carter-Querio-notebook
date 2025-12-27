import asyncio
from typing import Set, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Notebook, Cell, CellStatus, CellType
    from websocket import WebSocketBroadcaster
else:
    Notebook = 'Notebook'
    Cell = 'Cell'
    CellStatus = 'CellStatus'
    CellType = 'CellType'
    WebSocketBroadcaster = 'WebSocketBroadcaster'

class ExecutionScheduler:
    def __init__(self):
        self.current_tasks: Dict[str, asyncio.Task] = {}  # notebook_id -> task
        self.pending_runs: Dict[str, Set[str]] = {}  # notebook_id -> set of cell_ids
        self.locks: Dict[str, asyncio.Lock] = {}  # notebook_id -> lock

    def get_lock(self, notebook_id: str) -> asyncio.Lock:
        if notebook_id not in self.locks:
            self.locks[notebook_id] = asyncio.Lock()
        return self.locks[notebook_id]

    async def enqueue_run(self, notebook_id: str, cell_id: str, notebook, broadcaster):
        """Enqueue a cell to be run, handling concurrent requests"""
        lock = self.get_lock(notebook_id)

        async with lock:
            # Add to pending runs
            if notebook_id not in self.pending_runs:
                self.pending_runs[notebook_id] = set()
            self.pending_runs[notebook_id].add(cell_id)

            # If already running, the pending runs will be picked up after completion
            if notebook_id in self.current_tasks and not self.current_tasks[notebook_id].done():
                return

            # Start draining queue
            self.current_tasks[notebook_id] = asyncio.create_task(
                self._drain_queue(notebook_id, notebook, broadcaster)
            )

    async def _drain_queue(self, notebook_id: str, notebook, broadcaster):
        """Process all pending runs"""
        from graph import topological_sort, get_all_dependents
        from models import CellStatus

        while True:
            lock = self.get_lock(notebook_id)
            async with lock:
                if not self.pending_runs.get(notebook_id):
                    # Queue empty
                    break

                # Get all pending cells
                pending_cells = self.pending_runs[notebook_id].copy()
                self.pending_runs[notebook_id].clear()

            # Compute transitive closure (all cells to run)
            all_to_run = set(pending_cells)
            for cell_id in pending_cells:
                dependents = get_all_dependents(notebook.graph, cell_id)
                all_to_run.update(dependents)

            # Topological sort
            try:
                sorted_cells = topological_sort(notebook.graph, all_to_run)
            except ValueError:
                # Cycle detected - mark all as error
                for cell_id in all_to_run:
                    cell = self._get_cell(notebook, cell_id)
                    if cell:
                        cell.status = CellStatus.ERROR
                        cell.error = "Cycle detected in dependency graph"
                        await broadcaster.broadcast_cell_status(notebook_id, cell_id, CellStatus.ERROR)
                        await broadcaster.broadcast_cell_error(notebook_id, cell_id, cell.error)
                continue

            # Execute in order
            for cell_id in sorted_cells:
                cell = self._get_cell(notebook, cell_id)
                if not cell:
                    continue

                # Check if upstream dependency failed
                has_failed_dependency = False
                if cell_id in notebook.graph.reverse_edges:
                    for dep_id in notebook.graph.reverse_edges[cell_id]:
                        dep_cell = self._get_cell(notebook, dep_id)
                        if dep_cell and dep_cell.status == CellStatus.ERROR:
                            has_failed_dependency = True
                            break

                if has_failed_dependency:
                    # Mark as blocked
                    cell.status = CellStatus.BLOCKED
                    await broadcaster.broadcast_cell_status(notebook_id, cell_id, CellStatus.BLOCKED)
                    continue

                # Execute cell
                await self._execute_cell(notebook_id, cell, notebook, broadcaster)

    async def _execute_cell(self, notebook_id: str, cell, notebook, broadcaster):
        """Execute a single cell and broadcast results"""
        from executor import execute_python_cell, execute_sql_cell
        from models import CellStatus, CellType

        # Get cell index for better error messages
        cell_index = notebook.cells.index(cell)

        # Mark as running
        cell.status = CellStatus.RUNNING
        await broadcaster.broadcast_cell_status(notebook_id, cell.id, CellStatus.RUNNING)
        
        # Yield to event loop to flush WebSocket message before synchronous execution.
        # This is a standard Python async pattern - libraries like matplotlib use 
        # thread-local storage and don't work in thread pools, so we must run
        # execution in the main thread but yield first to send the RUNNING status.
        await asyncio.sleep(0)

        # Clear previous outputs
        cell.stdout = ""
        cell.outputs = []
        cell.error = None

        # Execute based on type
        if cell.type == CellType.PYTHON:
            result = await execute_python_cell(cell, notebook.kernel.globals_dict, cell_index)
        elif cell.type == CellType.SQL:
            result = await execute_sql_cell(cell, notebook.db_conn_string, notebook.kernel.globals_dict)
        else:
            from executor import ExecutionResult
            result = ExecutionResult(
                status=CellStatus.ERROR,
                error=f"Unknown cell type: {cell.type}"
            )

        # Update cell
        cell.status = result.status
        cell.stdout = result.stdout
        cell.outputs = result.outputs
        cell.error = result.error

        # Broadcast results
        await broadcaster.broadcast_cell_status(notebook_id, cell.id, result.status)

        if result.stdout:
            await broadcaster.broadcast_cell_stdout(notebook_id, cell.id, result.stdout)

        if result.error:
            await broadcaster.broadcast_cell_error(notebook_id, cell.id, result.error)

        # Broadcast outputs
        for output in result.outputs:
            await broadcaster.broadcast_cell_output(notebook_id, cell.id, {
                "mime_type": output.mime_type,
                "data": output.data,
                "metadata": output.metadata
            })

    def _get_cell(self, notebook, cell_id: str) -> Optional:
        return next((c for c in notebook.cells if c.id == cell_id), None)

# Global scheduler instance
scheduler = ExecutionScheduler()
