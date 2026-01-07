---
date: 2026-01-07 14:09:15 GMT
planner: Matthew Carter
topic: "WebSocket-Based Cell CRUD Operations with Reactive Deletion"
tags: [planning, implementation, websocket, crud, reactive-execution, dependency-graph, kernel-sync]
status: draft
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# WebSocket-Based Cell CRUD Operations with Reactive Deletion Implementation Plan

**Date**: 2026-01-07 14:09:15 GMT  
**Planner**: Matthew Carter

## Overview

This plan implements **Solution A** from `thoughts/shared/research/2026-01-07-crud-operations-kernel-sync-failure.md`: migrating cell creation and deletion operations from REST API to WebSocket protocol. This ensures that all cell CRUD operations are synchronized with the kernel's dependency graph and coordinator's in-memory state, enabling proper reactive execution including cascades triggered by cell deletion.

**Core Problem**: Currently, cell creation and deletion via REST API only update file storage. The kernel's dependency graph, cell registry, and coordinator's in-memory notebook remain out of sync, causing:
- New cells cannot execute until page reload
- Deleted cells remain in dependency graph with stale edges
- Frontend expects WebSocket messages (`cell_created`, `cell_deleted`) that never arrive

**Solution**: Extend WebSocket protocol to handle all cell CRUD operations, with deletion triggering reactive cascades for dependent cells.

## Current State Analysis

### What Exists Now

**REST API Layer** (`backend/app/api/cells.py`):
- `POST /api/v1/notebooks/{id}/cells` - Creates cell, only updates file storage (line 13-47)
- `DELETE /api/v1/notebooks/{id}/cells/{cell_id}` - Deletes cell, only updates file storage (line 49-63)
- Both endpoints **do not** notify coordinator or kernel

**WebSocket Layer** (`backend/app/websocket/handler.py`):
- Handles `cell_update`, `update_db_connection`, `run_cell` messages (line 71-92)
- **Missing handlers** for `create_cell` and `delete_cell`
- Already has working broadcast infrastructure via `ConnectionManager`

**Coordinator** (`backend/app/orchestration/coordinator.py`):
- `handle_cell_update()` - Updates code and re-registers with kernel (line 64-122)
- `handle_db_connection_update()` - Configures DB in kernel (line 124-159)
- `handle_run_cell()` - Executes cell and reactive cascade (line 161-183)
- **Missing methods** for `handle_cell_create()` and `handle_cell_delete()`

**Kernel IPC** (`backend/app/kernel/types.py`, `backend/app/kernel/process.py`):
- Supports `RegisterCellRequest` for adding/updating cells in dependency graph
- **Missing**: `RemoveCellRequest` IPC message type
- `DependencyGraph.remove_cell()` exists but is never called (backend/app/core/graph.py:138-152)

**Frontend** (`frontend/src/components/NotebookApp.tsx`, `frontend/src/useNotebookWebSocket.ts`):
- Expects `cell_created` message (line 94-106 of NotebookApp.tsx)
- Expects `cell_deleted` message (line 107-109 of NotebookApp.tsx)
- Currently calls REST API for create/delete (line 153-191 of NotebookApp.tsx)

### Key Constraints

1. **Per-Connection Architecture**: Each WebSocket connection has its own `NotebookCoordinator` and kernel process
2. **Broadcast for Multi-Client**: `ConnectionManager.broadcast()` sends to all connected clients
3. **File Storage as Source of Truth**: File storage remains the persistent state; coordinator/kernel hold ephemeral execution state
4. **Reactive Cascades**: Kernel computes execution order using `DependencyGraph.get_execution_order()`
5. **IPC Pattern**: Coordinator sends typed requests to kernel input queue, reads results from output queue

## System Context Analysis

The system follows a **dual-protocol architecture**:
- **REST API**: Originally intended for CRUD operations and persistence
- **WebSocket**: Originally intended for execution and real-time updates

This plan addresses the **root cause** of the synchronization issues by unifying all state-changing operations under the WebSocket protocol. This is not a symptom fix; it's an architectural correction that aligns with the system's reactive execution design.

**Why WebSocket for CRUD is the right approach**:
1. Single source of truth for state changes
2. Real-time synchronization across all connected clients
3. Coordinator naturally manages the transaction: file storage + kernel + broadcast
4. Enables reactive cascades on deletion (requirement from user)
5. Consistent with existing `cell_update` pattern

**What about REST API compatibility?**
- Keep REST endpoints as **thin wrappers** that forward to WebSocket internally
- This maintains backward compatibility while using WebSocket as the implementation layer

## Desired End State

After this implementation:

1. **Cell Creation**:
   - Frontend sends `create_cell` WebSocket message
   - Coordinator creates cell, persists to file, registers with kernel
   - Coordinator broadcasts `cell_created` to all clients
   - New cell appears in UI immediately and is ready for execution
   - All clients see the new cell in real-time

2. **Cell Deletion**:
   - Frontend sends `delete_cell` WebSocket message
   - Coordinator determines which cells depend on the deleted cell
   - Coordinator deletes cell, persists to file, removes from kernel
   - **Reactive cascade**: Dependent cells are re-executed to reflect variable changes
   - Coordinator broadcasts `cell_deleted` and execution results
   - Deleted cell disappears from UI immediately
   - All clients see deletion and cascade updates in real-time

3. **Verification**:
   - Create a cell, add code, run it → works without reload ✅
   - Delete a cell that other cells depend on → downstream cells re-execute ✅
   - Multiple browser tabs show consistent state ✅
   - No stale dependency graph edges ✅

## What We're NOT Doing

1. **Not modifying REST API behavior** (yet) - keeping for backward compatibility
2. **Not implementing undo/redo** for cell operations
3. **Not adding cell move/reorder** operations (different feature)
4. **Not changing execution order algorithm** - reusing `get_execution_order()`
5. **Not optimizing file storage format** - keeping current serialization
6. **Not adding bulk operations** (create/delete multiple cells at once)
7. **Not implementing cell templates** or initialization patterns
8. **Not handling partial failures** in multi-client scenarios (rely on broadcast)

## Implementation Approach

**Strategy**: Build incrementally, following the established patterns in the codebase:

1. **Phase 1**: Add kernel IPC support for cell removal
2. **Phase 2**: Implement coordinator methods for create and delete
3. **Phase 3**: Add WebSocket message handlers
4. **Phase 4**: Update frontend to use WebSocket
5. **Phase 5**: Add integration tests
6. **Phase 6**: Clean up REST API (make thin wrappers or deprecate)

**Key Design Decisions**:

1. **Deletion triggers reactive cascade**: When deleting cell X that writes variable `v`:
   - Find all cells that read `v` using `graph.get_execution_order()`
   - Remove cell X from kernel
   - Re-execute dependent cells (they'll now fail or use undefined `v`)
   - This matches the reactive execution philosophy: notebook is always consistent

2. **Creation registers immediately**: New cells start with empty code and no dependencies:
   - Registered with kernel immediately (empty dependency graph node)
   - Ready for user to add code via `cell_update` message
   - Follows same registration flow as notebook load

3. **Transaction semantics**: Each operation is coordinator-coordinated:
   - Mutate in-memory state
   - Persist to file storage
   - Notify kernel (register/remove)
   - Broadcast to clients
   - On failure at any step: broadcast error, leave system in safe state

---

## Phase 1: Add Kernel IPC Support for Cell Removal

### Overview

Add `RemoveCellRequest` and `RemoveCellResult` message types to kernel IPC protocol, and implement handler in kernel process to remove cells from dependency graph and cell registry.

### Changes Required

#### 1. Kernel Type Definitions

**File**: `backend/app/kernel/types.py`

**Changes**: Add new request and result models after existing types (after line 68)

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

#### 2. Kernel Process Handler

**File**: `backend/app/kernel/process.py`

**Changes**: Add handler in main loop after `register_cell` handler (after line 80, before execution request fallback at line 114)

```python
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
                # Return error result
                result = RemoveCellResult(
                    cell_id=remove_req.cell_id,
                    status='error',
                    error=str(e)
                )
                output_queue.put(result.model_dump())
            continue
```

**Note**: The `graph.remove_cell()` method already exists (line 138-152 of `backend/app/core/graph.py`) and properly cleans up:
- Graph nodes and edges
- `_cell_writes` and `_cell_reads` mappings
- `_var_writers` mappings

### Success Criteria

#### Automated Verification

- [ ] Type definitions parse successfully: `python -c "from backend.app.kernel.types import RemoveCellRequest, RemoveCellResult"`
- [ ] Kernel process handles remove message without crashing (unit test)
- [ ] Dependency graph properly cleaned after removal (unit test in `backend/tests/test_graph.py`)

#### Manual Verification

- [ ] Send `RemoveCellRequest` via test script, verify `RemoveCellResult` received
- [ ] Verify removed cell no longer in `cell_registry`
- [ ] Verify removed cell no longer in dependency graph

---

## Phase 2: Implement Coordinator Methods for Create and Delete

### Overview

Add `handle_cell_create()` and `handle_cell_delete()` methods to `NotebookCoordinator`, following the same patterns as `handle_cell_update()` and `handle_run_cell()`.

### Changes Required

#### 1. Coordinator Cell Creation Method

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add method after `handle_db_connection_update()` (after line 159)

```python
    async def handle_cell_create(self, cell_type: str, after_cell_id: Optional[str] = None):
        """
        Handle a new cell creation.
        
        Args:
            cell_type: Type of cell ('python' or 'sql')
            after_cell_id: Optional ID of cell to insert after (None = append)
        """
        if not self.notebook:
            return
        
        from uuid import uuid4
        from ..models import CellResponse
        
        # Create new cell with empty code
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
                (i + 1 for i, c in enumerate(self.notebook.cells) if c.id == after_cell_id),
                None
            )
            if insert_index is not None:
                self.notebook.cells.insert(insert_index, new_cell)
            else:
                # after_cell_id not found, append to end
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
        
        if result_data.get('type') == 'register_result':
            result = RegisterCellResult(**result_data)
            if result.status == 'error':
                # This shouldn't happen for empty code, but handle it
                new_cell.status = 'blocked'
                new_cell.error = result.error
        
        # Find final index for broadcast
        final_index = next(
            (i for i, c in enumerate(self.notebook.cells) if c.id == cell_id),
            None
        )
        
        # Broadcast creation to all clients
        await self.broadcaster.broadcast({
            'type': 'cell_created',
            'cellId': cell_id,
            'cell': {
                'id': cell_id,
                'type': cell_type,
                'code': '',
                'status': new_cell.status,
                'outputs': [],
                'stdout': '',
                'reads': [],
                'writes': []
            },
            'index': final_index
        })
```

#### 2. Coordinator Cell Deletion Method

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add method after `handle_cell_create()`

```python
    async def handle_cell_delete(self, cell_id: str):
        """
        Handle a cell deletion with reactive cascade.
        
        When a cell is deleted, any cells that depended on it must be re-executed
        to reflect the fact that the variables it wrote are no longer available.
        
        Args:
            cell_id: ID of cell to delete
        """
        if not self.notebook:
            return
        
        # Find cell to delete
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            # Cell not found, nothing to do
            return
        
        # IMPORTANT: Before removing the cell, determine which cells depend on it
        # We need to get the execution order BEFORE we remove it from the graph
        # This gives us all cells that transitively depend on the deleted cell
        from .types import ExecuteRequest
        
        # Get all cells that would be affected if this cell was modified
        # (i.e., all cells that depend on it)
        dependent_cells = []
        try:
            # Get execution order - this includes the cell itself plus dependents
            execution_order = self.kernel.get_execution_order(cell_id)
            # Remove the cell being deleted from the list (we don't want to execute it)
            dependent_cells = [cid for cid in execution_order if cid != cell_id]
        except:
            # If we can't get execution order, no cascade needed
            pass
        
        # Remove from in-memory notebook
        self.notebook.cells = [c for c in self.notebook.cells if c.id != cell_id]
        
        # Persist to file storage
        NotebookFileStorage.serialize_notebook(self.notebook)
        
        # Remove from kernel
        from ..kernel.types import RemoveCellRequest, RemoveCellResult
        remove_req = RemoveCellRequest(cell_id=cell_id)
        self.kernel.input_queue.put(remove_req.model_dump())
        
        # Read removal result
        loop = asyncio.get_event_loop()
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        
        if result_data.get('type') == 'remove_result':
            result = RemoveCellResult(**result_data)
            if result.status == 'error':
                print(f"[Coordinator] Warning: Error removing cell from kernel: {result.error}")
        
        # Broadcast deletion to all clients
        await self.broadcaster.broadcast({
            'type': 'cell_deleted',
            'cellId': cell_id
        })
        
        # REACTIVE CASCADE: Re-execute dependent cells
        # They will now fail or produce different results since the deleted cell's
        # variables are no longer available
        for dependent_cell_id in dependent_cells:
            dependent_cell = next(
                (c for c in self.notebook.cells if c.id == dependent_cell_id),
                None
            )
            if not dependent_cell:
                continue
            
            # Execute this dependent cell
            # The kernel will cascade to any cells that depend on it
            request = ExecuteRequest(
                cell_id=dependent_cell_id,
                code=dependent_cell.code,
                cell_type=dependent_cell.type
            )
            
            results = await self._execute_via_kernel(request)
            
            # Broadcast each result
            for result in results:
                await self._broadcast_execution_result(result)
```

**Wait - problem with above approach**: We can't call `self.kernel.get_execution_order()` directly because the kernel is a separate process. We need to either:
1. Query the execution order via IPC before deleting
2. Store the dependency information in the coordinator
3. Accept that deletion won't trigger cascades (simpler, but not desired)

**Revised approach**: Get execution order by looking at what cells would be affected. Actually, since we're removing the cell, we need a different approach. Let me reconsider...

**Better approach**: After deletion, simply re-execute ALL cells that reference variables that the deleted cell wrote. We can compute this from the in-memory `reads`/`writes` metadata:

```python
    async def handle_cell_delete(self, cell_id: str):
        """
        Handle a cell deletion with reactive cascade.
        
        When a cell is deleted, any cells that read variables it wrote must be 
        re-executed to reflect the fact that those variables are no longer available.
        
        Args:
            cell_id: ID of cell to delete
        """
        if not self.notebook:
            return
        
        # Find cell to delete
        cell_to_delete = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell_to_delete:
            # Cell not found, nothing to do
            return
        
        # Find all cells that read variables written by the deleted cell
        deleted_cell_writes = set(cell_to_delete.writes or [])
        cells_to_reexecute = []
        
        for cell in self.notebook.cells:
            if cell.id == cell_id:
                continue  # Skip the cell being deleted
            cell_reads = set(cell.reads or [])
            # If this cell reads any variable that the deleted cell wrote
            if deleted_cell_writes & cell_reads:
                cells_to_reexecute.append(cell.id)
        
        # Remove from in-memory notebook
        self.notebook.cells = [c for c in self.notebook.cells if c.id != cell_id]
        
        # Persist to file storage
        NotebookFileStorage.serialize_notebook(self.notebook)
        
        # Remove from kernel
        from ..kernel.types import RemoveCellRequest, RemoveCellResult
        remove_req = RemoveCellRequest(cell_id=cell_id)
        self.kernel.input_queue.put(remove_req.model_dump())
        
        # Read removal result
        loop = asyncio.get_event_loop()
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        
        if result_data.get('type') == 'remove_result':
            result = RemoveCellResult(**result_data)
            if result.status == 'error':
                print(f"[Coordinator] Warning: Error removing cell from kernel: {result.error}")
        
        # Broadcast deletion to all clients
        await self.broadcaster.broadcast({
            'type': 'cell_deleted',
            'cellId': cell_id
        })
        
        # REACTIVE CASCADE: Re-execute cells that depend on deleted cell's variables
        for dependent_cell_id in cells_to_reexecute:
            dependent_cell = next(
                (c for c in self.notebook.cells if c.id == dependent_cell_id),
                None
            )
            if not dependent_cell:
                continue
            
            # Execute this dependent cell
            # The kernel will cascade to any cells that depend on it
            request = ExecuteRequest(
                cell_id=dependent_cell_id,
                code=dependent_cell.code,
                cell_type=dependent_cell.type
            )
            
            results = await self._execute_via_kernel(request)
            
            # Broadcast each result
            for result in results:
                await self._broadcast_execution_result(result)
```

#### 3. Import Updates

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add imports at the top (line 3)

```python
from uuid import uuid4
```

And in method bodies where needed:

```python
from ..models import CellResponse  # In handle_cell_create
from ..kernel.types import RemoveCellRequest, RemoveCellResult  # In handle_cell_delete
```

### Success Criteria

#### Automated Verification

- [ ] Coordinator instantiates without errors
- [ ] Unit tests for `handle_cell_create()` pass
- [ ] Unit tests for `handle_cell_delete()` pass
- [ ] Mock broadcaster receives correct messages

#### Manual Verification

- [ ] Create cell via coordinator method, verify in file storage
- [ ] Delete cell via coordinator method, verify removed from file storage
- [ ] Delete cell that other cells depend on, verify dependent cells re-executed
- [ ] Verify broadcasts sent to all clients

---

## Phase 3: Add WebSocket Message Handlers

### Overview

Extend `handle_message()` in WebSocket handler to dispatch `create_cell` and `delete_cell` messages to coordinator methods.

### Changes Required

#### 1. WebSocket Handler

**File**: `backend/app/websocket/handler.py`

**Changes**: Add new message handlers in `handle_message()` function (after line 79, before `update_db_connection` handler)

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
        cell_type = message.get("cellType")  # Note: 'cellType' not 'type'
        after_cell_id = message.get("afterCellId")
        if cell_type:
            await coordinator.handle_cell_create(cell_type, after_cell_id)
    
    elif msg_type == "delete_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_cell_delete(cell_id)
    
    elif msg_type == "update_db_connection":
        connection_string = message.get("connectionString")
        if connection_string is not None:
            await coordinator.handle_db_connection_update(connection_string)
    
    elif msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_run_cell(cell_id)
    
    else:
        print(f"Unknown message type: {msg_type}")
```

**Note**: Message structure matches frontend expectations:
- `create_cell`: `{ type: 'create_cell', cellType: 'python'|'sql', afterCellId?: string }`
- `delete_cell`: `{ type: 'delete_cell', cellId: string }`

### Success Criteria

#### Automated Verification

- [ ] WebSocket handler parses messages without errors
- [ ] Integration test: send `create_cell` via WebSocket, verify cell created
- [ ] Integration test: send `delete_cell` via WebSocket, verify cell deleted

#### Manual Verification

- [ ] Connect via WebSocket, send `create_cell` message, verify `cell_created` broadcast
- [ ] Connect via WebSocket, send `delete_cell` message, verify `cell_deleted` broadcast
- [ ] Multiple clients connected, verify all receive broadcasts

---

## Phase 4: Update Frontend to Use WebSocket

### Overview

Change frontend `addCell()` and `deleteCell()` functions to send WebSocket messages instead of calling REST API.

### Changes Required

#### 1. NotebookApp Cell Creation

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: Replace REST API call with WebSocket message (line 153-166)

**Old code:**

```typescript
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

**New code:**

```typescript
  const addCell = async (type: CellType, afterCellId?: string) => {
    if (!notebookId) return;
    
    // Send cell creation via WebSocket
    sendMessage({ 
      type: 'create_cell', 
      cellType: type,
      afterCellId: afterCellId 
    });
    
    // Cell will be added via WebSocket 'cell_created' message
    // We don't have the cell_id yet, so we can't focus it immediately
    // The backend will broadcast the cell_created message with the new cell_id
  };
```

**Note**: We lose the ability to immediately focus the new cell since we don't know its ID yet. We could:
1. Accept this limitation (simplest)
2. Add the new cell_id to the `cell_created` broadcast (already done - it's in the message)
3. Focus the cell when we receive the `cell_created` message

**Better approach**: Focus the cell in the `cell_created` handler:

```typescript
  const handleWebSocketMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      // ... existing handlers ...
      
      case "cell_created":
        setCells((prev) => {
          const newCells = [...prev];
          if (typeof msg.index === 'number') {
            newCells.splice(msg.index, 0, msg.cell);
          } else {
            newCells.push(msg.cell);
          }
          return newCells;
        });
        // Auto-focus newly created cell
        setTimeout(() => setFocusedCellId(msg.cellId), 100);
        break;
        
      // ... rest of handlers ...
    }
  }, []);
```

#### 2. NotebookApp Cell Deletion

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: Replace REST API call with WebSocket message (line 168-191)

**Old code:**

```typescript
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

**New code:**

```typescript
  const deleteCell = async (id: string) => {
    if (!notebookId) return;

    if (cells.length <= 1) {
      await updateCellCode(id, "");
      return;
    }

    // Update focus before deletion (while we still have access to cells array)
    if (focusedCellId === id) {
      const index = cells.findIndex((c) => c.id === id);
      const nextCell = cells[index + 1] || cells[index - 1];
      setFocusedCellId(nextCell?.id || null);
    }

    // Send cell deletion via WebSocket
    sendMessage({ 
      type: 'delete_cell', 
      cellId: id 
    });
    
    // Cell will be removed via WebSocket 'cell_deleted' message
  };
```

#### 3. Update Imports (if needed)

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: The `api` import may no longer be needed for cell CRUD. Check if it's used elsewhere in the file. If only for `createCell` and `deleteCell`, remove it. If used for notebook loading, keep it.

Actually, looking at the file, `api` is likely used for:
- Loading notebook on mount
- Maybe other operations

So keep the import for now.

### Success Criteria

#### Automated Verification

- [ ] Frontend compiles without TypeScript errors: `cd frontend && npm run typecheck`
- [ ] Frontend builds successfully: `cd frontend && npm run build`
- [ ] No console errors on load

#### Manual Verification

- [ ] Click "Add Cell" button, new cell appears immediately
- [ ] New cell is ready for editing and execution
- [ ] Delete a cell, it disappears immediately
- [ ] Delete a cell that other cells depend on, see cascade execution
- [ ] Multiple browser tabs, verify all see create/delete in real-time

---

## Phase 5: Add Integration Tests

### Overview

Add comprehensive integration tests that verify the full create/delete flow: WebSocket → Coordinator → Kernel → Broadcast.

### Changes Required

#### 1. Test Cell Creation

**File**: `backend/tests/test_crud_websocket_integration.py` (new file)

**Changes**: Create new test file

```python
"""Integration tests for WebSocket-based cell CRUD operations."""
import pytest
import asyncio
from backend.app.orchestration.coordinator import NotebookCoordinator
from backend.app.models import NotebookResponse, CellResponse
from backend.app.file_storage import NotebookFileStorage
from uuid import uuid4


class MockBroadcaster:
    """Mock broadcaster for testing."""
    def __init__(self):
        self.messages = []

    async def broadcast(self, message: dict):
        self.messages.append(message)


@pytest.fixture
def setup_notebook():
    """Create a test notebook."""
    notebook_id = str(uuid4())
    notebook = NotebookResponse(
        id=notebook_id,
        name="Test Notebook",
        cells=[],
        db_conn_string=None
    )
    NotebookFileStorage.serialize_notebook(notebook)
    yield notebook_id
    # Cleanup: delete notebook file if exists
    # (implementation depends on NotebookFileStorage)


@pytest.mark.asyncio
async def test_cell_creation_via_websocket(setup_notebook):
    """Test creating a cell via WebSocket coordinator method."""
    notebook_id = setup_notebook
    
    # Create coordinator
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)
    
    # Create a cell
    await coordinator.handle_cell_create('python', None)
    
    # Verify broadcast
    cell_created_msgs = [m for m in broadcaster.messages if m['type'] == 'cell_created']
    assert len(cell_created_msgs) == 1
    
    created_msg = cell_created_msgs[0]
    assert created_msg['cell']['type'] == 'python'
    assert created_msg['cell']['code'] == ''
    assert created_msg['cell']['status'] == 'idle'
    assert 'cellId' in created_msg
    
    # Verify in-memory notebook
    assert len(coordinator.notebook.cells) == 1
    assert coordinator.notebook.cells[0].type == 'python'
    
    # Verify file storage
    reloaded = NotebookFileStorage.parse_notebook(notebook_id)
    assert len(reloaded.cells) == 1
    
    coordinator.shutdown()


@pytest.mark.asyncio
async def test_cell_creation_with_after_cell_id(setup_notebook):
    """Test creating a cell at a specific position."""
    notebook_id = setup_notebook
    
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)
    
    # Create first cell
    await coordinator.handle_cell_create('python', None)
    first_cell_id = coordinator.notebook.cells[0].id
    
    # Create second cell
    await coordinator.handle_cell_create('python', None)
    second_cell_id = coordinator.notebook.cells[1].id
    
    # Create cell between them
    broadcaster.messages.clear()
    await coordinator.handle_cell_create('sql', first_cell_id)
    
    # Verify position
    assert len(coordinator.notebook.cells) == 3
    assert coordinator.notebook.cells[0].id == first_cell_id
    assert coordinator.notebook.cells[1].type == 'sql'  # Inserted after first
    assert coordinator.notebook.cells[2].id == second_cell_id
    
    # Verify broadcast includes correct index
    cell_created_msg = [m for m in broadcaster.messages if m['type'] == 'cell_created'][0]
    assert cell_created_msg['index'] == 1
    
    coordinator.shutdown()


@pytest.mark.asyncio
async def test_cell_deletion_via_websocket(setup_notebook):
    """Test deleting a cell via WebSocket coordinator method."""
    notebook_id = setup_notebook
    
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)
    
    # Create a cell first
    await coordinator.handle_cell_create('python', None)
    cell_id = coordinator.notebook.cells[0].id
    
    broadcaster.messages.clear()
    
    # Delete the cell
    await coordinator.handle_cell_delete(cell_id)
    
    # Verify broadcast
    cell_deleted_msgs = [m for m in broadcaster.messages if m['type'] == 'cell_deleted']
    assert len(cell_deleted_msgs) == 1
    assert cell_deleted_msgs[0]['cellId'] == cell_id
    
    # Verify in-memory notebook
    assert len(coordinator.notebook.cells) == 0
    
    # Verify file storage
    reloaded = NotebookFileStorage.parse_notebook(notebook_id)
    assert len(reloaded.cells) == 0
    
    coordinator.shutdown()


@pytest.mark.asyncio
async def test_cell_deletion_triggers_cascade(setup_notebook):
    """Test that deleting a cell triggers re-execution of dependent cells."""
    notebook_id = setup_notebook
    
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)
    
    # Create cell 1: x = 10
    await coordinator.handle_cell_create('python', None)
    cell1_id = coordinator.notebook.cells[0].id
    await coordinator.handle_cell_update(cell1_id, 'x = 10')
    
    # Run cell 1 to establish writes
    await coordinator.handle_run_cell(cell1_id)
    
    # Create cell 2: y = x + 5
    await coordinator.handle_cell_create('python', None)
    cell2_id = coordinator.notebook.cells[1].id
    await coordinator.handle_cell_update(cell2_id, 'y = x + 5')
    
    # Run cell 2 to establish reads
    await coordinator.handle_run_cell(cell2_id)
    
    broadcaster.messages.clear()
    
    # Delete cell 1 - should trigger re-execution of cell 2
    await coordinator.handle_cell_delete(cell1_id)
    
    # Verify broadcasts include:
    # 1. cell_deleted for cell1
    # 2. Execution results for cell2 (which will error because x is undefined)
    
    cell_deleted_msgs = [m for m in broadcaster.messages if m['type'] == 'cell_deleted']
    assert len(cell_deleted_msgs) == 1
    
    cell_status_msgs = [m for m in broadcaster.messages 
                        if m['type'] == 'cell_status' and m['cellId'] == cell2_id]
    assert len(cell_status_msgs) >= 2  # At least 'running' and final status
    
    # Cell 2 should error because x is no longer defined
    cell_error_msgs = [m for m in broadcaster.messages 
                       if m['type'] == 'cell_error' and m['cellId'] == cell2_id]
    assert len(cell_error_msgs) >= 1
    
    coordinator.shutdown()


@pytest.mark.asyncio
async def test_delete_nonexistent_cell(setup_notebook):
    """Test that deleting a non-existent cell doesn't crash."""
    notebook_id = setup_notebook
    
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)
    
    # Try to delete a cell that doesn't exist
    await coordinator.handle_cell_delete('nonexistent-id')
    
    # Should not crash, and should not broadcast anything
    cell_deleted_msgs = [m for m in broadcaster.messages if m['type'] == 'cell_deleted']
    assert len(cell_deleted_msgs) == 0
    
    coordinator.shutdown()
```

### Success Criteria

#### Automated Verification

- [ ] All tests pass: `cd backend && pytest tests/test_crud_websocket_integration.py -v`
- [ ] Test coverage includes create, delete, cascade scenarios
- [ ] Tests pass consistently (no flaky tests)

#### Manual Verification

- [ ] Review test output for any warnings or unexpected behavior
- [ ] Verify tests clean up resources (no orphaned kernel processes)

---

## Phase 6: Clean Up REST API

### Overview

Make REST API endpoints thin wrappers around WebSocket operations, or deprecate them entirely if not needed for external API compatibility.

### Changes Required

#### Option A: Keep REST Endpoints as Thin Wrappers

**File**: `backend/app/api/cells.py`

**Changes**: Make endpoints call coordinator methods instead of directly manipulating file storage

This requires getting access to the coordinator, which is tricky since REST endpoints don't have WebSocket connection context. We'd need a `CoordinatorRegistry` pattern (more complex).

#### Option B: Deprecate REST Endpoints (Simpler)

**File**: `backend/app/api/cells.py`

**Changes**: Add deprecation warnings and documentation

```python
@router.post("/", response_model=CreateCellResponse)
async def create_cell(notebook_id: str, request: CreateCellRequest):
    """
    Create a new cell in a notebook.
    
    **DEPRECATED**: This endpoint only updates file storage and does not synchronize
    with the kernel or broadcast to connected clients. Use WebSocket message
    'create_cell' instead for proper reactive behavior.
    
    This endpoint is maintained for backward compatibility only.
    """
    # ... existing implementation ...
    # Add warning log
    print("[WARNING] REST endpoint create_cell is deprecated. Use WebSocket instead.")
    # ... rest of implementation ...


@router.delete("/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """
    Delete a cell.
    
    **DEPRECATED**: This endpoint only updates file storage and does not synchronize
    with the kernel or broadcast to connected clients. Use WebSocket message
    'delete_cell' instead for proper reactive behavior.
    
    This endpoint is maintained for backward compatibility only.
    """
    # ... existing implementation ...
    print("[WARNING] REST endpoint delete_cell is deprecated. Use WebSocket instead.")
    # ... rest of implementation ...
```

#### Option C: Remove REST Endpoints Entirely

If no external clients use these endpoints, simply remove them:

**File**: `backend/app/api/cells.py`

**Changes**: Delete the entire file or remove the endpoints

**File**: `backend/main.py`

**Changes**: Remove the router registration if cells.py is deleted

### Decision

**Recommend Option B (Deprecation)** for this phase:
- Maintains backward compatibility
- Documents the proper way to use the API
- Allows graceful migration
- Can be removed in a future phase after confirming no usage

### Success Criteria

#### Automated Verification

- [ ] Backend starts without errors
- [ ] REST endpoints still respond (if kept)
- [ ] Deprecation warnings appear in logs (if Option B)

#### Manual Verification

- [ ] Test REST endpoints (if kept), verify they still work for basic use
- [ ] Verify WebSocket is the primary method in all new code
- [ ] Documentation updated to reflect WebSocket-first approach

---

## Testing Strategy

### Unit Tests

**What to test**:
- `RemoveCellRequest` and `RemoveCellResult` serialization/deserialization
- Kernel process handles `remove_cell` messages correctly
- `DependencyGraph.remove_cell()` properly cleans up all mappings
- Coordinator `handle_cell_create()` creates cell and broadcasts
- Coordinator `handle_cell_delete()` deletes cell and broadcasts
- Coordinator identifies dependent cells correctly

**Key edge cases**:
- Delete cell that no other cells depend on (no cascade)
- Delete cell that multiple cells depend on (multi-cell cascade)
- Delete cell with empty `writes` list (no cascade)
- Create cell with invalid `after_cell_id` (append to end)
- Concurrent create/delete operations (should be serialized by coordinator)

### Integration Tests

**End-to-end scenarios**:
1. **Basic create flow**: Send WebSocket message → Verify file storage + kernel + broadcast
2. **Basic delete flow**: Send WebSocket message → Verify file storage + kernel + broadcast
3. **Create at position**: Use `afterCellId` → Verify correct insertion
4. **Delete with cascade**: Delete cell with dependents → Verify cascade execution
5. **Multi-client sync**: Two WebSocket connections → Create in one → Verify broadcast to both
6. **Delete last cell**: Try to delete when only one cell → Verify cleared code instead

### Manual Testing Steps

1. **Test Cell Creation**:
   - Open notebook in browser
   - Click "Add Cell" button
   - Verify new cell appears immediately
   - Add code to new cell
   - Click "Run" → Verify cell executes successfully
   - Open second browser tab to same notebook → Verify both tabs show the new cell

2. **Test Cell Deletion (No Dependencies)**:
   - Create a cell with code `z = 100` (standalone)
   - Run the cell
   - Delete the cell
   - Verify cell disappears immediately
   - Verify no cascade execution
   - Verify second tab also sees deletion

3. **Test Cell Deletion (With Dependencies)**:
   - Create cell 1: `a = 5`
   - Create cell 2: `b = a * 2`
   - Create cell 3: `c = b + 1`
   - Run all cells → Verify `a=5, b=10, c=11`
   - Delete cell 1
   - Verify cell 1 disappears
   - Verify cell 2 and cell 3 show "running" status
   - Verify cell 2 shows error (undefined name 'a')
   - Verify cell 3 shows error (undefined name 'b')
   - Verify correct execution order in cascade

4. **Test Cell Creation Position**:
   - Create 3 cells
   - Click "Add Cell" after cell 1
   - Verify new cell appears between cell 1 and cell 2
   - Verify cell order maintained

5. **Test Edge Cases**:
   - Try to delete the only cell → Verify code cleared, cell remains
   - Create cell, immediately delete it → Verify no errors
   - Create multiple cells rapidly → Verify all created correctly

## Performance Considerations

### Broadcast Overhead

- Each cell create/delete broadcasts to all connected clients
- With many clients, broadcast can be slow
- **Mitigation**: Current implementation is fine for reasonable client counts (<100)
- **Future optimization**: Batch broadcasts or use pub/sub pattern

### Cascade Execution on Delete

- Deleting a cell with many dependents triggers full cascade
- Could be slow for large notebooks
- **Mitigation**: This is expected behavior (reactive execution)
- **Future optimization**: Parallel execution of independent branches in cascade

### File Storage I/O

- Each create/delete writes to file storage
- Multiple rapid operations = multiple file writes
- **Mitigation**: File I/O is fast enough for user-initiated operations
- **Future optimization**: Debounce writes or use write-behind cache

### Kernel Process Memory

- Each connection has its own kernel process
- Multiple clients = multiple kernel processes
- **Mitigation**: This is by design for isolation
- **Future optimization**: Shared kernel with multi-tenancy (major refactor)

## Migration Notes

### Data Migration

**Not applicable**: No database schema changes. File storage format unchanged.

### API Migration

**Frontend changes required**:
- Update `addCell()` to use WebSocket (Phase 4)
- Update `deleteCell()` to use WebSocket (Phase 4)
- No backend API version changes needed

**Rollout strategy**:
1. Deploy backend changes (backward compatible)
2. Deploy frontend changes (uses new WebSocket messages)
3. Monitor for errors
4. Deprecate REST endpoints after confirming no usage

### Backward Compatibility

**REST endpoints**:
- Kept as deprecated endpoints (Option B in Phase 6)
- Still work for basic file storage updates
- Don't trigger kernel sync or broadcasts
- Documented as deprecated

**Rollback plan**:
- If issues arise, frontend can revert to REST API calls
- WebSocket handlers can be disabled without breaking system
- Kernel changes (Phase 1) don't affect existing operations

## References

- **Original Research**: `thoughts/shared/research/2026-01-07-crud-operations-kernel-sync-failure.md`
- **Task Requirements**: `the_task.md` (reactive notebook implementation)
- **Related Research**: 
  - `thoughts/shared/research/2026-01-07-reactive-cell-update-cascade-failure.md` (similar issue for cell updates)
  - `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md` (architecture context)
- **Existing Patterns**:
  - `backend/app/orchestration/coordinator.py:64-122` - Cell update pattern (follow this)
  - `backend/app/websocket/handler.py:71-92` - Message handling pattern
  - `backend/app/kernel/process.py:40-80` - Kernel IPC handler pattern
- **Related Tests**:
  - `backend/tests/test_coordinator_kernel_integration.py` - Integration test patterns
  - `backend/tests/test_reactive_cascade.py` - Cascade execution tests

