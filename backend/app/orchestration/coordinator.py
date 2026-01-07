"""Coordinates notebook execution and WebSocket broadcasting."""
import asyncio
import queue
from typing import Optional, List
from ..file_storage import NotebookFileStorage
from ..models import NotebookResponse
from ..kernel.manager import KernelManager
from ..kernel.types import (
    ExecuteRequest,
    ExecutionResult,
    RegisterCellRequest,
    RegisterCellResult,
    SetDatabaseConfigRequest,
    SetDatabaseConfigResult,
)


class NotebookCoordinator:
    """
    Coordinates notebook operations:
    - Manages kernel lifecycle
    - Broadcasts updates via WebSocket
    """

    def __init__(self, broadcaster):
        # Use kernel instead of in-process execution
        self.kernel = KernelManager()
        self.kernel.start()

        self.broadcaster = broadcaster
        self.notebook_id: Optional[str] = None
        self.notebook: Optional[NotebookResponse] = None

        # Background task flag and task handle
        self._running = True
        self._output_task: Optional[asyncio.Task] = None

    async def _start_background_task(self):
        """Start background output processing task."""
        self._output_task = asyncio.create_task(self._process_output_queue())

    async def _process_output_queue(self):
        """
        Background task that continuously processes ALL kernel outputs.
        This is the ONLY place that reads from output_queue.

        The coordinator is STATELESS for execution results - it just routes
        messages from kernel to clients. All execution state (status, outputs,
        errors) lives only in the frontend.
        """
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read from output queue with timeout (1 second)
                msg = await loop.run_in_executor(
                    None,
                    lambda: self.kernel.output_queue.get(timeout=1)
                )

                # All messages are CellNotification
                from ..kernel.types import CellNotification
                notification = CellNotification(**msg)

                # Just broadcast - don't update state!
                # Clients maintain their own execution state from the stream
                await self._broadcast_notification(notification)

            except queue.Empty:
                # Check if kernel is alive
                if not self.kernel.process.is_alive():
                    print("[Coordinator] Kernel died!")
                    await self._handle_kernel_death()
                    break
                continue
            except Exception as e:
                print(f"[Coordinator] Error processing output: {e}")
                import traceback
                traceback.print_exc()
                continue

    async def _broadcast_notification(self, notification):
        """Broadcast notification to WebSocket clients."""
        from ..kernel.types import CellChannel

        channel = notification.output.channel
        cell_id = notification.cell_id
        data = notification.output.data

        # Handle system messages
        if cell_id == "__system__":
            if channel == CellChannel.STATUS and data.get("status") == "db_configured":
                await self.broadcaster.broadcast({
                    'type': 'db_connection_updated',
                    'connectionString': self.notebook.db_conn_string if self.notebook else '',
                    'status': 'success'
                })
            elif channel == CellChannel.ERROR:
                await self.broadcaster.broadcast({
                    'type': 'db_connection_updated',
                    'connectionString': self.notebook.db_conn_string if self.notebook else '',
                    'status': 'error',
                    'error': data.get("message")
                })
            return

        # Broadcast cell-specific messages
        if channel == CellChannel.STATUS:
            await self.broadcaster.broadcast({
                'type': 'cell_status',
                'cellId': cell_id,
                'status': data.get("status")
            })
        elif channel == CellChannel.STDOUT:
            await self.broadcaster.broadcast({
                'type': 'cell_stdout',
                'cellId': cell_id,
                'data': data
            })
        elif channel == CellChannel.OUTPUT:
            await self.broadcaster.broadcast({
                'type': 'cell_output',
                'cellId': cell_id,
                'output': {
                    'mime_type': notification.output.mimetype,
                    'data': data
                }
            })
        elif channel == CellChannel.ERROR:
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': data.get("message")
            })
        elif channel == CellChannel.METADATA:
            await self.broadcaster.broadcast({
                'type': 'cell_updated',
                'cellId': cell_id,
                'cell': {
                    'reads': data.get("reads", []),
                    'writes': data.get("writes", [])
                }
            })

    async def _handle_kernel_death(self):
        """Handle kernel process death."""
        self._running = False

        # Broadcast error to all clients
        await self.broadcaster.broadcast({
            'type': 'kernel_error',
            'error': 'Kernel process died. Please reconnect.'
        })

    async def load_notebook(self, notebook_id: str):
        """Load a notebook and send all cells to kernel for graph building."""
        self.notebook_id = notebook_id
        self.notebook = NotebookFileStorage.parse_notebook(notebook_id)

        if not self.notebook:
            raise ValueError(f"Notebook {notebook_id} not found")

        # Start background task BEFORE registering cells
        await self._start_background_task()

        # Register all cells with the kernel to build dependency graph
        for cell in self.notebook.cells:
            register_req = RegisterCellRequest(
                cell_id=cell.id,
                code=cell.code,
                cell_type=cell.type
            )
            self.kernel.input_queue.put(register_req.model_dump())
            # Do NOT wait for response - background task handles it

        # Wait a bit for registration to complete
        await asyncio.sleep(0.5)

        # Configure database if connection string exists
        if self.notebook.db_conn_string:
            await self._configure_database(self.notebook.db_conn_string)

    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Handle a cell code update - returns immediately."""
        if not self.notebook:
            return

        # Find cell
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Optimistic update
        cell.code = new_code
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Send to kernel
        register_req = RegisterCellRequest(
            cell_id=cell_id,
            code=cell.code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(register_req.model_dump())

        # Return immediately - background task handles responses

    async def handle_db_connection_update(self, connection_string: str):
        """Handle database connection string update - returns immediately."""
        if not self.notebook:
            return

        # Optimistic update
        self.notebook.db_conn_string = connection_string
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Send to kernel
        await self._configure_database(connection_string)

        # Return immediately - background task broadcasts result

    async def handle_run_cell(self, cell_id: str):
        """Execute a cell - returns immediately."""
        if not self.notebook:
            return

        # Find cell
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Send to kernel
        request = ExecuteRequest(
            cell_id=cell_id,
            code=cell.code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(request.model_dump())

        # Return immediately - background task handles responses

    async def _configure_database(self, connection_string: str) -> None:
        """
        Send database connection string to kernel - returns immediately.
        Success/error will be broadcast via background task.
        """
        request = SetDatabaseConfigRequest(connection_string=connection_string)
        self.kernel.input_queue.put(request.model_dump())
        # Return immediately

    async def handle_create_cell(self, cell_type: str, after_cell_id: str = None):
        """Handle cell creation - returns immediately."""
        from uuid import uuid4
        from ..models import CellResponse

        if not self.notebook:
            return

        # Create new cell
        cell_id = str(uuid4())
        new_cell = CellResponse(
            id=cell_id,
            type=cell_type,
            code="",
            status="idle",
        )

        # Insert cell at the correct position
        if after_cell_id:
            insert_index = None
            for i, cell in enumerate(self.notebook.cells):
                if cell.id == after_cell_id:
                    insert_index = i + 1
                    break

            if insert_index is not None:
                self.notebook.cells.insert(insert_index, new_cell)
                index = insert_index
            else:
                # after_cell_id not found, append to end
                self.notebook.cells.append(new_cell)
                index = len(self.notebook.cells) - 1
        else:
            # Append to end
            self.notebook.cells.append(new_cell)
            index = len(self.notebook.cells) - 1

        # Save to file
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Broadcast cell creation
        await self.broadcaster.broadcast({
            'type': 'cell_created',
            'cellId': cell_id,
            'cell': new_cell.model_dump(),
            'index': index
        })

    async def handle_delete_cell(self, cell_id: str):
        """Handle cell deletion - returns immediately."""
        if not self.notebook:
            return

        # Find and remove cell
        for i, cell in enumerate(self.notebook.cells):
            if cell.id == cell_id:
                self.notebook.cells.pop(i)
                NotebookFileStorage.serialize_notebook(self.notebook)

                # Broadcast cell deletion
                await self.broadcaster.broadcast({
                    'type': 'cell_deleted',
                    'cellId': cell_id
                })
                return

    def shutdown(self):
        """Stop the background task and kernel process."""
        self._running = False

        # Wait for background task to finish
        if self._output_task and not self._output_task.done():
            self._output_task.cancel()

        # Stop kernel
        if self.kernel:
            self.kernel.stop()
