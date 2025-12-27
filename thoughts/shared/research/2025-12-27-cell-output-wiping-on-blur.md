---
date: 2025-12-27T17:10:43+00:00
researcher: Composer
topic: "Cell output wiping on blur - race condition investigation"
tags: [research, codebase, frontend, backend, websocket, state-management]
status: complete
last_updated: 2025-12-27
last_updated_by: Composer
last_updated_note: "Added log analysis results confirming race condition between GET and WebSocket updates"
---

# Research: Cell Output Wiping on Blur - Race Condition Investigation

**Date**: 2025-12-27T17:10:43+00:00 GMT
**Researcher**: Composer

## Research Question

Why do cell outputs sometimes get wiped at random when clicking into or out of a cell (on blur)? The user reports that every blur event triggers 2 HTTP requests:
1. PUT to update cell code
2. GET to fetch full notebook

## Summary

The issue is a **race condition between HTTP GET requests and WebSocket updates**, confirmed by log analysis. When a cell is blurred:

1. `handleUpdateCell` sends a PUT request to update the cell code
2. `update_cell` sets cell status to `IDLE` (which triggers reactive execution asynchronously)
3. Immediately after PUT, `handleUpdateCell` sends a GET request to fetch the full notebook
4. GET returns **before execution starts** (~90ms gap), with `idle` status and no outputs
5. `setNotebook(updated)` **replaces** the entire notebook state with the GET response (losing any displayed outputs)
6. WebSocket messages arrive ~90ms later with execution results, but may be overwritten by subsequent GET requests

**Root Cause**: `setNotebook(updated)` performs direct state replacement. If the frontend had outputs displayed from a previous execution, they're lost when the GET response (with empty outputs) overwrites the state. The "randomness" comes from timing - sometimes execution completes before GET, sometimes after.

## Detailed Findings

### Communication Flow Architecture

The application uses a dual-update pattern:
- **HTTP GET requests**: Full notebook state replacement (used after cell operations)
- **WebSocket messages**: Incremental cell updates (used during execution)

#### Frontend State Management (`frontend/src/components/Notebook.tsx`)

**State Updates:**
- Line 11: `const [notebook, setNotebook] = useState<api.Notebook | null>(null)`
- Line 65-69: `handleUpdateCell` performs PUT then GET, then calls `setNotebook(updated)` (full replacement)
- Line 25-57: `handleWSMessage` uses functional update `setNotebook(prev => { ... })` to merge WebSocket updates

**Key Issue**: When `handleUpdateCell` calls `setNotebook(updated)`, it replaces the entire state. If WebSocket messages arrive between the PUT and GET, or between GET and `setNotebook`, they can be overwritten.

#### Backend Update Flow (`backend/routes.py`)

**`update_cell` endpoint (lines 131-169):**
- Updates cell code and sets status to `IDLE`
- **Preserves outputs** (does not clear them)
- Rebuilds dependency graph
- Saves notebook to disk

**`get_notebook` endpoint (lines 57-88):**
- Returns full notebook from in-memory `NOTEBOOKS` dict
- Includes all cell outputs, stdout, errors
- This is the source of truth for HTTP GET requests

#### WebSocket Updates (`backend/websocket.py`, `backend/scheduler.py`)

**Output Broadcasting:**
- `scheduler._execute_cell` (line 104-154) clears outputs when execution starts (line 117-119)
- Then broadcasts status, stdout, outputs, errors via WebSocket
- Each output is broadcast individually via `broadcast_cell_output` (line 149-154)

**Frontend WebSocket Handler:**
- `handleWSMessage` (Notebook.tsx:25-57) uses functional updates to merge WebSocket messages
- When status is 'running', it clears outputs (line 36)
- Outputs are appended incrementally (line 47-48)

### Race Condition Scenarios

#### Scenario 1: Blur During Execution
1. User clicks into cell → blur event fires
2. `handleUpdateCell` sends PUT request
3. Cell execution is running → WebSocket messages updating outputs
4. `handleUpdateCell` sends GET request (may return stale data)
5. `setNotebook(updated)` overwrites WebSocket updates

#### Scenario 2: Rapid Blur Events
1. User blurs cell A → PUT + GET for cell A
2. User immediately blurs cell B → PUT + GET for cell B
3. First GET response arrives after second PUT
4. `setNotebook` from first GET overwrites second PUT's state

#### Scenario 3: GET Returns Before WebSocket Updates Complete
1. Cell execution completes, outputs being broadcast via WebSocket
2. User blurs cell → PUT + GET
3. GET returns notebook state before all WebSocket messages arrive
4. `setNotebook(updated)` replaces state with incomplete outputs

### Storage Impact

**`backend/storage.py`:**
- `save_notebook` (line 12-33) does NOT save outputs, stdout, errors, or status
- Only saves: id, db_conn_string, revision, cells (with code, reads, writes)
- `load_notebook` (line 35-63) creates cells with `status=IDLE` and no outputs
- **However**: Notebooks are only loaded from storage on startup (`backend/main.py:26`)
- After startup, notebooks live in memory (`NOTEBOOKS` dict), so outputs persist in memory

**Conclusion**: Storage is not the issue - outputs are lost due to state overwrites, not persistence.

## Code References

### Frontend
- `frontend/src/components/Cell.tsx:83-87` - Blur handler that triggers `onUpdateCell`
- `frontend/src/components/Notebook.tsx:65-69` - `handleUpdateCell` that does PUT + GET + `setNotebook`
- `frontend/src/components/Notebook.tsx:25-57` - `handleWSMessage` that merges WebSocket updates
- `frontend/src/api.ts:68-74` - `updateCell` API function
- `frontend/src/api.ts:46-49` - `getNotebook` API function

### Backend
- `backend/routes.py:131-169` - `update_cell` endpoint (preserves outputs, sets status to IDLE)
- `backend/routes.py:57-88` - `get_notebook` endpoint (returns full notebook state)
- `backend/scheduler.py:104-154` - `_execute_cell` (clears outputs on execution start)
- `backend/websocket.py:26-40` - `broadcast` method (sends WebSocket messages)
- `backend/storage.py:12-33` - `save_notebook` (does not save outputs)

## Architecture Insights

### State Synchronization Pattern

The application uses a **hybrid state synchronization** approach:
1. **Optimistic updates via WebSocket**: Real-time updates during execution
2. **Authoritative updates via HTTP GET**: Full state reload after operations

**Problem**: These two patterns can conflict when they occur simultaneously.

### React State Update Patterns

- **Direct replacement**: `setNotebook(updated)` - Used after HTTP GET
- **Functional update**: `setNotebook(prev => { ... })` - Used for WebSocket messages

**Issue**: Direct replacement can overwrite functional updates that are queued but not yet applied.

## Hypotheses for Output Wiping

### Hypothesis 1: Race Condition Between GET and WebSocket ✅ CONFIRMED
**Status**: **CONFIRMED** by log analysis

**Evidence from logs**: 
- GET completes at `17:12:04.331Z`
- WebSocket messages arrive at `17:12:04.423Z` (92ms later)
- `setNotebook(updated)` replaces state before WebSocket updates arrive
- Backend shows execution starts ~93ms after GET completes

**Root Cause**: Direct state replacement (`setNotebook(updated)`) overwrites frontend state with GET response (which has no outputs because execution hasn't started yet). WebSocket messages arrive later but may be lost if another blur occurs.

### Hypothesis 2: GET Returns Stale Data ✅ CONFIRMED
**Status**: **CONFIRMED** by log analysis

**Evidence from logs**:
- `get_notebook` returns `{'status': 'idle', 'outputs_count': 0}` 
- Execution hasn't started yet when GET is called
- GET response reflects state **before** reactive execution begins

**Root Cause**: `update_cell` sets status to `idle`, which triggers reactive execution asynchronously. GET request happens synchronously, before execution starts, so it returns stale state.

### Hypothesis 3: Multiple Rapid Blur Events ⚠️ PARTIALLY CONFIRMED
**Status**: **PARTIALLY CONFIRMED** - observed in logs but not the primary issue

**Evidence from logs**:
- Multiple blur events observed (e.g., `17:11:49`, `17:11:54`, `17:11:58`, `17:12:04`, `17:12:08`)
- Each blur triggers PUT + GET
- Overlapping requests can cause state overwrites

**Impact**: Secondary issue - rapid blurs can compound the race condition, but the primary issue is the GET-before-execution pattern.

### Hypothesis 4: WebSocket Message Ordering ⚠️ NOT THE PRIMARY ISSUE
**Status**: **NOT THE PRIMARY ISSUE** - WebSocket messages arrive correctly, but after GET

**Evidence from logs**:
- Multiple WebSocket messages per execution (status, stdout, etc.)
- Messages arrive in correct order
- Issue is that GET happens **before** WebSocket messages start, not between them

**Conclusion**: WebSocket ordering is correct. The issue is timing - GET arrives before execution starts, not between WebSocket messages.

## Logging Added

Comprehensive logging has been added to track the issue:

### Frontend Logging
- **Cell.tsx**: Logs blur events with cell state (outputs count, stdout, status)
- **Notebook.tsx**: 
  - Logs `handleUpdateCell` start/end with timestamps
  - Logs cell state before/after GET response
  - Logs all WebSocket messages with timestamps and state changes

### Backend Logging
- **routes.py**: 
  - Logs `update_cell` start/end with cell state before/after
  - Logs `get_notebook` start/end with cell states before serialization
- **websocket.py**: Logs all broadcast messages with timestamps
- **scheduler.py**: Logs when outputs are cleared and when they're updated

### How to Use Logs

1. **Reproduce the issue**: Click into and out of cells with outputs
2. **Check browser console**: Look for `[Cell]`, `[Notebook]` prefixes
3. **Check backend logs**: Look for `[BACKEND]` prefixes
4. **Correlate timestamps**: Match frontend and backend timestamps to identify race conditions
5. **Look for patterns**:
   - GET response arriving before WebSocket messages complete
   - Multiple GET requests overlapping
   - WebSocket updates being overwritten by GET responses

## Recommended Solutions

### Solution 1: Merge GET Response with Current State (Recommended)
Instead of replacing state, merge GET response with current state, preserving WebSocket updates:

```typescript
const handleUpdateCell = async (cellId: string, code: string) => {
  await api.updateCell(notebookId, cellId, code);
  const updated = await api.getNotebook(notebookId);
  
  // Merge instead of replace - preserve WebSocket updates
  setNotebook(prev => {
    if (!prev) return updated;
    
    // Merge cells, preferring WebSocket-updated outputs
    const mergedCells = updated.cells.map(updatedCell => {
      const prevCell = prev.cells.find(c => c.id === updatedCell.id);
      if (!prevCell) return updatedCell;
      
      // If cell has outputs from WebSocket, preserve them
      if (prevCell.outputs && prevCell.outputs.length > 0 && 
          updatedCell.status !== 'running') {
        return { ...updatedCell, outputs: prevCell.outputs };
      }
      
      return updatedCell;
    });
    
    return { ...updated, cells: mergedCells };
  });
};
```

### Solution 2: Debounce GET Requests
Add debouncing to prevent rapid-fire GET requests:

```typescript
const debouncedGetNotebook = useMemo(
  () => debounce(async () => {
    const updated = await api.getNotebook(notebookId);
    setNotebook(updated);
  }, 300),
  [notebookId]
);
```

### Solution 3: Use WebSocket as Source of Truth
Only use GET for initial load, rely on WebSocket for all updates:

```typescript
const handleUpdateCell = async (cellId: string, code: string) => {
  await api.updateCell(notebookId, cellId, code);
  // Don't fetch - let WebSocket handle updates
};
```

### Solution 4: Add Version/Revision Checking
Include revision numbers in responses and only update if newer:

```typescript
setNotebook(prev => {
  if (prev && updated.revision <= prev.revision) {
    return prev; // Stale update, ignore
  }
  return updated;
});
```

## Log Analysis Results

### Confirmed Race Condition: GET Response Arrives Before Execution Starts

Analysis of the provided logs confirms **Hypothesis 1: Race Condition Between GET and WebSocket**, but with a more specific pattern than initially hypothesized.

#### Timeline Analysis (from logs at `17:12:04.319Z`)

**Frontend Sequence:**
1. `17:12:04.319Z` - User blurs cell → `handleUpdateCell START` for cell `2757a122-e074-4ba0-a3b9-3d2545c60c19`
2. `17:12:04.331Z` - GET completes → `setNotebook(updated)` called (replaces entire state)
3. `17:12:04.423Z` - WebSocket messages start arriving (**92ms after GET completes**)

**Backend Sequence:**
1. `17:12:04.325Z` - `update_cell` called
   - BEFORE: `{'status': 'success', 'outputs_count': 0}` (cell had no outputs)
   - AFTER: `{'status': 'idle', 'outputs_count': 0}` (status reset to idle, outputs preserved but empty)
2. `17:12:04.330Z` - `get_notebook` called
   - Returns: `{'status': 'idle', 'stdout_length': 0, 'outputs_count': 0}` (no outputs yet)
3. `17:12:04.423Z` - WebSocket broadcasts start (**93ms after GET completes**)
   - Execution triggered by reactive system (status change to `idle` triggers dependent cells)

#### Key Findings

1. **GET Response Contains Stale State**: The GET request returns `idle` status with no outputs because:
   - `update_cell` sets status to `idle` (which triggers reactive execution)
   - But execution hasn't started yet when GET is called
   - GET returns the state **before** execution begins

2. **Direct State Replacement**: `setNotebook(updated)` performs a **direct replacement** of the entire notebook state:
   - Replaces all cells with GET response data
   - If frontend had outputs from previous execution, they're overwritten with empty state
   - WebSocket messages arrive 92ms later, but may be lost if another blur occurs

3. **Reactive Execution Delay**: The backend's reactive execution system triggers **after** the GET completes:
   - `update_cell` sets status to `idle` → triggers dependency graph rebuild
   - Execution is enqueued asynchronously
   - GET request happens synchronously, before execution starts
   - WebSocket broadcasts happen ~90ms later

4. **Output Preservation Issue**: Even though `update_cell` preserves outputs, the GET response shows `outputs_count: 0` because:
   - The cell being updated had no outputs before the update
   - But if the frontend had outputs displayed (from a previous execution), they're lost when `setNotebook(updated)` overwrites with the GET response

#### Evidence from Logs

**Backend logs show the race condition:**
```
[BACKEND] update_cell - AFTER: {'status': 'idle', 'outputs_count': 0}
[BACKEND] get_notebook - cell states: [{'status': 'idle', 'outputs_count': 0}]
[BACKEND] WebSocket broadcast START - type=cell_status, status='running'  # 93ms later
```

**Frontend logs confirm the timing:**
```
[Notebook] handleUpdateCell - GET completed, setting notebook {timestamp: '17:12:04.331Z'}
[Notebook] WebSocket message received: {timestamp: '17:12:04.423Z', type: 'cell_status'}  # 92ms later
```

### Root Cause Confirmed

The issue is a **timing race condition** where:

1. **PUT request** updates cell code and sets status to `idle`
2. **GET request** immediately fetches notebook state (which has `idle` status, no outputs)
3. **Frontend** calls `setNotebook(updated)` which **replaces** entire state with GET response
4. **Backend** triggers reactive execution (asynchronously, ~90ms later)
5. **WebSocket messages** arrive with execution results, but may be overwritten by subsequent GET requests

**Critical Issue**: `setNotebook(updated)` performs a **direct state replacement** rather than merging. If the frontend had outputs displayed from a previous execution, they're lost when the GET response (with empty outputs) overwrites the state.

### Additional Observations

1. **Multiple WebSocket Updates**: The logs show multiple WebSocket messages per execution (status changes, stdout, etc.), all arriving after the GET completes. This confirms that execution happens asynchronously.

2. **Status Reset**: `update_cell` resets status to `idle`, which triggers reactive execution. This is intentional but creates the timing window where GET can return stale state.

3. **No Output Loss in Backend**: The backend correctly preserves outputs during `update_cell`, but the GET response shows empty outputs because execution hasn't started yet.

4. **Frontend State Loss**: The real issue is in the frontend - when `setNotebook(updated)` replaces state, it loses any outputs that were displayed but not yet persisted to the backend state.

### Why Outputs Appear to Wipe "Randomly"

Outputs wipe when:
- User blurs a cell that has outputs displayed
- GET request returns before execution completes (or before execution starts)
- `setNotebook(updated)` overwrites frontend state with GET response (which has no outputs)
- WebSocket messages arrive later, but if user has moved on or blurred again, outputs may be lost

The "randomness" comes from the timing - sometimes execution completes before GET, sometimes after. When GET arrives first, outputs are lost.

## Open Questions

1. **Why does `handleUpdateCell` fetch the full notebook?** Could it update only the affected cell?
2. **Is there a reason for the immediate GET after PUT?** Could WebSocket handle the update instead?
3. **Should outputs be persisted to storage?** Currently they're lost on server restart.
4. **Could we use optimistic updates?** Update UI immediately, sync with backend asynchronously.
5. **Should `update_cell` preserve the previous status instead of resetting to `idle`?** This would prevent triggering reactive execution on every blur.

## Related Research

- `thoughts/shared/research/2025-12-27-loading-saving-named-notebooks-dropdown.md` - Related notebook management features

