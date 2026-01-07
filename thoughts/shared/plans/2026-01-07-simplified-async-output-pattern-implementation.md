# Simplified Async Output Pattern Implementation Plan

## Overview

This plan implements the "radically simplified async pattern" described in [2026-01-07-simplified-async-output-pattern.md](../research/2026-01-07-simplified-async-output-pattern.md). The core changes transform the architecture from a **blocking request-response model** to a **fully async streaming model** where all coordinator handlers return immediately and a background task continuously streams kernel outputs to clients.

## Current State Analysis

### Blocking Request-Response Architecture

**Coordinator Pattern** ([coordinator.py:64-122](backend/app/orchestration/coordinator.py)):
- Handlers send requests to kernel via `input_queue.put()`
- Handlers **block** waiting for responses via `await loop.run_in_executor(None, output_queue.get)`
- No background task processing outputs
- Each handler reads from output queue inline
- **Maintains execution state** in memory (status, outputs, errors) - unnecessarily duplicates client state

**Message Types** ([kernel/types.py](backend/app/kernel/types.py)):
- Multiple result types: `RegisterCellResult`, `ExecutionResult`, `SetDatabaseConfigResult`
- Cascade handled via `is_last` metadata flag
- Status changes implicit in result types

**CRUD Operations**:
- Cell creation via REST API only ([cells.py:14-47](backend/app/api/cells.py))
- Cell deletion via REST API only ([cells.py:49-63](backend/app/api/cells.py))
- No WebSocket broadcasts for CRUD
- No kernel graph cleanup on deletion

**Frontend Cell Editing** ([NotebookCell.tsx:105-117](frontend/src/components/NotebookCell.tsx)):
- Blur event saves code but does NOT trigger execution
- Auto-run only triggers after 1500ms debounce while typing

**Kernel Request Handling** ([process.py:105-110](backend/app/kernel/process.py)):
- Falls through to `ExecuteRequest` parsing if not shutdown/register/db_config
- No explicit `if request_data.get('type') == 'execute'` check
- Implicit default handler (problematic for extensibility)

### Key Discoveries

1. **Kernel health check exists**: `self.kernel.process.is_alive()` in [manager.py:42](backend/app/kernel/manager.py)
2. **Frontend already supports streaming**: Incremental updates via `cell_stdout`, `cell_output`, `cell_status`
3. **Each connection has isolated kernel**: One kernel process per WebSocket connection
4. **Broadcasting is global**: All clients receive all updates (suitable for collaboration)

## System Context Analysis

The notebook system uses a **process-isolated kernel architecture** where:
- Main FastAPI app handles HTTP/WebSocket
- Separate kernel process maintains Python execution state
- IPC via multiprocessing queues (blocking by design)
- Dependency graph tracks reactive relationships

The current blocking pattern creates **handler thread starvation** because each handler consumes a thread pool thread while waiting for kernel responses. The async pattern eliminates this by:
1. Handlers return immediately (no thread consumption)
2. Single background task streams outputs (one thread per coordinator)
3. Kernel's sequential processing provides all needed synchronization

This addresses the root cause (thread pool exhaustion under load) rather than symptoms (slow handlers).

## Desired End State

### Fully Async Streaming Architecture

**Handlers return immediately**:
- Send request to kernel via `input_queue.put()`
- Return without waiting for response
- No blocking `queue.get()` calls in handlers

**Single background task streams outputs**:
- `_process_output_queue()` runs continuously from `__init__`
- Reads from `output_queue` with timeout
- Detects kernel death via `process.is_alive()`
- Broadcasts all notifications immediately
- **Stateless for execution results** - no in-memory tracking of status/outputs/errors

**Coordinator state is minimal**:
- Only tracks notebook structure: `{id, name, db_conn_string, cells: [{id, type, code}]}`
- Execution state (status, outputs, errors, reads/writes) lives only in frontend
- File persistence only stores structure, not execution results
- Acts as pure message router between kernel and clients

**Unified message type**:
- `CellNotification` with `CellOutput` payload
- `CellChannel` enum discriminates output types (output/stdout/stderr/status/error/metadata)
- All kernel outputs use same structure

**WebSocket-based CRUD**:
- Cell creation via WebSocket with optimistic updates
- Cell deletion via WebSocket with kernel cleanup
- Immediate broadcast to all clients

**Auto-run on blur**:
- Frontend sends `cell_update` then `run_cell` on editor blur
- Matches debounced auto-run behavior

**Explicit request routing**:
- Kernel has explicit `if request_data.get('type') == 'execute':` handler
- No fallthrough to implicit default

### Verification

**Automated Testing**: Deferred to separate testing plan. Write minimal happy-path tests during implementation (Phase 2 onwards) using `uv run pytest tests/` to verify core functionality as you go.

**Manual**:
- [ ] Cell editing streams status changes in real-time (validating → idle/blocked)
- [ ] Cell execution streams outputs incrementally (not batched)
- [ ] Cascade execution shows running status for each cell as it executes
- [ ] Blur triggers save + execution
- [ ] Multiple browser tabs see each other's updates in real-time
- [ ] Cell creation/deletion propagates to all connected clients
- [ ] Kernel death detected and error shown to user

## What We're NOT Doing

- Kernel restart/recovery after death (manual reconnect required)
- Queue overflow handling with bounded queues
- Shared kernel per notebook (each connection keeps isolated kernel)
- Conflict resolution for concurrent edits (last write wins)
- Request timeout handling in handlers (not needed with async pattern)
- Backwards compatibility with old message types
- Comprehensive test suite refactoring (separate plan after implementation)

---

## Phase 1: Unified Message Types

### Overview
Create unified `CellNotification` message type and update kernel to emit all outputs using this format. This phase maintains the old coordinator pattern (blocking) to verify message format correctness before changing the async model.

### Changes Required

#### 1. Create Unified Message Types
**File**: `backend/app/kernel/types.py`

**Add new types**:

```python
import time
from enum import Enum

class CellChannel(str, Enum):
    """Channel discriminator for different output types."""
    OUTPUT = "output"           # Cell's final output (rich display)
    STDOUT = "stdout"           # Print statements
    STDERR = "stderr"           # Error output
    STATUS = "status"           # Cell status changes (idle/running/success/error/blocked)
    ERROR = "error"             # Error details (tracebacks, cycle errors)
    METADATA = "metadata"       # Dependency metadata (reads/writes)


class CellOutput(BaseModel):
    """Output payload - discriminated by channel."""
    channel: CellChannel
    mimetype: str
    data: str | dict | list
    timestamp: float = Field(default_factory=lambda: time.time())


class CellNotification(BaseModel):
    """
    Unified message type for ALL kernel outputs.
    Follows observable pattern - kernel emits notifications, frontend reacts.
    """
    type: Literal["cell_notification"] = "cell_notification"
    cell_id: str
    output: CellOutput
```

**Keep existing types** for requests (no changes):
- `RegisterCellRequest`
- `ExecuteRequest`
- `SetDatabaseConfigRequest`
- `ShutdownRequest`

#### 2. Update Kernel to Emit Unified Notifications
**File**: `backend/app/kernel/process.py`

**Add explicit execute handler** (after line 103):

```python
# Handle execute request (make explicit instead of fallthrough)
if request_data.get('type') == 'execute':
    try:
        request = ExecuteRequest(**request_data)
    except Exception as e:
        print(f"[Kernel] Invalid execute request: {e}")
        continue

    # Verify cell is registered
    if request.cell_id not in cell_registry:
        error_msg = (
            f"Cell {request.cell_id} not registered. "
            "Cells must be registered via RegisterCellRequest before execution."
        )
        output_queue.put(CellNotification(
            cell_id=request.cell_id,
            output=CellOutput(
                channel=CellChannel.ERROR,
                mimetype="application/json",
                data={
                    "error_type": "CellNotRegistered",
                    "message": error_msg
                }
            )
        ).model_dump())
        continue

    # Get execution order (reactive cascade)
    cells_to_run = graph.get_execution_order(request.cell_id)
    total_cells = len(cells_to_run)

    # Execute all affected cells in topological order
    for cell_id in cells_to_run:
        # ... execution logic with CellNotification emissions
```

**Cell Registration** (lines 35-77) - Replace result emission:

```python
# OLD (line 55-61):
result = RegisterCellResult(
    cell_id=register_req.cell_id,
    status='success',
    reads=list(reads),
    writes=list(writes)
)
output_queue.put(result.model_dump())

# NEW:
# Send metadata notification
output_queue.put(CellNotification(
    cell_id=register_req.cell_id,
    output=CellOutput(
        channel=CellChannel.METADATA,
        mimetype="application/json",
        data={"reads": list(reads), "writes": list(writes)}
    )
).model_dump())

# Send status notification
output_queue.put(CellNotification(
    cell_id=register_req.cell_id,
    output=CellOutput(
        channel=CellChannel.STATUS,
        mimetype="application/json",
        data={"status": "idle"}
    )
).model_dump())
```

**Cycle Detection** (lines 63-72) - Replace error emission:

```python
# NEW:
# Send error notification
output_queue.put(CellNotification(
    cell_id=register_req.cell_id,
    output=CellOutput(
        channel=CellChannel.ERROR,
        mimetype="application/json",
        data={
            "error_type": "CycleDetectedError",
            "message": str(e)
        }
    )
).model_dump())

# Send blocked status
output_queue.put(CellNotification(
    cell_id=register_req.cell_id,
    output=CellOutput(
        channel=CellChannel.STATUS,
        mimetype="application/json",
        data={"status": "blocked"}
    )
).model_dump())
```

**Cell Execution** - Stream notifications during execution:

```python
# Send status: running
output_queue.put(CellNotification(
    cell_id=cell_id,
    output=CellOutput(
        channel=CellChannel.STATUS,
        mimetype="application/json",
        data={"status": "running"}
    )
).model_dump())

# Execute cell...
if cell_type == 'python':
    exec_result = python_executor.execute(cell_code)
else:
    # SQL execution...

# Send stdout (if any)
if exec_result.stdout:
    output_queue.put(CellNotification(
        cell_id=cell_id,
        output=CellOutput(
            channel=CellChannel.STDOUT,
            mimetype="text/plain",
            data=exec_result.stdout
        )
    ).model_dump())

# Send outputs (plots, tables, etc.)
for output in exec_result.outputs:
    output_queue.put(CellNotification(
        cell_id=cell_id,
        output=CellOutput(
            channel=CellChannel.OUTPUT,
            mimetype=output.mime_type,
            data=output.data
        )
    ).model_dump())

# Send status: success or error
status = "success" if exec_result.status == "success" else "error"
output_queue.put(CellNotification(
    cell_id=cell_id,
    output=CellOutput(
        channel=CellChannel.STATUS,
        mimetype="application/json",
        data={"status": status}
    )
).model_dump())

# Send error details (if any)
if exec_result.error:
    output_queue.put(CellNotification(
        cell_id=cell_id,
        output=CellOutput(
            channel=CellChannel.ERROR,
            mimetype="application/json",
            data={
                "error_type": "RuntimeError",
                "message": exec_result.error
            }
        )
    ).model_dump())

# Send metadata (dependency info)
output_queue.put(CellNotification(
    cell_id=cell_id,
    output=CellOutput(
        channel=CellChannel.METADATA,
        mimetype="application/json",
        data={
            "reads": list(cell_reads),
            "writes": list(cell_writes)
        }
    )
).model_dump())
```

**Database Configuration** (lines 80-103) - Use system cell_id:

```python
# NEW:
# Send status notification (use special "system" cell_id for non-cell messages)
output_queue.put(CellNotification(
    cell_id="__system__",
    output=CellOutput(
        channel=CellChannel.STATUS,
        mimetype="application/json",
        data={"status": "db_configured"}
    )
).model_dump())
```

#### 3. Update Coordinator to Handle Unified Messages (Temporarily)
**File**: `backend/app/orchestration/coordinator.py`

Update `handle_cell_update` (lines 64-122) to parse `CellNotification` instead of `RegisterCellResult`. This phase keeps blocking pattern but adapts to new messages.

**Note**: This phase keeps the blocking pattern but adapts to new message format. Phase 2 will replace this with the background task.

### Success Criteria

#### Minimal Testing (As You Go):
- [ ] Write one happy-path test: cell registration returns notifications
- [ ] Write one happy-path test: cell execution returns notifications
- [ ] Run with: `uv run pytest tests/test_kernel_notifications.py -v`

#### Manual Verification:
- [x] Cell registration still works (code updates reflected)
- [x] Cycle detection still shows blocked status
- [x] Cell execution produces same outputs as before
- [x] Database configuration still works
- [x] WebSocket messages visible in browser DevTools match new format

**Phase 1 Complete** ✓

---

## Phase 2: Async Coordinator Pattern

### Overview
Replace blocking handlers with non-blocking handlers that return immediately. Add background task to continuously stream outputs from kernel. This is the core architectural change.

### Changes Required

#### 1. Add Background Task to Coordinator
**File**: `backend/app/orchestration/coordinator.py`

**Update `__init__`** (lines 24-31):

```python
def __init__(self, broadcaster):
    self.kernel = KernelManager()
    self.kernel.start()

    self.broadcaster = broadcaster
    self.notebook_id: Optional[str] = None
    self.notebook: Optional[NotebookResponse] = None

    # NEW: Background task flag and task handle
    self._running = True
    self._output_task: Optional[asyncio.Task] = None

async def _start_background_task(self):
    """Start background output processing task."""
    self._output_task = asyncio.create_task(self._process_output_queue())
```

**Add background processing loop**:

```python
async def _process_output_queue(self):
    """
    Background task that continuously processes ALL kernel outputs.
    This is the ONLY place that reads from output_queue.

    The coordinator is STATELESS for execution results - it just routes
    messages from kernel to clients. All execution state (status, outputs,
    errors) lives only in the frontend.
    """
    loop = asyncio.get_event_loop()

    while self._running:
        try:
            # Read from output queue with timeout (1 second)
            msg = await loop.run_in_executor(
                None,
                lambda: self.kernel.output_queue.get(timeout=1)
            )

            # All messages are CellNotification
            from ..kernel.types import CellNotification
            notification = CellNotification(**msg)

            # Just broadcast - don't update state!
            # Clients maintain their own execution state from the stream
            await self._broadcast_notification(notification)

        except queue.Empty:
            # Check if kernel is alive
            if not self.kernel.process.is_alive():
                print("[Coordinator] Kernel died!")
                await self._handle_kernel_death()
                break
            continue
        except Exception as e:
            print(f"[Coordinator] Error processing output: {e}")
            import traceback
            traceback.print_exc()
            continue

async def _broadcast_notification(self, notification: CellNotification):
    """Broadcast notification to WebSocket clients."""
    from ..kernel.types import CellChannel

    channel = notification.output.channel
    cell_id = notification.cell_id
    data = notification.output.data

    # Handle system messages
    if cell_id == "__system__":
        if channel == CellChannel.STATUS and data.get("status") == "db_configured":
            await self.broadcaster.broadcast({
                'type': 'db_connection_updated',
                'connectionString': self.notebook.db_conn_string,
                'status': 'success'
            })
        elif channel == CellChannel.ERROR:
            await self.broadcaster.broadcast({
                'type': 'db_connection_updated',
                'connectionString': self.notebook.db_conn_string,
                'status': 'error',
                'error': data.get("message")
            })
        return

    # Broadcast cell-specific messages
    if channel == CellChannel.STATUS:
        await self.broadcaster.broadcast({
            'type': 'cell_status',
            'cellId': cell_id,
            'status': data.get("status")
        })
    elif channel == CellChannel.STDOUT:
        await self.broadcaster.broadcast({
            'type': 'cell_stdout',
            'cellId': cell_id,
            'data': data
        })
    elif channel == CellChannel.OUTPUT:
        await self.broadcaster.broadcast({
            'type': 'cell_output',
            'cellId': cell_id,
            'output': {
                'mimetype': notification.output.mimetype,
                'data': data
            }
        })
    elif channel == CellChannel.ERROR:
        await self.broadcaster.broadcast({
            'type': 'cell_error',
            'cellId': cell_id,
            'error': data.get("message")
        })
    elif channel == CellChannel.METADATA:
        await self.broadcaster.broadcast({
            'type': 'cell_updated',
            'cellId': cell_id,
            'cell': {
                'reads': data.get("reads", []),
                'writes': data.get("writes", [])
            }
        })

async def _handle_kernel_death(self):
    """Handle kernel process death."""
    self._running = False

    # Broadcast error to all clients
    await self.broadcaster.broadcast({
        'type': 'kernel_error',
        'error': 'Kernel process died. Please reconnect.'
    })
```

#### 2. Update `load_notebook` to Start Background Task
**File**: `backend/app/orchestration/coordinator.py` (lines 33-62)

```python
async def load_notebook(self, notebook_id: str):
    """Load a notebook and send all cells to kernel for graph building."""
    self.notebook_id = notebook_id
    self.notebook = NotebookFileStorage.parse_notebook(notebook_id)

    if not self.notebook:
        raise ValueError(f"Notebook {notebook_id} not found")

    # Start background task BEFORE registering cells
    await self._start_background_task()

    # Register all cells with the kernel to build dependency graph
    for cell in self.notebook.cells:
        register_req = RegisterCellRequest(
            cell_id=cell.id,
            code=cell.code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(register_req.model_dump())
        # Do NOT wait for response - background task handles it

    # Wait a bit for registration to complete
    await asyncio.sleep(0.5)

    # Configure database if connection string exists
    if self.notebook.db_conn_string:
        await self._configure_database(self.notebook.db_conn_string)
```

#### 3. Make Handlers Non-Blocking

**Update `handle_cell_update`** - Remove blocking:

```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Handle a cell code update - returns immediately."""
    if not self.notebook:
        return

    # Find cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Optimistic update
    cell.code = new_code
    NotebookFileStorage.serialize_notebook(self.notebook)

    # Send to kernel
    register_req = RegisterCellRequest(
        cell_id=cell_id,
        code=cell.code,
        cell_type=cell.type
    )
    self.kernel.input_queue.put(register_req.model_dump())

    # Return immediately - background task handles responses
```

**Update `handle_run_cell`** - Remove blocking:

```python
async def handle_run_cell(self, cell_id: str):
    """Execute a cell - returns immediately."""
    if not self.notebook:
        return

    # Find cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Send to kernel
    request = ExecuteRequest(
        cell_id=cell_id,
        code=cell.code,
        cell_type=cell.type
    )
    self.kernel.input_queue.put(request.model_dump())

    # Return immediately - background task handles responses
```

**Update `_configure_database`** - Remove blocking:

```python
async def _configure_database(self, connection_string: str) -> None:
    """
    Send database connection string to kernel - returns immediately.
    Success/error will be broadcast via background task.
    """
    request = SetDatabaseConfigRequest(connection_string=connection_string)
    self.kernel.input_queue.put(request.model_dump())
    # Return immediately
```

**Update `handle_db_connection_update`**:

```python
async def handle_db_connection_update(self, connection_string: str):
    """Handle database connection string update - returns immediately."""
    if not self.notebook:
        return

    # Optimistic update
    self.notebook.db_conn_string = connection_string
    NotebookFileStorage.serialize_notebook(self.notebook)

    # Send to kernel
    await self._configure_database(connection_string)

    # Return immediately - background task broadcasts result
```

#### 4. Remove Old Helper Methods

**Delete** `_execute_via_kernel` (lines 185-208) - No longer needed
**Delete** `_broadcast_execution_result` (lines 210-273) - Replaced by `_broadcast_notification`

#### 5. Update Shutdown Method

```python
def shutdown(self):
    """Stop the background task and kernel process."""
    self._running = False

    # Wait for background task to finish
    if self._output_task and not self._output_task.done():
        self._output_task.cancel()

    # Stop kernel
    if self.kernel:
        self.kernel.stop()
```

#### 6. Add Missing Import

**Add to imports** (top of file):

```python
import queue  # For queue.Empty exception
```

#### 7. Simplify Models (Optional but Recommended)

**File**: `backend/app/models.py`

The `CellResponse` model currently includes execution state fields that are no longer needed in the coordinator:

```python
class CellResponse(BaseModel):
    id: str
    type: CellType
    code: str
    # The following fields can be removed from coordinator's in-memory model:
    # status: CellStatus = "idle"
    # stdout: Optional[str] = None
    # outputs: list[OutputResponse] = Field(default_factory=list)
    # error: Optional[str] = None
    # reads: list[str] = Field(default_factory=list)
    # writes: list[str] = Field(default_factory=list)
```

**Options**:
1. **Keep model as-is** but don't populate execution fields in coordinator (easier, no breaking changes)
2. **Create separate models**: `CellStructure` (coordinator) vs `CellResponse` (API/frontend) (cleaner separation)

**Recommendation**: Keep model as-is for now (Option 1) - focus on behavior changes first, refactor models later if needed.

### Success Criteria

#### Minimal Testing (As You Go):
- [ ] Write one happy-path test: handler returns in < 100ms
- [ ] Write one happy-path test: background task broadcasts messages
- [ ] Run with: `uv run pytest tests/test_coordinator_async.py -v`

#### Manual Verification:
- [x] Handlers return instantly (no blocking)
- [x] Cell status changes stream in real-time
- [x] Execution outputs appear incrementally (not batched)
- [x] Cascade execution shows each cell status as it runs
- [x] Kernel death detected and error displayed
- [x] Database config updates work without blocking

**Phase 2 Complete** ✓

---

## Phase 3: WebSocket CRUD Operations

### Overview
Move cell creation and deletion from REST API to WebSocket handlers with optimistic updates and kernel synchronization.

### Changes Required

#### 1-2. Add Cell Creation/Deletion Handlers to Coordinator
**File**: `backend/app/orchestration/coordinator.py`

See detailed implementation in full plan above.

#### 3. Add DeleteCellRequest Type
**File**: `backend/app/kernel/types.py`

```python
class DeleteCellRequest(BaseModel):
    """Request to delete cell and cascade to dependents."""
    type: Literal["delete_cell"] = "delete_cell"
    cell_id: str
```

#### 4. Add Kernel Support for Cell Deletion
**File**: `backend/app/kernel/process.py`

Add handler after database config handler (after line 103). See full plan for implementation.

#### 5. Add WebSocket Handlers
**File**: `backend/app/websocket/handler.py`

Add `cell_create` and `cell_delete` message handlers.

#### 6-7. Update Frontend and Remove REST Endpoints

Update `NotebookApp.tsx` to use WebSocket for CRUD. Delete `backend/app/api/cells.py`.

### Success Criteria

#### Minimal Testing (As You Go):
- [ ] Write one happy-path test: cell creation broadcasts to clients
- [ ] Write one happy-path test: cell deletion removes from notebook
- [ ] Run with: `uv run pytest tests/test_websocket_crud.py -v`

#### Manual Verification:
- [ ] Create cell button works and broadcasts to other clients
- [ ] Delete cell button works and broadcasts to other clients
- [ ] Deleting cell with dependents re-executes them
- [ ] Cell creation appears immediately (optimistic)
- [ ] Cell deletion removes immediately (optimistic)
- [ ] Multiple browser tabs see CRUD operations in real-time

---

## Phase 4: Frontend Behavior Updates

### Overview
Update frontend to send `run_cell` after `cell_update` on blur event, matching the debounced auto-run behavior.

### Changes Required

#### 1. Update Blur Handler to Trigger Execution
**File**: `frontend/src/components/NotebookCell.tsx`

**Update `handleEditorBlur`** (lines 105-117):

```typescript
const handleEditorBlur = async () => {
  // Cancel auto-run timer if active
  if (autoRunTimer) {
    clearTimeout(autoRunTimer);
    setAutoRunTimer(null);
  }

  // If there are unsaved changes, save AND run
  if (hasUnsavedChangesRef.current && localCode !== cell.code) {
    await onUpdateCode(localCode);
    hasUnsavedChangesRef.current = false;

    // NEW: Trigger execution after save
    onRun();
  }
};
```

### Success Criteria

#### Minimal Testing (As You Go):
- [ ] Frontend compiles without TypeScript errors
- [ ] No console errors in browser DevTools

#### Manual Verification:
- [x] Typing in cell then clicking away triggers save + execution
- [x] Typing and waiting 1500ms triggers save + execution (existing behavior)
- [x] Shift+Enter still works (save + execute)
- [x] Blur event sends `cell_update` before `run_cell` (check DevTools Network tab)

**Phase 4 Complete** ✓

---

## Phase 5: Multi-Client Broadcasting

### Overview
Verify that broadcasts properly propagate to all clients connected to the same notebook. This phase is mostly validation since the architecture already supports it.

### Changes Required

#### 1. Verify Broadcasting Scope
No code changes needed - current broadcast to all connections is correct.

#### 2. Add Frontend Message Type Definitions
**File**: `frontend/src/useNotebookWebSocket.ts`

Add `kernel_error` message type:

```typescript
| {
    type: "kernel_error";
    error: string;
  };
```

#### 3. Handle Kernel Error in Frontend
**File**: `frontend/src/components/NotebookApp.tsx`

```typescript
case "kernel_error":
  console.error("Kernel error:", msg.error);
  alert(`Kernel crashed: ${msg.error}\n\nPlease refresh the page.`);
  break;
```

### Success Criteria

#### Minimal Testing (As You Go):
- [ ] Manually test with two browser tabs side-by-side
- [ ] Verify updates propagate between clients

#### Manual Verification:
- [x] Open notebook in two browser tabs
- [x] Edit cell in Tab A → Tab B sees update immediately
- [x] Run cell in Tab A → Tab B sees execution status and outputs
- [ ] Create cell in Tab A → Tab B sees new cell appear (Phase 3 not implemented)
- [ ] Delete cell in Tab A → Tab B sees cell disappear (Phase 3 not implemented)
- [x] Update database connection in Tab A → Tab B sees connection update
- [x] Kernel death → all clients receive error message

**Phase 5 Partially Complete** ✓ (Phase 3 CRUD operations deferred)

---

## Testing Strategy

### Approach
Write **minimal happy-path tests as you implement each phase** to verify core functionality. Defer comprehensive test suite refactoring to a separate testing plan after implementation is complete.

### Example Happy-Path Tests (Write During Implementation)

**Phase 1 - Kernel emits notifications** (`backend/tests/test_kernel_notifications.py`):
```python
def test_kernel_emits_cell_notification():
    """Basic test: kernel sends CellNotification format."""
    from multiprocessing import Queue
    from backend.app.kernel.types import RegisterCellRequest

    input_q = Queue()
    output_q = Queue()

    # Start kernel in background...
    # Send register request
    input_q.put(RegisterCellRequest(
        cell_id='test',
        code='x = 1',
        cell_type='python'
    ).model_dump())

    # Read response
    msg = output_q.get(timeout=2)
    assert msg['type'] == 'cell_notification'
    assert 'output' in msg
```

**Phase 2 - Handler returns quickly** (`backend/tests/test_coordinator_async.py`):
```python
@pytest.mark.asyncio
async def test_handler_returns_immediately():
    """Verify handler doesn't block."""
    import time
    coordinator = NotebookCoordinator(MockBroadcaster())

    start = time.time()
    await coordinator.handle_cell_update('cell-1', 'x = 10')
    duration = time.time() - start

    # Should return in < 100ms
    assert duration < 0.1
```

Run with: `uv run pytest tests/ -v -k "test_name"`

### Manual Testing Steps

1. **Basic editing and execution**: Type code, verify status changes, blur to run
2. **Cascade execution**: Create dependent cells, verify cascade streams
3. **Cycle detection**: Create cycle, verify blocked status
4. **Multi-client collaboration**: Two tabs, verify updates propagate
5. **Kernel death recovery**: Kill kernel, verify error shown

---

## Architectural Benefits: Stateless Coordinator

### Why Remove State Tracking?

The coordinator no longer needs to maintain execution state because:

1. **Single Source of Truth**: Execution state lives in exactly one place - the frontend that displays it
2. **No Stale State**: Can't have coordinator state diverging from frontend state
3. **Simpler Recovery**: On reconnect, frontend just requests notebook structure, execution state rebuilds from scratch
4. **Memory Efficient**: Coordinator doesn't accumulate outputs/stdout across all cells
5. **True Streaming**: Coordinator is a pure message router, not a state store

### What Coordinator Maintains

**Structure only**:
- `notebook_id`, `name`, `db_conn_string`
- `cells[]` with just `id`, `type`, `code`

**What it does NOT maintain**:
- ❌ `cell.status` (kernel tracks, frontend displays)
- ❌ `cell.stdout` (streamed to frontend, not accumulated)
- ❌ `cell.outputs[]` (streamed to frontend, not accumulated)
- ❌ `cell.error` (streamed to frontend)
- ❌ `cell.reads/writes` (kernel tracks for graph, frontend displays)

### Persistence Model

**Notebook file on disk** (`.py` format):
```python
# id: abc-123
# name: My Notebook
# db_conn_string: postgresql://...

# cell: cell-1
# type: python
x = 10

# cell: cell-2
# type: python
y = x + 5
```

**What's persisted**: Only structure and code
**What's NOT persisted**: Execution results (ephemeral, like Jupyter)

On page refresh, frontend starts with empty execution state. User can re-run cells to regenerate outputs.

---

## Performance Considerations

### Thread Pool Usage

**Before**: Each handler blocks → consumes one thread from asyncio executor pool
- 10 concurrent requests = 10 threads blocked
- Default thread pool size = 5-10 threads

**After**: Handlers return immediately → no thread consumption
- 10 concurrent requests = 0 threads blocked (just queue puts)
- Only 1 thread per coordinator (background task reading queue)

### Latency

**Before**: Batch cascade results → 3-cell cascade taking 3 seconds = 3 second delay
**After**: Stream outputs as they arrive → first output after 1 second

### Memory Usage

**Before**: Collect all cascade results in list
**After**: Broadcast immediately, constant memory

---

## Migration Notes

### Breaking Changes

1. **REST API removed**: Cell creation/deletion now WebSocket-only
2. **Message format changed**: Old result types replaced with `CellNotification`
3. **No synchronous responses**: Handlers return immediately, responses via broadcast

### Deployment Strategy

Since backwards compatibility is not required:

1. **Deploy backend + frontend together** (atomic update)
2. **Existing WebSocket connections will disconnect** (clients must refresh)
3. **File format unchanged** (notebooks on disk remain compatible)

### Rollback Plan

If issues arise:
1. Revert to previous git commit
2. Restart backend services
3. Clients refresh to reconnect

---

## References

- Original research: [thoughts/shared/research/2026-01-07-simplified-async-output-pattern.md](../research/2026-01-07-simplified-async-output-pattern.md)
- Current coordinator: [backend/app/orchestration/coordinator.py](backend/app/orchestration/coordinator.py)
- Current kernel: [backend/app/kernel/process.py](backend/app/kernel/process.py)
- Message types: [backend/app/kernel/types.py](backend/app/kernel/types.py)
- WebSocket handler: [backend/app/websocket/handler.py](backend/app/websocket/handler.py)
- Frontend WebSocket hook: [frontend/src/useNotebookWebSocket.ts](frontend/src/useNotebookWebSocket.ts)

---

## Conclusion

This implementation transforms the architecture from a blocking request-response model to a fully async streaming model. The key insight is that **kernel's sequential processing provides all needed synchronization** - handlers don't need to wait for responses because:

1. ✅ Kernel processes requests in FIFO order (guarantees ordering)
2. ✅ Background task streams outputs as they arrive (true streaming)
3. ✅ Frontend reacts optimistically (instant UI updates)
4. ✅ Errors appear when detected (no blocking waits)

The result is a simpler, faster, more scalable architecture that eliminates thread pool exhaustion and enables real-time collaborative editing.
