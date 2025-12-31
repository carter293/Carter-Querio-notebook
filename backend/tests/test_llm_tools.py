import pytest
import asyncio
from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState
from llm_tools import (
    tool_get_notebook_state,
    tool_create_cell,
    tool_update_cell,
    tool_run_cell,
    tool_delete_cell,
    create_output_preview
)


class MockBroadcaster:
    """Mock broadcaster for testing."""
    async def broadcast_cell_created(self, *args, **kwargs):
        pass
    
    async def broadcast_cell_updated(self, *args, **kwargs):
        pass
    
    async def broadcast_cell_deleted(self, *args, **kwargs):
        pass


class MockScheduler:
    """Mock scheduler for testing."""
    async def enqueue_run(self, notebook_id: str, cell_id: str, notebook, broadcaster):
        # For testing, we'll just mark the cell as running
        # In real implementation, this would trigger execution
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if cell:
            cell.status = CellStatus.RUNNING


@pytest.fixture
def notebook():
    """Create test notebook."""
    from tests.test_utils import create_test_notebook, create_test_cell
    
    nb = create_test_notebook(
        notebook_id="test-notebook",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            create_test_cell(
                cell_id="cell1",
                cell_type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.SUCCESS,
                reads=set(),
                writes={"x"}
            )
        ]
    )
    # Add x to the kernel globals
    nb.kernel.globals_dict["x"] = 1
    return nb


@pytest.fixture
def broadcaster():
    return MockBroadcaster()


@pytest.fixture
def scheduler():
    return MockScheduler()


@pytest.mark.asyncio
async def test_get_notebook_state(notebook):
    """Test retrieving notebook state."""
    state = await tool_get_notebook_state(notebook)
    
    assert state["cell_count"] == 1
    assert len(state["cells"]) == 1
    assert state["cells"][0]["id"] == "cell1"
    assert state["cells"][0]["code"] == "x = 1"
    assert state["execution_in_progress"] is False


@pytest.mark.asyncio
async def test_create_cell(notebook, broadcaster):
    """Test creating a new cell."""
    result = await tool_create_cell(
        notebook,
        "python",
        "y = 2",
        None,
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert "cell_id" in result
    assert len(notebook.cells) == 2
    assert notebook.revision == 1


@pytest.mark.asyncio
async def test_update_cell(notebook, broadcaster):
    """Test updating a cell."""
    result = await tool_update_cell(
        notebook,
        "cell1",
        "x = 10",
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert notebook.cells[0].code == "x = 10"
    assert notebook.revision == 1


@pytest.mark.asyncio
async def test_delete_cell(notebook, broadcaster):
    """Test deleting a cell."""
    result = await tool_delete_cell(
        notebook,
        "cell1",
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert len(notebook.cells) == 0
    assert notebook.revision == 1
    assert "x" not in notebook.kernel.globals_dict


@pytest.mark.asyncio
async def test_create_output_preview():
    """Test output preview creation."""
    from models import Output
    
    # Test empty outputs
    cell = Cell(id="cell1", type=CellType.PYTHON, code="", outputs=[])
    preview = create_output_preview(cell)
    assert preview["type"] == "none"
    assert preview["preview"] == ""
    
    # Test text output
    cell = Cell(
        id="cell2",
        type=CellType.PYTHON,
        code="",
        outputs=[Output(mime_type="text/plain", data="Hello, world!")]
    )
    preview = create_output_preview(cell)
    assert preview["type"] == "text"
    assert "Hello, world!" in preview["preview"]
    
    # Test plotly output
    plotly_data = {
        "data": [{"type": "scatter", "x": [1, 2, 3], "y": [4, 5, 6]}]
    }
    cell = Cell(
        id="cell3",
        type=CellType.PYTHON,
        code="",
        outputs=[Output(mime_type="application/vnd.plotly.v1+json", data=plotly_data)]
    )
    preview = create_output_preview(cell)
    assert preview["type"] == "plotly"
    assert "scatter" in preview["preview"]
    assert preview["has_visual"] is True
    
    # Test image output
    cell = Cell(
        id="cell4",
        type=CellType.PYTHON,
        code="",
        outputs=[Output(mime_type="image/png", data="base64data")]
    )
    preview = create_output_preview(cell)
    assert preview["type"] == "image"
    assert preview["has_visual"] is True

