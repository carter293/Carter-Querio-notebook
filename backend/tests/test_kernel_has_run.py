"""
Tests for has_run state tracking in kernel process.

Validates that:
- First execution runs stale ancestors
- Subsequent executions skip already-run ancestors
- Code changes invalidate has_run state
- Execution errors don't mark cells as run
- Descendants are properly invalidated
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

    # Create test notebook with dependent cells (c1 → c2 → c3)
    notebook = NotebookResponse(
        id='test-has-run',
        name='Test has_run State Tracking',
        cells=[
            CellResponse(id='c1', type='python', code='x = 10'),
            CellResponse(id='c2', type='python', code='y = x * 2'),
            CellResponse(id='c3', type='python', code='z = y + 5'),
        ]
    )

    NotebookFileStorage.serialize_notebook(notebook)
    event_loop.run_until_complete(coord.load_notebook('test-has-run'))

    # Wait for initial registration
    event_loop.run_until_complete(asyncio.sleep(0.5))
    broadcaster.clear()

    yield coord, broadcaster

    coord.shutdown()


@pytest.mark.asyncio
async def test_first_run_executes_ancestors(coordinator):
    """First time running c2 should execute c1 first (stale ancestor)."""
    coord, broadcaster = coordinator

    # Execute c2 (should also run c1 because c1 hasn't run yet)
    await coord.handle_run_cell('c2')
    await asyncio.sleep(0.8)

    # Verify both c1 and c2 received status updates
    c1_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]
    c2_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c2'
    ]

    assert len(c1_status) >= 1, "c1 should execute (stale ancestor)"
    assert len(c2_status) >= 1, "c2 should execute (requested)"

    # Verify execution order: c1 runs before c2
    c1_running_idx = next(
        i for i, m in enumerate(broadcaster.messages)
        if m.get('cellId') == 'c1' and m.get('status') == 'running'
    )
    c2_running_idx = next(
        i for i, m in enumerate(broadcaster.messages)
        if m.get('cellId') == 'c2' and m.get('status') == 'running'
    )

    assert c1_running_idx < c2_running_idx, "c1 must execute before c2"


@pytest.mark.asyncio
async def test_second_run_skips_ancestors(coordinator):
    """Second time running c2 should NOT re-execute c1 (already run)."""
    coord, broadcaster = coordinator

    # First execution: run c1 to mark it as executed
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)
    broadcaster.clear()

    # Second execution: run c2 (should skip c1)
    await coord.handle_run_cell('c2')
    await asyncio.sleep(0.5)

    # c1 should NOT have execution status updates
    c1_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]

    # c2 should have execution status updates
    c2_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c2'
    ]

    assert len(c1_status) == 0, "c1 should be skipped (already executed)"
    assert len(c2_status) >= 1, "c2 should execute"


@pytest.mark.asyncio
async def test_code_change_invalidates_descendants(coordinator):
    """Changing c1 code should invalidate c1, c2, and c3."""
    coord, broadcaster = coordinator

    # First execution: run all cells
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.8)
    broadcaster.clear()

    # Update c1 code (should invalidate c1, c2, c3)
    await coord.handle_cell_update('c1', 'x = 20')
    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Execute c3 (should re-run c1, c2, c3 because all are now stale)
    await coord.handle_run_cell('c3')
    await asyncio.sleep(0.8)

    # Verify all three cells executed
    for cell_id in ['c1', 'c2', 'c3']:
        status_msgs = [
            m for m in broadcaster.messages
            if m.get('type') == 'cell_status' and m.get('cellId') == cell_id
        ]
        assert len(status_msgs) >= 1, f"Cell {cell_id} should execute (invalidated by c1 change)"


@pytest.mark.asyncio
async def test_failed_execution_keeps_stale(coordinator):
    """Failed execution should NOT mark cell as run."""
    coord, broadcaster = coordinator

    # Update c1 to fail
    await coord.handle_cell_update('c1', '1 / 0')  # ZeroDivisionError
    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Run c1 (will fail)
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)

    # Verify c1 has error status
    error_msgs = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_error' and m.get('cellId') == 'c1'
    ]
    assert len(error_msgs) >= 1, "c1 should have error message"

    broadcaster.clear()

    # Run c1 again (should execute again because it failed last time)
    # Fix the code first
    await coord.handle_cell_update('c1', 'x = 10')
    await asyncio.sleep(0.3)
    broadcaster.clear()

    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)

    # Verify c1 executed again
    c1_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]
    assert len(c1_status) >= 1, "c1 should execute again (was stale after failure)"


@pytest.mark.asyncio
async def test_independent_cells_no_cascade(coordinator):
    """Independent cells should not affect each other's has_run state."""
    coord, broadcaster = coordinator

    # Update c1 to be independent
    await coord.handle_cell_update('c1', 'independent = 100')
    await asyncio.sleep(0.3)

    # Run c1
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)
    broadcaster.clear()

    # Run c2 (depends on x, not independent)
    # c2 should still try to run its dependencies, but c1 writes 'independent', not 'x'
    # So c2 should fail with NameError (x not defined)
    await coord.handle_run_cell('c2')
    await asyncio.sleep(0.5)

    # Verify c1 was NOT re-executed (it's independent and already ran)
    c1_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]

    # c1 should not have status updates (doesn't write 'x', so c2 doesn't depend on it)
    assert len(c1_status) == 0, "Independent cell c1 should not execute"


@pytest.mark.asyncio
async def test_registration_invalidates_has_run(coordinator):
    """Registering a cell should mark it as not run."""
    coord, broadcaster = coordinator

    # Run c1
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.5)
    broadcaster.clear()

    # Re-register c1 with same code
    await coord.handle_cell_update('c1', 'x = 10')
    await asyncio.sleep(0.3)
    broadcaster.clear()

    # Run c2 (should re-run c1 because re-registration invalidated it)
    await coord.handle_run_cell('c2')
    await asyncio.sleep(0.5)

    # Verify c1 executed again
    c1_status = [
        m for m in broadcaster.messages
        if m.get('type') == 'cell_status' and m.get('cellId') == 'c1'
    ]

    assert len(c1_status) >= 1, "c1 should re-execute (invalidated by re-registration)"


@pytest.mark.asyncio
async def test_cascade_includes_descendants_always(coordinator):
    """Running c1 should always cascade to c2 and c3, regardless of has_run."""
    coord, broadcaster = coordinator

    # Run all cells first
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.8)
    broadcaster.clear()

    # Run c1 again (c2 and c3 should re-execute as descendants)
    await coord.handle_run_cell('c1')
    await asyncio.sleep(0.8)

    # Verify c2 and c3 executed (reactive cascade)
    for cell_id in ['c1', 'c2', 'c3']:
        status_msgs = [
            m for m in broadcaster.messages
            if m.get('type') == 'cell_status' and m.get('cellId') == cell_id
        ]
        assert len(status_msgs) >= 1, f"Cell {cell_id} should execute (reactive cascade)"
