---
date: 2026-01-07 13:07:47 GMT
planner: Matthew Carter
topic: "Fix Reactive Cell Update Cascade via WebSocket Synchronization"
tags: [planning, implementation, websocket, reactive-execution, bug-fix, coordinator, dependency-graph]
status: draft
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Fix Reactive Cell Update Cascade via WebSocket Synchronization Implementation Plan

**Date**: 2026-01-07 13:07:47 GMT  
**Planner**: Matthew Carter

## Overview

Fix a critical bug where editing a cell's code and re-running it doesn't update dependent cells with the new values. The root cause is a disconnect between the REST API persistence layer and the WebSocket/Coordinator execution layer. When cell code is updated via PUT request, the coordinator's in-memory state and the kernel's dependency graph are not updated, causing execution to use stale code.

**Example of the bug**:
- Cell 1: `x = 5`
- Cell 2: `y = x + 1` (outputs `y = 6`)
- User changes Cell 1 to `x = 10` and runs it
- Expected: `y = 11`
- Actual: `y = 6` (still using old value)

## Current State Analysis

### The Disconnect

The system uses a dual protocol:
1. **REST API** (`/api/v1/notebooks/{id}/cells/{cell_id}`): Used for cell CRUD operations and persistence
2. **WebSocket** (`/api/v1/ws/notebook/{notebook_id}`): Used for real-time execution and reactive cascades

**Problem**: These two channels don't communicate. When the frontend updates a cell via PUT:
1. File storage is updated ✅
2. Coordinator's in-memory `notebook.cells` still has old code ❌
3. Kernel's cell registry still has old code ❌
4. Dependency graph is never updated ❌

### Current Flow (Broken)

**File**: `backend/app/api/cells.py:49-63`
```python
@router.put("/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update a cell's code."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    # ... validation ...
    for cell in notebook.cells:
        if cell.id == cell_id:
            cell.code = request.code
            NotebookFileStorage.serialize_notebook(notebook)  # ← Only updates file!
            return {"status": "ok"}
```

**File**: `backend/app/websocket/handler.py:63-72`
```python
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    msg_type = message.get("type")
    if msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_run_cell(cell_id)  # ← Uses stale in-memory code!
    else:
        print(f"Unknown message type: {msg_type}")  # ← No handler for cell_update!
```

**File**: `frontend/src/components/NotebookApp.tsx:201-213`
```typescript
const updateCellCode = async (id: string, code: string) => {
    if (!notebookId) return;
    try {
        await api.updateCell(notebookId, id, code);  // ← HTTP PUT
    } catch (err) {
        console.error("Failed to update cell:", err);
    }
};

const runCell = (id: string) => {
    sendMessage({ type: 'run_cell', cellId: id });  // ← WebSocket
};
```

### What Already Works

The coordinator **already has** a complete `handle_cell_update` method that:
- Updates in-memory cell code
- Re-registers the cell with the kernel
- Updates the dependency graph
- Handles cycle detection errors
- Broadcasts the update to all connected clients

**File**: `backend/app/orchestration/coordinator.py:64-119`
```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Handle a cell code update."""
    # This method exists and is fully implemented, but NEVER CALLED!
```

### Key Discoveries

From analyzing the codebase and research document:

1. **The coordinator is the single source of truth** for execution state (`coordinator.py:17-31`)
2. **Registration must happen before execution** when code changes (`coordinator.py:64-119`)
3. **The frontend WebSocket hook is ready** for bidirectional messaging (`useNotebookWebSocket.ts:52-141`)
4. **Database connection updates have the same bug** (`notebooks.py:47-63` uses REST, but coordinator needs notification)
5. **Tests already use `handle_cell_update`** (`test_rich_output_integration.py` calls it directly)

## System Context Analysis

This is a **root cause fix**, not a symptom fix. The issue stems from an architectural decision to split persistence (REST API) from execution (WebSocket), but the two layers were never properly synchronized.

The chosen approach (WebSocket-first with persistence) aligns with the reactive architecture's design:
- **Single source of truth**: Coordinator manages all execution state
- **Real-time coordination**: WebSocket is the natural channel for state changes that affect execution
- **Broadcast to all clients**: Multiple connections can stay synchronized
- **Leverage existing code**: The `handle_cell_update` method is already complete

Alternative approaches (like making REST API notify coordinators) would require complex coordinator registries, potential race conditions, and wouldn't leverage the existing WebSocket infrastructure.

## Desired End State

### Functional Requirements

1. **Cell code updates trigger dependency graph updates immediately**
   - Editing a cell and running it uses the new code
   - Dependent cells recalculate with new values
   - Dependency graph reflects the new variable relationships

2. **Database connection updates reconfigure the kernel**
   - Changing db connection string updates the kernel's SQL executor
   - Error handling for invalid connections

3. **Persistence happens at appropriate times**
   - On blur (when user leaves a cell)
   - Before execution (when user runs a cell)
   - Auto-save prevents data loss

### Verification Criteria

**Automated Verification**:
- [ ] All unit tests pass: `cd backend && uv run pytest tests/`
- [ ] Integration tests pass: `uv run pytest tests/test_coordinator_kernel_integration.py`
- [ ] Rich output tests pass: `uv run pytest tests/test_rich_output_integration.py`
- [ ] No linting errors: `cd backend && uv run ruff check .`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] No TypeScript errors: `cd frontend && npm run typecheck`

**Manual Verification**:
1. Open notebook with two cells: `x = 5` and `y = x + 1`
2. Run both cells → verify `y = 6`
3. Edit cell 1 to `x = 10` (don't run yet)
4. Verify cell is auto-saved on blur
5. Run cell 1 → verify cascade runs cell 2 and outputs `y = 11`
6. Edit cell 1 to read from `z` (undefined variable)
7. Run cell 1 → verify error is shown
8. Update database connection string
9. Run SQL cell → verify it uses new connection

## What We're NOT Doing

To prevent scope creep, explicitly out of scope:

1. **Multi-user collaboration** - Not implementing conflict resolution or operational transforms
2. **Undo/redo** - Not implementing change history or reverting
3. **Cell locking** - Not preventing concurrent edits
4. **Optimistic updates** - Keeping server as source of truth
5. **Lazy execution mode** - Not implementing Marimo-style lazy evaluation (cells always auto-run for now)
6. **Custom execution delays** - Using fixed 1.5s debounce, not user-configurable

## Implementation Approach

Implement a **WebSocket-first architecture** with **auto-execution** inspired by Marimo:
1. All state-changing operations go through WebSocket messages
2. The coordinator is the single handler for these operations
3. Persistence happens within the coordinator (single responsibility)
4. **Auto-execution**: Cells auto-run after 1.5s of no typing (debounced)
5. **Run button**: Still available for explicit/immediate control
6. **REST API cleanup**: Remove PUT endpoint (this is a greenfield project, no backwards compatibility needed)

**Phasing**:
- **Phase 1**: Add WebSocket message handlers (backend)
- **Phase 2**: Wire up coordinator to persist changes (backend)
- **Phase 3**: Remove/deprecate PUT endpoints (backend cleanup)
- **Phase 4**: Update frontend to use WebSocket messages with debounced auto-execution (frontend)
- **Phase 5**: Integration testing and validation

---

## Phase 1: Add WebSocket Message Handlers

### Overview
Extend the WebSocket message handler to support `cell_update` and `update_db_connection` message types, routing them to the existing coordinator methods.

### Changes Required

#### 1. WebSocket Handler - Add Message Types

**File**: `backend/app/websocket/handler.py`

**Changes**: Add handlers for `cell_update` and `update_db_connection` messages

```python
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "cell_update":
        cell_id = message.get("cellId")
        new_code = message.get("code")
        if cell_id and new_code is not None:
            await coordinator.handle_cell_update(cell_id, new_code)
    
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

**Rationale**: Route messages to coordinator methods. The coordinator already has `handle_cell_update`, we just need to add `handle_db_connection_update`.

#### 2. Update Message Type Validation (Optional)

If there's a message schema/validation layer, update it to include:
- `cell_update` with `cellId: string` and `code: string`
- `update_db_connection` with `connectionString: string`

### Success Criteria

#### Automated Verification
- [ ] No syntax errors: `cd backend && python -m py_compile app/websocket/handler.py`
- [ ] No linting errors: `cd backend && uv run ruff check app/websocket/handler.py`
- [ ] Type checking passes: `cd backend && uv run mypy app/websocket/handler.py` (if mypy is configured)

#### Manual Verification
- [ ] Backend starts without errors: `cd backend && uv run uvicorn main:app --reload`
- [ ] Can connect to WebSocket endpoint
- [ ] Unknown message type logs show "Unknown message type: test" when sending `{"type": "test"}`

---

## Phase 2: Add Database Connection Update Handler

### Overview
Implement the `handle_db_connection_update` method in the coordinator to update the in-memory notebook, persist to file, and reconfigure the kernel.

### Changes Required

#### 1. Coordinator - Add Database Update Handler

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add new method after `handle_cell_update` (around line 120)

```python
async def handle_db_connection_update(self, connection_string: str):
    """Handle database connection string update."""
    if not self.notebook:
        return
    
    # Update in-memory notebook
    old_connection = self.notebook.db_conn_string
    self.notebook.db_conn_string = connection_string
    
    # Persist to file storage
    NotebookFileStorage.serialize_notebook(self.notebook)
    
    # Configure kernel with new connection
    try:
        await self._configure_database(connection_string)
        
        # Broadcast success
        await self.broadcaster.broadcast({
            'type': 'db_connection_updated',
            'connectionString': connection_string,
            'status': 'success'
        })
    except RuntimeError as e:
        # Revert in-memory state on error
        self.notebook.db_conn_string = old_connection
        
        # Broadcast error
        await self.broadcaster.broadcast({
            'type': 'db_connection_updated',
            'connectionString': connection_string,
            'status': 'error',
            'error': str(e)
        })
        
        # Re-raise to log the error
        raise
```

**Rationale**: 
- Update in-memory state first for fast access
- Persist to file for durability
- Use existing `_configure_database` method to reconfigure kernel
- Broadcast result to all connected clients
- Handle errors gracefully with rollback

### Success Criteria

#### Automated Verification
- [ ] No syntax errors: `cd backend && python -m py_compile app/orchestration/coordinator.py`
- [ ] No linting errors: `cd backend && uv run ruff check app/orchestration/coordinator.py`
- [ ] Integration tests pass: `cd backend && uv run pytest tests/test_coordinator_kernel_integration.py`

#### Manual Verification
- [ ] Method signature matches `_configure_database` expectations
- [ ] Error handling prevents invalid connection strings from crashing the kernel

---

## Phase 3: Add Persistence to Cell Update Handler

### Overview
Modify the existing `handle_cell_update` method to also persist changes to file storage.

### Changes Required

#### 1. Coordinator - Add Persistence to Cell Update

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add persistence call after updating in-memory state (around line 75)

```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Handle a cell code update."""
    if not self.notebook:
        return

    # Find cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Update code in memory
    cell.code = new_code
    
    # Persist to file storage
    NotebookFileStorage.serialize_notebook(self.notebook)

    # Register updated cell with kernel to update dependency graph
    # ... rest of existing method ...
```

**Rationale**: 
- Persist immediately after updating in-memory state
- If registration fails (e.g., cycle detected), the file still has the new code
- User's edits are never lost

### Success Criteria

#### Automated Verification
- [ ] Unit tests pass: `cd backend && uv run pytest tests/test_rich_output_integration.py`
- [ ] No linting errors: `cd backend && uv run ruff check app/orchestration/coordinator.py`

#### Manual Verification
- [ ] Verify file is updated: edit cell via WebSocket, check `backend/notebooks/*.py` file
- [ ] Verify in-memory and file state match after update

---

## Phase 3: Remove PUT Endpoints (Cleanup)

### Overview
Since this is a greenfield project (take-home assignment), we don't need backwards compatibility. Remove the PUT endpoints that are now superseded by WebSocket messages.

### Changes Required

#### 1. Remove Cell Update PUT Endpoint

**File**: `backend/app/api/cells.py`

**Changes**: Remove the `update_cell` endpoint (lines 49-63)

**Delete this entire function**:
```python
@router.put("/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update a cell's code."""
    # ... (delete entire function)
```

**Rationale**: 
- WebSocket `cell_update` message now handles this
- Eliminates the dual-protocol confusion
- Simpler architecture with single source of truth

#### 2. Simplify Database Connection Update

**File**: `backend/app/api/notebooks.py`

**Changes**: Remove coordinator notification logic (lines 57-61) since WebSocket handles it

**OLD** (lines 47-63):
```python
@router.put("/{notebook_id}/db")
async def update_db_connection(notebook_id: str, request: UpdateDbConnectionRequest):
    """Update database connection string."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook.db_conn_string = request.connection_string
    NotebookFileStorage.serialize_notebook(notebook)

    # Notify active coordinators for this notebook
    from ..websocket.handler import manager
    for coordinator in manager.coordinators.values():
        if coordinator.notebook_id == notebook_id:
            await coordinator._configure_database(request.connection_string)

    return {"status": "ok"}
```

**NEW**: Remove this endpoint entirely - WebSocket `update_db_connection` handles it

**Rationale**: WebSocket message is the canonical way to update database connection, keeping coordinator as single source of truth

### Success Criteria

#### Automated Verification
- [ ] Backend starts without errors: `cd backend && uv run uvicorn main:app --reload`
- [ ] No import errors: `cd backend && python -c "from app.api import cells, notebooks"`
- [ ] Routes reflect changes: Check `http://localhost:8000/docs` - PUT endpoints should be gone

#### Manual Verification
- [ ] Swagger UI at `/docs` shows only WebSocket-based flow
- [ ] Attempting to call removed endpoints returns 404
- [ ] All functionality works via WebSocket

---

## Phase 4: Update Frontend with Auto-Execution

### Overview
Replace HTTP PUT calls with WebSocket messages, and add **debounced auto-execution** after typing stops (~1.5 seconds). The run button remains for immediate/explicit control, matching the task requirement: "No manual 'run' buttons needed (though optional for explicit control)".

**Marimo-Inspired Behavior**:
- **Auto-run**: Cell auto-executes 1.5s after user stops typing
- **Run button**: Still available for immediate execution
- **Visual feedback**: Show "will auto-run in..." indicator during debounce

### Changes Required

#### 1. Frontend - Add Debounced Auto-Execution Hook

**File**: `frontend/src/components/NotebookCell.tsx`

**Changes**: Add debounced auto-execution logic

**NEW**: Add auto-run logic with debounce (add after imports, around line 20)

```typescript
import { useEffect, useRef, useState, useCallback } from 'react';

// Inside NotebookCell component:
const [autoRunTimer, setAutoRunTimer] = useState<NodeJS.Timeout | null>(null);
const AUTO_RUN_DELAY = 1500; // 1.5 seconds

// Clear existing timer when code changes
useEffect(() => {
  if (autoRunTimer) {
    clearTimeout(autoRunTimer);
  }
  
  // Don't auto-run if code hasn't changed
  if (localCode === cell.code) {
    return;
  }
  
  // Set auto-run timer
  const timer = setTimeout(() => {
    handleRun(); // Auto-execute after delay
  }, AUTO_RUN_DELAY);
  
  setAutoRunTimer(timer);
  
  return () => {
    clearTimeout(timer);
  };
}, [localCode]);

// Cancel auto-run on blur (will save but not run)
const handleEditorBlur = async () => {
  if (autoRunTimer) {
    clearTimeout(autoRunTimer);
    setAutoRunTimer(null);
    setAutoRunCountdown(null);
  }
  
  if (hasUnsavedChangesRef.current && localCode !== cell.code) {
    await onUpdateCode(localCode);
    hasUnsavedChangesRef.current = false;
  }
};
```

**Rationale**:
- Matches Marimo's auto-execution model
- 1.5s delay is long enough to avoid triggering on every keystroke
- Blur cancels auto-run (just saves) - user may be switching focus, not wanting to run
- Silent auto-execution keeps UI clean and unobtrusive

#### 2. Frontend - Update Cell Code via WebSocket

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: Replace `updateCellCode` method (around line 201-209)

**OLD**:
```typescript
const updateCellCode = async (id: string, code: string) => {
    if (!notebookId) return;
    try {
        await api.updateCell(notebookId, id, code);
    } catch (err) {
        console.error("Failed to update cell:", err);
    }
};
```

**NEW**:
```typescript
const updateCellCode = async (id: string, code: string) => {
    if (!notebookId) return;
    
    // Send cell update via WebSocket
    sendMessage({ 
        type: 'cell_update', 
        cellId: id, 
        code: code 
    });
};
```

**Rationale**: 
- WebSocket is faster (no HTTP overhead)
- Coordinator handles persistence
- All connected clients receive the update in real-time
- Debouncing prevents excessive updates during typing

**Note**: This replaces both the HTTP PUT call AND the blur-based save. The auto-run flow handles both saving and executing.

#### 3. Frontend - Update Database Connection via WebSocket

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: Replace `handleDbConnectionUpdate` method (around line 232-240)

**OLD**:
```typescript
const handleDbConnectionUpdate = async () => {
    if (!notebookId) return;
    try {
        await api.updateDbConnection(notebookId, dbConnection);
    } catch (err) {
        console.error("Failed to update DB connection:", err);
    }
};
```

**NEW**:
```typescript
const handleDbConnectionUpdate = async () => {
    if (!notebookId) return;
    
    sendMessage({ 
        type: 'update_db_connection', 
        connectionString: dbConnection 
    });
};
```

**Rationale**: 
- Consistent with cell update pattern
- Kernel reconfigures immediately
- Error messages broadcast via WebSocket

#### 3. Frontend - Handle Database Connection Update Response

**File**: `frontend/src/components/NotebookApp.tsx`

**Changes**: Add new case to `handleWebSocketMessage` (around line 160)

```typescript
const handleWebSocketMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
        // ... existing cases ...
        
        case "db_connection_updated":
            if (msg.status === 'error') {
                console.error("Failed to update DB connection:", msg.error);
                // Optionally: show toast notification
            } else {
                console.log("DB connection updated successfully");
                // Optionally: show success toast
            }
            break;
    }
}, []);
```

**Rationale**: Provide user feedback for database connection updates

#### 4. Frontend - Update WebSocket Message Type

**File**: `frontend/src/useNotebookWebSocket.ts`

**Changes**: Add new message types to `WSMessage` union (around line 8-24)

```typescript
export type WSMessage =
  | {
      type: "cell_updated";
      cellId: string;
      cell: { code: string; reads: string[]; writes: string[]; status: string };
    }
  | { type: "cell_created"; cellId: string; cell: CellResponse; index?: number }
  | { type: "cell_deleted"; cellId: string }
  | { type: "cell_status"; cellId: string; status: CellStatus }
  | { type: "cell_stdout"; cellId: string; data: string }
  | { type: "cell_error"; cellId: string; error: string }
  | { type: "cell_output"; cellId: string; output: OutputResponse }
  | { 
      type: "db_connection_updated"; 
      connectionString: string; 
      status: "success" | "error"; 
      error?: string 
    };
```

**Rationale**: TypeScript type safety for new message

### Success Criteria

#### Automated Verification
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] No TypeScript errors: `cd frontend && npm run typecheck`
- [ ] No linting errors: `cd frontend && npm run lint`

#### Manual Verification
- [ ] Cell updates work without page refresh
- [ ] Changes persist after browser refresh
- [ ] **Auto-run: Type in a cell, wait 1.5s, see it execute automatically (silently)**
- [ ] **Auto-run cancel: Blur/focus away cancels auto-run, just saves**
- [ ] **Run button: Clicking run button immediately executes (skips auto-run timer)**
- [ ] Database connection updates show success/error feedback
- [ ] No network errors in browser console

---

## Phase 5: Integration Testing and Validation

### Overview
Comprehensive testing of the entire flow from frontend to kernel and back.

### Testing Strategy

#### Unit Tests

**File**: Create `backend/tests/test_websocket_cell_update.py`

```python
import pytest
from app.orchestration.coordinator import NotebookCoordinator
from app.websocket.handler import ConnectionManager

@pytest.mark.asyncio
async def test_cell_update_via_websocket():
    """Test that cell updates via WebSocket update the dependency graph."""
    manager = ConnectionManager()
    coordinator = NotebookCoordinator(broadcaster=manager)
    
    # Load test notebook
    await coordinator.load_notebook("test-reactive")
    
    # Update cell code
    await coordinator.handle_cell_update("cell1", "x = 10")
    
    # Run cell and dependent cells
    results = await coordinator._execute_via_kernel(
        ExecuteRequest(cell_id="cell1", code="x = 10", cell_type="python")
    )
    
    # Verify cascade executed with new code
    assert len(results) == 2  # cell1 and cell2
    assert results[0].writes == ["x"]
    assert results[1].reads == ["x"]

@pytest.mark.asyncio
async def test_db_connection_update():
    """Test that database connection updates reconfigure the kernel."""
    manager = ConnectionManager()
    coordinator = NotebookCoordinator(broadcaster=manager)
    
    await coordinator.load_notebook("test-sql")
    
    # Update connection string
    await coordinator.handle_db_connection_update(
        "postgresql://user:pass@localhost:5432/testdb"
    )
    
    # Verify notebook state updated
    assert coordinator.notebook.db_conn_string == "postgresql://user:pass@localhost:5432/testdb"
```

**Rationale**: Ensure WebSocket flow matches the existing REST API behavior

#### Integration Tests

Add to existing `backend/tests/test_coordinator_kernel_integration.py`:

```python
@pytest.mark.asyncio
async def test_cell_update_cascade(coordinator):
    """Test that updating a cell triggers cascade with new values."""
    # Register initial cells
    await coordinator.handle_cell_update("c1", "x = 5")
    await coordinator.handle_cell_update("c2", "y = x + 1")
    
    # Run cells
    await coordinator.handle_run_cell("c1")
    
    # Update c1
    await coordinator.handle_cell_update("c1", "x = 10")
    
    # Run c1 again
    results = await coordinator._execute_via_kernel(
        ExecuteRequest(cell_id="c1", code="x = 10", cell_type="python")
    )
    
    # Verify c2 recalculated with new value
    c2_result = next((r for r in results if r.cell_id == "c2"), None)
    assert c2_result is not None
    assert "11" in c2_result.stdout or any("11" in str(o.data) for o in c2_result.outputs)
```

**Rationale**: Test the exact bug scenario from the research document

#### Manual Testing Steps

1. **Basic Cell Update and Cascade (Manual Run)**
   - [ ] Open notebook in browser
   - [ ] Create cell 1: `x = 5`
   - [ ] Create cell 2: `y = x + 1`
   - [ ] Click run on cell 1 → verify cell 2 runs automatically and outputs `y = 6`
   - [ ] Edit cell 1 to `x = 10`
   - [ ] Click run on cell 1 → verify cell 2 outputs `y = 11`

1b. **Auto-Execution After Typing Stops**
   - [ ] Edit cell 1 to `x = 20`
   - [ ] Wait 1.5s without typing → verify cell auto-runs silently
   - [ ] Verify cell 2 cascades and outputs `y = 21`
   - [ ] Edit cell 1 to `x = 25`
   - [ ] Before 1.5s elapses, blur/click away
   - [ ] Verify cell does NOT auto-run (just saves)
   - [ ] Verify changes are saved (refresh browser, see `x = 25`)

2. **Dependency Graph Updates**
   - [ ] Create cell 1: `a = 1`
   - [ ] Create cell 2: `b = a + 1`
   - [ ] Run cell 1 → verify cascade
   - [ ] Edit cell 1 to `c = 1` (change variable name)
   - [ ] Run cell 1 → verify cell 2 shows undefined variable error
   - [ ] Edit cell 2 to `b = c + 1`
   - [ ] Run cell 1 → verify cascade works with new variable

3. **Cycle Detection**
   - [ ] Create cell 1: `x = 1`
   - [ ] Create cell 2: `y = x + 1`
   - [ ] Run both cells → verify works
   - [ ] Edit cell 1 to `x = y + 1` (create cycle)
   - [ ] Run cell 1 → verify cycle error shown, cell marked as blocked
   - [ ] Edit cell 1 back to `x = 1`
   - [ ] Run cell 1 → verify cycle cleared, cells execute normally

4. **Database Connection**
   - [ ] Enter PostgreSQL connection string in header
   - [ ] Wait for blur event
   - [ ] Create SQL cell: `SELECT 1 as test`
   - [ ] Run SQL cell → verify connects to database
   - [ ] Change connection string to invalid value
   - [ ] Run SQL cell → verify error message shown
   - [ ] Change connection string back to valid value
   - [ ] Run SQL cell → verify works again

5. **Persistence**
   - [ ] Edit a cell
   - [ ] Wait for auto-save (blur)
   - [ ] Refresh browser
   - [ ] Verify cell has the edited code
   - [ ] Run cell → verify executes with saved code

6. **Multi-Cell Edits**
   - [ ] Edit multiple cells without running
   - [ ] Each should auto-save on blur
   - [ ] Run any cell → verify all use latest code in cascades

7. **Error Handling**
   - [ ] Edit cell to have syntax error: `x =` (incomplete)
   - [ ] Run cell → verify error shown
   - [ ] Edit to fix: `x = 5`
   - [ ] Run cell → verify works

### Performance Considerations

**WebSocket Message Size**: Cell updates send the full code string. For very large cells (>1MB), this could be slow. Mitigation: Not implementing compression for MVP, but could add gzip encoding if needed.

**Persistence Frequency**: Currently persists on every blur and before every run. This could cause high I/O if user switches cells rapidly. Mitigation: The file system should handle this fine for single-user notebooks. If needed, could add debounce.

**Broadcast Overhead**: Every update broadcasts to all connected clients. For a single-user notebook with one connection, this is negligible. For multi-user (out of scope), would need to implement targeted broadcasts.

### Success Criteria

#### Automated Verification
- [ ] All unit tests pass: `cd backend && uv run pytest tests/`
- [ ] All integration tests pass: `cd backend && uv run pytest tests/test_coordinator_kernel_integration.py tests/test_websocket_cell_update.py`
- [ ] Rich output tests pass: `cd backend && uv run pytest tests/test_rich_output_integration.py`
- [ ] Reactive cascade tests pass: `cd backend && uv run pytest tests/test_reactive_cascade.py`
- [ ] Cycle prevention tests pass: `cd backend && uv run pytest tests/test_cycle_prevention.py`
- [ ] No linting errors: `cd backend && uv run ruff check .`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] No TypeScript errors: `cd frontend && npm run typecheck`
- [ ] Frontend runs without console errors: Start frontend, open browser console, perform all manual tests

#### Manual Verification
- [ ] All manual testing steps above pass
- [ ] No WebSocket disconnections during normal usage
- [ ] No data loss when switching between cells
- [ ] Cycle detection prevents infinite loops
- [ ] Database connection errors are user-friendly
- [ ] Performance is acceptable (no noticeable lag on cell updates)

---

## Migration Notes

### No Backwards Compatibility Needed

Since this is a greenfield take-home project, we're removing the PUT endpoints entirely:
- ~~`PUT /api/v1/notebooks/{notebook_id}/cells/{cell_id}`~~ - **REMOVED**
- ~~`PUT /api/v1/notebooks/{notebook_id}/db`~~ - **REMOVED**

All updates now go through WebSocket messages:
- `{ type: 'cell_update', cellId, code }` - updates and optionally runs cells
- `{ type: 'update_db_connection', connectionString }` - updates database connection

### Deployment Strategy

1. **Deploy backend changes** (Phases 1-3)
   - Add WebSocket handlers
   - Add coordinator persistence
   - Remove PUT endpoints
   
2. **Deploy frontend changes** (Phase 4)
   - Switch to WebSocket messages
   - Add debounced auto-execution
   - Update UI for countdown indicator

3. **Test thoroughly** (Phase 5)
   - Run full manual test suite
   - Verify auto-run behavior matches expectations
   - Check for WebSocket disconnection edge cases

### Rollback Plan

If issues arise after deployment:
1. **Git revert** the changes (simple rollback)
2. **Investigate** the issue
3. **Fix and redeploy**

Note: Since this is a take-home project, there's no production system to worry about. The full implementation can be tested locally before submission.

## References

- Original research: `thoughts/shared/research/2026-01-07-reactive-cell-update-cascade-failure.md`
- Coordinator implementation: `backend/app/orchestration/coordinator.py:64-119`
- WebSocket handler: `backend/app/websocket/handler.py:63-72`
- Frontend WebSocket hook: `frontend/src/useNotebookWebSocket.ts:52-141`
- REST API cells: `backend/app/api/cells.py:49-63`
- Related architecture: `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md`
- Cycle prevention: `thoughts/shared/research/2026-01-07-cycle-prevention-architecture.md`

