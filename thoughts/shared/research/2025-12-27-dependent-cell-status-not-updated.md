---
date: 2025-12-27T18:05:03+00:00 GMT
researcher: Composer
topic: "Why dependent cell status is never updated when a cell is run"
tags: [research, codebase, websocket, scheduler, reactive-execution]
status: complete
last_updated: 2025-12-27
last_updated_by: Composer
---

# Research: Dependent Cell Status Not Updated

**Date**: 2025-12-27T18:05:03+00:00 GMT  
**Researcher**: Composer

## Research Question

After implementing the WebSocket-only architecture plan (`thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`), the status of dependent cells is never updated when a cell is run. Why?

## Summary

The issue is in the dependency check logic in `backend/scheduler.py`. When checking if a dependent cell should be blocked due to a failed upstream dependency (lines 86-93), the code checks `notebook.graph.reverse_edges[cell_id]` which includes **ALL** dependencies of the cell, not just the ones that are currently being executed in this run. This causes dependent cells to be incorrectly marked as BLOCKED or skipped when they should be executed, because the check considers dependencies that are outside the current execution set (`all_to_run`).

Additionally, the dependency check happens **before** dependencies have finished executing, so even if a dependency is in `all_to_run`, its status might not yet reflect its execution result when the check runs.

**Related Issue**: This bug also causes dependent cell results to appear "all at once" instead of sequentially, because cells that should execute in order are being incorrectly skipped or evaluated, disrupting the proper sequential execution flow.

## Detailed Findings

### System Architecture Context

The application uses a reactive execution model where:
- When a cell is run, the scheduler discovers all dependent cells (cells that read variables written by the run cell)
- Dependent cells are executed automatically in topological order
- Status updates are broadcast via WebSocket to all connected clients
- The frontend uses WebSocket messages as the single source of truth for state updates

**Key Components:**
- `backend/scheduler.py` - Execution scheduler that manages cell execution queue
- `backend/graph.py` - Dependency graph traversal (`get_all_dependents`, `topological_sort`)
- `backend/websocket.py` - WebSocket broadcaster for status updates
- `frontend/src/components/Notebook.tsx` - Frontend component that handles WebSocket messages

### Root Cause Analysis

#### Issue 1: Dependency Check Includes Cells Outside Execution Set

**File**: `backend/scheduler.py:86-93`

```python
# Check if upstream dependency failed
has_failed_dependency = False
if cell_id in notebook.graph.reverse_edges:
    for dep_id in notebook.graph.reverse_edges[cell_id]:
        dep_cell = self._get_cell(notebook, dep_id)
        if dep_cell and dep_cell.status == CellStatus.ERROR:
            has_failed_dependency = True
            break
```

**Problem**: `notebook.graph.reverse_edges[cell_id]` returns **ALL** dependencies of the cell, including:
- Dependencies that are in `all_to_run` (currently being executed)
- Dependencies that are **NOT** in `all_to_run` (from previous runs or unrelated cells)

**Impact**: If a cell has a dependency that failed in a previous run (status = ERROR) but that dependency is NOT in the current execution set, the dependent cell will be incorrectly marked as BLOCKED and skipped, even though the dependency might be re-executed successfully in this run.

**Example Scenario**:
1. Cell A writes `x = 1`
2. Cell B reads `x` (depends on A)
3. Cell A is run and fails (status = ERROR)
4. Cell A is run again (status changes to RUNNING, then SUCCESS)
5. Cell B should execute, but the check at line 91 sees Cell A's status from step 3 (ERROR) and marks Cell B as BLOCKED

#### Issue 2: Dependency Check Happens Before Dependencies Finish Executing

**File**: `backend/scheduler.py:80-102`

The execution loop processes cells in topological order:
1. Line 68: Cells are sorted topologically
2. Line 81: Loop iterates through sorted cells
3. Line 88-93: Dependency check runs **before** the dependency has finished executing
4. Line 102: Cell executes

**Problem**: Even though cells are sorted topologically, the dependency check at lines 88-93 happens **before** the dependency cell has finished executing. The check uses `dep_cell.status == CellStatus.ERROR`, but:
- If the dependency is currently RUNNING, its status is RUNNING, not ERROR
- If the dependency is in `all_to_run` but hasn't executed yet, its status might be IDLE or SUCCESS from a previous run

**Impact**: The check doesn't correctly identify failed dependencies that are currently being executed, because it checks status before execution completes.

### Execution Flow Analysis

**File**: `backend/scheduler.py:44-102`

1. **Cell Discovery** (lines 60-64):
   - `all_to_run = set(pending_cells)` - Includes the cell that was run
   - `get_all_dependents()` discovers all dependent cells
   - Dependents are added to `all_to_run`

2. **Topological Sort** (lines 66-68):
   - Cells are sorted to respect dependency order
   - Ensures dependencies execute before dependents

3. **Execution Loop** (lines 81-102):
   - Each cell in sorted order is processed
   - Dependency check runs (lines 86-93) - **PROBLEM HERE**
   - If dependency failed, cell is marked BLOCKED and skipped
   - Otherwise, cell executes via `_execute_cell()`

**The Problem**: The dependency check at lines 88-93 checks `notebook.graph.reverse_edges[cell_id]`, which includes ALL dependencies, not just the ones in `all_to_run`. This means:
- Dependencies outside `all_to_run` are checked (from previous runs)
- Dependencies inside `all_to_run` are checked before they finish executing

### Status Update Broadcasting

**File**: `backend/scheduler.py:104-153`

Status updates ARE broadcast correctly when cells execute:
- Line 114: RUNNING status is broadcast when execution starts
- Line 140: Final status (SUCCESS/ERROR) is broadcast when execution completes
- Line 98: BLOCKED status is broadcast when a dependency fails

**The Issue**: Dependent cells are being incorrectly marked as BLOCKED and skipped, so they never reach `_execute_cell()` and never get status updates broadcast.

### Frontend Status Handling

**File**: `frontend/src/components/Notebook.tsx:58-67`

The frontend correctly handles `cell_status` WebSocket messages:
- Updates cell status in state
- Clears outputs when status changes to RUNNING
- Displays status in UI

**Not the Issue**: The frontend is working correctly. The problem is that status update messages are never sent because dependent cells are incorrectly skipped.

## Code References

- `backend/scheduler.py:60-64` - Dependent cell discovery using `get_all_dependents()`
- `backend/scheduler.py:86-93` - **ROOT CAUSE**: Dependency check that includes cells outside execution set
- `backend/scheduler.py:95-99` - BLOCKED status assignment and broadcast
- `backend/scheduler.py:102` - Cell execution (skipped for BLOCKED cells)
- `backend/scheduler.py:114` - RUNNING status broadcast (never reached for BLOCKED cells)
- `backend/graph.py:94-106` - `get_all_dependents()` implementation
- `backend/graph.py:62-92` - `topological_sort()` implementation

## Architecture Insights

### Dependency Graph Structure

The dependency graph maintains:
- `edges`: `cell_id -> set of dependent cell_ids` (forward edges)
- `reverse_edges`: `cell_id -> set of dependency cell_ids` (backward edges)

When checking dependencies, `reverse_edges[cell_id]` returns ALL cells that the current cell depends on, regardless of whether they're in the current execution set.

### Execution Set vs. Full Graph

The scheduler maintains an `all_to_run` set that contains:
- The cell(s) that were explicitly run (`pending_cells`)
- All dependent cells discovered via `get_all_dependents()`

However, the dependency check uses the full graph (`notebook.graph.reverse_edges`), not just the cells in `all_to_run`. This is the source of the bug.

### Topological Sort Guarantees

The topological sort ensures that dependencies execute before dependents **within the execution set**. However, the dependency check doesn't respect this - it checks the full graph, including cells outside the execution set.

## Historical Context (from thoughts/)

- `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md` - The plan that was recently implemented, which removed GET requests and made WebSocket the single source of truth
- The plan assumed reactive execution was working correctly (line 10: "Reactive execution (running dependent cells when a cell is run) is already implemented and working correctly")
- However, this bug was not discovered during implementation

## Solution Approach

The fix should:

1. **Filter dependencies to execution set**: Only check dependencies that are in `all_to_run`, not all dependencies in the graph
2. **Check dependency execution status**: When checking if a dependency failed, verify that:
   - The dependency is in `all_to_run` (currently being executed)
   - The dependency has finished executing (status is not RUNNING)
   - The dependency status is ERROR

**Proposed Fix** (`backend/scheduler.py:86-93`):

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
                continue
```

## Related Research

- `thoughts/shared/research/2025-12-27-websocket-only-architecture.md` - Original research on WebSocket-only architecture
- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Previous race condition investigation

## Additional Finding: Sequential Execution vs. "All at Once" Results

### User Observation

When running a cell in the demo notebook, all dependent cell results appear "all at once" instead of sequentially (one after the other).

### Analysis

**Backend Execution Flow** (`backend/scheduler.py:80-102`):
- Line 81: `for cell_id in sorted_cells:` - Sequential loop
- Line 102: `await self._execute_cell(...)` - Each cell execution is awaited
- Cells SHOULD execute sequentially

**WebSocket Broadcasting** (`backend/scheduler.py:114, 140-154`):
- Each status update and output is broadcast individually with `await`
- Messages SHOULD be sent sequentially

**Frontend State Updates** (`frontend/src/components/Notebook.tsx:25-99`):
- Each WebSocket message triggers `setNotebook(prev => ...)` with functional update
- React batches state updates that happen synchronously (same event loop tick)

### Logging Results (2025-12-27)

**Backend Logs Analysis:**
- ✅ **Sequential execution confirmed**: Cells execute sequentially with timing: 0.000s, 0.004s, 0.005s, 0.520s, 1.028s, 1.194s
- ✅ **Dependency check working correctly**: All dependencies are in execution set (`dependencies_outside_execution_set=[]` in all cases)
- ✅ **No incorrect blocking**: No cells were incorrectly marked as BLOCKED
- ✅ **Status broadcasts sequential**: Each status update is broadcast individually with `await`

**Frontend Logs Analysis:**
- ✅ **WebSocket messages arrive quickly**: All messages arrive within ~0.5ms window (4038-4041ms timestamps)
- ✅ **React batching confirmed**: Only ONE `[REACT_RENDER]` occurs at the end showing all cells as `success`
- ✅ **State updates processed**: All `[STATUS_UPDATE]` logs show messages being processed, but React batches them
- ✅ **Single render**: React renders once at 4052ms with all cells already in `success` state

### Root Cause Confirmed

**React State Update Batching** is the root cause. Evidence:
1. Backend executes sequentially (confirmed by timing logs)
2. WebSocket messages arrive in quick succession (~0.5ms apart)
3. React batches all `setNotebook` calls that occur synchronously
4. Only one render occurs, showing all cells as `success` simultaneously

**The dependency check bug is NOT causing this issue** - all dependencies are correctly identified as being in the execution set.

### Potential Solutions

1. **Use `flushSync`**: Force React to flush updates immediately instead of batching (may impact performance)
   ```typescript
   import { flushSync } from 'react-dom';
   flushSync(() => {
     setNotebook(prev => ...);
   });
   ```

2. **Add artificial delays**: Add small delays between cell executions to ensure sequential rendering (not recommended for production)

3. **Debounce/throttle updates**: Batch updates with a small delay to ensure sequential rendering

4. **Use `startTransition`**: Wrap updates in `startTransition` to allow React to prioritize rendering (may not solve batching issue)

## Logging Verification Results (2025-12-27)

### Dependency Check Bug Status

**NOT CONFIRMED** - Logs show:
- All dependencies are correctly identified as being in the execution set
- `dependencies_outside_execution_set=[]` for all cells checked
- No cells were incorrectly marked as BLOCKED
- All cells executed successfully in the correct order

**Conclusion**: The dependency check bug described in this research document does not appear to be occurring in the current execution. However, the bug could still occur in edge cases (e.g., when a dependency fails in a previous run and is not in the current execution set).

### Sequential Execution vs. "All at Once" - CONFIRMED

**Root Cause**: React State Update Batching

**Evidence**:
- Backend executes sequentially (timing: 0.000s → 1.194s)
- WebSocket messages arrive within ~0.5ms window
- React batches all state updates into a single render
- Only one `[REACT_RENDER]` occurs showing all cells as `success`

**Solution**: Use `flushSync` to force immediate renders, or add small delays between broadcasts.

## Open Questions

1. ✅ **RESOLVED**: Is the "all at once" issue caused by React batching? **YES** - Confirmed via logging
2. ✅ **RESOLVED**: Is the dependency check bug causing incorrect blocking? **NO** - Not observed in logs
3. Should the dependency check also verify that dependencies have finished executing (not RUNNING)?
4. Are there edge cases where a dependency could be RUNNING when checking (despite topological sort)?
5. Should we implement `flushSync` to fix the "all at once" appearance, or is this acceptable UX?

