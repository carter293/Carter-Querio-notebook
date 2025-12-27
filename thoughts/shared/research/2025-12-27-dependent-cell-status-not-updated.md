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

## Open Questions

1. Should the dependency check also verify that dependencies have finished executing (not RUNNING)?
2. Are there edge cases where a dependency could be RUNNING when checking (despite topological sort)?
3. Should we add logging to track when cells are incorrectly marked as BLOCKED?

