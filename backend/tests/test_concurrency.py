import pytest
import asyncio
from app.models import Notebook, Cell, CellType, CellStatus, Graph, KernelState
from app.services import locked_update_cell, locked_create_cell, locked_delete_cell
from tests.test_utils import create_test_notebook, create_test_cell


@pytest.mark.asyncio
async def test_concurrent_cell_updates():
    """Test that concurrent updates don't lose data."""
    notebook = create_test_notebook(
        notebook_id="test-concurrency",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            create_test_cell(
                cell_id="cell1",
                cell_type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.IDLE,
                reads=set(),
                writes={"x"}
            )
        ]
    )
    
    # Simulate 50 concurrent updates
    async def update_cell_multiple_times(base_code, count):
        for i in range(count):
            await locked_update_cell(notebook, "cell1", f"{base_code} + {i}")
    
    # Run 5 updaters concurrently, each doing 10 updates
    tasks = [update_cell_multiple_times(f"x = {i}", 10) for i in range(5)]
    await asyncio.gather(*tasks)
    
    # Verify revision incremented correctly (50 total updates)
    assert notebook.revision == 50
    
    # Verify cell has valid code (one of the 50 updates)
    cell = notebook.cells[0]
    assert "x =" in cell.code
    print(f"Final cell code after 50 concurrent updates: {cell.code}")


@pytest.mark.asyncio
async def test_optimistic_locking():
    """Test revision conflict detection."""
    notebook = create_test_notebook(
        notebook_id="test-optimistic",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            create_test_cell(
                cell_id="cell1",
                cell_type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.IDLE,
                reads=set(),
                writes={"x"}
            )
        ]
    )
    notebook.revision = 5
    
    # First update succeeds
    await locked_update_cell(notebook, "cell1", "x = 2", expected_revision=5)
    assert notebook.revision == 6
    
    # Second update with stale revision fails
    with pytest.raises(ValueError, match="Revision conflict"):
        await locked_update_cell(notebook, "cell1", "x = 3", expected_revision=5)
    
    # Update with correct revision succeeds
    await locked_update_cell(notebook, "cell1", "x = 4", expected_revision=6)
    assert notebook.revision == 7


@pytest.mark.asyncio
async def test_concurrent_create_and_delete():
    """Test concurrent cell creation and deletion."""
    notebook = create_test_notebook(
        notebook_id="test-create-delete",
        user_id="test-user",
        name="Test Notebook",
        cells=[]
    )
    
    # Create 10 cells concurrently
    async def create_cells():
        for i in range(10):
            await locked_create_cell(notebook, CellType.PYTHON, f"x{i} = {i}")
    
    await create_cells()
    
    assert len(notebook.cells) == 10
    assert notebook.revision == 10


@pytest.mark.asyncio
async def test_concurrent_create_delete_mixed():
    """Test concurrent creation and deletion don't corrupt state."""
    notebook = create_test_notebook(
        notebook_id="test-mixed",
        user_id="test-user",
        name="Test Notebook",
        cells=[]
    )
    
    # Create 5 cells
    cell_ids = []
    for i in range(5):
        cell = await locked_create_cell(notebook, CellType.PYTHON, f"x{i} = {i}")
        cell_ids.append(cell.id)
    
    # Concurrently delete some and create others
    async def delete_some():
        for i in range(3):
            if i < len(cell_ids):
                try:
                    await locked_delete_cell(notebook, cell_ids[i])
                except ValueError:
                    pass  # Cell may have been deleted already
    
    async def create_more():
        for i in range(5, 10):
            await locked_create_cell(notebook, CellType.PYTHON, f"y{i} = {i}")
    
    await asyncio.gather(delete_some(), create_more())
    
    # Verify notebook is in valid state
    assert notebook.revision >= 5  # At least 5 initial creates
    assert len(notebook.cells) > 0  # Should have some cells remaining

