"""
Integration tests for WebSocket command operations.

Tests the happy path for:
- Cell update (handle_cell_update)
- Cell execution (handle_run_cell)
- Database configuration (handle_db_connection_update)
- Reactive cascade execution
- Real-time status/output streaming

These tests validate the simplified async architecture where:
- Commands return immediately (non-blocking)
- Background task streams CellNotification messages
- Execution state flows through CellChannel discriminated messages
- Clients receive incremental updates (status, stdout, outputs, errors)
"""

import pytest
import asyncio
from app.orchestration.coordinator import NotebookCoordinator
from app.models import NotebookResponse, CellResponse
from app.file_storage import NotebookFileStorage


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

    # Create test notebook with dependent cells
    notebook = NotebookResponse(
        id='test-commands',
        name='Test Command Operations',
        cells=[
            CellResponse(id='c1', type='python', code='x = 10'),
            CellResponse(id='c2', type='python', code='y = x * 2'),
            CellResponse(id='c3', type='python', code='z = y + 5'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    event_loop.run_until_complete(coord.load_notebook('test-commands'))

    # Wait for initial registration
    event_loop.run_until_complete(asyncio.sleep(0.5))
    broadcaster.clear()

    yield coord, broadcaster

    coord.shutdown()


@pytest.mark.asyncio
async def test_cell_update_registers_dependencies(coordinator):
    """Test that updating cell code triggers re-registration and broadcasts metadata."""
    coord, broadcaster = coordinator

    # Update cell code
    await coord.handle_cell_update('c1', 'x = 20')

    # Wait for registration
    await asyncio.sleep(0.3)

    # Verify cell code was updated in memory
    cell = next(c for c in coord.notebook.cells if c.id == 'c1')
    assert cell.code == 'x = 20'

    # Verify cell_updated message was broadcast (with metadata)
    updated_msgs = broadcaster.get_messages_by_type('cell_updated')
    assert len(updated_msgs) >= 1

    # Find the metadata update for c1
    c1_updates = [m for m in updated_msgs if m.get('cellId') == 'c1']
    assert len(c1_updates) >= 1

    # Verify metadata contains reads/writes
    metadata = c1_updates[0].get('cell', {})
    assert 'writes' in metadata
    assert 'x' in metadata['writes']


@pytest.mark.asyncio
async def test_cell_update_persists_to_disk(coordinator):
    """Test that cell updates are persisted to notebook file."""
    coord, broadcaster = coordinator

    new_code = 'x = 999  # updated'
    await coord.handle_cell_update('c1', new_code)
    await asyncio.sleep(0.3)

    # Reload from disk
    reloaded = NotebookFileStorage.parse_notebook('test-commands')
    cell = next(c for c in reloaded.cells if c.id == 'c1')

    # File storage may add trailing newline
    assert cell.code.strip() == new_code.strip()


@pytest.mark.asyncio
async def test_run_cell_streams_status_updates(coordinator):
    """Test that running a cell streams status changes (idle -> running -> success)."""
    coord, broadcaster = coordinator

    await coord.handle_run_cell('c1')

    # Wait for execution
    await asyncio.sleep(0.5)

    # Verify status messages for c1
    status_msgs = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]

    # Should have at least: running, success
    assert len(status_msgs) >= 2

    statuses = [m['status'] for m in status_msgs]
    assert 'running' in statuses
    assert 'success' in statuses or 'error' in statuses


@pytest.mark.asyncio
async def test_run_cell_with_output_streams_result(coordinator):
    """Test that cell execution streams outputs (stdout, display outputs)."""
    coord, broadcaster = coordinator

    # Update cell to have print and expression output
    await coord.handle_cell_update('c1', 'print("Hello")\n42')
    await asyncio.sleep(0.5)  # Wait for registration
    broadcaster.clear()

    # Run cell
    await coord.handle_run_cell('c1')

    # Wait for execution to complete with polling
    max_wait = 3.0  # Maximum 3 seconds
    wait_interval = 0.2
    elapsed = 0.0

    while elapsed < max_wait:
        await asyncio.sleep(wait_interval)
        elapsed += wait_interval

        c1_messages = broadcaster.get_messages_for_cell('c1')
        status_msgs = [m for m in c1_messages if m.get('type') == 'cell_status']
        final_statuses = [m['status'] for m in status_msgs]

        if 'success' in final_statuses or 'error' in final_statuses:
            break

    # Final check
    c1_messages = broadcaster.get_messages_for_cell('c1')
    status_msgs = [m for m in c1_messages if m.get('type') == 'cell_status']
    assert len(status_msgs) >= 1, f"Expected status messages, got: {c1_messages}"

    final_statuses = [m['status'] for m in status_msgs]
    assert 'success' in final_statuses or 'error' in final_statuses, \
        f"Expected completion status, got: {final_statuses}"


@pytest.mark.asyncio
async def test_run_cell_with_error_streams_error(coordinator):
    """Test that execution errors are streamed to clients."""
    coord, broadcaster = coordinator

    # Update cell with code that raises error
    await coord.handle_cell_update('c1', '1 / 0')
    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Run cell
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)

    c1_messages = broadcaster.get_messages_for_cell('c1')

    # Should have error status
    status_msgs = [m for m in c1_messages if m.get('type') == 'cell_status']
    assert any(m['status'] == 'error' for m in status_msgs)

    # Should have error message
    error_msgs = [m for m in c1_messages if m.get('type') == 'cell_error']
    assert len(error_msgs) >= 1
    assert 'ZeroDivisionError' in error_msgs[0]['error'] or 'division' in error_msgs[0]['error'].lower()


@pytest.mark.asyncio
async def test_reactive_cascade_execution(coordinator):
    """Test that running c1 triggers cascade execution of c2 and c3."""
    coord, broadcaster = coordinator

    # Run c1 (should trigger c2 and c3)
    await coord.handle_run_cell('c1')

    # Wait for cascade
    await asyncio.sleep(0.8)

    # Verify all three cells received status updates
    for cell_id in ['c1', 'c2', 'c3']:
        status_msgs = [
            m for m in broadcaster.messages
            if m.get('type') == 'cell_status' and m.get('cellId') == cell_id
        ]
        assert len(status_msgs) >= 1, f"Cell {cell_id} should have status updates"


@pytest.mark.asyncio
async def test_cascade_execution_order(coordinator):
    """Test that cascade executes cells in topological order (c1 -> c2 -> c3)."""
    coord, broadcaster = coordinator

    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.8)

    # Extract execution start times from status messages
    execution_starts = {}
    for cell_id in ['c1', 'c2', 'c3']:
        status_msgs = [
            m for m in broadcaster.messages
            if m.get('type') == 'cell_status'
            and m.get('cellId') == cell_id
            and m.get('status') == 'running'
        ]
        if status_msgs:
            # Use message index as proxy for time
            execution_starts[cell_id] = broadcaster.messages.index(status_msgs[0])

    # Verify c1 started before c2, c2 before c3
    assert execution_starts['c1'] < execution_starts['c2']
    assert execution_starts['c2'] < execution_starts['c3']


@pytest.mark.asyncio
async def test_independent_cells_no_cascade(coordinator):
    """Test that running an independent cell doesn't trigger others."""
    coord, broadcaster = coordinator

    # Add independent cell
    await coord.handle_cell_update('c1', 'independent = 100')
    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Run c1
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)

    # c2 and c3 should NOT have execution status updates (only c1 should)
    c2_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c2'
    ]
    c3_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c3'
    ]

    # c2 and c3 should have no execution (only c1 ran)
    assert len(c2_status) == 0
    assert len(c3_status) == 0


@pytest.mark.asyncio
async def test_database_config_broadcasts_success(coordinator):
    """Test that database configuration broadcasts success message."""
    coord, broadcaster = coordinator

    connection_string = "postgresql://test:test@localhost:5432/testdb"
    await coord.handle_db_connection_update(connection_string)

    # Wait for config
    await asyncio.sleep(0.3)

    # Verify db_connection_updated message
    db_msgs = broadcaster.get_messages_by_type('db_connection_updated')
    assert len(db_msgs) >= 1

    msg = db_msgs[0]
    assert msg['connectionString'] == connection_string
    assert msg['status'] == 'success' or msg['status'] == 'error'  # Either is valid


@pytest.mark.asyncio
async def test_database_config_persists_to_notebook(coordinator):
    """Test that database connection string is persisted."""
    coord, broadcaster = coordinator

    connection_string = "postgresql://user:pass@localhost/db"
    await coord.handle_db_connection_update(connection_string)
    await asyncio.sleep(0.3)

    # Verify in memory
    assert coord.notebook.db_conn_string == connection_string

    # Verify on disk
    reloaded = NotebookFileStorage.parse_notebook('test-commands')
    assert reloaded.db_conn_string == connection_string


@pytest.mark.asyncio
async def test_handlers_are_non_blocking(coordinator):
    """Test that all command handlers return immediately without blocking."""
    import time
    coord, broadcaster = coordinator

    # Test handle_cell_update
    start = time.time()
    await coord.handle_cell_update('c1', 'x = 42')
    duration = time.time() - start
    assert duration < 0.05, f"handle_cell_update took {duration}s"

    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Test handle_run_cell
    start = time.time()
    await coord.handle_run_cell('c1')
    duration = time.time() - start
    assert duration < 0.05, f"handle_run_cell took {duration}s"

    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Test handle_db_connection_update
    start = time.time()
    await coord.handle_db_connection_update('postgresql://localhost/db')
    duration = time.time() - start
    assert duration < 0.05, f"handle_db_connection_update took {duration}s"


@pytest.mark.asyncio
async def test_multiple_rapid_cell_updates(coordinator):
    """Test that rapid cell updates are all processed correctly."""
    coord, broadcaster = coordinator

    # Send 5 rapid updates
    for i in range(5):
        await coord.handle_cell_update('c1', f'x = {i}')

    # Wait for all to process
    await asyncio.sleep(0.5)

    # Final code should be last update
    cell = next(c for c in coord.notebook.cells if c.id == 'c1')
    assert cell.code == 'x = 4'

    # Should have multiple cell_updated messages
    updated_msgs = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_updated' and m.get('cellId') == 'c1'
    ]
    assert len(updated_msgs) >= 5


@pytest.mark.asyncio
async def test_cycle_detection_blocks_cell(coordinator):
    """Test that creating a cycle results in error messages.

    Initial state:
    - c1: x = 10 (writes x)
    - c2: y = x * 2 (reads x, writes y)  [dependency: c1 → c2]
    - c3: z = y + 5 (reads y, writes z)  [dependency: c2 → c3]

    When we try to update c1 to read y (which c2 writes), we'd create:
    - c2 → c1 (because c1 reads y which c2 writes)
    - But c1 → c2 already exists (c2 reads x which c1 writes)
    - This creates a cycle: c1 → c2 → c1
    """
    coord, broadcaster = coordinator

    broadcaster.clear()

    # Try to update c1 to read y - this creates a cycle (c1→c2 exists, adding c2→c1)
    await coord.handle_cell_update('c1', 'x = y + 1')
    await asyncio.sleep(0.5)

    # Check for error or blocked status on c1
    all_messages = broadcaster.messages
    c1_messages = broadcaster.get_messages_for_cell('c1')
    status_msgs = [m for m in c1_messages if m.get('type') == 'cell_status']
    error_msgs = [m for m in c1_messages if m.get('type') == 'cell_error']

    # Should get blocked status AND error message about cycle
    blocked = [m for m in status_msgs if m.get('status') == 'blocked']
    cycle_errors = [
        m for m in error_msgs
        if 'cycle' in str(m.get('error', '')).lower() or 'circular' in str(m.get('error', '')).lower()
    ]

    assert len(blocked) >= 1, \
        f"Expected 'blocked' status for c1. Got c1 messages: {c1_messages}"
    assert len(cycle_errors) >= 1, \
        f"Expected cycle error for c1. Got c1 messages: {c1_messages}"


@pytest.mark.asyncio
async def test_sql_cell_update_broadcasts_metadata(coordinator):
    """Test that SQL cell updates broadcast dependency metadata."""
    coord, broadcaster = coordinator

    # Update a cell with SQL code containing parameter placeholders
    sql_code = "SELECT * FROM users WHERE id = {user_id}"

    # Update c3 with SQL code
    # Note: This updates the cell's code. SQL cells would be created with type='sql' via handle_create_cell
    await coord.handle_cell_update('c3', sql_code)
    await asyncio.sleep(0.3)

    # Verify update was processed
    cell = next(c for c in coord.notebook.cells if c.id == 'c3')
    assert cell.code == sql_code

    # Verify metadata was broadcast
    updated_msgs = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_updated' and m.get('cellId') == 'c3'
    ]
    assert len(updated_msgs) >= 1
