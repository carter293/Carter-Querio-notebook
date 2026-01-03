"""Test utilities for loading test notebooks and creating fixtures."""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.storage import load_notebook
from app.models import Notebook, Cell, CellType, CellStatus, Graph, KernelState


def load_test_notebook(notebook_id: str) -> Notebook:
    """Load a notebook from the test notebooks directory.
    
    Args:
        notebook_id: The ID of the test notebook (without .json extension)
        
    Returns:
        Loaded notebook with fresh kernel state
    """
    return load_notebook(notebook_id, subdirectory="test")


def create_test_notebook(
    notebook_id: str = "test-notebook",
    user_id: str = "test-user",
    name: str = "Test Notebook",
    cells: list[Cell] = None
) -> Notebook:
    """Create a test notebook with default configuration.
    
    Args:
        notebook_id: Notebook ID
        user_id: User ID
        name: Notebook name
        cells: List of cells (defaults to empty list)
        
    Returns:
        New notebook instance
    """
    if cells is None:
        cells = []
        
    return Notebook(
        id=notebook_id,
        user_id=user_id,
        name=name,
        cells=cells,
        graph=Graph(),
        kernel=KernelState(globals_dict={"__builtins__": __builtins__})
    )


def create_test_cell(
    cell_id: str = "test-cell",
    cell_type: CellType = CellType.PYTHON,
    code: str = "",
    status: CellStatus = CellStatus.IDLE,
    reads: set = None,
    writes: set = None
) -> Cell:
    """Create a test cell with default configuration.
    
    Args:
        cell_id: Cell ID
        cell_type: Cell type
        code: Cell code
        status: Cell status
        reads: Set of variables read by cell
        writes: Set of variables written by cell
        
    Returns:
        New cell instance
    """
    if reads is None:
        reads = set()
    if writes is None:
        writes = set()
        
    return Cell(
        id=cell_id,
        type=cell_type,
        code=code,
        status=status,
        reads=reads,
        writes=writes
    )

