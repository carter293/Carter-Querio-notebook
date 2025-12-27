---
date: 2025-12-27T18:00:00+00:00
researcher: Composer
topic: "WebSocket-only architecture - eliminating GET requests after initial load"
tags: [research, architecture, websocket, state-management, marimo, jupyter]
status: draft
last_updated: 2025-12-27
last_updated_by: Composer
---

# Research: WebSocket-Only Architecture - Eliminating GET Requests After Initial Load

**Date**: 2025-12-27T18:00:00+00:00 GMT
**Researcher**: Composer

## Research Question

How can we eliminate HTTP GET requests after initial load, relying solely on WebSocket updates for state synchronization? This aligns with how marimo and Jupyter handle real-time notebook updates.

## Current Architecture Problems

### Current Flow (Problematic)

1. **Initial Load**: GET `/notebooks/{id}` → Load full notebook state
2. **Cell Update (Blur)**: 
   - PUT `/notebooks/{id}/cells/{cell_id}` → Update cell code
   - GET `/notebooks/{id}` → **Fetch full notebook** (causes race condition)
   - WebSocket messages arrive later → May be overwritten by GET response
3. **Cell Create/Delete**: Similar pattern - PUT/POST/DELETE + GET
4. **Cell Run**: WebSocket message → Backend executes → WebSocket updates

### Issues

1. **Race Condition**: GET requests return stale state before reactive execution starts
2. **State Overwrites**: Direct `setNotebook(updated)` replaces entire state, losing WebSocket updates
3. **Unnecessary Network Traffic**: Full notebook fetch on every operation
4. **Complexity**: Dual update paths (HTTP + WebSocket) create synchronization challenges

## How marimo and Jupyter Handle This

### marimo Architecture

**Key Principles:**
- **WebSocket-first**: After initial load, all updates flow through WebSocket
- **Reactive Execution**: Cell updates automatically trigger dependent cell execution
- **Incremental Updates**: Only changed cells are broadcast, not full notebook state
- **Optimistic Updates**: Frontend updates immediately, backend confirms via WebSocket

**Communication Pattern:**
```
Initial Load: GET /notebook → Full state
After Load: WebSocket only
  - Cell update → WebSocket message → Backend updates → WebSocket broadcasts changes
  - Execution → WebSocket message → Backend executes → WebSocket broadcasts results
  - No GET requests for state synchronization
```

### Jupyter Architecture

**Key Principles:**
- **ZeroMQ + WebSocket**: Server multiplexes ZeroMQ channels into single WebSocket
- **Message Protocol**: Structured messages (execute_request, execute_reply, stream, display_data)
- **Incremental Updates**: Each message type updates specific parts of cell state
- **No State Polling**: Client never polls for state - all updates via WebSocket

**Communication Pattern:**
```
Initial Load: GET /notebook → Full state
After Load: WebSocket only
  - execute_request → kernel executes → execute_reply + stream + display_data messages
  - No GET requests for execution results
```

## Proposed Solutions

### Solution 1: WebSocket-Only Updates (Recommended)

**Principle**: After initial load, all state changes flow through WebSocket. HTTP endpoints only perform mutations, not state retrieval.

#### Backend Changes

1. **Extend WebSocket Protocol**:
   - Add message types: `cell_updated`, `cell_created`, `cell_deleted`, `notebook_updated`
   - Broadcast these events after mutations

2. **Update `update_cell` endpoint**:
   ```python
   @router.put("/notebooks/{notebook_id}/cells/{cell_id}")
   async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
       # ... existing update logic ...
       
       # Broadcast cell update via WebSocket
       await broadcaster.broadcast_cell_updated(notebook_id, cell_id, {
           "code": cell.code,
           "reads": list(cell.reads),
           "writes": list(cell.writes),
           "status": cell.status.value
       })
       
       # Trigger reactive execution if needed
       if cell.status == CellStatus.IDLE:
           await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)
       
       return {"status": "ok"}
   ```

3. **Update `create_cell` endpoint**:
   ```python
   @router.post("/notebooks/{notebook_id}/cells")
   async def create_cell(notebook_id: str, request: CreateCellRequest):
       # ... existing create logic ...
       
       # Broadcast cell creation via WebSocket
       await broadcaster.broadcast_cell_created(notebook_id, {
           "id": new_cell.id,
           "type": new_cell.type,
           "code": new_cell.code,
           "status": new_cell.status.value,
           "after_cell_id": request.after_cell_id
       })
       
       return {"cell_id": new_cell.id}
   ```

4. **Update `delete_cell` endpoint**:
   ```python
   @router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
   async def delete_cell(notebook_id: str, cell_id: str):
       # ... existing delete logic ...
       
       # Broadcast cell deletion via WebSocket
       await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
       
       return {"status": "ok"}
   ```

#### Frontend Changes

1. **Remove GET requests from mutation handlers**:
   ```typescript
   const handleUpdateCell = async (cellId: string, code: string) => {
     // Optimistic update
     setNotebook(prev => {
       if (!prev) return prev;
       return {
         ...prev,
         cells: prev.cells.map(cell =>
           cell.id === cellId ? { ...cell, code } : cell
         )
       };
     });
     
     // Send mutation - WebSocket will confirm
     await api.updateCell(notebookId, cellId, code);
     // No GET request!
   };
   ```

2. **Handle new WebSocket message types**:
   ```typescript
   const handleWSMessage = useCallback((msg: WSMessage) => {
     setNotebook(prev => {
       if (!prev) return prev;
       
       switch (msg.type) {
         case 'cell_updated':
           // Update cell metadata (code, reads, writes)
           return {
             ...prev,
             cells: prev.cells.map(cell =>
               cell.id === msg.cellId
                 ? { ...cell, ...msg.cell }
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
         
         // ... existing execution update handlers ...
       }
     });
   }, []);
   ```

#### Benefits

- ✅ Eliminates race conditions (no GET requests to overwrite WebSocket updates)
- ✅ Single source of truth (WebSocket updates)
- ✅ Reduced network traffic (incremental updates only)
- ✅ Simpler mental model (one update path)
- ✅ Better performance (no full notebook serialization on every operation)

#### Challenges

- ⚠️ Requires WebSocket connection to be reliable
- ⚠️ Need to handle WebSocket reconnection gracefully
- ⚠️ Optimistic updates may need rollback on errors

---

### Solution 2: Automatic Reactive Execution on Update

**Principle**: When a cell is updated, automatically trigger reactive execution (like marimo). This eliminates the need for manual "run" actions and makes the notebook truly reactive.

#### Backend Changes

1. **Auto-trigger execution in `update_cell`**:
   ```python
   @router.put("/notebooks/{notebook_id}/cells/{cell_id}")
   async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
       # ... existing update logic ...
       
       # Automatically trigger reactive execution
       if cell.status != CellStatus.ERROR:  # Don't run if cycle detected
           await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)
       
       return {"status": "ok"}
   ```

2. **Add debouncing/throttling** (optional):
   ```python
   # Prevent rapid-fire executions
   async def update_cell(...):
       # ... update code ...
       
       # Debounce execution (wait 300ms for more updates)
       await asyncio.sleep(0.3)
       if cell.code == request.code:  # Still matches latest code
           await scheduler.enqueue_run(...)
   ```

#### Frontend Changes

- No changes needed! Execution happens automatically via WebSocket.

#### Benefits

- ✅ True reactive behavior (like marimo)
- ✅ No manual "run" needed
- ✅ Simpler UX

#### Challenges

- ⚠️ May execute too frequently (need debouncing)
- ⚠️ User may want to edit without executing (need "draft" mode?)

---

### Solution 3: Hybrid Approach with Version/Revision Checking

**Principle**: Keep GET requests but add version checking to prevent stale updates.

#### Implementation

1. **Add revision to notebook state**:
   ```python
   # Backend already has notebook.revision
   # Include in GET response
   ```

2. **Frontend checks revision before applying GET response**:
   ```typescript
   const handleUpdateCell = async (cellId: string, code: string) => {
     await api.updateCell(notebookId, cellId, code);
     
     const updated = await api.getNotebook(notebookId);
     
     setNotebook(prev => {
       if (!prev) return updated;
       
       // Only apply if revision is newer
       if (updated.revision > prev.revision) {
         // Merge instead of replace
         return mergeNotebookState(prev, updated);
       }
       
       return prev; // Stale update, ignore
     });
   };
   ```

#### Benefits

- ✅ Backward compatible
- ✅ Handles WebSocket failures gracefully
- ✅ Prevents stale updates

#### Challenges

- ⚠️ Still has GET requests (doesn't solve original problem)
- ⚠️ More complex merge logic needed

---

## Recommended Approach: Solution 1 + Solution 2

**Combine WebSocket-only updates with automatic reactive execution:**

1. **Eliminate GET requests** after initial load (Solution 1)
2. **Auto-trigger execution** on cell updates (Solution 2)
3. **Add WebSocket reconnection handling** for reliability

### Implementation Plan

#### Phase 1: Extend WebSocket Protocol
- Add `cell_updated`, `cell_created`, `cell_deleted` message types
- Update backend to broadcast these events
- Update frontend to handle these messages

#### Phase 2: Remove GET Requests
- Remove GET calls from `handleUpdateCell`, `handleAddCell`, `handleDeleteCell`
- Add optimistic updates in frontend
- Rely on WebSocket for state confirmation

#### Phase 3: Auto-trigger Reactive Execution
- Modify `update_cell` to automatically enqueue execution
- Add debouncing if needed
- Test reactive behavior

#### Phase 4: Handle Edge Cases
- WebSocket reconnection: Re-fetch notebook on reconnect
- Error handling: Rollback optimistic updates on errors
- Offline mode: Queue mutations, sync on reconnect

## Comparison with marimo/Jupyter

| Feature | Current | marimo/Jupyter | Proposed |
|---------|---------|----------------|----------|
| Initial Load | GET | GET | GET |
| Cell Update | PUT + GET | WebSocket | WebSocket |
| Cell Create | POST + GET | WebSocket | WebSocket |
| Cell Delete | DELETE + GET | WebSocket | WebSocket |
| Execution | WebSocket | WebSocket | WebSocket (auto) |
| State Sync | HTTP + WebSocket | WebSocket only | WebSocket only |

## Open Questions

1. **Debouncing**: Should cell updates trigger immediate execution or wait for pause?
   - **marimo**: Immediate execution (truly reactive)
   - **Jupyter**: Manual execution (user controls)
   - **Recommendation**: Immediate with optional debouncing

2. **Error Handling**: How to handle WebSocket failures?
   - **Option A**: Fallback to GET requests
   - **Option B**: Queue mutations, sync on reconnect
   - **Recommendation**: Option B (maintain WebSocket-only model)

3. **Optimistic Updates**: Should frontend update immediately or wait for backend?
   - **marimo**: Optimistic (instant feedback)
   - **Jupyter**: Wait for backend (authoritative)
   - **Recommendation**: Optimistic for code changes, wait for execution results

4. **Cell Ordering**: How to handle cell insertion/deletion without GET?
   - **Solution**: Include `after_cell_id` in WebSocket message
   - **Already implemented**: `create_cell` has `after_cell_id` parameter

## Next Steps

1. ✅ Research marimo/Jupyter architectures
2. ⏳ Implement WebSocket message types (`cell_updated`, `cell_created`, `cell_deleted`)
3. ⏳ Update backend endpoints to broadcast events
4. ⏳ Remove GET requests from frontend mutation handlers
5. ⏳ Add optimistic updates
6. ⏳ Implement auto-trigger reactive execution
7. ⏳ Add WebSocket reconnection handling
8. ⏳ Test edge cases

## Related Research

- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Race condition investigation
- `thoughts/shared/research/2025-12-27-loading-saving-named-notebooks-dropdown.md` - Notebook management

