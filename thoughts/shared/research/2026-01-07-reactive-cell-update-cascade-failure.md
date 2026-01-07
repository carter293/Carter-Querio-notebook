---
date: 2026-01-07 12:56:37 GMT
researcher: Matthew Carter
topic: "Reactive Cell Update and Cascade Failure Investigation"
tags: [research, codebase, reactive-execution, websocket, dependency-graph, bug-fix]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Research: Reactive Cell Update and Cascade Failure Investigation

**Date**: 2026-01-07 12:56:37 GMT  
**Researcher**: Matthew Carter

## Research Question

Why aren't subsequent cells processing updates when a cell's code is changed in the frontend? For example, when changing `x = 5` to `x = 10` and clicking run, dependent cells (like `y = x + 1`) are not recalculating with the new value.

## Summary

**Root Cause Identified**: The system has a critical disconnect between the REST API layer and the WebSocket/Coordinator layer that breaks reactive execution when cell code is updated.

**The Bug**: When a user edits a cell and clicks "Run":
1. The frontend sends a PUT request to update the cell code in file storage
2. The frontend then sends a WebSocket `run_cell` message to execute
3. The PUT endpoint updates file storage but does NOT notify the coordinator
4. The coordinator's in-memory notebook still contains the OLD code
5. When executing, the coordinator uses stale code and never re-registers with the kernel
6. The dependency graph is never updated, so reactive cascades use outdated variable relationships

**Impact**: Changing a cell's code and re-running it appears to work initially, but the reactive cascade doesn't propagate the new values because the kernel is still using the old code and dependency information.

## Detailed Findings

### Architecture Overview: Reactive Execution System

The notebook implements a sophisticated reactive execution system based on:
- **Dependency Graph** (`backend/app/core/graph.py`): DAG-based tracking of variable reads/writes
- **Kernel Process** (`backend/app/kernel/process.py`): Isolated execution environment with dependency tracking
- **Coordinator** (`backend/app/orchestration/coordinator.py`): Orchestrates execution and broadcasts results via WebSocket
- **Dual Protocol**: REST API for persistence + WebSocket for real-time execution

### The Execution Flow (How It Should Work)

#### 1. Cell Registration (Dependency Graph Update)

When a cell's code changes, it must be registered with the kernel to update the dependency graph:

```python
# backend/app/orchestration/coordinator.py:64-119
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Handle a cell code update."""
    # Update code in memory
    cell.code = new_code
    
    # Register updated cell with kernel to update dependency graph
    register_req = RegisterCellRequest(
        cell_id=cell_id,
        code=cell.code,
        cell_type=cell.type
    )
    self.kernel.input_queue.put(register_req.model_dump())
    
    # Read registration result
    result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
    
    # Broadcast the code change
    await self.broadcaster.broadcast({
        'type': 'cell_updated',
        'cellId': cell_id,
        'cell': {
            'code': cell.code,
            'reads': cell.reads,
            'writes': cell.writes
        }
    })
```

**This method exists but is never called!**

#### 2. Dependency Graph Mechanics

The dependency graph (`backend/app/core/graph.py`) maintains:
- `_graph`: NetworkX DiGraph representing cell dependencies
- `_cell_writes`: Variables each cell writes
- `_cell_reads`: Variables each cell reads  
- `_var_writers`: Latest cell that writes each variable

When `update_cell(cell_id, reads, writes)` is called:

```python
# backend/app/core/graph.py:46-110
def update_cell(self, cell_id: str, reads: Set[str], writes: Set[str]):
    # Compute new edges based on variable dependencies
    new_parent_edges = []  # From writers of vars we read
    new_child_edges = []   # To readers of vars we write
    
    # Cycle detection BEFORE mutation
    for edge in all_new_edges:
        if _would_edge_create_cycle(from_cell, to_cell):
            raise CycleDetectedError(...)
    
    # Apply update: remove old, add new edges and metadata
    # Update _var_writers mapping
```

#### 3. Reactive Cascade Execution

When a cell is executed, the kernel computes which cells need to re-run:

```python
# backend/app/kernel/process.py:127-175
# Compute cascade execution order
cells_to_run = graph.get_execution_order(request.cell_id)

# Execute all affected cells in topological order
for cell_id in cells_to_run:
    cell_code, cell_type = cell_registry[cell_id]
    exec_result = executor.execute(cell_code)
    
    # Emit ExecutionResult with cascade metadata
    result = ExecutionResult(
        cell_id=cell_id,
        status=exec_result.status,
        reads=list(cell_reads),
        writes=list(cell_writes),
        metadata={
            'cascade_index': cascade_index,
            'cascade_total': total_cells,
            'is_last': (cascade_index == total_cells - 1)
        }
    )
    output_queue.put(result.model_dump())
```

### The Broken Flow (Current Implementation)

#### Frontend: Cell Update and Run

```typescript
// frontend/src/components/NotebookCell.tsx:82-90
const handleRun = async () => {
    // Save any unsaved changes before running
    if (hasUnsavedChangesRef.current && localCode !== cell.code) {
        await onUpdateCode(localCode);  // ← Calls PUT /api/v1/notebooks/{id}/cells/{cell_id}
        hasUnsavedChangesRef.current = false;
    }
    // Then run the cell
    onRun();  // ← Sends WebSocket message { type: 'run_cell', cellId: id }
};
```

```typescript
// frontend/src/components/NotebookApp.tsx:201-213
const updateCellCode = async (id: string, code: string) => {
    if (!notebookId) return;
    try {
        await api.updateCell(notebookId, id, code);  // ← HTTP PUT request
    } catch (err) {
        console.error("Failed to update cell:", err);
    }
};

const runCell = (id: string) => {
    sendMessage({ type: 'run_cell', cellId: id });  // ← WebSocket message
};
```

#### Backend: Disconnected PUT Endpoint

```python
# backend/app/api/cells.py:49-63
@router.put("/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update a cell's code."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    # Find and update cell
    for cell in notebook.cells:
        if cell.id == cell_id:
            cell.code = request.code
            NotebookFileStorage.serialize_notebook(notebook)  # ← Only updates file!
            return {"status": "ok"}
    
    raise HTTPException(status_code=404, detail="Cell not found")
```

**Problem**: This endpoint:
- ✅ Updates the file storage
- ❌ Does NOT update the coordinator's in-memory notebook
- ❌ Does NOT re-register the cell with the kernel
- ❌ Does NOT update the dependency graph

#### Backend: WebSocket Handler Missing Cell Update

```python
# backend/app/websocket/handler.py:63-72
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")
    
    if msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_run_cell(cell_id)  # ← Executes with stale code!
    else:
        print(f"Unknown message type: {msg_type}")
```

**Problem**: No handler for `cell_update` messages, so the coordinator's `handle_cell_update` method is never called.

#### Backend: Coordinator Executes With Stale Code

```python
# backend/app/orchestration/coordinator.py:121-143
async def handle_run_cell(self, cell_id: str):
    """Execute a cell and all dependent cells via kernel."""
    if not self.notebook:
        return
    
    # Find cell - THIS USES IN-MEMORY NOTEBOOK WITH OLD CODE!
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return
    
    # Create execution request with STALE CODE
    request = ExecuteRequest(
        cell_id=cell_id,
        code=cell.code,  # ← OLD CODE from initial load
        cell_type=cell.type
    )
    
    # Send to kernel - kernel still has old dependency graph!
    results = await self._execute_via_kernel(request)
```

### The Sequence of Failure

Let's trace a specific example:

**Initial State**:
- Cell 1: `x = 5`
- Cell 2: `y = x + 1`
- Kernel knows Cell 2 depends on Cell 1 via variable `x`
- Running Cell 1 cascades to Cell 2, outputs `y = 6` ✅

**User edits Cell 1 to `x = 10`**:

1. Frontend calls `updateCellCode(cell1_id, "x = 10")`
2. PUT `/api/v1/notebooks/{id}/cells/{cell1_id}` with `{"code": "x = 10"}`
3. Backend `cells.py:update_cell()` updates file storage only
4. **Coordinator's in-memory notebook still has `x = 5`** ❌
5. **Kernel's cell registry still has `x = 5`** ❌
6. **Dependency graph is unchanged** ❌

7. Frontend calls `runCell(cell1_id)`
8. WebSocket sends `{type: "run_cell", cellId: cell1_id}`
9. Backend `handler.py` calls `coordinator.handle_run_cell(cell1_id)`
10. Coordinator looks up cell1 in `self.notebook`, gets **OLD code** `x = 5`
11. Creates `ExecuteRequest(code="x = 5")` ❌
12. Kernel executes `x = 5` (not `x = 10`!)
13. Kernel uses existing dependency graph (which is correct structurally but has old code)
14. Cascade executes Cell 2 with `x = 5`, outputs `y = 6` ❌

**Result**: User sees the same output even though they changed the code!

## Code References

### Key Files Involved

- `backend/app/api/cells.py:49-63` - PUT endpoint that only updates file storage
- `backend/app/orchestration/coordinator.py:64-119` - `handle_cell_update()` method (unused)
- `backend/app/orchestration/coordinator.py:121-143` - `handle_run_cell()` uses stale in-memory code
- `backend/app/websocket/handler.py:63-72` - WebSocket handler missing `cell_update` message type
- `backend/app/core/graph.py:46-110` - Dependency graph `update_cell()` method
- `backend/app/kernel/process.py:37-78` - Kernel registration handler
- `backend/app/kernel/process.py:127-175` - Kernel execution and cascade logic
- `frontend/src/components/NotebookCell.tsx:82-90` - Frontend `handleRun()` flow
- `frontend/src/components/NotebookApp.tsx:201-213` - Frontend PUT and WebSocket calls

## Architecture Insights

### Dual Protocol Design (REST + WebSocket)

The system uses two communication channels:
1. **REST API** (`/api/v1/notebooks/{id}/cells/{cell_id}`): For CRUD operations and persistence
2. **WebSocket**: For real-time execution, status updates, and reactive cascades

**Intended Design**: REST API for durable state, WebSocket for ephemeral execution state.

**Actual Problem**: The two protocols are not properly synchronized. The REST API updates persistence but doesn't notify the execution layer.

### Coordinator as Central Hub

The `NotebookCoordinator` is designed to be the central orchestrator:
- Manages kernel lifecycle (one kernel per WebSocket connection)
- Maintains in-memory notebook state for fast access
- Broadcasts execution results to all connected clients
- Coordinates reactive cascades

**Problem**: The coordinator loads notebook state on WebSocket connection but never reloads or synchronizes with the REST API updates.

### Kernel Registration vs Execution

The kernel has two distinct operations:
1. **Register Cell** (`RegisterCellRequest`): Parse dependencies, update graph, detect cycles
2. **Execute Cell** (`ExecuteRequest`): Run code, compute cascade, emit results

**Critical Insight**: Registration must happen BEFORE execution whenever code changes, otherwise the dependency graph and cell registry have stale code.

**Current Bug**: Code updates via PUT bypass registration entirely.

## Historical Context (from thoughts/)

### Related Architecture Documents

- `thoughts/shared/research/2026-01-06-fresh-start-architecture.md`
  - Original architecture design for reactive notebook kernel
  - Describes topological sort and dependency handling
  - **Note**: This design assumes cell updates trigger re-registration

- `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md`
  - Details separation between orchestration and kernel layers
  - Describes cascade completion signaling via `is_last` metadata
  - **Confirms**: Coordinator should be the only component calling kernel

- `thoughts/shared/plans/2026-01-06-kernel-layer-reactive-execution-engine.md`
  - Core kernel/reactive execution engine implementation plan
  - Details automatic dependency tracking and DAG-based graph
  - **Assumption**: Registration happens on every code change (not implemented)

- `thoughts/shared/plans/2026-01-06-orchestration-layer-reactive-execution.md`
  - Orchestration layer plan for dependency graph and reactive cascades
  - **Key Missing Piece**: No mention of synchronizing REST API updates with coordinator

- `thoughts/shared/plans/2026-01-07-kernel-orchestration-integration.md`
  - Kernel-orchestration IPC details
  - Describes cascade metadata and completion detection
  - **Does not address**: How code updates flow from REST API to kernel

## Proposed Solutions

### Solution A: Add WebSocket `cell_update` Message Type (Recommended)

Replace the PUT request with a WebSocket message for cell updates.

**Pros**:
- Keeps all real-time coordination in one channel
- Coordinator naturally handles the update
- Aligns with reactive architecture
- Can broadcast updates to all connected clients in real-time

**Cons**:
- Breaking change to frontend-backend protocol
- Doesn't persist immediately (would need explicit save or auto-save)

**Implementation**:

1. Add handler in `backend/app/websocket/handler.py`:

```python
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
    msg_type = message.get("type")
    
    if msg_type == "cell_update":
        cell_id = message.get("cellId")
        new_code = message.get("code")
        if cell_id and new_code is not None:
            await coordinator.handle_cell_update(cell_id, new_code)
    elif msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await coordinator.handle_run_cell(cell_id)
```

2. Modify `coordinator.handle_cell_update()` to also persist:

```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    # ... existing registration logic ...
    
    # Persist to file storage
    NotebookFileStorage.serialize_notebook(self.notebook)
```

3. Update frontend to send WebSocket message instead of PUT:

```typescript
const updateCellCode = async (id: string, code: string) => {
    sendMessage({ type: 'cell_update', cellId: id, code: code });
};
```

### Solution B: Make PUT Endpoint Notify Coordinator

Keep the dual protocol but add synchronization.

**Pros**:
- No breaking changes to frontend
- Maintains separation between persistence and execution

**Cons**:
- More complex: requires coordinator registry or event bus
- Coordinators are per-connection, but PUT is stateless
- Race conditions between PUT and WebSocket messages

**Implementation** (sketch):

1. Create a coordinator registry/manager singleton
2. When PUT updates a cell, notify all coordinators for that notebook
3. Each coordinator reloads the cell and re-registers with kernel

**Challenges**: 
- Multiple coordinators per notebook (one per WebSocket connection)
- Need to track which notebook each coordinator manages
- Potential race between file update and WebSocket run message

### Solution C: Reload Cell from Storage in `handle_run_cell`

Simplest fix: always load fresh code before execution.

**Pros**:
- Minimal changes
- Guarantees consistency with persisted state

**Cons**:
- Doesn't update dependency graph until execution
- Performance overhead (file I/O on every run)
- Doesn't fix the stale in-memory state issue
- Won't work if multiple cells are updated without running each

**Implementation**:

```python
async def handle_run_cell(self, cell_id: str):
    # Reload notebook from storage to get latest code
    self.notebook = NotebookFileStorage.parse_notebook(self.notebook_id)
    
    # Re-register the cell to update dependency graph
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if cell:
        register_req = RegisterCellRequest(
            cell_id=cell_id,
            code=cell.code,
            cell_type=cell.type
        )
        await self._register_cell(register_req)
    
    # Now execute with fresh code
    # ... existing execution logic ...
```

### Recommendation: Hybrid Approach (WebSocket + Persist on Blur)

**Solution A with persistence on blur** is the best approach given requirements:

1. **WebSocket for real-time updates after keystrokes stop and with debounce**:
   - Send `cell_update` WebSocket message on every code change
   - Updates in-memory state and dependency graph immediately
   - No disk I/O on every keystroke

2. **Persist on blur**:
   - Keep existing frontend auto-save on blur behavior
   - Coordinator persists to file storage when handling `cell_update`
   - OR add separate `cell_save` message if you want explicit control

3. **Benefits**:
   - ✅ Dependency graph always current for reactive cascades
   - ✅ Reasonable persistence strategy (save on blur)
   - ✅ Leverages existing `handle_cell_update()` method
   - ✅ Single source of truth (WebSocket for all state changes)
   - ✅ Low risk of data loss

**Implementation details in Solution A below.**

## Open Questions ✅ Resolved

1. **Multi-user collaboration**: ~~If multiple users connect to the same notebook, how should cell updates be synchronized?~~
   - **Answer**: Not needed for this implementation (single-user notebooks)

2. **Persistence timing**: When should cell changes be written to disk?
   - **Recommendation**: **Persist on blur** (when user moves away from cell)
   - **Rationale**: 
     - Avoids disk I/O on every keystroke
     - Matches user expectations (save when done editing)
     - Already implemented in frontend (`NotebookCell.tsx:74-80`)
     - Low risk of data loss (auto-saves when switching cells or running)
     - For WebSocket approach: Send lightweight `cell_update` for graph updates, persist separately on blur

3. **Undo/redo**: ~~How would cell updates integrate with undo/redo functionality?~~
   - **Answer**: Not needed for this implementation

4. **Database connection**: How does db_conn_string update flow to coordinator? ⚠️
   - **Same Bug!** PUT `/api/v1/notebooks/{id}/db-connection` updates file storage only
   - Coordinator never reloads the connection string
   - **User Requirement**: Changing db connection should re-run the notebook
   - **Solution**: Add WebSocket `set_database_config` message type (see below)

## Additional Issue: Database Connection String Updates

### The Same Bug Affects Database Configuration!

When investigating the db connection string flow, I found **the exact same disconnect**:

```python
# backend/app/api/notebooks.py - PUT endpoint (assumed)
@router.put("/{notebook_id}/db-connection")
async def update_db_connection(notebook_id: str, request: UpdateDbConnectionRequest):
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    notebook.db_conn_string = request.connection_string
    NotebookFileStorage.serialize_notebook(notebook)  # Only updates file!
    return {"status": "ok"}
```

**Problem**: 
- Updates file storage ✅
- Coordinator's in-memory `self.notebook.db_conn_string` is stale ❌
- Kernel's SQL executor still uses old connection ❌
- **User Requirement**: Changing db connection should re-configure kernel and potentially re-run notebook

### Solution: Add WebSocket `update_db_connection` Message

The coordinator already has a `_configure_database()` method (`coordinator.py:235-258`)!

**Implementation**:

1. **Backend** - Add handler in `websocket/handler.py`:

```python
async def handle_message(connection_id: str, coordinator: NotebookCoordinator, message: dict):
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
```

2. **Backend** - Add method in `coordinator.py`:

```python
async def handle_db_connection_update(self, connection_string: str):
    """Handle database connection string update."""
    if not self.notebook:
        return
    
    # Update in-memory notebook
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
        # Broadcast error
        await self.broadcaster.broadcast({
            'type': 'db_connection_updated',
            'connectionString': connection_string,
            'status': 'error',
            'error': str(e)
        })
```

3. **Frontend** - Replace PUT with WebSocket in `NotebookApp.tsx`:

```typescript
const handleDbConnectionUpdate = async () => {
    if (!notebookId) return;
    
    sendMessage({ 
        type: 'update_db_connection', 
        connectionString: dbConnection 
    });
};

// Optionally: Re-run all SQL cells after db connection change
const handleDbConnectionUpdateAndRerun = async () => {
    if (!notebookId) return;
    
    sendMessage({ 
        type: 'update_db_connection', 
        connectionString: dbConnection 
    });
    
    // Wait a moment for kernel to reconfigure, then re-run SQL cells
    setTimeout(() => {
        cells
            .filter(c => c.type === 'sql')
            .forEach(c => runCell(c.id));
    }, 500);
};
```

## Related Research

- `thoughts/shared/research/2026-01-07-cycle-prevention-architecture.md` - Cycle detection in dependency graph
- `thoughts/shared/research/2026-01-07-rich-output-mime-conversion.md` - Reactive output flow and visualizations
- `thoughts/shared/plans/2026-01-07-cycle-detection-refactor.md` - Cycle handling tests
- `thoughts/shared/plans/2026-01-07-integration-summary.md` - System integration and reactive cascade testing

## Next Steps

1. **Immediate Fix**: Implement Solution C (reload on run) as a hotfix to unblock testing
2. **Proper Fix**: Implement Solution A (WebSocket cell_update) for production
3. **Add Integration Test**: Create test that:
   - Edits cell code via API/WebSocket
   - Runs the cell
   - Verifies cascade executes with NEW code
   - Verifies dependency graph is updated correctly
4. **Review Multi-User Story**: Design proper state synchronization for collaborative editing

