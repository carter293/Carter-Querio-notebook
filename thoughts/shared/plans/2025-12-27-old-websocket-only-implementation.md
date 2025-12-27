---
date: 2025-12-27T18:00:00+00:00
planner: Composer
topic: "WebSocket-only architecture implementation plan"
tags: [plan, architecture, websocket, implementation]
status: draft
---

# Implementation Plan: WebSocket-Only Architecture

## Goal

Eliminate HTTP GET requests after initial load, relying solely on WebSocket for state synchronization (like marimo and Jupyter).

## Current Problem

Every cell operation (update/create/delete) triggers:
1. PUT/POST/DELETE request (mutation)
2. GET request (state sync) ← **This causes race conditions**

The GET request returns stale state before reactive execution starts, overwriting WebSocket updates.

## Solution Overview

**After initial load:**
- ✅ HTTP endpoints: Only mutations (PUT/POST/DELETE)
- ✅ WebSocket: All state updates (cell changes, execution results)
- ✅ No GET requests for state synchronization

## Implementation Steps

### Step 1: Extend WebSocket Protocol

Add new message types to `backend/websocket.py`:

```python
async def broadcast_cell_updated(self, notebook_id: str, cell_id: str, cell_data: dict):
    await self.broadcast(notebook_id, {
        "type": "cell_updated",
        "cellId": cell_id,
        "cell": cell_data  # {code, reads, writes, status}
    })

async def broadcast_cell_created(self, notebook_id: str, cell_data: dict, after_cell_id: str | None):
    await self.broadcast(notebook_id, {
        "type": "cell_created",
        "cell": cell_data,
        "afterCellId": after_cell_id
    })

async def broadcast_cell_deleted(self, notebook_id: str, cell_id: str):
    await self.broadcast(notebook_id, {
        "type": "cell_deleted",
        "cellId": cell_id
    })
```

### Step 2: Update Backend Endpoints

**`backend/routes.py` - `update_cell`:**
```python
@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(...):
    # ... existing update logic ...
    
    # Broadcast update via WebSocket
    await broadcaster.broadcast_cell_updated(notebook_id, cell_id, {
        "code": cell.code,
        "reads": list(cell.reads),
        "writes": list(cell.writes),
        "status": cell.status.value
    })
    
    # Auto-trigger reactive execution
    if cell.status != CellStatus.ERROR:
        await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)
    
    return {"status": "ok"}
```

**`backend/routes.py` - `create_cell`:**
```python
@router.post("/notebooks/{notebook_id}/cells")
async def create_cell(...):
    # ... existing create logic ...
    
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

**`backend/routes.py` - `delete_cell`:**
```python
@router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
async def delete_cell(...):
    # ... existing delete logic ...
    
    await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
    
    return {"status": "ok"}
```

### Step 3: Update Frontend - Remove GET Requests

**`frontend/src/components/Notebook.tsx`:**

```typescript
// Remove GET from handleUpdateCell
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
  
  // Mutation only - WebSocket will confirm
  await api.updateCell(notebookId, cellId, code);
  // No GET request!
};

// Remove GET from handleAddCell
const handleAddCell = async (type: 'python' | 'sql') => {
  await api.createCell(notebookId, type);
  // WebSocket will send cell_created message
};

// Remove GET from handleDeleteCell
const handleDeleteCell = async (cellId: string) => {
  if (notebook && notebook.cells.length <= 1) {
    alert('Cannot delete the last cell');
    return;
  }
  await api.deleteCell(notebookId, cellId);
  // WebSocket will send cell_deleted message
};
```

### Step 4: Handle New WebSocket Messages

**`frontend/src/components/Notebook.tsx` - `handleWSMessage`:**

```typescript
const handleWSMessage = useCallback((msg: WSMessage) => {
  setNotebook(prev => {
    if (!prev) return prev;
    
    switch (msg.type) {
      case 'cell_updated':
        // Update cell metadata
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
      
      // Existing execution handlers...
      case 'cell_status':
      case 'cell_stdout':
      case 'cell_error':
      case 'cell_output':
        // ... existing logic ...
    }
  });
}, []);
```

### Step 5: Update TypeScript Types

**`frontend/src/useWebSocket.ts`:**

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

### Step 6: Handle WebSocket Reconnection

**`frontend/src/components/Notebook.tsx`:**

```typescript
const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage);

// Re-fetch on reconnect if needed
useEffect(() => {
  if (connected && notebook) {
    // Optionally re-fetch to ensure sync
    // Or trust WebSocket messages to catch up
  }
}, [connected]);
```

## Benefits

✅ **Eliminates race conditions** - No GET requests to overwrite WebSocket updates  
✅ **Single source of truth** - WebSocket is the only update path  
✅ **Reduced network traffic** - Incremental updates only  
✅ **Simpler architecture** - One update mechanism  
✅ **Better performance** - No full notebook serialization on every operation  
✅ **True reactive behavior** - Auto-execution on cell updates (like marimo)

## Testing Checklist

- [ ] Cell update triggers WebSocket `cell_updated` message
- [ ] Cell create triggers WebSocket `cell_created` message
- [ ] Cell delete triggers WebSocket `cell_deleted` message
- [ ] No GET requests after initial load
- [ ] Optimistic updates work correctly
- [ ] WebSocket updates override optimistic updates
- [ ] Reactive execution triggers automatically
- [ ] WebSocket reconnection handles state sync
- [ ] Multiple clients stay in sync
- [ ] Error handling works (rollback optimistic updates)

## Migration Notes

- **Backward compatible**: Old clients can still use GET requests (but won't get auto-execution)
- **Gradual rollout**: Can implement WebSocket messages first, then remove GET requests
- **Fallback**: If WebSocket fails, could fallback to GET (but defeats purpose)

## Related Research

- `thoughts/shared/research/2025-12-27-websocket-only-architecture.md` - Detailed research
- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Race condition investigation

