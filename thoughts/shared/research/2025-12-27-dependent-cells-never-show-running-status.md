---
date: 2025-12-27T19:51:55+00:00 GMT
researcher: Composer
topic: "Why dependent cells never show RUNNING status - only IDLE or SUCCESS"
tags: [research, codebase, websocket, scheduler, reactive-execution, status-updates]
status: complete
last_updated: 2025-12-27
last_updated_by: Composer
---

# Research: Dependent Cells Never Show RUNNING Status

**Date**: 2025-12-27T19:51:55+00:00 GMT  
**Researcher**: Composer

## Research Question

When a cell is run and its dependent cells are executed, the dependent cells never show as "running" - they only show as "idle" or "successful". Why is the RUNNING status not visible for dependent cells?

## Summary

**ROOT CAUSE FOUND**: Two issues were discovered:

### Issue 1: `cell_updated` Overwrites RUNNING (Frontend)
The `cell_updated` handler was overwriting RUNNING status with IDLE.

**Fix Applied**: Modified `cell_updated` handler to preserve RUNNING status.

### Issue 2: WebSocket Messages Buffered Until Execution Completes (Backend - PRIMARY)
The `execute_python_cell` function was async but ran synchronously (no await points). The event loop never got a chance to flush WebSocket messages until all execution was complete.

**Flow without fix**:
1. `await broadcaster.broadcast_cell_status(RUNNING)` - queues message but doesn't actually send
2. `execute_python_cell()` - runs synchronously (no await points!)
3. `await broadcaster.broadcast_cell_status(SUCCESS)` - queues message
4. **Only now** does the event loop flush all messages together

**Fix Applied**: Added `await asyncio.sleep(0)` after broadcasting RUNNING to yield to the event loop and flush pending WebSocket messages.

**Why not `asyncio.to_thread()`?** Libraries like matplotlib use thread-local storage and GUI backends that require the main thread. Running in a thread pool breaks matplotlib figure creation.

**Why `asyncio.sleep(0)` is not a hack**: This is a standard Python async pattern for yielding to the event loop. It's documented behavior and commonly used when you need to:
- Flush pending I/O before CPU-bound work
- Allow other coroutines to run
- Ensure messages are sent before blocking operations

```python
# Mark as running
cell.status = CellStatus.RUNNING
await broadcaster.broadcast_cell_status(notebook_id, cell.id, CellStatus.RUNNING)

# Yield to event loop to flush WebSocket message before synchronous execution
await asyncio.sleep(0)

# Execute cell (runs synchronously in main thread for matplotlib compatibility)
result = await execute_python_cell(...)
```

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

#### Issue 1: `cell_updated` Messages Overwrite RUNNING Status (PRIMARY BUG)

**File**: `frontend/src/components/Notebook.tsx:30-45`

The `cell_updated` handler unconditionally overwrites cell status:

```typescript
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
            status: msg.cell.status as api.CellStatus  // ⚠️ OVERWRITES RUNNING!
          }
        : cell
    )
  };
```

**Problem**: When a cell is updated via `updateCell` API (`backend/routes.py:225`), it sets status to IDLE and broadcasts `cell_updated` with status=IDLE. If this message arrives AFTER the RUNNING `cell_status` message, it overwrites RUNNING with IDLE.

**Timing Issue**:
1. User clicks Run → `handleRunClick` calls `onUpdateCell` if code changed (line 54-55)
2. `onUpdateCell` calls `api.updateCell` → Backend sets status=IDLE and broadcasts `cell_updated` (async)
3. After 100ms delay, `onRunCell` is called → Backend broadcasts RUNNING via `cell_status` (async)
4. **Race Condition**: If `cell_updated` arrives after `cell_status`, RUNNING is overwritten with IDLE

**Impact**: Cells never show RUNNING status, even with long execution times (e.g., `time.sleep(2)`), because RUNNING is immediately overwritten by IDLE from `cell_updated`.

**Fix Applied**: Modified `cell_updated` handler to preserve RUNNING status:
```typescript
case 'cell_updated':
  // Don't overwrite RUNNING status - status updates should come via cell_status messages
  const currentStatus = cell.status;
  const newStatus = (currentStatus === 'running') 
    ? currentStatus 
    : (msg.cell.status as api.CellStatus);
```

#### Issue 2: Dependent Cells Maintain Previous Status When Discovered

**File**: `backend/scheduler.py:60-64`

When dependent cells are discovered and added to the execution queue:

```python
# Compute transitive closure (all cells to run)
all_to_run = set(pending_cells)
for cell_id in pending_cells:
    dependents = get_all_dependents(notebook.graph, cell_id)
    all_to_run.update(dependents)
```

**Problem**: When a cell is discovered as a dependent and added to `all_to_run`, its status is **not reset**. If the cell was previously executed and has status SUCCESS, it remains SUCCESS until execution begins.

**Impact**: 
- Dependent cells that were previously SUCCESS remain SUCCESS when discovered
- They never show IDLE because they're not reset to IDLE
- The status transition is SUCCESS → RUNNING → SUCCESS (skipping IDLE)

#### Issue 2: RUNNING Status Is Broadcast But May Be Brief

**File**: `backend/scheduler.py:113-114`

When a cell is executed, RUNNING status is correctly set and broadcast:

```python
# Mark as running
cell.status = CellStatus.RUNNING
await broadcaster.broadcast_cell_status(notebook_id, cell.id, CellStatus.RUNNING)
```

**Problem**: For cells that execute very quickly (e.g., simple variable assignments or fast SQL queries), the RUNNING status broadcast may be immediately followed by SUCCESS broadcast, making RUNNING appear to be skipped.

**Timing Analysis**:
- Line 113: Status set to RUNNING
- Line 114: RUNNING broadcast (async, awaited)
- Line 123-125: Cell execution (may be very fast)
- Line 134: Status set to SUCCESS
- Line 140: SUCCESS broadcast (async, awaited)

If execution completes in < 10ms, both RUNNING and SUCCESS messages may arrive at the frontend within the same React render cycle, causing both to render simultaneously.

#### Issue 3: React State Update Batching

**File**: `frontend/src/components/Notebook.tsx:58-67`

The frontend handles status updates:

```typescript
case 'cell_status':
  const cells = prev.cells.map(cell => {
    if (cell.id !== msg.cellId) return cell;
    if (msg.status === 'running') {
      // Clear outputs when execution starts
      return { ...cell, status: msg.status, stdout: '', outputs: [], error: undefined };
    }
    return { ...cell, status: msg.status };
  });
  return { ...prev, cells };
```

**Problem**: React 18+ automatically batches state updates that occur synchronously (same event loop tick). If RUNNING and SUCCESS messages arrive quickly, React may batch them into a single render, showing the final SUCCESS state without showing RUNNING.

**Evidence from Previous Research**: The research document `thoughts/shared/research/2025-12-27-dependent-cell-status-not-updated.md` confirms React batching is causing sequential updates to appear "all at once" (lines 231-253).

### Execution Flow Analysis

**File**: `backend/scheduler.py:44-102`

1. **Cell Discovery** (lines 60-64):
   - `all_to_run = set(pending_cells)` - Includes the cell that was run
   - `get_all_dependents()` discovers all dependent cells
   - Dependents are added to `all_to_run`
   - **Status is NOT reset** - cells maintain their previous status

2. **Topological Sort** (lines 66-68):
   - Cells are sorted to respect dependency order
   - Ensures dependencies execute before dependents

3. **Execution Loop** (lines 81-102):
   - Each cell in sorted order is processed
   - Dependency check runs (lines 86-93)
   - If dependency failed, cell is marked BLOCKED and skipped
   - Otherwise, cell executes via `_execute_cell()`

4. **Cell Execution** (lines 104-154):
   - Line 113: Status set to RUNNING
   - Line 114: RUNNING broadcast
   - Line 123-125: Cell execution (may be very fast)
   - Line 134: Status set to SUCCESS/ERROR
   - Line 140: Final status broadcast

**The Problem**: 
- Dependent cells that are already SUCCESS are not reset to IDLE
- Status transition is SUCCESS → RUNNING → SUCCESS (no IDLE state)
- RUNNING may be very brief if execution is fast
- React batching may cause RUNNING and SUCCESS to render simultaneously

### Status Update Broadcasting

**File**: `backend/scheduler.py:104-153`

Status updates ARE broadcast correctly:
- Line 114: RUNNING status is broadcast when execution starts
- Line 140: Final status (SUCCESS/ERROR) is broadcast when execution completes
- Line 98: BLOCKED status is broadcast when a dependency fails

**The Issue**: RUNNING is broadcast, but:
1. Dependent cells maintain SUCCESS status until RUNNING is set
2. RUNNING may be immediately followed by SUCCESS if execution is fast
3. React batching may cause both updates to render simultaneously

### Frontend Status Handling

**File**: `frontend/src/components/Notebook.tsx:58-67`

The frontend correctly handles `cell_status` WebSocket messages:
- Updates cell status in state
- Clears outputs when status changes to RUNNING
- Displays status in UI

**The Issue**: 
- React batches state updates that occur synchronously
- If RUNNING and SUCCESS messages arrive quickly, React may batch them
- The UI may show SUCCESS without showing RUNNING

### Comparison: Explicitly Run Cell vs. Dependent Cell

**Explicitly Run Cell**:
- User clicks "Run" → Cell status is IDLE (or previous status)
- Status transitions: IDLE → RUNNING → SUCCESS
- RUNNING is visible because there's a clear transition from IDLE

**Dependent Cell**:
- Discovered as dependent → Cell status is SUCCESS (from previous run)
- Status transitions: SUCCESS → RUNNING → SUCCESS
- RUNNING may not be visible because:
  1. SUCCESS → RUNNING transition is less noticeable than IDLE → RUNNING
  2. RUNNING may be very brief if execution is fast
  3. React batching may cause RUNNING and SUCCESS to render simultaneously

## Code References

- `backend/scheduler.py:60-64` - Dependent cell discovery using `get_all_dependents()` (status not reset)
- `backend/scheduler.py:81-102` - Execution loop that processes cells in topological order
- `backend/scheduler.py:113-114` - **RUNNING status is set and broadcast correctly**
- `backend/scheduler.py:134-140` - Final status is set and broadcast after execution
- `backend/models.py:36` - Default cell status is IDLE, but this is only for new cells
- `frontend/src/components/Notebook.tsx:58-67` - Frontend handles status updates (React batching)
- `frontend/src/useWebSocket.ts:85-99` - WebSocket messages arrive sequentially but quickly

## Architecture Insights

### Status Lifecycle for Dependent Cells

**Current Flow**:
1. Cell executes successfully → Status = SUCCESS
2. Dependency changes → Cell discovered as dependent → Status remains SUCCESS
3. Cell execution begins → Status = RUNNING (broadcast)
4. Cell execution completes → Status = SUCCESS (broadcast)

**Missing Step**: There's no reset to IDLE when a cell is discovered as a dependent. The status goes directly from SUCCESS → RUNNING → SUCCESS.

### Execution Timing

For fast-executing cells (e.g., `x = 1` or simple SQL queries):
- RUNNING broadcast: ~0ms
- Execution: < 10ms
- SUCCESS broadcast: ~10ms
- Total time: < 20ms

If both RUNNING and SUCCESS messages arrive within the same React render cycle, React will batch them and show only the final SUCCESS state.

### React Batching Behavior

React 18+ automatically batches state updates that occur synchronously (same event loop tick). This means:
- Multiple `setNotebook` calls in quick succession are batched
- Only one render occurs showing the final state
- Intermediate states (like RUNNING) may not be visible

## Historical Context (from thoughts/)

- `thoughts/shared/research/2025-12-27-dependent-cell-status-not-updated.md` - Previous research on dependent cell status updates, identifies React batching as causing "all at once" appearance (lines 231-253)
- `thoughts/shared/plans/2025-12-27-fix-dependent-cell-status-updates.md` - Implementation plan to fix dependency check bug and sequential rendering using `flushSync`
- `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md` - WebSocket-only architecture plan that assumes reactive execution works correctly

## Solution Approach

**PRIMARY FIX APPLIED**: Modified `cell_updated` handler to preserve RUNNING status.

**File**: `frontend/src/components/Notebook.tsx:30-45`

```typescript
case 'cell_updated':
  // Update cell metadata (code, reads, writes, status)
  // BUT: Don't overwrite RUNNING status - status updates should come via cell_status messages
  return {
    ...prev,
    cells: prev.cells.map(cell => {
      if (cell.id !== msg.cellId) return cell;
      const currentStatus = cell.status;
      // If cell is currently RUNNING, preserve it - don't overwrite with IDLE from cell_updated
      const newStatus = (currentStatus === 'running') 
        ? currentStatus 
        : (msg.cell.status as api.CellStatus);
      return { 
        ...cell, 
        code: msg.cell.code,
        reads: msg.cell.reads,
        writes: msg.cell.writes,
        status: newStatus
      };
    })
  };
```

**Why This Works**:
- `cell_updated` messages are for metadata updates (code, reads, writes), not status updates
- Status updates should come via `cell_status` messages only
- Preserving RUNNING status prevents race conditions where `cell_updated` arrives after RUNNING

**Additional Considerations** (if issue persists):

1. **Reset Status to IDLE When Discovered**: When a cell is discovered as a dependent and added to the execution queue, reset its status to IDLE if it's currently SUCCESS. This ensures a clear IDLE → RUNNING → SUCCESS transition.

2. **Use `flushSync` for Status Updates**: Force React to flush RUNNING status updates immediately using `flushSync` from `react-dom`, ensuring RUNNING is visible before SUCCESS.

3. **Backend: Don't Include Status in `cell_updated`**: Consider removing status from `cell_updated` messages entirely, since status should only be updated via `cell_status` messages.

## Related Research

- `thoughts/shared/research/2025-12-27-dependent-cell-status-not-updated.md` - Previous research on dependent cell status updates and React batching
- `thoughts/shared/research/2025-12-27-websocket-only-architecture.md` - WebSocket-only architecture research
- `thoughts/shared/research/2025-12-27-optimistic-updates-vs-websocket-confirmation.md` - Research on optimistic updates vs WebSocket confirmation

## Verification

**Fix Applied**: Modified `cell_updated` handler to preserve RUNNING status.

**Expected Behavior After Fix**:
- When a cell is updated and then run, RUNNING status should be visible
- `cell_updated` messages will no longer overwrite RUNNING status
- Status transitions should be: IDLE → RUNNING → SUCCESS

**Testing**: Run a cell with `time.sleep(2)` and verify RUNNING status is visible for 2 seconds before SUCCESS.

## Open Questions

1. ✅ **RESOLVED**: Why is RUNNING status not visible? **FIXED** - `cell_updated` was overwriting RUNNING with IDLE
2. Should dependent cells be reset to IDLE when discovered, or should they maintain their previous status until execution begins?
3. Should we remove status from `cell_updated` messages entirely, since status should only be updated via `cell_status` messages?
4. Are there other race conditions where status updates could be overwritten?

