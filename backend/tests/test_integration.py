"""Integration tests for reactive execution."""
import pytest
from app.orchestration.coordinator import NotebookCoordinator
from app.models import NotebookResponse, CellResponse
from app.file_storage import NotebookFileStorage


class MockBroadcaster:
    """Mock broadcaster for testing."""
    def __init__(self):
        self.messages = []

    async def broadcast(self, message: dict):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_reactive_cascade():
    """Test that changing A causes B and C to re-execute."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    # Create test notebook
    notebook = NotebookResponse(
        id='test',
        name='Test',
        cells=[
            CellResponse(id='c1', type='python', code='x = 10'),
            CellResponse(id='c2', type='python', code='y = x * 2'),
            CellResponse(id='c3', type='python', code='z = y + 5'),
        ]
    )

    # Save and load
    NotebookFileStorage.serialize_notebook(notebook)
    coordinator.load_notebook('test')

    # Run cell c1
    await coordinator.handle_run_cell('c1')

    # Verify all three cells executed
    statuses = [msg for msg in broadcaster.messages if msg['type'] == 'cell_status']
    cell_ids = [msg['cellId'] for msg in statuses if msg['status'] == 'success']

    assert 'c1' in cell_ids
    assert 'c2' in cell_ids
    assert 'c3' in cell_ids

    # Verify execution order (c1 before c2 before c3)
    success_statuses = [msg for msg in statuses if msg['status'] == 'success']
    assert success_statuses[0]['cellId'] == 'c1'
    assert success_statuses[1]['cellId'] == 'c2'
    assert success_statuses[2]['cellId'] == 'c3'


@pytest.mark.asyncio
async def test_cycle_detection():
    """Test that circular dependencies are detected."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    notebook = NotebookResponse(
        id='test-cycle',
        name='Test Cycle',
        cells=[
            CellResponse(id='c1', type='python', code='x = y + 1'),
            CellResponse(id='c2', type='python', code='y = x + 1'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    coordinator.load_notebook('test-cycle')

    # One of the cells should be blocked
    blocked_cells = [c for c in coordinator.notebook.cells if c.status == 'blocked']
    assert len(blocked_cells) > 0
    assert 'Circular dependency' in blocked_cells[0].error


@pytest.mark.asyncio
async def test_diamond_pattern():
    """Test A → B, C → D pattern."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    notebook = NotebookResponse(
        id='test-diamond',
        name='Test Diamond',
        cells=[
            CellResponse(id='a', type='python', code='x = 10'),
            CellResponse(id='b', type='python', code='y = x * 2'),
            CellResponse(id='c', type='python', code='z = x + 5'),
            CellResponse(id='d', type='python', code='result = y + z'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    coordinator.load_notebook('test-diamond')

    # Run cell 'a'
    await coordinator.handle_run_cell('a')

    # All cells should execute
    statuses = [msg for msg in broadcaster.messages if msg['type'] == 'cell_status']
    success_cell_ids = [msg['cellId'] for msg in statuses if msg['status'] == 'success']

    assert set(success_cell_ids) == {'a', 'b', 'c', 'd'}

    # Verify 'd' executes last (depends on both 'b' and 'c')
    success_statuses = [msg for msg in statuses if msg['status'] == 'success']
    assert success_statuses[-1]['cellId'] == 'd'


@pytest.mark.asyncio
async def test_independent_cells():
    """Test that independent cells don't trigger each other."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    notebook = NotebookResponse(
        id='test-independent',
        name='Test Independent',
        cells=[
            CellResponse(id='c1', type='python', code='x = 10'),
            CellResponse(id='c2', type='python', code='y = 20'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    coordinator.load_notebook('test-independent')

    # Run cell c1
    await coordinator.handle_run_cell('c1')

    # Only c1 should execute
    statuses = [msg for msg in broadcaster.messages if msg['type'] == 'cell_status']
    cell_ids = [msg['cellId'] for msg in statuses if msg['status'] == 'success']

    assert cell_ids == ['c1']


@pytest.mark.asyncio
async def test_sql_execution():
    """Test SQL cell with variable substitution."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    notebook = NotebookResponse(
        id='test-sql',
        name='Test SQL',
        cells=[
            CellResponse(id='c1', type='python', code='user_id = 42'),
            CellResponse(id='c2', type='sql', code='SELECT * FROM users WHERE id = {user_id}'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    coordinator.load_notebook('test-sql')

    # Run c1 (should trigger c2)
    await coordinator.handle_run_cell('c1')

    # Both cells should execute
    statuses = [msg for msg in broadcaster.messages if msg['type'] == 'cell_status']
    cell_ids = [msg['cellId'] for msg in statuses if msg['status'] == 'success']

    assert 'c1' in cell_ids
    assert 'c2' in cell_ids

    # Check that SQL was executed with substitution
    stdout_messages = [msg for msg in broadcaster.messages if msg['type'] == 'cell_stdout']
    sql_stdout = [msg for msg in stdout_messages if msg['cellId'] == 'c2']
    assert len(sql_stdout) > 0
    assert '42' in sql_stdout[0]['data']
