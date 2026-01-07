---
date: 2026-01-07 18:30:00 GMT
researcher: Matthew Carter
topic: "CRUD Operations Not Synchronized with Kernel Dependency Graph"
tags: [research, codebase, reactive-execution, websocket, dependency-graph, bug-fix, crud]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Research: CRUD Operations Not Synchronized with Kernel Dependency Graph

**Date**: 2026-01-07 18:30:00 GMT  
**Researcher**: Matthew Carter

## Research Question

Following the investigation of cell update synchronization failures, are there other CRUD operations (create, delete) that are not being sent to the kernel? What is the impact on the dependency graph and reactive execution?

## Summary

**Root Cause Identified**: The system has critical disconnects between REST API operations and the WebSocket/Coordinator/Kernel layer for **cell creation** and **cell deletion**, similar to the cell update issue documented in `2026-01-07-reactive-cell-update-cascade-failure.md`.

**The Bugs**:

1. **Cell Creation**: When a new cell is created via REST API:
   - File storage is updated ✅
   - Coordinator's in-memory notebook is NOT updated ❌
   - Kernel's dependency graph is NOT updated ❌
   - Kernel's cell registry does NOT include the new cell ❌
   - Frontend expects `cell_created` WebSocket message but backend never sends it ❌

2. **Cell Deletion**: When a cell is deleted via REST API:
   - File storage is updated ✅
   - Coordinator's in-memory notebook is NOT updated ❌
   - Kernel's dependency graph still contains the deleted cell ❌
   - Kernel's cell registry still contains the deleted cell ❌
   - Frontend expects `cell_deleted` WebSocket message but backend never sends it ❌
   - **Critical**: Kernel may try to execute deleted cells, causing errors or stale dependency edges

**Impact**: 
- New cells cannot be executed until notebook is reloaded (new WebSocket connection)
- Deleted cells remain in dependency graph, causing stale edges and potential execution errors
- Frontend state becomes out of sync with backend execution state
- Reactive cascades may reference non-existent cells

## Detailed Findings

### Architecture Context

The system uses a dual-protocol architecture:
- **REST API** (`/api/v1/notebooks/{id}/cells`): For CRUD operations and persistence
- **WebSocket**: For real-time execution, status updates, and reactive cascades
- **Coordinator**: Manages kernel lifecycle and bridges WebSocket to kernel IPC
- **Kernel Process**: Maintains dependency graph and cell registry in isolated process

**Intended Design**: REST API for durable state, WebSocket for ephemeral execution state.

**Actual Problem**: The two protocols are not properly synchronized. REST API updates persistence but doesn't notify the execution layer.

### Bug #1: Cell Creation Not Synchronized

#### Frontend: Cell Creation Flow

```typescript
// frontend/src/components/NotebookApp.tsx:178-188
const addCell = async (type: CellType, afterCellId?: string) => {
    if (!notebookId) return;
    
    try {
        const { cell_id } = await api.createCell(notebookId, type, afterCellId);
        // Cell will be added via WebSocket message
        setTimeout(() => setFocusedCellId(cell_id), 100);
    } catch (err) {
        console.error("Failed to create cell:", err);
    }
};
```

**Frontend Expectation**: The comment says "Cell will be added via WebSocket message", and the frontend has a handler for `cell_created`:

```typescript
// frontend/src/components/NotebookApp.tsx:102-112
case "cell_created":
    setCells((prev) => {
        const newCells = [...prev];
        // Insert at the specified index, or append if index not provided
        if (typeof msg.index === 'number') {
            newCells.splice(msg.index, 0, msg.cell);
        } else {
            newCells.push(msg.cell);
        }
        return newCells;
    });
    break;
```

#### Backend: REST API Only Updates File Storage

```python
# backend/app/api/cells.py:13-47
@router.post("/", response_model=CreateCellResponse)
async def create_cell(notebook_id: str, request: CreateCellRequest):
    """Create a new cell in a notebook."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Create new cell
    cell_id = str(uuid4())
    new_cell = CellResponse(
        id=cell_id,
        type=request.type,
        code="",
        status="idle",
    )

    # Insert cell at the correct position
    if request.after_cell_id:
        # ... find insert position ...
        notebook.cells.insert(insert_index, new_cell)
    else:
        notebook.cells.append(new_cell)

    NotebookFileStorage.serialize_notebook(notebook)  # ← Only updates file!
    return CreateCellResponse(cell_id=cell_id)
```

**Problem**: This endpoint:
- ✅ Creates cell in file storage
- ❌ Does NOT update coordinator's in-memory notebook
- ❌ Does NOT register cell with kernel
- ❌ Does NOT broadcast `cell_created` WebSocket message
- ❌ Does NOT update dependency graph

#### Backend: No WebSocket Handler for Cell Creation

```python
# backend/app/websocket/handler.py:63-84
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "cell_update":
        # ... handles cell updates ...
    elif msg_type == "update_db_connection":
        # ... handles db connection updates ...
    elif msg_type == "run_cell":
        # ... handles cell execution ...
    else:
        print(f"Unknown message type: {msg_type}")
```

**Problem**: No handler for `create_cell` or `cell_create` message types.

#### Backend: Coordinator Has No Cell Creation Method

The `NotebookCoordinator` class has:
- `handle_cell_update()` - for code updates
- `handle_db_connection_update()` - for db config
- `handle_run_cell()` - for execution

But **no method** for:
- Creating a new cell
- Registering a new cell with the kernel

#### Kernel: Registration Only Happens on Load

The kernel registers cells in two scenarios:

1. **On notebook load** (`coordinator.py:33-62`):
   ```python
   async def load_notebook(self, notebook_id: str):
       # ... load notebook ...
       # Register all cells with the kernel to build dependency graph
       for cell in self.notebook.cells:
           register_req = RegisterCellRequest(...)
           self.kernel.input_queue.put(register_req.model_dump())
   ```

2. **On cell code update** (`coordinator.py:64-122`):
   ```python
   async def handle_cell_update(self, cell_id: str, new_code: str):
       # ... update code ...
       # Register updated cell with kernel
       register_req = RegisterCellRequest(...)
       self.kernel.input_queue.put(register_req.model_dump())
   ```

**Problem**: New cells created via REST API are never registered because:
- They're not in `coordinator.notebook.cells` (coordinator never reloads)
- `handle_cell_update` only works for existing cells

#### Impact of Cell Creation Bug

**Scenario**: User creates a new cell, adds code, tries to run it

1. User clicks "Add Cell" → Frontend calls `POST /api/v1/notebooks/{id}/cells`
2. Backend creates cell in file storage with empty code
3. Frontend optimistically adds cell to UI (expects WebSocket message that never comes)
4. User types code in new cell
5. User clicks "Run" → WebSocket sends `{type: "run_cell", cellId: new_cell_id}`
6. Coordinator looks up cell in `self.notebook.cells` → **NOT FOUND** (coordinator has stale state)
7. Coordinator's `handle_run_cell()` returns early (line 168: `if not cell: return`)
8. **Result**: Cell never executes, no error message, user confused

**Alternative Scenario**: If coordinator reloaded notebook before execution:
1. New cell would be in `coordinator.notebook.cells`
2. But cell is NOT in kernel's `cell_registry` (never registered)
3. Kernel execution fails with: `"Cell {cell_id} not registered. Cells must be registered via RegisterCellRequest before execution."` (see `kernel/process.py:113-125`)

### Bug #2: Cell Deletion Not Synchronized

#### Frontend: Cell Deletion Flow

```typescript
// frontend/src/components/NotebookApp.tsx:190-208
const deleteCell = async (id: string) => {
    if (!notebookId) return;

    if (cells.length <= 1) {
        await updateCellCode(id, "");
        return;
    }

    try {
        await api.deleteCell(notebookId, id);
        if (focusedCellId === id) {
            const index = cells.findIndex((c) => c.id === id);
            const nextCell = cells[index + 1] || cells[index - 1];
            setFocusedCellId(nextCell?.id || null);
        }
    } catch (err) {
        console.error("Failed to delete cell:", err);
    }
};
```

**Frontend Expectation**: Frontend has a handler for `cell_deleted`:

```typescript
// frontend/src/components/NotebookApp.tsx:114-116
case "cell_deleted":
    setCells((prev) => prev.filter((c) => c.id !== msg.cellId));
    break;
```

#### Backend: REST API Only Updates File Storage

```python
# backend/app/api/cells.py:49-63
@router.delete("/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """Delete a cell."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Find and remove cell
    for i, cell in enumerate(notebook.cells):
        if cell.id == cell_id:
            notebook.cells.pop(i)
            NotebookFileStorage.serialize_notebook(notebook)  # ← Only updates file!
            return {"status": "ok"}

    raise HTTPException(status_code=404, detail="Cell not found")
```

**Problem**: This endpoint:
- ✅ Deletes cell from file storage
- ❌ Does NOT update coordinator's in-memory notebook
- ❌ Does NOT remove cell from kernel's dependency graph
- ❌ Does NOT remove cell from kernel's cell registry
- ❌ Does NOT broadcast `cell_deleted` WebSocket message

#### Backend: No WebSocket Handler for Cell Deletion

Same as creation - no handler exists for `delete_cell` or `cell_delete` message types.

#### Backend: Coordinator Has No Cell Deletion Method

The `NotebookCoordinator` class has no method for:
- Deleting a cell
- Unregistering a cell from the kernel

#### Kernel: No IPC Message Type for Cell Removal

The kernel process supports these operations:
- `register_cell` - Register/update cell in dependency graph
- `execute` - Execute cell and cascade
- `set_database_config` - Configure database
- `shutdown` - Shutdown kernel

**Missing**: No `remove_cell` or `delete_cell` message type exists.

However, the **dependency graph implementation** does support removal:

```python
# backend/app/core/graph.py:138-152
def remove_cell(self, cell_id: str) -> None:
    """Remove a cell from the graph."""
    if self._graph.has_node(cell_id):
        self._graph.remove_node(cell_id)

    # Clean up variable mappings
    if cell_id in self._cell_writes:
        old_writes = self._cell_writes[cell_id]
        for var in old_writes:
            if self._var_writers.get(var) == cell_id:
                del self._var_writers[var]
        del self._cell_writes[cell_id]

    if cell_id in self._cell_reads:
        del self._cell_reads[cell_id]
```

**Problem**: This method exists but is never called because:
- No kernel IPC message type triggers it
- No coordinator method calls it
- No REST endpoint notifies the kernel

#### Impact of Cell Deletion Bug

**Scenario 1: Stale Dependency Edges**

1. Initial state:
   - Cell 1: `x = 5`
   - Cell 2: `y = x + 1` (depends on Cell 1)
   - Kernel graph: Cell 2 → Cell 1 edge exists

2. User deletes Cell 1 via REST API
3. File storage: Cell 1 removed ✅
4. Kernel graph: **Cell 1 still exists with edge to Cell 2** ❌
5. User runs Cell 2 → Kernel tries to execute Cell 1 (in cascade) → **Cell 1 not in coordinator's notebook** → Error or stale execution

**Scenario 2: Execution of Deleted Cell**

1. User deletes Cell 1 via REST API
2. Kernel's `cell_registry` still contains Cell 1
3. If any execution cascade includes Cell 1, kernel will try to execute it
4. Kernel looks up code: `cell_code, cell_type = cell_registry[cell_id]`
5. Executes **stale code** from deleted cell
6. **Result**: Deleted cell's code still runs, causing confusion

**Scenario 3: Variable Writer Mappings**

1. Cell 1 writes variable `x`
2. Cell 2 reads variable `x`
3. Kernel's `_var_writers['x'] = 'cell_1'`
4. User deletes Cell 1 via REST API
5. Kernel's `_var_writers['x']` still points to deleted `cell_1` ❌
6. Future cells that write `x` won't create proper dependencies
7. **Result**: Dependency graph becomes inconsistent

## Code References

### Key Files Involved

**REST API (File Storage Only)**:
- `backend/app/api/cells.py:13-47` - `create_cell()` endpoint
- `backend/app/api/cells.py:49-63` - `delete_cell()` endpoint

**WebSocket Handler (Missing Handlers)**:
- `backend/app/websocket/handler.py:63-84` - No handlers for `create_cell` or `delete_cell`

**Coordinator (Missing Methods)**:
- `backend/app/orchestration/coordinator.py` - No `handle_cell_create()` or `handle_cell_delete()` methods

**Kernel (Missing IPC Types)**:
- `backend/app/kernel/types.py` - No `CreateCellRequest` or `DeleteCellRequest` types
- `backend/app/kernel/process.py` - No handlers for cell creation/deletion
- `backend/app/core/graph.py:138-152` - `remove_cell()` method exists but unused

**Frontend (Expects WebSocket Messages)**:
- `frontend/src/components/NotebookApp.tsx:102-112` - Handler for `cell_created` (never received)
- `frontend/src/components/NotebookApp.tsx:114-116` - Handler for `cell_deleted` (never received)
- `frontend/src/components/NotebookApp.tsx:178-188` - `addCell()` calls REST API
- `frontend/src/components/NotebookApp.tsx:190-208` - `deleteCell()` calls REST API

## Architecture Insights

### Pattern: All CRUD Operations Have Same Issue

The investigation reveals a **systematic pattern**:

| Operation | REST API | Coordinator | Kernel | WebSocket | Status |
|-----------|----------|--------------|--------|-----------|--------|
| **Create Cell** | ✅ Updates file | ❌ Not notified | ❌ Not registered | ❌ No message | **BROKEN** |
| **Update Cell** | ✅ Updates file | ❌ Not notified | ❌ Not re-registered | ✅ Has handler (unused) | **BROKEN** (see previous research) |
| **Delete Cell** | ✅ Updates file | ❌ Not notified | ❌ Not removed | ❌ No message | **BROKEN** |
| **Run Cell** | N/A | ✅ Handles via WebSocket | ✅ Executes | ✅ Works | **WORKS** |

**Root Cause**: REST API and WebSocket/Coordinator layers are completely disconnected. REST API only touches file storage, never notifies the execution layer.

### Kernel State Management

The kernel maintains two critical data structures:

1. **`cell_registry: Dict[str, tuple[str, str]]`** - Maps cell_id → (code, cell_type)
   - Updated only via `register_cell` messages
   - Used during execution to look up cell code
   - **Problem**: Never cleaned up when cells deleted

2. **`DependencyGraph`** - NetworkX DiGraph with variable mappings
   - Updated via `graph.update_cell()` on registration
   - Has `graph.remove_cell()` method but never called
   - **Problem**: Stale nodes and edges accumulate

**Impact**: Kernel state diverges from file storage state over time, causing:
- Execution errors (trying to run deleted cells)
- Stale dependency edges (dependencies on deleted cells)
- Inconsistent variable writer mappings

### Frontend Optimistic Updates

The frontend code shows **optimistic update patterns**:

```typescript
// frontend/src/components/NotebookApp.tsx:182
const { cell_id } = await api.createCell(notebookId, type, afterCellId);
// Cell will be added via WebSocket message
setTimeout(() => setFocusedCellId(cell_id), 100);
```

The comment "Cell will be added via WebSocket message" suggests the frontend **expects** the backend to broadcast the creation, but the backend never does. The frontend likely works because:
1. It optimistically updates local state
2. On page reload, it fetches notebook from REST API (which has the cell)
3. But during the session, WebSocket state is out of sync

## Related Research

- `thoughts/shared/research/2026-01-07-reactive-cell-update-cascade-failure.md` - Cell update synchronization failure (same root cause)
- `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md` - Architecture separation between layers
- `thoughts/shared/plans/2026-01-07-reactive-cell-update-websocket-sync.md` - Proposed solution for cell updates

## Proposed Solutions

### Solution A: Add WebSocket Message Types for CRUD (Recommended)

Extend the WebSocket protocol to handle all cell CRUD operations, similar to the cell update solution.

**Pros**:
- Consistent with reactive architecture
- Single source of truth (WebSocket for all state changes)
- Real-time synchronization across clients
- Coordinator naturally handles updates

**Cons**:
- Breaking change to frontend-backend protocol
- Requires coordinator methods for create/delete

**Implementation**:

1. **Add Kernel IPC Types** (`backend/app/kernel/types.py`):

```python
class RemoveCellRequest(BaseModel):
    """Request to remove a cell from the dependency graph."""
    type: Literal["remove_cell"] = "remove_cell"
    cell_id: str

class RemoveCellResult(BaseModel):
    """Result of cell removal."""
    type: Literal["remove_result"] = "remove_result"
    cell_id: str
    status: Literal["success", "error"]
    error: str | None = None
```

2. **Add Kernel Handler** (`backend/app/kernel/process.py`):

```python
# In kernel_main loop, after register_cell handler:
if request_data.get('type') == 'remove_cell':
    try:
        from .types import RemoveCellRequest, RemoveCellResult
        remove_req = RemoveCellRequest(**request_data)
        
        # Remove from dependency graph
        graph.remove_cell(remove_req.cell_id)
        
        # Remove from cell registry
        if remove_req.cell_id in cell_registry:
            del cell_registry[remove_req.cell_id]
        
        result = RemoveCellResult(
            cell_id=remove_req.cell_id,
            status='success'
        )
        output_queue.put(result.model_dump())
    except Exception as e:
        result = RemoveCellResult(
            cell_id=remove_req.cell_id,
            status='error',
            error=str(e)
        )
        output_queue.put(result.model_dump())
    continue
```

3. **Add Coordinator Methods** (`backend/app/orchestration/coordinator.py`):

```python
async def handle_cell_create(self, cell_type: str, after_cell_id: Optional[str] = None):
    """Handle a new cell creation."""
    if not self.notebook:
        return
    
    # Create new cell
    cell_id = str(uuid4())
    new_cell = CellResponse(
        id=cell_id,
        type=cell_type,
        code="",
        status="idle",
    )
    
    # Insert at correct position
    if after_cell_id:
        insert_index = next(
            (i for i, c in enumerate(self.notebook.cells) if c.id == after_cell_id),
            None
        )
        if insert_index is not None:
            self.notebook.cells.insert(insert_index + 1, new_cell)
        else:
            self.notebook.cells.append(new_cell)
    else:
        self.notebook.cells.append(new_cell)
    
    # Persist to file storage
    NotebookFileStorage.serialize_notebook(self.notebook)
    
    # Register with kernel (empty code, no dependencies yet)
    register_req = RegisterCellRequest(
        cell_id=cell_id,
        code="",
        cell_type=cell_type
    )
    self.kernel.input_queue.put(register_req.model_dump())
    
    # Read registration result
    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
    
    # Broadcast creation
    insert_index = next(
        (i for i, c in enumerate(self.notebook.cells) if c.id == cell_id),
        None
    )
    await self.broadcaster.broadcast({
        'type': 'cell_created',
        'cellId': cell_id,
        'cell': {
            'id': cell_id,
            'type': cell_type,
            'code': '',
            'status': 'idle'
        },
        'index': insert_index
    })

async def handle_cell_delete(self, cell_id: str):
    """Handle a cell deletion."""
    if not self.notebook:
        return
    
    # Find and remove cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return
    
    # Remove from in-memory notebook
    self.notebook.cells = [c for c in self.notebook.cells if c.id != cell_id]
    
    # Persist to file storage
    NotebookFileStorage.serialize_notebook(self.notebook)
    
    # Remove from kernel
    remove_req = RemoveCellRequest(cell_id=cell_id)
    self.kernel.input_queue.put(remove_req.model_dump())
    
    # Read removal result
    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
    
    # Broadcast deletion
    await self.broadcaster.broadcast({
        'type': 'cell_deleted',
        'cellId': cell_id
    })
```

4. **Add WebSocket Handlers** (`backend/app/websocket/handler.py`):

```python
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "cell_update":
        cell_id = message.get("cellId")
        new_code = message.get("code")
        if cell_id and new_code is not None:
            await coordinator.handle_cell_update(cell_id, new_code)
    
    elif msg_type == "create_cell":
        cell_type = message.get("type")  # 'python' or 'sql'
        after_cell_id = message.get("afterCellId")
        if cell_type:
            await coordinator.handle_cell_create(cell_type, after_cell_id)
    
    elif msg_type == "delete_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_cell_delete(cell_id)
    
    elif msg_type == "update_db_connection":
        # ... existing handler ...
    
    elif msg_type == "run_cell":
        # ... existing handler ...
    
    else:
        print(f"Unknown message type: {msg_type}")
```

5. **Update Frontend** (`frontend/src/components/NotebookApp.tsx`):

```typescript
const addCell = async (type: CellType, afterCellId?: string) => {
    if (!notebookId) return;
    
    // Send via WebSocket instead of REST API
    sendMessage({ 
        type: 'create_cell', 
        cellType: type,  // Note: different from message type
        afterCellId: afterCellId 
    });
};

const deleteCell = async (id: string) => {
    if (!notebookId) return;

    if (cells.length <= 1) {
        await updateCellCode(id, "");
        return;
    }

    // Send via WebSocket instead of REST API
    sendMessage({ 
        type: 'delete_cell', 
        cellId: id 
    });
};
```

### Solution B: Make REST Endpoints Notify Coordinator (Alternative)

Keep REST API but add coordinator registry/notification mechanism.

**Pros**:
- No breaking changes to frontend
- Maintains REST API for external clients

**Cons**:
- More complex: requires coordinator registry
- Race conditions between REST and WebSocket
- Multiple coordinators per notebook (one per connection)

**Implementation Sketch**:

1. Create `CoordinatorRegistry` singleton to track active coordinators per notebook
2. REST endpoints call registry to notify coordinators
3. Each coordinator updates in-memory state and notifies kernel
4. Coordinators broadcast WebSocket messages

**Challenges**:
- Need to track which notebook each coordinator manages
- Need to handle coordinators that disconnect
- Potential race: REST delete → WebSocket run (cell already deleted)

### Solution C: Reload Notebook on Every Operation (Not Recommended)

Simplest but worst performance: always reload notebook from storage.

**Pros**:
- Minimal code changes
- Guarantees consistency

**Cons**:
- Performance overhead (file I/O on every operation)
- Doesn't update dependency graph until reload
- Doesn't fix kernel state divergence

## Recommendation

**Solution A (WebSocket for all CRUD)** is the best approach, consistent with the cell update solution:

1. **Unified Protocol**: All state changes go through WebSocket
2. **Real-time Sync**: All connected clients receive updates immediately
3. **Kernel Consistency**: Kernel state always matches coordinator state
4. **Reactive Architecture**: Aligns with the reactive execution design
5. **Single Source of Truth**: WebSocket becomes the authoritative channel

**Migration Path**:
1. Implement WebSocket handlers (backend)
2. Update frontend to use WebSocket (frontend)
3. Deprecate REST CRUD endpoints (optional, for external API compatibility)
4. Add integration tests for create/delete operations

## Next Steps

1. **Immediate**: Document the bugs (this research document) ✅
2. **Short-term**: Implement Solution A for cell creation and deletion
3. **Testing**: Add integration tests that verify:
   - Creating a cell registers it with kernel
   - Deleting a cell removes it from kernel graph
   - Reactive cascades don't reference deleted cells
   - Multiple clients see create/delete in real-time
4. **Long-term**: Consider deprecating REST CRUD endpoints in favor of WebSocket-only approach

