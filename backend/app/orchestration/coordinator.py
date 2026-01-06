"""Coordinates notebook execution and WebSocket broadcasting."""
from typing import Set, Optional
from ..core.ast_parser import extract_python_dependencies, extract_sql_dependencies
from ..core.graph import DependencyGraph, CycleDetectedError
from ..core.executor import PythonExecutor, SQLExecutor
from ..file_storage import NotebookFileStorage
from ..models import NotebookResponse, CellResponse


class NotebookCoordinator:
    """
    Coordinates notebook operations:
    - Manages dependency graph
    - Executes cells reactively
    - Broadcasts updates via WebSocket
    """

    def __init__(self, broadcaster):
        self.graph = DependencyGraph()
        self.python_executor = PythonExecutor()
        self.sql_executor = SQLExecutor()
        self.broadcaster = broadcaster
        self.notebook_id: Optional[str] = None
        self.notebook: Optional[NotebookResponse] = None

    def load_notebook(self, notebook_id: str):
        """Load a notebook and rebuild the dependency graph."""
        self.notebook_id = notebook_id
        self.notebook = NotebookFileStorage.parse_notebook(notebook_id)

        if not self.notebook:
            raise ValueError(f"Notebook {notebook_id} not found")

        # Rebuild graph from all cells
        for cell in self.notebook.cells:
            reads, writes = self._extract_dependencies(cell)
            try:
                self.graph.update_cell(cell.id, reads, writes)
                # Update cell metadata
                cell.reads = list(reads)
                cell.writes = list(writes)
            except CycleDetectedError:
                # Mark cell as blocked
                cell.status = 'blocked'
                cell.error = 'Circular dependency detected'

    def _extract_dependencies(self, cell: CellResponse) -> tuple[Set[str], Set[str]]:
        """Extract reads and writes from a cell."""
        if cell.type == 'python':
            reads, writes = extract_python_dependencies(cell.code)
            return reads, writes
        elif cell.type == 'sql':
            reads = extract_sql_dependencies(cell.code)
            return reads, set()  # SQL doesn't write variables
        return set(), set()

    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Handle a cell code update."""
        if not self.notebook:
            return

        # Find cell
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Update code
        cell.code = new_code

        # Extract dependencies
        reads, writes = self._extract_dependencies(cell)
        cell.reads = list(reads)
        cell.writes = list(writes)

        # Update graph
        try:
            self.graph.update_cell(cell_id, reads, writes)

            # Broadcast updated cell metadata
            await self.broadcaster.broadcast({
                'type': 'cell_updated',
                'cellId': cell_id,
                'cell': {
                    'code': cell.code,
                    'reads': cell.reads,
                    'writes': cell.writes
                }
            })
        except CycleDetectedError as e:
            # Mark cell as blocked
            cell.status = 'blocked'
            cell.error = str(e)

            await self.broadcaster.broadcast({
                'type': 'cell_status',
                'cellId': cell_id,
                'status': 'blocked'
            })
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': str(e)
            })

    async def handle_run_cell(self, cell_id: str):
        """Execute a cell and all dependent cells."""
        if not self.notebook:
            return

        # Get execution order (cell + descendants)
        execution_order = self.graph.get_execution_order(cell_id)

        # Execute cells in order
        for cid in execution_order:
            await self._execute_cell(cid)

    async def _execute_cell(self, cell_id: str):
        """Execute a single cell."""
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Skip blocked cells
        if cell.status == 'blocked':
            return

        # Broadcast running status
        cell.status = 'running'
        cell.outputs = []
        cell.stdout = ''
        cell.error = None

        await self.broadcaster.broadcast({
            'type': 'cell_status',
            'cellId': cell_id,
            'status': 'running'
        })

        # Execute based on type
        if cell.type == 'python':
            result = self.python_executor.execute(cell.code)
        elif cell.type == 'sql':
            result = self.sql_executor.execute(cell.code, self.python_executor.globals_dict)
        else:
            return

        # Update cell with results
        cell.status = result.status
        cell.stdout = result.stdout
        cell.error = result.error

        # Broadcast stdout
        if result.stdout:
            await self.broadcaster.broadcast({
                'type': 'cell_stdout',
                'cellId': cell_id,
                'data': result.stdout
            })

        # Broadcast outputs
        for output in result.outputs:
            cell.outputs.append(output)
            await self.broadcaster.broadcast({
                'type': 'cell_output',
                'cellId': cell_id,
                'output': output.model_dump()
            })

        # Broadcast final status
        await self.broadcaster.broadcast({
            'type': 'cell_status',
            'cellId': cell_id,
            'status': cell.status
        })

        # If error, broadcast it
        if result.error:
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': result.error
            })
