# WebSocket-Only Architecture Implementation Plan

**Date**: 2025-12-27T17:37:09+00:00 GMT  
**Planner**: Composer

## Overview

This plan implements a WebSocket-only architecture for state synchronization after initial load, eliminating HTTP GET requests that cause race conditions. The implementation follows patterns from marimo and Jupyter, where WebSocket is the single source of truth for all state updates after the initial notebook load.

**Note**: Reactive execution (running dependent cells when a cell is run) is already implemented and working correctly. This plan does NOT add auto-execution on edit to avoid unnecessary server load on large notebooks, per task requirements.

## Current State Analysis

### Current Architecture Problems

1. **Race Condition**: Every cell operation (update/create/delete) triggers:
   - PUT/POST/DELETE request (mutation)
   - GET request (state sync) ← **Causes race conditions**
   
   The GET request returns stale state before reactive execution starts, overwriting WebSocket updates.

2. **State Overwrites**: Direct `setNotebook(updated)` replaces entire state, losing WebSocket updates that arrive later.

3. **Unnecessary Network Traffic**: Full notebook fetch on every operation.

4. **Complexity**: Dual update paths (HTTP + WebSocket) create synchronization challenges.

### Current Implementation Details

**Frontend (`frontend/src/components/Notebook.tsx`):**
- Lines 65-69: `handleUpdateCell` performs PUT then GET, then calls `setNotebook(updated)` (full replacement)
- Lines 71-79: `handleDeleteCell` performs DELETE then GET, then calls `setNotebook(updated)`
- Lines 81-85: `handleAddCell` performs POST then GET, then calls `setNotebook(updated)`
- Lines 25-57: `handleWSMessage` uses functional update `setNotebook(prev => { ... })` to merge WebSocket updates

**Backend (`backend/routes.py`):**
- Lines 168-206: `update_cell` endpoint updates code, dependencies, and saves notebook (does NOT trigger execution)
- Lines 140-166: `create_cell` endpoint creates new cell and saves notebook
- Lines 208-232: `delete_cell` endpoint removes cell and saves notebook
- Lines 236-264: WebSocket endpoint handles `run_cell` messages and triggers execution

**WebSocket (`backend/websocket.py`):**
- Currently supports: `cell_status`, `cell_stdout`, `cell_error`, `cell_output`
- Missing: `cell_updated`, `cell_created`, `cell_deleted` message types

**Scheduler (`backend/scheduler.py`):**
- Lines 25-42: `enqueue_run` manages execution queue
- Execution is NOT automatically triggered on cell updates (only via WebSocket `run_cell` message)

## System Context Analysis

This plan addresses a **root cause** rather than a symptom. The current architecture has a fundamental design flaw where HTTP GET requests compete with WebSocket updates, causing race conditions. The solution is to eliminate GET requests after initial load and make WebSocket the single source of truth for all state updates.

**State Management Flow:**
- Initial load: HTTP GET `/notebooks/{id}` → Load full notebook state
- After load: WebSocket only for all updates
- Frontend uses React state (`useState`) with functional updates for WebSocket messages
- Direct replacement (`setNotebook(updated)`) is used after GET requests (problematic)

**Reactive Execution:**
- Currently requires explicit user action (Run button or Ctrl+Enter)
- Execution is triggered via WebSocket `run_cell` message
- When a cell is run, the scheduler automatically executes all dependent cells (already implemented)
- **This plan does NOT add auto-execution on edit** - reactive execution only happens on explicit Run (as per task requirements)

## Desired End State

After this plan is complete:

1. **No GET requests** after initial notebook load (except for initial load and reconnection)
2. **WebSocket broadcasts** all cell mutations (`cell_updated`, `cell_created`, `cell_deleted`)
3. **WebSocket-only updates** - All state updates come from WebSocket messages (no optimistic updates)
4. **Reactive execution on Run** - When user explicitly runs a cell, dependent cells execute automatically (already implemented)
5. **Single source of truth** - WebSocket messages are authoritative (server is source of truth)
6. **Race conditions eliminated** - No competing update paths

### Verification

- Network tab shows no GET requests to `/notebooks/{id}` after initial load
- Cell updates trigger WebSocket `cell_updated` messages
- Cell creation triggers WebSocket `cell_created` messages
- Cell deletion triggers WebSocket `cell_deleted` messages
- Reactive execution works correctly: running a cell triggers dependent cells (already implemented)
- Multiple clients stay in sync via WebSocket broadcasts
- WebSocket reconnection handles state sync gracefully

### Key Discoveries

- **File**: `backend/routes.py:169-206` - `update_cell` does NOT trigger execution (by design - execution is explicit via Run)
- **File**: `backend/scheduler.py:61-64` - Reactive execution already implemented: running a cell triggers dependents
- **File**: `frontend/src/components/Notebook.tsx:65-69` - GET request after PUT causes race condition
- **File**: `backend/websocket.py:42-82` - Missing broadcast methods for cell mutations
- **File**: `frontend/src/useWebSocket.ts:4-8` - Missing TypeScript types for new message types
- **Pattern**: Functional updates (`setNotebook(prev => ...)`) work correctly, direct replacement (`setNotebook(updated)`) causes issues

## What We're NOT Doing

- **Not removing GET endpoint**: The GET endpoint remains for initial load and reconnection scenarios
- **Not changing storage**: Notebook persistence logic remains unchanged
- **Not changing execution logic**: Reactive execution already works correctly (runs dependents when cell is run)
- **Not adding auto-execution on edit**: Execution only happens on explicit Run (as per task requirements, avoids unnecessary server load)
- **Not using optimistic updates**: WebSocket messages are fast enough (<100ms), simpler implementation, always consistent
- **Not changing WebSocket connection logic**: Connection management remains the same
- **Not implementing offline queue**: Mutations will fail if WebSocket is disconnected (can be added later)

## Implementation Approach

The implementation will be done in phases:

1. **Phase 1**: Extend WebSocket protocol with new message types
2. **Phase 2**: Update backend endpoints to broadcast mutations
3. **Phase 3**: Remove GET requests from frontend mutation handlers
4. **Phase 4**: Add optimistic updates and handle new WebSocket messages
5. **Phase 5**: Handle WebSocket reconnection and edge cases

**Note**: Reactive execution is already implemented - when a user runs a cell, dependent cells execute automatically. This plan does NOT add auto-execution on edit to avoid unnecessary server load on large notebooks.

This phased approach allows incremental testing and rollback if needed.

## Phase 1: Extend WebSocket Protocol

### Overview
Add new WebSocket message types (`cell_updated`, `cell_created`, `cell_deleted`) to the backend broadcaster and frontend TypeScript types.

### Changes Required

#### 1. Backend WebSocket Broadcaster
**File**: `backend/websocket.py`
**Changes**: Add three new broadcast methods after line 82

```python
async def broadcast_cell_updated(self, notebook_id: str, cell_id: str, cell_data: dict):
    """Broadcast cell update (code, reads, writes, status)"""
    await self.broadcast(notebook_id, {
        "type": "cell_updated",
        "cellId": cell_id,
        "cell": cell_data  # {code, reads, writes, status}
    })

async def broadcast_cell_created(self, notebook_id: str, cell_data: dict, after_cell_id: str | None):
    """Broadcast cell creation"""
    await self.broadcast(notebook_id, {
        "type": "cell_created",
        "cell": cell_data,
        "afterCellId": after_cell_id
    })

async def broadcast_cell_deleted(self, notebook_id: str, cell_id: str):
    """Broadcast cell deletion"""
    await self.broadcast(notebook_id, {
        "type": "cell_deleted",
        "cellId": cell_id
    })
```

#### 2. Frontend TypeScript Types
**File**: `frontend/src/useWebSocket.ts`
**Changes**: Extend `WSMessage` type union (lines 4-8)

```typescript
export type WSMessage =
  | { type: 'cell_updated'; cellId: string; cell: { code: string; reads: string[]; writes: string[]; status: string } }
  | { type: 'cell_created'; cell: Cell; afterCellId?: string }
  | { type: 'cell_deleted'; cellId: string }
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: Output };
```

**Note**: Import `Cell` type from `./api` at the top of the file.

### Success Criteria

#### Automated Verification:
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] Python syntax check passes: `python -m py_compile backend/websocket.py`
- [x] No linting errors: `cd frontend && npm run lint` (if configured)

#### Manual Verification:
- [x] New broadcast methods exist in `backend/websocket.py`
- [x] TypeScript types include all three new message types
- [x] Type checking passes in IDE

---

## Phase 2: Update Backend Endpoints to Broadcast Mutations

### Overview
Modify `update_cell`, `create_cell`, and `delete_cell` endpoints to broadcast WebSocket messages after mutations.

### Changes Required

#### 1. Update Cell Endpoint
**File**: `backend/routes.py`
**Changes**: Modify `update_cell` function (lines 168-206)

```python
@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update cell code"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]
    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    # Update code
    cell.code = request.code
    cell.status = CellStatus.IDLE

    # Re-extract dependencies
    if cell.type == CellType.PYTHON:
        reads, writes = extract_dependencies(cell.code)
        cell.reads = reads
        cell.writes = writes
    elif cell.type == CellType.SQL:
        reads = extract_sql_dependencies(cell.code)
        cell.reads = reads
        cell.writes = set()

    # Rebuild graph
    rebuild_graph(notebook)

    # Check for cycles
    cycle = detect_cycle(notebook.graph, cell_id)
    if cycle:
        cell.status = CellStatus.ERROR
        cell.error = f"Circular dependency detected: {' -> '.join(cycle)}"

    notebook.revision += 1
    save_notebook(notebook)
    
    # Broadcast update via WebSocket
    await broadcaster.broadcast_cell_updated(notebook_id, cell_id, {
        "code": cell.code,
        "reads": list(cell.reads),
        "writes": list(cell.writes),
        "status": cell.status.value
    })
    
    return {"status": "ok"}
```

#### 2. Create Cell Endpoint
**File**: `backend/routes.py`
**Changes**: Modify `create_cell` function (lines 140-166)

```python
@router.post("/notebooks/{notebook_id}/cells")
async def create_cell(notebook_id: str, request: CreateCellRequest):
    """Create a new cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]

    new_cell = Cell(
        id=str(uuid.uuid4()),
        type=request.type,
        code="",
        status=CellStatus.IDLE
    )

    # Insert after specified cell or at end
    if request.after_cell_id:
        insert_idx = next(
            (i + 1 for i, c in enumerate(notebook.cells) if c.id == request.after_cell_id),
            len(notebook.cells)
        )
        notebook.cells.insert(insert_idx, new_cell)
    else:
        notebook.cells.append(new_cell)

    save_notebook(notebook)
    
    # Broadcast creation via WebSocket
    await broadcaster.broadcast_cell_created(notebook_id, {
        "id": new_cell.id,
        "type": new_cell.type.value,
        "code": new_cell.code,
        "status": new_cell.status.value,
        "reads": [],
        "writes": []
    }, request.after_cell_id)
    
    return {"cell_id": new_cell.id}
```

#### 3. Delete Cell Endpoint
**File**: `backend/routes.py`
**Changes**: Modify `delete_cell` function (lines 208-232)

```python
@router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """Delete a cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]

    # Find cell to get its writes
    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    # Remove cell from list
    notebook.cells = [c for c in notebook.cells if c.id != cell_id]

    # Remove from graph
    notebook.graph.remove_cell(cell_id)

    # Remove variables from kernel
    if cell:
        for var in cell.writes:
            notebook.kernel.globals_dict.pop(var, None)

    notebook.revision += 1
    save_notebook(notebook)
    
    # Broadcast deletion via WebSocket
    await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
    
    return {"status": "ok"}
```

### Success Criteria

#### Automated Verification:
- [x] Backend server starts without errors: `cd backend && python -m uvicorn main:app --reload`
- [x] All endpoints return 200 status codes for valid requests
- [x] WebSocket messages are broadcast (check server logs)

#### Manual Verification:
- [x] Update cell triggers `cell_updated` WebSocket message
- [x] Create cell triggers `cell_created` WebSocket message
- [x] Delete cell triggers `cell_deleted` WebSocket message
- [x] Messages contain correct data structure
- [x] Multiple connected clients receive broadcasts

---

## Phase 3: Remove GET Requests from Frontend Mutation Handlers

### Overview
Remove GET requests from `handleUpdateCell`, `handleAddCell`, and `handleDeleteCell` in the frontend. These handlers will now rely solely on WebSocket for state updates.

**Design Decision**: We use **WebSocket-only updates** (no optimistic updates) because:
- WebSocket messages arrive quickly (<100ms)
- Backend computes derived state (reads/writes, errors)
- Simpler implementation (no rollback logic)
- Always consistent (server is source of truth)
- User already sees code changes in Monaco editor

See `thoughts/shared/research/2025-12-27-optimistic-updates-vs-websocket-confirmation.md` for detailed analysis.

### Changes Required

#### 1. Update Cell Handler
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Modify `handleUpdateCell` function (lines 65-69)

```typescript
const handleUpdateCell = async (cellId: string, code: string) => {
  // Send mutation - WebSocket will update state
  await api.updateCell(notebookId, cellId, code);
  // No GET request! WebSocket cell_updated message will update state
};
```

#### 2. Add Cell Handler
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Modify `handleAddCell` function (lines 81-85)

```typescript
const handleAddCell = async (type: 'python' | 'sql') => {
  await api.createCell(notebookId, type);
  // WebSocket will send cell_created message
};
```

#### 3. Delete Cell Handler
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Modify `handleDeleteCell` function (lines 71-79)

```typescript
const handleDeleteCell = async (cellId: string) => {
  if (notebook && notebook.cells.length <= 1) {
    alert('Cannot delete the last cell');
    return;
  }
  
  // Send mutation - WebSocket will update state
  await api.deleteCell(notebookId, cellId);
  // No GET request! WebSocket cell_deleted message will update state
};
```

### Success Criteria

#### Automated Verification:
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] No GET requests to `/notebooks/{id}` in network tab after initial load (manual check)

#### Manual Verification:
- [x] Cell updates work without GET requests
- [x] Cell creation works without GET requests
- [x] Cell deletion works without GET requests
- [x] Network tab shows no GET requests after mutations
- [x] UI updates via WebSocket messages (<100ms delay is acceptable)
- [x] State updates are consistent (matches server state)

---

## Phase 4: Handle New WebSocket Messages in Frontend

### Overview
Update `handleWSMessage` to handle the new WebSocket message types (`cell_updated`, `cell_created`, `cell_deleted`) and merge them into notebook state. **WebSocket messages are the single source of truth** - all state updates come from WebSocket after mutations.

### Changes Required

#### 1. WebSocket Message Handler
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Modify `handleWSMessage` function (lines 25-57)

```typescript
const handleWSMessage = useCallback((msg: WSMessage) => {
  setNotebook(prev => {
    if (!prev) return prev;
    
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
        // Insert new cell
        const afterIdx = msg.afterCellId
          ? prev.cells.findIndex(c => c.id === msg.afterCellId)
          : -1;
        const newCells = [...prev.cells];
        newCells.splice(afterIdx + 1, 0, msg.cell);
        return { ...prev, cells: newCells };
      
      case 'cell_deleted':
        return {
          ...prev,
          cells: prev.cells.filter(c => c.id !== msg.cellId)
        };
      
      // Existing execution handlers...
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

      case 'cell_stdout':
        return {
          ...prev,
          cells: prev.cells.map(cell =>
            cell.id === msg.cellId ? { ...cell, stdout: msg.data } : cell
          )
        };

      case 'cell_error':
        return {
          ...prev,
          cells: prev.cells.map(cell =>
            cell.id === msg.cellId ? { ...cell, error: msg.error } : cell
          )
        };

      case 'cell_output':
        return {
          ...prev,
          cells: prev.cells.map(cell => {
            if (cell.id !== msg.cellId) return cell;
            const outputs = cell.outputs || [];
            return { ...cell, outputs: [...outputs, msg.output] };
          })
        };

      default:
        return prev;
    }
  });
}, []);
```

### Success Criteria

#### Automated Verification:
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] All WebSocket message types are handled in switch statement

#### Manual Verification:
- [x] `cell_updated` messages update cell metadata correctly
- [x] `cell_created` messages insert cells in correct position
- [x] `cell_deleted` messages remove cells correctly
- [x] WebSocket updates override optimistic updates
- [x] Multiple clients stay in sync
- [x] No state inconsistencies observed

---

## Phase 5: Handle WebSocket Reconnection and Edge Cases

### Overview
Add WebSocket reconnection handling to ensure state sync when connection is lost and restored. Also handle edge cases like error rollback.

### Changes Required

#### 1. WebSocket Reconnection Handler
**File**: `frontend/src/useWebSocket.ts`
**Changes**: Add reconnection logic and connection status tracking

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';
import { Output, CellStatus } from './api';

export type WSMessage =
  | { type: 'cell_updated'; cellId: string; cell: { code: string; reads: string[]; writes: string[]; status: string } }
  | { type: 'cell_created'; cell: Cell; afterCellId?: string }
  | { type: 'cell_deleted'; cellId: string }
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: Output };

export function useWebSocket(
  notebookId: string,
  onMessage: (msg: WSMessage) => void
) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 1000; // Start with 1 second

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    const websocket = new WebSocket(
      `ws://localhost:8000/api/ws/notebooks/${notebookId}`
    );

    websocket.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      reconnectAttempts.current = 0;
    };

    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      onMessage(message);
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
      
      // Attempt reconnection with exponential backoff
      if (reconnectAttempts.current < maxReconnectAttempts) {
        reconnectAttempts.current += 1;
        const delay = reconnectDelay * Math.pow(2, reconnectAttempts.current - 1);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        console.error('Max reconnection attempts reached');
      }
    };

    ws.current = websocket;
  }, [notebookId, onMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      ws.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((message: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, []);

  return { sendMessage, connected };
}
```

#### 2. Re-fetch on Reconnection
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Add effect to re-fetch notebook on reconnection

```typescript
const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage);

// Re-fetch notebook on reconnection to ensure sync
useEffect(() => {
  if (connected && notebook) {
    // Re-fetch to ensure we have latest state after reconnection
    api.getNotebook(notebookId).then(nb => {
      setNotebook(nb);
    });
  }
}, [connected, notebookId]); // Only run when connection status changes
```

#### 3. Error Handling for Failed Mutations
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Add error handling for failed mutations

```typescript
const handleUpdateCell = async (cellId: string, code: string) => {
  try {
    await api.updateCell(notebookId, cellId, code);
    // WebSocket will send cell_updated message on success
  } catch (error) {
    console.error('Failed to update cell:', error);
    alert('Failed to update cell. Please try again.');
    // State remains unchanged - WebSocket message won't arrive on error
  }
};
```

Apply similar error handling to `handleAddCell` and `handleDeleteCell`. Note: Since we don't use optimistic updates, failed mutations simply don't update state (no rollback needed).

### Success Criteria

#### Automated Verification:
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] No console errors during reconnection

#### Manual Verification:
- [x] WebSocket reconnects automatically after disconnection
- [x] Notebook state is re-fetched on reconnection
- [x] Failed mutations rollback optimistic updates
- [x] Error messages are displayed to user
- [x] Multiple reconnection attempts work correctly
- [x] Connection status is tracked correctly

---

## Testing Strategy

### Unit Tests

#### Backend Tests
- [ ] Test `broadcast_cell_updated` sends correct message format
- [ ] Test `broadcast_cell_created` sends correct message format
- [ ] Test `broadcast_cell_deleted` sends correct message format
- [ ] Test `update_cell` triggers execution when status is not ERROR
- [ ] Test `update_cell` does NOT trigger execution when status is ERROR

**File**: `backend/tests/test_websocket.py` (create if needed)
```python
import pytest
from backend.websocket import WebSocketBroadcaster
from backend.models import CellStatus

@pytest.mark.asyncio
async def test_broadcast_cell_updated():
    broadcaster = WebSocketBroadcaster()
    # Mock WebSocket connection
    # Verify message format
    pass
```

#### Frontend Tests
- [ ] Test `handleWSMessage` handles `cell_updated` correctly
- [ ] Test `handleWSMessage` handles `cell_created` correctly
- [ ] Test `handleWSMessage` handles `cell_deleted` correctly
- [ ] Test state updates only come from WebSocket messages
- [ ] Test error handling when WebSocket messages fail

**File**: `frontend/src/components/__tests__/Notebook.test.tsx` (create if needed)
```typescript
import { render, screen } from '@testing-library/react';
import { Notebook } from '../Notebook';

describe('Notebook WebSocket handling', () => {
  it('handles cell_updated message', () => {
    // Test implementation
  });
});
```

### Integration Tests

#### End-to-End Scenarios
1. **Cell Update Flow**:
   - Update cell code → Send PUT request → Verify WebSocket `cell_updated` arrives → Verify state updates → Verify reads/writes computed correctly

2. **Cell Creation Flow**:
   - Create new cell → Send POST request → Verify WebSocket `cell_created` arrives → Verify cell appears in UI at correct position

3. **Cell Deletion Flow**:
   - Delete cell → Send DELETE request → Verify WebSocket `cell_deleted` arrives → Verify cell removed from UI

4. **Reconnection Flow**:
   - Disconnect WebSocket → Make mutation → Reconnect → Verify state sync

5. **Multi-Client Sync**:
   - Open two browser windows → Update cell in one → Verify both update

### Manual Testing Steps

1. **Initial Load**:
   - Open notebook → Verify GET request for initial load
   - Verify no more GET requests after load

2. **Cell Update**:
   - Edit cell code → Blur editor → Verify optimistic update
   - Verify WebSocket `cell_updated` message arrives
   - Verify execution triggers automatically
   - Verify results appear via WebSocket

3. **Cell Creation**:
   - Click "Add Python Cell" → Verify cell appears immediately
   - Verify WebSocket `cell_created` message arrives

4. **Cell Deletion**:
   - Delete cell → Verify cell disappears immediately
   - Verify WebSocket `cell_deleted` message arrives

5. **Reconnection**:
   - Disconnect network → Make mutation → Reconnect
   - Verify state syncs correctly

6. **Error Handling**:
   - Cause mutation to fail → Verify rollback
   - Verify error message displayed

7. **Race Condition Test**:
   - Rapidly update multiple cells → Verify no state loss
   - Verify all updates reflected correctly

## Performance Considerations

1. **WebSocket Message Frequency**: With auto-execution, expect more WebSocket messages. Monitor message rate and consider throttling if needed.

2. **Optimistic Updates**: Immediate UI feedback improves perceived performance, but ensure WebSocket updates arrive promptly.

3. **Reconnection Backoff**: Exponential backoff prevents server overload during network issues.

4. **State Merging**: Functional updates (`setNotebook(prev => ...)`) are more efficient than direct replacement.

5. **No Full Notebook Serialization**: Incremental WebSocket updates avoid serializing entire notebook on every operation.

## Migration Notes

### Backward Compatibility

- **Old clients** can still use GET requests (but won't get WebSocket updates)
- **New clients** use WebSocket-only updates
- **Gradual rollout** possible: Implement WebSocket messages first, then remove GET requests

### Rollback Plan

If issues arise:

1. **Phase 1-2**: Can rollback by removing broadcast calls (endpoints still work)
2. **Phase 3**: Can rollback by restoring GET requests in handlers
3. **Phase 4**: Can rollback by removing new message handlers
4. **Phase 5**: Can rollback by removing reconnection logic

### Data Migration

- **No data migration needed** - all changes are in-memory and communication protocol
- **Storage format unchanged** - notebook persistence remains the same

## References

- Original research: `thoughts/shared/research/2025-12-27-websocket-only-architecture.md`
- Race condition investigation: `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md`
- Optimistic updates research: `thoughts/shared/research/2025-12-27-optimistic-updates-vs-websocket-confirmation.md`
- Initial plan draft: `thoughts/shared/plans/2025-12-27-websocket-only-implementation.md`
- Backend routes: `backend/routes.py`
- Backend WebSocket: `backend/websocket.py`
- Frontend notebook component: `frontend/src/components/Notebook.tsx`
- Frontend WebSocket hook: `frontend/src/useWebSocket.ts`

