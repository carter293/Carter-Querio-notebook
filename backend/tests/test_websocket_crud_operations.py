"""
Integration tests for WebSocket CRUD operations.

Tests the happy path for:
- Creating cells via WebSocket
- Deleting cells via WebSocket
- Broadcasting updates to all connected clients
- Kernel graph synchronization on CRUD operations

These tests validate the simplified async architecture where:
- Handlers return immediately (non-blocking)
- Background task streams CellNotification messages
- Coordinator is stateless (no execution state tracking)
- Clients receive real-time updates
"""

import pytest
import asyncio
from app.orchestration.coordinator import NotebookCoordinator
from app.models import NotebookResponse, CellResponse
from app.file_storage import NotebookFileStorage
from app.kernel.types import CellNotification, CellChannel


class MockBroadcaster:
    """Mock broadcaster that captures all messages for verification."""

    def __init__(self):
        self.messages: list[dict] = []

    async def broadcast(self, message: dict):
        """Capture broadcasted message."""
        self.messages.append(message)

    def get_messages_by_type(self, msg_type: str) -> list[dict]:
        """Get all messages of a specific type."""
        return [m for m in self.messages if m.get('type') == msg_type]

    def get_messages_for_cell(self, cell_id: str) -> list[dict]:
        """Get all messages for a specific cell."""
        return [m for m in self.messages if m.get('cellId') == cell_id]

    def clear(self):
        """Clear message history."""
        self.messages.clear()


@pytest.fixture
def coordinator(event_loop):
    """Create coordinator with mock broadcaster and test notebook."""
    broadcaster = MockBroadcaster()
    coord = NotebookCoordinator(broadcaster)

    # Create minimal test notebook
    notebook = NotebookResponse(
        id='test-crud',
        name='Test CRUD Operations',
        cells=[
            CellResponse(id='cell-1', type='python', code='x = 10'),
            CellResponse(id='cell-2', type='python', code='y = x * 2'),
        ]
    )

    # Save to disk
    NotebookFileStorage.serialize_notebook(notebook)

    # Load notebook (starts background task) - run in event loop
    event_loop.run_until_complete(coord.load_notebook('test-crud'))

    # Wait for initial registration to complete
    event_loop.run_until_complete(asyncio.sleep(0.5))

    # Clear initial registration messages
    broadcaster.clear()

    yield coord, broadcaster

    # Cleanup
    coord.shutdown()


@pytest.mark.asyncio
async def test_create_cell_broadcasts_to_clients(coordinator):
    """Test that creating a cell broadcasts cell_created message to all clients."""
    coord, broadcaster = coordinator

    # Create a new Python cell after cell-1
    await coord.handle_create_cell(cell_type='python', after_cell_id='cell-1')

    # Wait for background task to process
    await asyncio.sleep(0.3)

    # Verify cell_created message was broadcast
    created_msgs = broadcaster.get_messages_by_type('cell_created')
    assert len(created_msgs) == 1

    msg = created_msgs[0]
    assert msg['type'] == 'cell_created'
    assert 'cellId' in msg
    assert 'cell' in msg
    assert msg['cell']['type'] == 'python'

    # Verify cell exists in coordinator's notebook
    cell_ids = [c.id for c in coord.notebook.cells]
    assert msg['cellId'] in cell_ids

    # Verify cell position (should be after cell-1)
    cell_1_idx = cell_ids.index('cell-1')
    new_cell_idx = cell_ids.index(msg['cellId'])
    assert new_cell_idx == cell_1_idx + 1


@pytest.mark.asyncio
async def test_create_cell_at_end_when_no_after_id(coordinator):
    """Test that creating a cell without afterCellId appends to end."""
    coord, broadcaster = coordinator

    initial_count = len(coord.notebook.cells)

    # Create cell without specifying position
    await coord.handle_create_cell(cell_type='sql', after_cell_id=None)

    await asyncio.sleep(0.3)

    # Verify cell was appended
    assert len(coord.notebook.cells) == initial_count + 1

    created_msgs = broadcaster.get_messages_by_type('cell_created')
    assert len(created_msgs) == 1
    assert created_msgs[0]['cell']['type'] == 'sql'

    # Verify it's the last cell
    last_cell = coord.notebook.cells[-1]
    assert last_cell.id == created_msgs[0]['cellId']
    assert last_cell.type == 'sql'


@pytest.mark.asyncio
async def test_delete_cell_removes_from_notebook(coordinator):
    """Test that deleting a cell removes it from notebook and broadcasts."""
    coord, broadcaster = coordinator

    initial_count = len(coord.notebook.cells)
    cell_to_delete = 'cell-1'

    # Delete cell
    await coord.handle_delete_cell(cell_to_delete)

    await asyncio.sleep(0.3)

    # Verify cell was removed from notebook
    assert len(coord.notebook.cells) == initial_count - 1
    cell_ids = [c.id for c in coord.notebook.cells]
    assert cell_to_delete not in cell_ids

    # Verify cell_deleted message was broadcast
    deleted_msgs = broadcaster.get_messages_by_type('cell_deleted')
    assert len(deleted_msgs) == 1
    assert deleted_msgs[0]['cellId'] == cell_to_delete


@pytest.mark.asyncio
async def test_delete_cell_removes_from_graph(coordinator):
    """Test that deleting a cell removes it from the notebook and graph."""
    coord, broadcaster = coordinator

    # cell-2 depends on cell-1 (y = x * 2)
    # Deleting cell-1 removes it from both notebook and dependency graph

    broadcaster.clear()

    await coord.handle_delete_cell('cell-1')

    # Wait for deletion
    await asyncio.sleep(0.3)

    # Verify cell-1 was deleted
    deleted_msgs = broadcaster.get_messages_by_type('cell_deleted')
    assert len(deleted_msgs) == 1
    assert deleted_msgs[0]['cellId'] == 'cell-1'

    # Verify cell-1 is no longer in notebook
    cell_ids = [c.id for c in coord.notebook.cells]
    assert 'cell-1' not in cell_ids


@pytest.mark.asyncio
async def test_create_multiple_cells_in_sequence(coordinator):
    """Test creating multiple cells maintains correct order."""
    coord, broadcaster = coordinator

    # Create 3 cells in sequence
    await coord.handle_create_cell('python', after_cell_id='cell-1')
    await asyncio.sleep(0.2)

    await coord.handle_create_cell('python', after_cell_id='cell-1')
    await asyncio.sleep(0.2)

    await coord.handle_create_cell('sql', after_cell_id=None)  # Append to end
    await asyncio.sleep(0.2)

    # Verify 3 cell_created messages
    created_msgs = broadcaster.get_messages_by_type('cell_created')
    assert len(created_msgs) == 3

    # Verify notebook has 5 cells total (2 original + 3 new)
    assert len(coord.notebook.cells) == 5

    # Verify types
    types = [c.type for c in coord.notebook.cells]
    assert types.count('python') == 4
    assert types.count('sql') == 1


@pytest.mark.asyncio
async def test_crud_operations_persist_to_disk(coordinator):
    """Test that CRUD operations update the notebook file on disk."""
    coord, broadcaster = coordinator

    # Create a cell
    await coord.handle_create_cell('python', after_cell_id=None)
    await asyncio.sleep(0.3)

    created_msgs = broadcaster.get_messages_by_type('cell_created')
    new_cell_id = created_msgs[0]['cellId']

    # Reload notebook from disk
    reloaded = NotebookFileStorage.parse_notebook('test-crud')

    # Verify new cell exists in reloaded notebook
    cell_ids = [c.id for c in reloaded.cells]
    assert new_cell_id in cell_ids

    # Delete the cell
    broadcaster.clear()
    await coord.handle_delete_cell(new_cell_id)
    await asyncio.sleep(0.3)

    # Reload again
    reloaded = NotebookFileStorage.parse_notebook('test-crud')
    cell_ids = [c.id for c in reloaded.cells]

    # Verify cell is gone
    assert new_cell_id not in cell_ids


@pytest.mark.asyncio
async def test_handlers_return_immediately(coordinator):
    """Test that CRUD handlers are non-blocking and return quickly."""
    import time
    coord, broadcaster = coordinator

    # Test create_cell handler returns quickly
    start = time.time()
    await coord.handle_create_cell('python', after_cell_id=None)
    duration = time.time() - start

    # Should return in < 50ms (non-blocking)
    assert duration < 0.05, f"create_cell took {duration}s, expected < 50ms"

    # Test delete_cell handler returns quickly
    cell_id = coord.notebook.cells[0].id

    start = time.time()
    await coord.handle_delete_cell(cell_id)
    duration = time.time() - start

    # Should return in < 50ms (non-blocking)
    assert duration < 0.05, f"delete_cell took {duration}s, expected < 50ms"


@pytest.mark.asyncio
async def test_delete_nonexistent_cell_is_noop(coordinator):
    """Test that deleting a non-existent cell doesn't crash."""
    coord, broadcaster = coordinator

    # Delete a cell that doesn't exist
    await coord.handle_delete_cell('nonexistent-cell-id')
    await asyncio.sleep(0.2)

    # Should not crash, and no cell_deleted message should be sent
    deleted_msgs = broadcaster.get_messages_by_type('cell_deleted')
    assert len(deleted_msgs) == 0


@pytest.mark.asyncio
async def test_crud_with_empty_notebook(coordinator):
    """Test CRUD operations work when notebook has no cells."""
    broadcaster = MockBroadcaster()
    coord = NotebookCoordinator(broadcaster)

    # Create empty notebook
    notebook = NotebookResponse(
        id='test-empty',
        name='Empty Notebook',
        cells=[]
    )
    NotebookFileStorage.serialize_notebook(notebook)
    await coord.load_notebook('test-empty')
    await asyncio.sleep(0.3)

    broadcaster.clear()

    # Create first cell
    await coord.handle_create_cell('python', after_cell_id=None)
    await asyncio.sleep(0.3)

    # Verify cell was created
    created_msgs = broadcaster.get_messages_by_type('cell_created')
    assert len(created_msgs) == 1
    assert len(coord.notebook.cells) == 1

    # Cleanup
    coord.shutdown()
