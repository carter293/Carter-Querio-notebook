---
date: 2026-01-07
planner: Matthew Carter
topic: "WebSocket CRUD with Proper Kernel Delegation"
tags: [planning, implementation, websocket, crud, kernel-separation, reactive-execution]
status: draft
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# WebSocket CRUD with Proper Kernel Delegation Implementation Plan

**Date**: 2026-01-07
**Planner**: Matthew Carter

## Overview

This plan implements **WebSocket-based CRUD operations** (create, update, delete cells) with **proper separation of concerns** between the Coordinator and Kernel layers. The key principle: **the coordinator NEVER manipulates cells directly** - all cell state management flows through the kernel.

**Current Problem**:
1. REST API endpoints manipulate cells directly in file storage without notifying the kernel
2. `handle_cell_update` in coordinator waits synchronously with `loop.run_in_executor(None, self.kernel.output_queue.get)` - this is a blocking pattern that works but violates async best practices
3. No kernel support for cell creation/deletion
4. Cell deletion doesn't trigger reactive cascades

**Solution**:
1. **Move ALL CRUD to WebSocket** - REST API becomes deprecated/removed
2. **Kernel handles ALL cell state** - Create new kernel IPC message types for cell creation and deletion
3. **Fix IPC pattern** - Replace blocking queue reads with proper async coordination using asyncio primitives
4. **Deletion triggers cascade** - When deleting a cell, kernel computes affected downstream cells and re-executes them

## Current State Analysis

### What Exists Now

**Kernel Layer** (`backend/app/kernel/`):
- ✅ Executes code via `ExecuteRequest` with reactive cascades
- ✅ Registers cells via `RegisterCellRequest` (updates dependency graph)
- ✅ Configures database via `SetDatabaseConfigRequest`
- ❌ **NO** cell creation message type
- ❌ **NO** cell deletion message type
- ❌ **NO** dependency tracking for deletion cascades

**Coordinator Layer** (`backend/app/orchestration/coordinator.py`):
- ✅ Routes messages between WebSocket and kernel
- ✅ Broadcasts results to all connected clients
- ✅ Maintains in-memory notebook state for REST API responses
- ⚠️ `handle_cell_update` manipulates cell code directly (line 75), then notifies kernel
- ⚠️ Uses `loop.run_in_executor(None, queue.get)` pattern (lines 52, 90, 200, 292)
- ❌ **NO** cell creation handler
- ❌ **NO** cell deletion handler

**WebSocket Handler** (`backend/app/websocket/handler.py`):
- ✅ Handles `cell_update`, `update_db_connection`, `run_cell`
- ❌ **NO** `create_cell` handler
- ❌ **NO** `delete_cell` handler

**REST API** (`backend/app/api/cells.py`):
- ✅ Creates cells directly in file storage (line 13-47)
- ✅ Deletes cells directly in file storage (line 49-63)
- ⚠️ Does NOT notify kernel of changes
- ⚠️ Does NOT broadcast WebSocket messages

### Key Discovery from Research

The blocking `loop.run_in_executor(None, queue.get)` pattern exists because:
1. Kernel uses `multiprocessing.Queue` (synchronous, blocking)
2. Coordinator runs in asyncio (asynchronous, non-blocking)
3. `run_in_executor` is the **correct** way to bridge these

**However**, this pattern has issues:
- ❌ No timeout - hangs forever if kernel crashes
- ❌ Each blocking read consumes a thread from asyncio's thread pool
- ❌ With cascades, multiple threads can be blocked simultaneously

## System Context Analysis

### Intended Architecture (from fresh-start-architecture.md)

```
┌────────────────────────────────────────────────────────────┐
│                   INTERFACE LAYER                          │
│  - HTTP REST (deprecated for CRUD)                         │
│  - WebSocket (primary interface)                           │
└────────────────────────┬───────────────────────────────────┘
                         │
                         │ async calls
                         ▼
┌────────────────────────────────────────────────────────────┐
│              ORCHESTRATION LAYER (Coordinator)             │
│  - Routes messages to kernel                               │
│  - Broadcasts kernel results to clients                    │
│  - NO direct cell manipulation                             │
│  - NO dependency logic                                     │
│  - NO execution logic                                      │
└────────────────────────┬───────────────────────────────────┘
                         │
                         │ IPC (Queue-based)
                         ▼
┌────────────────────────────────────────────────────────────┐
│                   KERNEL LAYER                             │
│  - Owns ALL cell state                                     │
│  - Manages dependency graph                                │
│  - Executes code                                           │
│  - Computes reactive cascades                              │
│  - Returns results via output queue                        │
└────────────────────────────────────────────────────────────┘
```

### Current Violations

**Problem 1: Coordinator manipulates cells directly**
```python
# coordinator.py:75
cell.code = new_code  # ❌ Direct manipulation
NotebookFileStorage.serialize_notebook(self.notebook)  # ❌ Direct file write
```

**What should happen**: Kernel should own cell state, coordinator should only route messages.

**Problem 2: REST API bypasses kernel**
```python
# cells.py:21-46
new_cell = CellResponse(...)  # ❌ Created in REST layer
notebook.cells.append(new_cell)  # ❌ Direct list manipulation
NotebookFileStorage.serialize_notebook(notebook)  # ❌ Direct file write
# NO kernel notification
# NO WebSocket broadcast
```

**What should happen**: WebSocket sends `create_cell` → Coordinator → Kernel creates cell → Kernel returns result → Coordinator broadcasts.

**Problem 3: Blocking IPC pattern**
```python
# coordinator.py:200
result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
```

**What's wrong**:
- Blocks a thread from asyncio's thread pool
- No timeout (hangs forever on kernel crash)
- Difficult to reason about with multiple concurrent operations

**What should happen**: Use asyncio-native coordination (Event, Future) or timeout-wrapped queue reads.

## Desired End State

After this implementation:

1. **WebSocket is the ONLY way to modify cells**:
   - `create_cell` WebSocket message → Kernel creates → Broadcasts `cell_created`
   - `delete_cell` WebSocket message → Kernel deletes → Broadcasts `cell_deleted`
   - `cell_update` WebSocket message → Kernel updates → Broadcasts `cell_updated`

2. **Kernel owns ALL cell state**:
   - Coordinator has READONLY copy for REST API responses
   - All mutations flow through kernel IPC
   - Kernel maintains single source of truth

3. **Proper async IPC pattern**:
   - Add timeouts to all queue reads
   - Use asyncio.Event for coordination when appropriate
   - Document why blocking pattern is necessary

4. **Deletion triggers reactive cascade**:
   - Kernel identifies cells that depend on deleted cell
   - Re-executes those cells (they will error or produce different results)
   - Returns cascade results to coordinator
   - Frontend shows cascade execution in real-time

5. **REST API is deprecated or thin wrapper**:
   - Option A: Remove REST CRUD endpoints entirely
   - Option B: Keep as deprecated, logged warnings
   - Option C: Make REST internally call WebSocket (complex)

## What We're NOT Doing

1. **Not implementing undo/redo** for cell operations
2. **Not adding cell move/reorder** functionality (different feature)
3. **Not implementing cell templates** or initialization patterns
4. **Not changing to async queues** (requires kernel refactor to use asyncio instead of multiprocessing)
5. **Not implementing shared kernels** (each WebSocket connection has its own kernel)
6. **Not adding bulk operations** (create/delete multiple cells at once)
7. **Not changing file storage format** (keeping current .py serialization)

## Implementation Approach

**Strategy**: Build incrementally, kernel-first approach:

1. **Phase 1**: Add kernel IPC message types for CRUD operations
2. **Phase 2**: Fix IPC pattern - add timeouts and proper error handling
3. **Phase 3**: Implement coordinator handlers that delegate to kernel
4. **Phase 4**: Add WebSocket message handlers
5. **Phase 5**: Deprecate/remove REST API CRUD endpoints
6. **Phase 6**: Integration testing and cascade verification

**Key Design Principles**:

1. **Kernel owns cell lifecycle**:
   - Create: Kernel adds to registry, initializes dependency node
   - Update: Kernel re-registers, updates graph
   - Delete: Kernel removes from registry, cleans up graph, triggers cascade

2. **Coordinator is pure routing**:
   - Receives WebSocket message → Creates kernel request → Sends to input queue
   - Reads kernel result from output queue → Broadcasts to clients
   - Maintains readonly notebook state synced with kernel results

3. **File storage is written by coordinator AFTER kernel confirms**:
   - Kernel operations are in-memory (fast, atomic)
   - Coordinator persists to file after successful kernel operation
   - On failure, kernel state is correct (file may be stale, but next load rebuilds from file)

---

## Phase 1: Add Kernel IPC Types for Cell CRUD

### Overview

Add `CreateCellRequest`, `CreateCellResult`, `DeleteCellRequest`, `DeleteCellResult` message types to kernel IPC protocol. Implement handlers in kernel process.

### Changes Required

#### 1. Kernel Type Definitions

**File**: `backend/app/kernel/types.py`

**Changes**: Add new request and result models (after line 68)

```python
class CreateCellRequest(BaseModel):
    """Request to create a new cell in the kernel."""
    type: Literal["create_cell"] = "create_cell"
    cell_id: str
    cell_type: CellType
    after_cell_id: str | None = None  # Position hint (coordinator maintains order)


class CreateCellResult(BaseModel):
    """Result of cell creation."""
    type: Literal["create_result"] = "create_result"
    cell_id: str
    status: Literal["success", "error"]
    error: str | None = None


class DeleteCellRequest(BaseModel):
    """Request to delete a cell and trigger cascade for dependents."""
    type: Literal["delete_cell"] = "delete_cell"
    cell_id: str


class DeleteCellResult(BaseModel):
    """Result of cell deletion (immediate confirmation, cascade follows)."""
    type: Literal["delete_result"] = "delete_result"
    cell_id: str
    status: Literal["success", "error"]
    error: str | None = None
    affected_cell_ids: list[str] = Field(default_factory=list)  # Cells that will cascade
```

**Design Note**:
- `CreateCellRequest` doesn't include code - cell starts empty
- `after_cell_id` is a hint for coordinator to maintain cell order, kernel doesn't care about order
- `DeleteCellResult` includes `affected_cell_ids` so coordinator knows which cells will re-execute
- Actual cascade execution results come through as separate `ExecutionResult` messages

#### 2. Kernel Process - Create Handler

**File**: `backend/app/kernel/process.py`

**Changes**: Add handler in main loop (after `set_database_config` handler, before execution request)

```python
        # Handle cell creation
        if request_data.get('type') == 'create_cell':
            try:
                from .types import CreateCellRequest, CreateCellResult
                create_req = CreateCellRequest(**request_data)

                # Register cell with empty code and no dependencies
                cell_registry[create_req.cell_id] = ("", create_req.cell_type)

                # Add to dependency graph with no reads/writes
                graph.update_cell(create_req.cell_id, reads=set(), writes=set())

                result = CreateCellResult(
                    cell_id=create_req.cell_id,
                    status='success'
                )
                output_queue.put(result.model_dump())
            except Exception as e:
                result = CreateCellResult(
                    cell_id=create_req.cell_id,
                    status='error',
                    error=str(e)
                )
                output_queue.put(result.model_dump())
            continue
```

**Design Note**: Cell creation is simple - just register with empty state. The cell will be populated later via `RegisterCellRequest` when user adds code.

#### 3. Kernel Process - Delete Handler with Cascade

**File**: `backend/app/kernel/process.py`

**Changes**: Add handler in main loop (after create handler, before execution request)

```python
        # Handle cell deletion with cascade
        if request_data.get('type') == 'delete_cell':
            try:
                from .types import DeleteCellRequest, DeleteCellResult
                delete_req = DeleteCellRequest(**request_data)

                # Get cells that depend on the deleted cell BEFORE removing it
                affected_cells = []
                if delete_req.cell_id in cell_registry:
                    try:
                        # Get execution order - this includes the cell itself + dependents
                        execution_order = graph.get_execution_order(delete_req.cell_id)
                        # Remove the deleted cell from the list (we don't execute it)
                        affected_cells = [cid for cid in execution_order if cid != delete_req.cell_id]
                    except Exception as e:
                        # If we can't get execution order (e.g., cell not in graph), no cascade
                        print(f"[Kernel] Warning: Could not compute affected cells: {e}")

                # Remove from cell registry
                if delete_req.cell_id in cell_registry:
                    del cell_registry[delete_req.cell_id]

                # Remove from dependency graph (cleans up edges and variable mappings)
                graph.remove_cell(delete_req.cell_id)

                # Send deletion confirmation FIRST
                result = DeleteCellResult(
                    cell_id=delete_req.cell_id,
                    status='success',
                    affected_cell_ids=affected_cells
                )
                output_queue.put(result.model_dump())

                # NOW trigger cascade execution for affected cells
                # This will send ExecutionResult messages for each affected cell
                for affected_cell_id in affected_cells:
                    if affected_cell_id not in cell_registry:
                        continue  # Cell was deleted or doesn't exist

                    cell_code, cell_type = cell_registry[affected_cell_id]

                    # Execute this cell (it will likely fail since deleted cell's vars are gone)
                    exec_result = None
                    if cell_type == 'python':
                        exec_result = python_executor.execute(cell_code)
                    elif cell_type == 'sql':
                        exec_result = sql_executor.execute(cell_code)

                    if exec_result:
                        # Create ExecutionResult with cascade metadata
                        cascade_index = affected_cells.index(affected_cell_id)
                        result = ExecutionResult(
                            cell_id=affected_cell_id,
                            status=exec_result.status,
                            stdout=exec_result.stdout,
                            outputs=exec_result.outputs,
                            error=exec_result.error,
                            reads=exec_result.reads,
                            writes=exec_result.writes,
                            metadata={
                                'cascade_index': cascade_index,
                                'cascade_total': len(affected_cells),
                                'is_last': cascade_index == len(affected_cells) - 1,
                                'triggered_by': 'delete'  # NEW: indicates this is a deletion cascade
                            }
                        )
                        output_queue.put(result.model_dump())

            except Exception as e:
                result = DeleteCellResult(
                    cell_id=delete_req.cell_id,
                    status='error',
                    error=str(e)
                )
                output_queue.put(result.model_dump())
            continue
```

**Design Note**:
- Delete sends TWO types of messages:
  1. `DeleteCellResult` (immediate confirmation)
  2. Multiple `ExecutionResult` messages (for cascade)
- Cascade has special metadata: `triggered_by: 'delete'`
- Coordinator can distinguish deletion cascades from execution cascades

### Success Criteria

#### Automated Verification

- [ ] Type definitions parse successfully: `python -c "from backend.app.kernel.types import CreateCellRequest, CreateCellResult, DeleteCellRequest, DeleteCellResult"`
- [ ] Kernel process starts without errors
- [ ] Unit test: Send `CreateCellRequest` → Receive `CreateCellResult` with status='success'
- [ ] Unit test: Send `DeleteCellRequest` → Receive `DeleteCellResult` + cascade `ExecutionResult` messages
- [ ] Unit test: Deleted cell no longer in `cell_registry`
- [ ] Unit test: Deleted cell removed from dependency graph

#### Manual Verification

- [ ] Create cell via test script, verify it appears in kernel registry
- [ ] Delete cell that other cells depend on, verify cascade execution results received
- [ ] Verify removed cell no longer in graph (`graph._graph.has_node(cell_id)` returns False)

---

## Phase 2: Fix IPC Pattern - Add Timeouts and Error Handling

### Overview

Replace unsafe `loop.run_in_executor(None, queue.get)` with timeout-wrapped version. Add health checks for kernel process. Document why blocking pattern is necessary.

### Changes Required

#### 1. Add Timeout Utility

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add utility method at the top of the class (after `__init__`)

```python
    async def _read_kernel_result(self, timeout: int = 30) -> dict:
        """
        Read a result from kernel output queue with timeout.

        Args:
            timeout: Timeout in seconds

        Returns:
            Deserialized result dictionary

        Raises:
            TimeoutError: If kernel doesn't respond within timeout
            RuntimeError: If kernel process has died

        Design Note:
            We use loop.run_in_executor because multiprocessing.Queue.get() is
            a blocking operation, but we're running in an asyncio context.
            This is the correct pattern for bridging sync blocking code with async.
            The timeout prevents hanging if the kernel crashes or hangs.
        """
        import queue
        loop = asyncio.get_event_loop()

        # Check if kernel is alive before attempting read
        if not self.kernel.process.is_alive():
            raise RuntimeError("Kernel process has died")

        try:
            # Wrap blocking queue.get() with timeout
            result_data = await loop.run_in_executor(
                None,
                lambda: self.kernel.output_queue.get(timeout=timeout)
            )
            return result_data
        except queue.Empty:
            # Timeout expired
            if not self.kernel.process.is_alive():
                raise RuntimeError("Kernel process died during operation")
            else:
                raise TimeoutError(f"Kernel did not respond within {timeout} seconds")
```

#### 2. Update All Queue Reads

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Replace all `loop.run_in_executor(None, self.kernel.output_queue.get)` with `await self._read_kernel_result()`

**Location 1: `load_notebook` (line 52)**
```python
# OLD:
result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)

# NEW:
result_data = await self._read_kernel_result(timeout=30)
```

**Location 2: `handle_cell_update` (line 90)**
```python
# OLD:
result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)

# NEW:
result_data = await self._read_kernel_result(timeout=10)
```

**Location 3: `_execute_via_kernel` (line 200)**
```python
# OLD:
result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)

# NEW:
result_data = await self._read_kernel_result(timeout=60)  # Longer timeout for execution
```

**Location 4: `_configure_database` (line 292)**
```python
# OLD:
result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)

# NEW:
result_data = await self._read_kernel_result(timeout=15)
```

#### 3. Add Error Handling in Coordinator Methods

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Wrap coordinator methods with try/except for timeout and kernel death

Example for `handle_cell_update` (lines 64-122):
```python
    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Handle a cell code update."""
        if not self.notebook:
            return

        # Find cell
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        try:
            # Update code in memory
            cell.code = new_code

            # Persist to file storage
            NotebookFileStorage.serialize_notebook(self.notebook)

            # Register updated cell with kernel to update dependency graph
            register_req = RegisterCellRequest(
                cell_id=cell_id,
                code=cell.code,
                cell_type=cell.type
            )
            self.kernel.input_queue.put(register_req.model_dump())

            # Read registration result with timeout
            result_data = await self._read_kernel_result(timeout=10)

            if result_data.get('type') == 'register_result':
                result = RegisterCellResult(**result_data)

                if result.status == 'error':
                    # Registration failed (likely cycle) - mark cell as blocked
                    cell.status = 'blocked'
                    cell.error = result.error

                    # Broadcast error
                    await self.broadcaster.broadcast({
                        'type': 'cell_status',
                        'cellId': cell_id,
                        'status': 'blocked'
                    })
                    await self.broadcaster.broadcast({
                        'type': 'cell_error',
                        'cellId': cell_id,
                        'error': result.error
                    })
                    return

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

        except (TimeoutError, RuntimeError) as e:
            # Kernel is dead or unresponsive
            print(f"[Coordinator] Kernel error during cell update: {e}")

            # Mark cell as error
            cell.status = 'error'
            cell.error = f"Kernel error: {str(e)}"

            # Broadcast error to frontend
            await self.broadcaster.broadcast({
                'type': 'cell_status',
                'cellId': cell_id,
                'status': 'error'
            })
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': cell.error
            })

            # TODO: Restart kernel?
```

**Repeat similar error handling for**:
- `load_notebook`
- `handle_db_connection_update`
- `_execute_via_kernel`
- `_configure_database`

### Success Criteria

#### Automated Verification

- [ ] Unit test: Kernel timeout is detected and raises `TimeoutError`
- [ ] Unit test: Dead kernel is detected and raises `RuntimeError`
- [ ] Integration test: Coordinator handles kernel death gracefully
- [ ] All existing tests still pass

#### Manual Verification

- [ ] Kill kernel process mid-operation, verify coordinator broadcasts error
- [ ] Long-running cell (sleep 100s) times out if timeout is short
- [ ] Error messages are user-friendly in frontend

---

## Phase 3: Implement Coordinator Handlers for Cell CRUD

### Overview

Add `handle_cell_create` and `handle_cell_delete` methods to `NotebookCoordinator`. These methods delegate ALL work to the kernel and only update in-memory state based on kernel responses.

### Changes Required

#### 1. Coordinator Cell Creation Method

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add method after `handle_db_connection_update` (after line 159)

```python
    async def handle_cell_create(self, cell_type: str, after_cell_id: Optional[str] = None):
        """
        Handle a new cell creation by delegating to kernel.

        Args:
            cell_type: Type of cell ('python' or 'sql')
            after_cell_id: Optional ID of cell to insert after
        """
        if not self.notebook:
            return

        from uuid import uuid4
        from ..models import CellResponse
        from ..kernel.types import CreateCellRequest, CreateCellResult

        # Generate cell ID
        cell_id = str(uuid4())

        try:
            # Send creation request to kernel
            create_req = CreateCellRequest(
                cell_id=cell_id,
                cell_type=cell_type,
                after_cell_id=after_cell_id  # Hint for coordinator ordering
            )
            self.kernel.input_queue.put(create_req.model_dump())

            # Wait for kernel confirmation
            result_data = await self._read_kernel_result(timeout=10)

            if result_data.get('type') != 'create_result':
                raise RuntimeError(f"Unexpected result type: {result_data.get('type')}")

            result = CreateCellResult(**result_data)

            if result.status == 'error':
                # Kernel failed to create cell
                print(f"[Coordinator] Kernel failed to create cell: {result.error}")
                await self.broadcaster.broadcast({
                    'type': 'cell_create_error',
                    'error': result.error
                })
                return

            # Kernel successfully created cell - now update coordinator state
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

            # Persist to file storage AFTER kernel confirms
            NotebookFileStorage.serialize_notebook(self.notebook)

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
                    'status': 'idle',
                    'outputs': [],
                    'stdout': '',
                    'reads': [],
                    'writes': []
                },
                'index': final_index
            })

        except (TimeoutError, RuntimeError) as e:
            print(f"[Coordinator] Error creating cell: {e}")
            await self.broadcaster.broadcast({
                'type': 'cell_create_error',
                'error': str(e)
            })
```

**Design Note**:
- Kernel creates cell FIRST (in its registry)
- Coordinator updates its state ONLY after kernel confirms
- File storage is written AFTER kernel confirms
- If kernel fails, coordinator state is unchanged

#### 2. Coordinator Cell Deletion Method

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Add method after `handle_cell_create`

```python
    async def handle_cell_delete(self, cell_id: str):
        """
        Handle cell deletion by delegating to kernel.

        Kernel will:
        1. Confirm deletion
        2. Send cascade execution results for dependent cells

        Args:
            cell_id: ID of cell to delete
        """
        if not self.notebook:
            return

        from ..kernel.types import DeleteCellRequest, DeleteCellResult

        # Find cell to delete
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            # Cell not found, nothing to do
            return

        try:
            # Send deletion request to kernel
            delete_req = DeleteCellRequest(cell_id=cell_id)
            self.kernel.input_queue.put(delete_req.model_dump())

            # Wait for deletion confirmation
            result_data = await self._read_kernel_result(timeout=10)

            if result_data.get('type') != 'delete_result':
                raise RuntimeError(f"Unexpected result type: {result_data.get('type')}")

            result = DeleteCellResult(**result_data)

            if result.status == 'error':
                # Kernel failed to delete cell
                print(f"[Coordinator] Kernel failed to delete cell: {result.error}")
                await self.broadcaster.broadcast({
                    'type': 'cell_delete_error',
                    'cellId': cell_id,
                    'error': result.error
                })
                return

            # Kernel successfully deleted cell - update coordinator state
            self.notebook.cells = [c for c in self.notebook.cells if c.id != cell_id]

            # Persist to file storage AFTER kernel confirms
            NotebookFileStorage.serialize_notebook(self.notebook)

            # Broadcast deletion to all clients
            await self.broadcaster.broadcast({
                'type': 'cell_deleted',
                'cellId': cell_id
            })

            # NOW wait for cascade execution results
            # Kernel sends ExecutionResult messages for each affected cell
            affected_count = len(result.affected_cell_ids)

            if affected_count > 0:
                print(f"[Coordinator] Expecting {affected_count} cascade results after deletion")

                # Read cascade results (same pattern as _execute_via_kernel)
                cascade_results = []
                while len(cascade_results) < affected_count:
                    result_data = await self._read_kernel_result(timeout=60)

                    # Should be ExecutionResult
                    if result_data.get('status') and 'cell_id' in result_data:
                        exec_result = ExecutionResult(**result_data)
                        cascade_results.append(exec_result)

                        # Broadcast this cascade result
                        await self._broadcast_execution_result(exec_result)

                        # Check if this is the last one
                        if exec_result.metadata and exec_result.metadata.get('is_last', False):
                            break
                    else:
                        print(f"[Coordinator] Warning: Unexpected message during cascade: {result_data}")

                print(f"[Coordinator] Deletion cascade complete: {len(cascade_results)} cells re-executed")

        except (TimeoutError, RuntimeError) as e:
            print(f"[Coordinator] Error deleting cell: {e}")
            await self.broadcaster.broadcast({
                'type': 'cell_delete_error',
                'cellId': cell_id,
                'error': str(e)
            })
```

**Design Note**:
- Deletion has TWO phases:
  1. Deletion confirmation (`DeleteCellResult`)
  2. Cascade execution (multiple `ExecutionResult` messages)
- Coordinator removes cell from its state AFTER kernel confirms
- Coordinator broadcasts deletion BEFORE cascade results
- Frontend sees: `cell_deleted` → `cell_status: running` (for dependents) → `cell_output` → `cell_status: success/error`

#### 3. Update `handle_cell_update` to Not Manipulate Directly

**File**: `backend/app/orchestration/coordinator.py`

**Changes**: Refactor `handle_cell_update` (lines 64-122) to update file storage AFTER kernel confirms

Actually, looking at the current implementation, it already does this correctly:
1. Updates in-memory state (line 75)
2. Persists to file (line 78)
3. Sends to kernel (line 86)
4. Waits for kernel response (line 90)

The only issue is that it updates state BEFORE kernel confirms. Let's fix that:

```python
    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Handle a cell code update."""
        if not self.notebook:
            return

        # Find cell
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        try:
            # Store old code in case we need to revert
            old_code = cell.code

            # Register updated cell with kernel to update dependency graph
            register_req = RegisterCellRequest(
                cell_id=cell_id,
                code=new_code,  # Send new code to kernel
                cell_type=cell.type
            )
            self.kernel.input_queue.put(register_req.model_dump())

            # Read registration result with timeout
            result_data = await self._read_kernel_result(timeout=10)

            if result_data.get('type') == 'register_result':
                result = RegisterCellResult(**result_data)

                if result.status == 'error':
                    # Registration failed (likely cycle) - DON'T update state
                    # Broadcast error
                    await self.broadcaster.broadcast({
                        'type': 'cell_status',
                        'cellId': cell_id,
                        'status': 'blocked'
                    })
                    await self.broadcaster.broadcast({
                        'type': 'cell_error',
                        'cellId': cell_id,
                        'error': result.error
                    })
                    return

            # Kernel accepted the update - NOW update coordinator state
            cell.code = new_code

            # Persist to file storage AFTER kernel confirms
            NotebookFileStorage.serialize_notebook(self.notebook)

            # Broadcast the code change
            await self.broadcaster.broadcast({
                'type': 'cell_updated',
                'cellId': cell_id,
                'cell': {
                    'code': cell.code,
                    'reads': result.reads,  # Use kernel's reads/writes
                    'writes': result.writes
                }
            })

        except (TimeoutError, RuntimeError) as e:
            # Kernel is dead or unresponsive
            print(f"[Coordinator] Kernel error during cell update: {e}")

            # Broadcast error to frontend
            await self.broadcaster.broadcast({
                'type': 'cell_status',
                'cellId': cell_id,
                'status': 'error'
            })
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': str(e)
            })
```

**Key Change**: Cell code is updated in coordinator AFTER kernel confirms, not before.

### Success Criteria

#### Automated Verification

- [ ] Unit test: `handle_cell_create` creates cell in kernel, then coordinator
- [ ] Unit test: `handle_cell_delete` deletes cell in kernel, then coordinator
- [ ] Unit test: `handle_cell_update` updates kernel first, coordinator second
- [ ] Unit test: Cell creation broadcasts `cell_created` message
- [ ] Unit test: Cell deletion broadcasts `cell_deleted` + cascade results
- [ ] Mock broadcaster receives correct message sequence

#### Manual Verification

- [ ] Create cell via coordinator method, verify in file storage
- [ ] Delete cell via coordinator method, verify removed from file storage
- [ ] Delete cell that other cells depend on, verify dependent cells re-executed
- [ ] Verify broadcasts sent to all clients

---

## Phase 4: Add WebSocket Message Handlers

### Overview

Extend WebSocket handler to dispatch `create_cell` and `delete_cell` messages to coordinator methods.

### Changes Required

#### 1. WebSocket Handler

**File**: `backend/app/websocket/handler.py`

**Changes**: Add new message handlers in `handle_message` function (after line 71, before `update_db_connection`)

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
        cell_type = message.get("cellType")  # 'python' or 'sql'
        after_cell_id = message.get("afterCellId")  # Optional
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

**Message Formats**:
- Create: `{ type: 'create_cell', cellType: 'python'|'sql', afterCellId?: string }`
- Delete: `{ type: 'delete_cell', cellId: string }`

### Success Criteria

#### Automated Verification

- [ ] Integration test: Send `create_cell` via WebSocket → Receive `cell_created` broadcast
- [ ] Integration test: Send `delete_cell` via WebSocket → Receive `cell_deleted` broadcast
- [ ] Integration test: Multiple clients receive broadcasts

#### Manual Verification

- [ ] Connect via WebSocket client, send `create_cell`, verify broadcast received
- [ ] Send `delete_cell`, verify cascade broadcasts received
- [ ] Multiple browser tabs open, verify all receive events

---

## Phase 5: Deprecate or Remove REST API CRUD Endpoints

### Overview

Since WebSocket now handles all CRUD operations, REST API endpoints for cell create/delete become redundant. We have three options.

### Option A: Remove Endpoints Entirely (Recommended)

**File**: `backend/app/api/cells.py`

**Changes**: Delete the entire file or comment out the endpoints

**File**: `backend/main.py`

**Changes**: Remove the router registration:
```python
# app.include_router(cells.router)  # REMOVED: Use WebSocket for CRUD
```

**Pros**:
- Clean, no dead code
- Enforces single interface (WebSocket)
- Simpler to maintain

**Cons**:
- Breaking change if external tools use REST API

### Option B: Add Deprecation Warnings

**File**: `backend/app/api/cells.py`

**Changes**: Add deprecation notices and warnings

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
    print("[WARNING] REST endpoint create_cell is deprecated. Use WebSocket 'create_cell' message instead.")

    # ... existing implementation ...


@router.delete("/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """
    Delete a cell.

    **DEPRECATED**: This endpoint only updates file storage and does not synchronize
    with the kernel or broadcast to connected clients. Use WebSocket message
    'delete_cell' instead for proper reactive behavior.

    This endpoint is maintained for backward compatibility only.
    """
    print("[WARNING] REST endpoint delete_cell is deprecated. Use WebSocket 'delete_cell' message instead.")

    # ... existing implementation ...
```

**Pros**:
- Backward compatible
- Gives time for migration
- Logs warnings for monitoring

**Cons**:
- Maintains dead code
- Two ways to do the same thing (confusion)

### Option C: Make REST Call WebSocket Internally (Complex)

Create a "fake" WebSocket connection internally and use coordinator methods.

**NOT RECOMMENDED** because:
- Complex to implement correctly
- Coordinator expects WebSocket broadcaster
- Would need to synthesize WebSocket context
- Better to just use WebSocket directly

### Recommendation

**Choose Option A (Remove)** if:
- This is internal-only application
- No external consumers of REST API
- Clean slate desired

**Choose Option B (Deprecate)** if:
- Need gradual migration
- External tools might use REST API
- Want to monitor usage before removal

For this project, **recommend Option A** since the frontend already uses WebSocket.

### Success Criteria

#### Automated Verification

- [ ] Backend starts without errors
- [ ] OpenAPI docs don't show deprecated endpoints (if removed)
- [ ] Frontend still works (uses WebSocket)

#### Manual Verification

- [ ] Test that frontend cell creation uses WebSocket
- [ ] Test that frontend cell deletion uses WebSocket
- [ ] Verify no REST API calls in browser network tab for cell CRUD

---

## Phase 6: Integration Testing and Cascade Verification

### Overview

Add comprehensive integration tests that verify the full CRUD flow through WebSocket → Coordinator → Kernel → Broadcast.

### Changes Required

#### 1. Test Cell Creation Integration

**File**: `backend/tests/test_websocket_crud_integration.py` (new file)

**Content**:

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
        db_conn_string=""
    )
    NotebookFileStorage.serialize_notebook(notebook)
    yield notebook_id
    # Cleanup
    import os
    notebook_path = f"backend/notebooks/{notebook_id}.py"
    if os.path.exists(notebook_path):
        os.remove(notebook_path)


@pytest.mark.asyncio
async def test_cell_creation_via_websocket(setup_notebook):
    """Test creating a cell via WebSocket coordinator method."""
    notebook_id = setup_notebook

    # Create coordinator
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook(notebook_id)

    broadcaster.messages.clear()

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
async def test_cell_creation_after_specific_cell(setup_notebook):
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
```

### Success Criteria

#### Automated Verification

- [ ] All tests pass: `cd backend && pytest tests/test_websocket_crud_integration.py -v`
- [ ] Test coverage includes create, delete, cascade scenarios
- [ ] Tests pass consistently (no flaky tests)

#### Manual Verification

- [ ] Review test output for warnings
- [ ] Verify no orphaned kernel processes after tests
- [ ] Memory usage is reasonable

---

## Testing Strategy

### Unit Tests

**What to test**:
- `CreateCellRequest` and `CreateCellResult` serialization/deserialization
- `DeleteCellRequest` and `DeleteCellResult` serialization/deserialization
- Kernel process handles `create_cell` messages correctly
- Kernel process handles `delete_cell` messages and triggers cascade
- `_read_kernel_result` timeout handling
- Coordinator methods handle kernel errors gracefully

**Key edge cases**:
- Create cell when kernel is dead
- Delete cell when kernel is dead
- Delete cell that no other cells depend on (no cascade)
- Delete cell that multiple cells depend on (multi-cell cascade)
- Create cell with invalid `after_cell_id`
- Timeout during cell creation
- Timeout during cell deletion

### Integration Tests

**End-to-end scenarios**:
1. **Basic create flow**: WebSocket `create_cell` → Kernel → Broadcast `cell_created`
2. **Basic delete flow**: WebSocket `delete_cell` → Kernel → Broadcast `cell_deleted`
3. **Create at position**: Use `afterCellId` → Verify correct insertion
4. **Delete with cascade**: Delete cell with dependents → Verify cascade execution
5. **Multi-client sync**: Two WebSocket connections → Create in one → Verify broadcast to both
6. **Kernel crash during create**: Kill kernel mid-operation → Verify error broadcast
7. **Kernel crash during delete**: Kill kernel mid-operation → Verify error broadcast

### Manual Testing Steps

1. **Test Cell Creation**:
   - Open notebook in browser
   - Open browser console, send WebSocket message: `ws.send(JSON.stringify({type: 'create_cell', cellType: 'python'}))`
   - Verify new cell appears in UI
   - Add code to new cell
   - Run cell → Verify executes successfully
   - Open second browser tab → Verify both tabs show the new cell

2. **Test Cell Deletion (No Dependencies)**:
   - Create a cell with code `z = 100` (standalone)
   - Run the cell
   - Delete the cell: `ws.send(JSON.stringify({type: 'delete_cell', cellId: '<id>'}))`
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

4. **Test Cell Creation Position**:
   - Create 3 cells
   - Send: `ws.send(JSON.stringify({type: 'create_cell', cellType: 'python', afterCellId: '<cell1_id>'}))`
   - Verify new cell appears between cell 1 and cell 2

## Performance Considerations

### Timeout Values

- **Cell creation**: 10 seconds (should be instant)
- **Cell update**: 10 seconds (AST parsing is fast)
- **Cell execution**: 60 seconds (code can be slow)
- **Cell deletion**: 10 seconds base + time for cascade (cascade uses execution timeout)
- **Database config**: 15 seconds (network operation)

### Thread Pool Usage

- Each `_read_kernel_result` call consumes one thread from asyncio's default pool
- Default pool size: `min(32, os.cpu_count() + 4)`
- With cascades, multiple threads may be blocked simultaneously (one reading cascade results)
- Monitor thread pool saturation in production

### Cascade Execution on Delete

- Deleting a cell with many dependents triggers full cascade
- Could be slow for large notebooks (100+ cells)
- This is expected behavior (reactive execution)
- Future optimization: Parallel execution of independent branches

## Migration Notes

### Breaking Changes

**Frontend changes required**:
1. Update `addCell()` to use WebSocket message instead of REST API
2. Update `deleteCell()` to use WebSocket message instead of REST API
3. Handle new error message types: `cell_create_error`, `cell_delete_error`

**Backend changes**:
1. REST API endpoints removed (if Option A chosen)
2. New WebSocket message types: `create_cell`, `delete_cell`
3. New kernel IPC message types: `CreateCellRequest`, `DeleteCellRequest`

### Rollout Strategy

1. **Deploy backend changes** (backward compatible with old frontend)
2. **Deploy frontend changes** (uses new WebSocket messages)
3. **Monitor for errors** in logs and frontend console
4. **Remove REST endpoints** after confirming no usage (if Option A)

### Rollback Plan

If issues arise:
1. Revert frontend to use REST API for cell CRUD
2. Backend WebSocket handlers can be disabled without breaking system
3. Kernel changes (Phase 1) don't affect existing operations

## References

- **Original Research**:
  - `thoughts/shared/research/2026-01-07-crud-operations-kernel-sync-failure.md` (identified the problem)
  - `thoughts/shared/research/2026-01-06-fresh-start-architecture.md` (architecture principles)
- **Task Requirements**: `the_task.md` (reactive notebook implementation)
- **Current Architecture Research**: Detailed analysis from subagent
- **Existing Patterns**:
  - `backend/app/orchestration/coordinator.py:161-183` - `handle_run_cell` pattern (follow this)
  - `backend/app/kernel/process.py:105-184` - Execution with cascade (model deletion cascade after this)
  - `backend/app/websocket/handler.py:63-84` - Message handling pattern

## Open Questions

None - all design decisions have been made.

## Summary

This plan implements WebSocket-based CRUD operations with **proper separation of concerns**:

1. **Kernel owns ALL cell state** - Create, update, delete all flow through kernel IPC
2. **Coordinator is pure routing** - Never manipulates cells directly, only routes and broadcasts
3. **Fixed IPC pattern** - Timeouts prevent hanging, error handling is robust
4. **Deletion triggers cascades** - Dependent cells re-execute when upstream cell is deleted
5. **REST API is removed** - WebSocket is the single interface for cell operations

The architecture now correctly follows the hexagonal pattern:
- **Interface Layer** (WebSocket) → **Orchestration Layer** (Coordinator) → **Kernel Layer** (Execution Engine)
