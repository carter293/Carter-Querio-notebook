---
date: 2025-12-27T19:45:08+00:00 GMT
planner: Composer
topic: "Fix Dependent Cell Status Updates and Sequential Rendering"
tags: [planning, implementation, scheduler, websocket, frontend, reactive-execution]
status: draft
last_updated: 2025-12-27
last_updated_by: Composer
---

# Fix Dependent Cell Status Updates and Sequential Rendering Implementation Plan

**Date**: 2025-12-27T19:45:08+00:00 GMT  
**Planner**: Composer

## Overview

This plan fixes two issues identified in the research document (`thoughts/shared/research/2025-12-27-dependent-cell-status-not-updated.md`):

1. **Dependency Check Bug**: The scheduler's dependency check includes cells outside the execution set and checks dependencies before they finish executing, potentially causing dependent cells to be incorrectly marked as BLOCKED.

2. **Sequential Rendering Issue**: React batches state updates from WebSocket messages, causing all dependent cell results to appear "all at once" instead of sequentially, even though backend execution is sequential.

## Current State Analysis

### Dependency Check Implementation

**File**: `backend/scheduler.py:86-93`

The current dependency check logic:
- Checks `notebook.graph.reverse_edges[cell_id]` which includes **ALL** dependencies in the graph
- Does not filter to only dependencies in the current execution set (`all_to_run`)
- Checks dependency status before dependencies have finished executing
- May incorrectly mark cells as BLOCKED if a dependency failed in a previous run but is not in the current execution set

**Logging Results**: Recent logs show the bug is NOT occurring in normal cases (all dependencies are correctly identified as being in the execution set), but the bug could still occur in edge cases (e.g., when a dependency fails in a previous run and is not re-executed).

### Sequential Rendering Issue

**File**: `frontend/src/components/Notebook.tsx:68-80`

The current frontend implementation:
- Receives WebSocket messages sequentially from backend
- Updates state using `setNotebook(prev => ...)` functional updates
- React automatically batches all state updates that occur synchronously (same event loop tick)
- Results in a single render showing all cells as `success` simultaneously

**Root Cause Confirmed**: React State Update Batching
- Backend executes sequentially (confirmed by timing logs: 0.000s → 1.194s)
- WebSocket messages arrive in quick succession (~0.5ms apart)
- React batches all `setNotebook` calls into a single render
- Only one `[REACT_RENDER]` occurs showing all cells as `success`

### Key Discoveries

- **File**: `backend/scheduler.py:86-93` - Dependency check uses full graph, not execution set
- **File**: `backend/scheduler.py:60-64` - Execution set (`all_to_run`) correctly includes all cells to run
- **File**: `backend/graph.py:62-92` - Topological sort ensures dependencies execute before dependents
- **File**: `frontend/src/components/Notebook.tsx:34-148` - State updates use functional updates but are batched by React
- **File**: `frontend/src/useWebSocket.ts:85-109` - WebSocket messages arrive sequentially but quickly
- **Pattern**: React 18+ automatically batches state updates in the same event loop tick

## System Context Analysis

This plan addresses **both root causes and symptoms**:

1. **Dependency Check Bug**: This is a **root cause** issue in the scheduler logic. Even though logging shows it's not occurring in normal cases, the bug exists and could cause incorrect blocking in edge cases. The fix ensures the dependency check only considers dependencies in the current execution set and verifies they have finished executing.

2. **Sequential Rendering Issue**: This is a **symptom** of React's automatic batching behavior. The backend executes correctly and sends messages sequentially, but React batches the updates. The fix uses `flushSync` to force immediate renders, addressing the UX symptom while maintaining correct backend behavior.

**State Management Flow**:
- Backend executes cells sequentially in topological order
- WebSocket broadcasts status updates sequentially
- Frontend receives messages sequentially but React batches updates
- Single render shows all cells updated simultaneously

**Dependency Graph Structure**:
- `edges`: `cell_id -> set of dependent cell_ids` (forward edges)
- `reverse_edges`: `cell_id -> set of dependency cell_ids` (backward edges)
- Execution set (`all_to_run`) contains cells currently being executed
- Dependency check should only consider dependencies in `all_to_run`

## Desired End State

After this plan is complete:

1. **Dependency Check Fixed**: Only dependencies in the current execution set are checked, and the check verifies dependencies have finished executing before blocking dependent cells.

2. **Sequential Rendering**: Dependent cell results appear sequentially in the UI, matching the sequential backend execution.

3. **Edge Cases Handled**: Cells are not incorrectly blocked when dependencies fail in previous runs but are not in the current execution set.

4. **Performance Maintained**: `flushSync` is used judiciously to avoid performance degradation.

### Verification

- Dependency check logs show only dependencies in execution set are checked
- Cells are not incorrectly marked as BLOCKED when dependencies are re-executed successfully
- Dependent cell results appear sequentially in the UI (one after another, not all at once)
- Backend execution remains sequential (no changes to execution logic)
- WebSocket messages continue to arrive sequentially
- React renders occur sequentially for each cell status update

## What We're NOT Doing

- **Not changing execution logic**: Backend execution order and timing remain unchanged
- **Not changing WebSocket protocol**: Message types and structure remain the same
- **Not removing React batching entirely**: Only using `flushSync` for cell status updates, not all state updates
- **Not adding artificial delays**: Using `flushSync` instead of delays for sequential rendering
- **Not changing dependency graph structure**: Graph structure remains the same, only the check logic changes
- **Not changing topological sort**: Execution order logic remains unchanged

## Implementation Approach

The implementation will be done in phases:

1. **Phase 1**: Fix dependency check to only consider dependencies in execution set
2. **Phase 2**: Add verification that dependencies have finished executing
3. **Phase 3**: Add tests for dependency check edge cases
4. **Phase 4**: Implement `flushSync` for sequential rendering
5. **Phase 5**: Add tests and verify sequential rendering

This phased approach allows incremental testing and ensures each fix is verified independently.

## Phase 1: Fix Dependency Check to Only Consider Execution Set

### Overview
Modify the dependency check in `backend/scheduler.py` to only check dependencies that are in the current execution set (`all_to_run`), not all dependencies in the graph.

### Changes Required

#### 1. Update Dependency Check Logic
**File**: `backend/scheduler.py`
**Changes**: Modify dependency check (lines 86-93)

```python
# Check if upstream dependency failed (only check dependencies in current execution set)
has_failed_dependency = False
if cell_id in notebook.graph.reverse_edges:
    for dep_id in notebook.graph.reverse_edges[cell_id]:
        # Only check dependencies that are in the current execution set
        if dep_id not in all_to_run:
            continue
        dep_cell = self._get_cell(notebook, dep_id)
        if dep_cell and dep_cell.status == CellStatus.ERROR:
            has_failed_dependency = True
            break
```

**Rationale**: This ensures we only consider dependencies that are currently being executed in this run, not dependencies from previous runs that may have failed but are not being re-executed.

### Success Criteria

#### Automated Verification:
- [ ] Python syntax check passes: `python -m py_compile backend/scheduler.py`
- [ ] Existing tests pass: `pytest backend/tests/test_executor.py backend/tests/test_graph.py`
- [ ] No linting errors: `pylint backend/scheduler.py` (if configured)

#### Manual Verification:
- [ ] Dependency check only considers dependencies in execution set
- [ ] Cells are not incorrectly blocked when dependencies fail in previous runs
- [ ] Logs show `dependencies_outside_execution_set=[]` or correct filtering

---

## Phase 2: Verify Dependencies Have Finished Executing

### Overview
Add verification that dependencies have finished executing (status is not RUNNING) before blocking dependent cells. This handles edge cases where topological sort might not guarantee execution order.

### Changes Required

#### 1. Add Execution Status Check
**File**: `backend/scheduler.py`
**Changes**: Enhance dependency check (lines 86-99)

```python
# Check if upstream dependency failed (only check dependencies in current execution set)
has_failed_dependency = False
if cell_id in notebook.graph.reverse_edges:
    for dep_id in notebook.graph.reverse_edges[cell_id]:
        # Only check dependencies that are in the current execution set
        if dep_id not in all_to_run:
            continue
        dep_cell = self._get_cell(notebook, dep_id)
        if dep_cell:
            # Check if dependency has finished executing and failed
            if dep_cell.status == CellStatus.ERROR:
                has_failed_dependency = True
                break
            # If dependency is still running, wait for it (shouldn't happen due to topological sort, but be safe)
            if dep_cell.status == CellStatus.RUNNING:
                # This shouldn't happen due to topological sort, but handle gracefully
                # Log warning for debugging
                import logging
                logging.warning(
                    f"Cell {cell_id} has dependency {dep_id} that is still RUNNING. "
                    f"This should not happen due to topological sort."
                )
                continue
```

**Rationale**: This adds a safety check to ensure dependencies have finished executing before we check their status. The topological sort should guarantee this, but this provides an extra safety net.

### Success Criteria

#### Automated Verification:
- [ ] Python syntax check passes: `python -m py_compile backend/scheduler.py`
- [ ] Existing tests pass: `pytest backend/tests/test_executor.py backend/tests/test_graph.py`
- [ ] No linting errors: `pylint backend/scheduler.py` (if configured)

#### Manual Verification:
- [ ] Dependency check verifies dependencies have finished executing
- [ ] Warning logs appear if dependency is RUNNING (should not happen in normal cases)
- [ ] Cells are correctly blocked only when dependencies have failed

---

## Phase 3: Add Tests for Dependency Check Edge Cases

### Overview
Add comprehensive tests to verify the dependency check works correctly in edge cases, including dependencies outside execution set and dependencies that fail in previous runs.

### Changes Required

#### 1. Create Test File for Scheduler Dependency Checks
**File**: `backend/tests/test_scheduler.py` (create new file)
**Changes**: Add tests for dependency check edge cases

```python
import pytest
from backend.scheduler import ExecutionScheduler
from backend.models import Notebook, Cell, CellStatus, CellType, Graph
from backend.graph import rebuild_graph

@pytest.mark.asyncio
async def test_dependency_check_only_considers_execution_set():
    """Test that dependency check only considers dependencies in execution set"""
    scheduler = ExecutionScheduler()
    notebook = Notebook(id="test")
    
    # Create cells: A writes x, B reads x (depends on A), C reads x (depends on A)
    cell_a = Cell(id="a", type=CellType.PYTHON, code="x = 1", status=CellStatus.ERROR)
    cell_a.writes = {'x'}
    cell_b = Cell(id="b", type=CellType.PYTHON, code="y = x + 1", status=CellStatus.IDLE)
    cell_b.reads = {'x'}
    cell_b.writes = {'y'}
    cell_c = Cell(id="c", type=CellType.PYTHON, code="z = x + 2", status=CellStatus.IDLE)
    cell_c.reads = {'x'}
    cell_c.writes = {'z'}
    
    notebook.cells = [cell_a, cell_b, cell_c]
    rebuild_graph(notebook)
    
    # Mock broadcaster
    class MockBroadcaster:
        async def broadcast_cell_status(self, notebook_id, cell_id, status):
            pass
        async def broadcast_cell_error(self, notebook_id, cell_id, error):
            pass
    
    broadcaster = MockBroadcaster()
    
    # Run only cell B (not A, which has ERROR status from previous run)
    # Cell B should NOT be blocked because A is not in execution set
    await scheduler.enqueue_run("test", "b", notebook, broadcaster)
    
    # Wait for execution to complete
    await asyncio.sleep(0.1)
    
    # Cell B should execute (not be blocked) because A is not in execution set
    assert cell_b.status != CellStatus.BLOCKED

@pytest.mark.asyncio
async def test_dependency_check_blocks_when_dependency_fails_in_execution_set():
    """Test that dependency check blocks cells when dependency fails in execution set"""
    scheduler = ExecutionScheduler()
    notebook = Notebook(id="test")
    
    # Create cells: A writes x, B reads x (depends on A)
    cell_a = Cell(id="a", type=CellType.PYTHON, code="x = 1 / 0", status=CellStatus.IDLE)
    cell_a.writes = {'x'}
    cell_b = Cell(id="b", type=CellType.PYTHON, code="y = x + 1", status=CellStatus.IDLE)
    cell_b.reads = {'x'}
    cell_b.writes = {'y'}
    
    notebook.cells = [cell_a, cell_b]
    rebuild_graph(notebook)
    
    # Mock broadcaster
    class MockBroadcaster:
        async def broadcast_cell_status(self, notebook_id, cell_id, status):
            pass
        async def broadcast_cell_error(self, notebook_id, cell_id, error):
            pass
    
    broadcaster = MockBroadcaster()
    
    # Run cell A (which will fail), then B should be blocked
    await scheduler.enqueue_run("test", "a", notebook, broadcaster)
    
    # Wait for execution to complete
    await asyncio.sleep(0.1)
    
    # Cell A should have ERROR status
    assert cell_a.status == CellStatus.ERROR
    
    # Cell B should be BLOCKED because A failed and is in execution set
    assert cell_b.status == CellStatus.BLOCKED
```

### Success Criteria

#### Automated Verification:
- [ ] All new tests pass: `pytest backend/tests/test_scheduler.py -v`
- [ ] Test coverage increases for scheduler dependency checks
- [ ] No linting errors: `pylint backend/tests/test_scheduler.py` (if configured)

#### Manual Verification:
- [ ] Tests verify dependency check only considers execution set
- [ ] Tests verify cells are blocked when dependencies fail in execution set
- [ ] Tests verify cells are not blocked when dependencies fail outside execution set

---

## Phase 4: Implement Sequential Rendering with flushSync

### Overview
Use React's `flushSync` to force immediate renders for cell status updates, ensuring dependent cell results appear sequentially instead of all at once.

### Changes Required

#### 1. Import flushSync
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Add import at top of file (after line 1)

```typescript
import { useState, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { Cell } from './Cell';
```

#### 2. Restructure handleWSMessage to Support flushSync
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Restructure `handleWSMessage` to handle `cell_status` separately with `flushSync` (lines 25-156)

The current implementation uses a functional update pattern inside `handleWSMessage`. We need to restructure it so that `cell_status` updates use `flushSync` while other message types continue to use the functional update pattern.

**Approach**: Split the message handling - use `flushSync` for `cell_status` messages outside the functional update, and keep other message types in the functional update pattern.

```typescript
// Handle WebSocket messages
const handleWSMessage = useCallback((msg: WSMessage) => {
  const messageReceivedTime = performance.now();
  const messageTimestamp = new Date().toISOString();
  
  console.log(
    `[WS_MESSAGE_RECEIVED] type=${msg.type}, cellId=${msg.cellId}, ` +
    `timestamp=${messageTimestamp}, perf_time=${messageReceivedTime.toFixed(3)}`
  );
  
  // Special handling for cell_status to enable sequential rendering
  if (msg.type === 'cell_status') {
    // Use flushSync to force immediate render for sequential appearance
    flushSync(() => {
      setNotebook(prev => {
        if (!prev) return prev;
        const oldStatus = prev.cells.find(c => c.id === msg.cellId)?.status;
        console.log(
          `[STATUS_UPDATE] cellId=${msg.cellId}, old_status=${oldStatus}, new_status=${msg.status}, ` +
          `time_since_message_received=${(performance.now() - messageReceivedTime).toFixed(3)}ms`
        );
        
        const cells = prev.cells.map(cell => {
          if (cell.id !== msg.cellId) return cell;
          if (msg.status === 'running') {
            // Clear outputs when execution starts
            return { ...cell, status: msg.status, stdout: '', outputs: [], error: undefined };
          }
          return { ...cell, status: msg.status };
        });
        
        const stateUpdateEnd = performance.now();
        console.log(
          `[STATUS_UPDATE_COMPLETE] cellId=${msg.cellId}, ` +
          `state_update_duration=${(stateUpdateEnd - messageReceivedTime).toFixed(3)}ms, ` +
          `total_time_since_message=${(stateUpdateEnd - messageReceivedTime).toFixed(3)}ms`
        );
        
        return { ...prev, cells };
      });
    });
    return;
  }
  
  // Handle other message types with functional updates (batched)
  setNotebook(prev => {
    if (!prev) return prev;
    
    const stateUpdateStart = performance.now();
    
    switch (msg.type) {
      case 'cell_updated':
        // Update cell metadata (code, reads, writes, status)
        return {
          ...prev,
          cells: prev.cells.map(cell =>
            cell.id === msg.cellId
              ? { 
                  ...cell, 
                  code: msg.cell.code,
                  reads: msg.cell.reads,
                  writes: msg.cell.writes,
                  status: msg.cell.status as api.CellStatus
                }
              : cell
          )
        };
      
      case 'cell_created':
        // Append new cell to end
        return { ...prev, cells: [...prev.cells, msg.cell] };
      
      case 'cell_deleted':
        return {
          ...prev,
          cells: prev.cells.filter(c => c.id !== msg.cellId)
        };
      
      case 'cell_stdout':
        console.log(
          `[STDOUT_UPDATE] cellId=${msg.cellId}, ` +
          `time_since_message_received=${(performance.now() - messageReceivedTime).toFixed(3)}ms`
        );
        const stdoutResult = {
          ...prev,
          cells: prev.cells.map(cell =>
            cell.id === msg.cellId ? { ...cell, stdout: msg.data } : cell
          )
        };
        console.log(
          `[STDOUT_UPDATE_COMPLETE] cellId=${msg.cellId}, ` +
          `state_update_duration=${(performance.now() - stateUpdateStart).toFixed(3)}ms`
        );
        return stdoutResult;

      case 'cell_error':
        console.log(
          `[ERROR_UPDATE] cellId=${msg.cellId}, error=${msg.error?.substring(0, 50)}..., ` +
          `time_since_message_received=${(performance.now() - messageReceivedTime).toFixed(3)}ms`
        );
        const errorResult = {
          ...prev,
          cells: prev.cells.map(cell =>
            cell.id === msg.cellId ? { ...cell, error: msg.error } : cell
          )
        };
        console.log(
          `[ERROR_UPDATE_COMPLETE] cellId=${msg.cellId}, ` +
          `state_update_duration=${(performance.now() - stateUpdateStart).toFixed(3)}ms`
        );
        return errorResult;

      case 'cell_output':
        const outputMimeType = msg.output?.mime_type || 'unknown';
        console.log(
          `[OUTPUT_UPDATE] cellId=${msg.cellId}, mime_type=${outputMimeType}, ` +
          `time_since_message_received=${(performance.now() - messageReceivedTime).toFixed(3)}ms`
        );
        const outputResult = {
          ...prev,
          cells: prev.cells.map(cell => {
            if (cell.id !== msg.cellId) return cell;
            const outputs = cell.outputs || [];
            return { ...cell, outputs: [...outputs, msg.output] };
          })
        };
        console.log(
          `[OUTPUT_UPDATE_COMPLETE] cellId=${msg.cellId}, mime_type=${outputMimeType}, ` +
          `state_update_duration=${(performance.now() - stateUpdateStart).toFixed(3)}ms`
        );
        return outputResult;

      default:
        return prev;
    }
  });
  
  // Log after state update is queued (React will batch these for non-status messages)
  const afterUpdateTime = performance.now();
  console.log(
    `[WS_MESSAGE_HANDLED] type=${msg.type}, cellId=${msg.cellId}, ` +
    `total_handling_time=${(afterUpdateTime - messageReceivedTime).toFixed(3)}ms`
  );
}, []);
```

**Rationale**: `flushSync` forces React to flush state updates immediately instead of batching them. This ensures each cell status update triggers a separate render, making results appear sequentially.

**Performance Consideration**: `flushSync` can impact performance if used excessively. We only use it for `cell_status` updates, not for other message types (stdout, error, output) which can still be batched.

### Success Criteria

#### Automated Verification:
- [ ] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] No TypeScript errors: `cd frontend && npm run typecheck`
- [ ] No linting errors: `cd frontend && npm run lint` (if configured)

#### Manual Verification:
- [ ] Dependent cell results appear sequentially (one after another)
- [ ] Each cell status update triggers a separate render
- [ ] Console logs show multiple `[REACT_RENDER]` entries (one per cell)
- [ ] Performance is acceptable (no noticeable lag)
- [ ] Other message types (stdout, error, output) still work correctly

---

## Phase 5: Add Tests and Verify Sequential Rendering

### Overview
Add tests to verify sequential rendering behavior and ensure the fix works correctly. Also verify that the dependency check fix doesn't break existing functionality.

### Changes Required

#### 1. Add Integration Test for Sequential Execution
**File**: `backend/tests/test_scheduler.py`
**Changes**: Add test for sequential execution and status updates

```python
@pytest.mark.asyncio
async def test_sequential_execution_and_status_updates():
    """Test that cells execute sequentially and status updates are broadcast in order"""
    scheduler = ExecutionScheduler()
    notebook = Notebook(id="test")
    
    # Create cells: A writes x, B reads x (depends on A), C reads x (depends on A)
    cell_a = Cell(id="a", type=CellType.PYTHON, code="x = 1", status=CellStatus.IDLE)
    cell_a.writes = {'x'}
    cell_b = Cell(id="b", type=CellType.PYTHON, code="y = x + 1", status=CellStatus.IDLE)
    cell_b.reads = {'x'}
    cell_b.writes = {'y'}
    cell_c = Cell(id="c", type=CellType.PYTHON, code="z = x + 2", status=CellStatus.IDLE)
    cell_c.reads = {'x'}
    cell_c.writes = {'z'}
    
    notebook.cells = [cell_a, cell_b, cell_c]
    rebuild_graph(notebook)
    
    # Track status updates
    status_updates = []
    
    class MockBroadcaster:
        async def broadcast_cell_status(self, notebook_id, cell_id, status):
            status_updates.append((cell_id, status))
        async def broadcast_cell_error(self, notebook_id, cell_id, error):
            pass
        async def broadcast_cell_stdout(self, notebook_id, cell_id, stdout):
            pass
        async def broadcast_cell_output(self, notebook_id, cell_id, output):
            pass
    
    broadcaster = MockBroadcaster()
    
    # Run cell A, which should trigger B and C
    await scheduler.enqueue_run("test", "a", notebook, broadcaster)
    
    # Wait for execution to complete
    await asyncio.sleep(0.5)
    
    # Verify execution order: A should run first, then B and C (order may vary for B and C)
    assert len(status_updates) >= 6  # At least 3 RUNNING + 3 SUCCESS/ERROR
    
    # A should start first
    assert status_updates[0] == ("a", CellStatus.RUNNING)
    # A should complete before B or C start
    a_complete_idx = next(i for i, (cid, status) in enumerate(status_updates) if cid == "a" and status != CellStatus.RUNNING)
    b_start_idx = next((i for i, (cid, status) in enumerate(status_updates) if cid == "b" and status == CellStatus.RUNNING), None)
    c_start_idx = next((i for i, (cid, status) in enumerate(status_updates) if cid == "c" and status == CellStatus.RUNNING), None)
    
    if b_start_idx is not None:
        assert b_start_idx > a_complete_idx
    if c_start_idx is not None:
        assert c_start_idx > a_complete_idx
```

#### 2. Manual Testing Checklist
Create a manual testing checklist to verify sequential rendering:

1. **Sequential Execution Test**:
   - Open demo notebook
   - Run a cell that has multiple dependent cells
   - Verify cells execute sequentially (timing logs show sequential execution)
   - Verify WebSocket messages arrive sequentially

2. **Sequential Rendering Test**:
   - Open demo notebook
   - Run a cell that has multiple dependent cells
   - Verify cell results appear sequentially in UI (one after another, not all at once)
   - Check console logs show multiple `[REACT_RENDER]` entries
   - Verify each render shows incremental cell status updates

3. **Dependency Check Edge Case Test**:
   - Create cells: A writes x (fails), B reads x
   - Run A (fails), verify B is blocked
   - Fix A, run A again (succeeds), verify B executes
   - Verify B is not incorrectly blocked

4. **Performance Test**:
   - Run notebook with many dependent cells
   - Verify sequential rendering doesn't cause noticeable lag
   - Verify UI remains responsive

### Success Criteria

#### Automated Verification:
- [ ] All tests pass: `pytest backend/tests/test_scheduler.py -v`
- [ ] No regressions in existing tests: `pytest backend/tests/`
- [ ] TypeScript compilation passes: `cd frontend && npm run build`

#### Manual Verification:
- [ ] Sequential execution verified (backend logs show sequential timing)
- [ ] Sequential rendering verified (UI shows results one after another)
- [ ] Dependency check edge cases handled correctly
- [ ] Performance is acceptable (no noticeable lag)
- [ ] No regressions in existing functionality

---

## Testing Strategy

### Unit Tests

#### Backend Tests
- **Test dependency check only considers execution set**: Verify cells are not blocked when dependencies fail outside execution set
- **Test dependency check blocks when dependency fails in execution set**: Verify cells are blocked when dependencies fail in execution set
- **Test sequential execution**: Verify cells execute in topological order
- **Test status updates**: Verify status updates are broadcast in correct order

**File**: `backend/tests/test_scheduler.py` (create new file)

#### Frontend Tests
- **Test flushSync usage**: Verify `flushSync` is used correctly for cell status updates
- **Test sequential rendering**: Verify multiple renders occur for sequential status updates
- **Test other message types**: Verify other message types (stdout, error, output) still work correctly

**File**: `frontend/src/components/__tests__/Notebook.test.tsx` (create if needed)

### Integration Tests

#### End-to-End Scenarios
1. **Sequential Execution and Rendering**:
   - Run cell with multiple dependents → Verify backend executes sequentially → Verify frontend renders sequentially

2. **Dependency Check Edge Case**:
   - Create cells with failed dependency → Run dependency → Verify dependent is blocked → Fix dependency → Run again → Verify dependent executes

3. **Performance Under Load**:
   - Run notebook with many dependent cells → Verify sequential rendering doesn't cause lag → Verify UI remains responsive

### Manual Testing Steps

1. **Sequential Rendering Verification**:
   - Open demo notebook
   - Run a cell with multiple dependents
   - Observe cell results appear one after another (not all at once)
   - Check console logs show multiple renders

2. **Dependency Check Verification**:
   - Create cells: A writes x (fails), B reads x
   - Run A (fails), verify B is blocked
   - Fix A, run A again (succeeds), verify B executes
   - Verify B is not incorrectly blocked

3. **Performance Verification**:
   - Run notebook with many dependent cells
   - Verify no noticeable lag
   - Verify UI remains responsive

## Performance Considerations

1. **flushSync Impact**: `flushSync` forces synchronous renders, which can impact performance. We only use it for `cell_status` updates, not for other message types (stdout, error, output) which can still be batched.

2. **Dependency Check Performance**: Filtering dependencies to execution set improves performance by reducing the number of cells checked.

3. **Sequential Rendering**: Multiple renders may impact performance for notebooks with many cells. Monitor performance and consider optimizations if needed.

4. **WebSocket Message Frequency**: Sequential rendering doesn't change WebSocket message frequency, only how React processes them.

## Migration Notes

### Backward Compatibility

- **No breaking changes**: All changes are internal improvements
- **WebSocket protocol unchanged**: Message types and structure remain the same
- **API unchanged**: No changes to REST API endpoints

### Rollback Plan

If issues arise:

1. **Phase 1-2**: Can rollback by reverting dependency check changes (restore original logic)
2. **Phase 3**: Can rollback by removing new tests (no functional changes)
3. **Phase 4**: Can rollback by removing `flushSync` import and usage (restore original batching behavior)
4. **Phase 5**: Can rollback by removing new tests (no functional changes)

### Data Migration

- **No data migration needed** - all changes are in-memory and rendering logic
- **Storage format unchanged** - notebook persistence remains the same

## References

- Original research: `thoughts/shared/research/2025-12-27-dependent-cell-status-not-updated.md`
- WebSocket-only implementation: `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`
- Backend scheduler: `backend/scheduler.py`
- Backend graph: `backend/graph.py`
- Frontend notebook component: `frontend/src/components/Notebook.tsx`
- Frontend WebSocket hook: `frontend/src/useWebSocket.ts`

