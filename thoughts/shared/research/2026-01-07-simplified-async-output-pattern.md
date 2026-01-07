---
date: 2026-01-07
researcher: Matthew Carter + Claude
topic: "Simplified Async Output Pattern - Everything is Async"
tags: [research, architecture, async, queue, websocket, output-only, streaming]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Simplified Async Output Pattern - Everything is Async

**Date**: 2026-01-07
**Researchers**: Matthew Carter + Claude

## Executive Summary

This document describes a **radically simplified async pattern** where:
1. **ALL handlers send commands and return immediately** (no waiting, no Event coordination)
2. **Kernel processes commands sequentially** (FIFO queue guarantees ordering)
3. **Background task streams ALL outputs** (results, status changes, errors)
4. **Frontend reacts to output stream** (optimistic updates + corrections)

**Key Insight**: The kernel's **sequential processing** provides all the synchronization you need. You don't need to wait for responses in handlers.

---

## The Simplified Pattern

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    WebSocket Handler                             │
│  - Receives messages                                             │
│  - Routes to coordinator                                         │
│  - Returns immediately (always)                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ async function call (non-blocking)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Coordinator (Stateless)                       │
│                                                                  │
│  ALL handlers follow same pattern:                               │
│    handle_*(args):                                               │
│      kernel.input_queue.put(request)                            │
│      return  # ← Always returns immediately!                    │
│                                                                  │
│  Background task (single loop):                                  │
│    _process_output_queue():                                     │
│      while True:                                                 │
│        msg = output_queue.get(timeout=1)                        │
│        broadcast(msg)  # ← Stream everything to frontend        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ IPC via multiprocessing.Queue
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kernel Process                                │
│  - Reads input_queue (FIFO - sequential processing)            │
│  - Processes each command                                        │
│  - Writes ALL outputs to output_queue                           │
│    - Cell status changes                                         │
│    - Execution results                                           │
│    - Errors (cycles, validation, runtime)                       │
│    - Registration confirmations                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Message Types - Output Only

### Philosophy

**One unified message type for everything**: `CellNotification`

Similar to how some systems use a single "cell operation" message that carries different payloads, we use one message type with a `channel` discriminator.

### Unified Message Structure

```python
class CellNotification(BaseModel):
    """
    Unified message type for ALL kernel outputs.
    Follows observable pattern - kernel emits notifications, frontend reacts.
    """
    type: Literal["cell_notification"] = "cell_notification"
    cell_id: str
    output: CellOutput


class CellOutput(BaseModel):
    """Output payload - discriminated by channel."""
    channel: CellChannel
    mimetype: str
    data: str | dict | list
    timestamp: float = Field(default_factory=lambda: time.time())


class CellChannel(str, Enum):
    """Channel discriminator for different output types."""
    OUTPUT = "output"           # Cell's final output (rich display)
    STDOUT = "stdout"           # Print statements
    STDERR = "stderr"           # Error output
    STATUS = "status"           # Cell status changes (idle/running/success/error/blocked)
    ERROR = "error"             # Error details (tracebacks, cycle errors)
    METADATA = "metadata"       # Dependency metadata (reads/writes)
```

### Examples

**Cell Status Change**:
```json
{
  "type": "cell_notification",
  "cell_id": "abc123",
  "output": {
    "channel": "status",
    "mimetype": "application/json",
    "data": {"status": "running"},
    "timestamp": 1704552505.123
  }
}
```

**Cell Output**:
```json
{
  "type": "cell_notification",
  "cell_id": "abc123",
  "output": {
    "channel": "output",
    "mimetype": "text/html",
    "data": "<div>Hello World</div>",
    "timestamp": 1704552505.456
  }
}
```

**Cycle Error**:
```json
{
  "type": "cell_notification",
  "cell_id": "abc123",
  "output": {
    "channel": "error",
    "mimetype": "application/json",
    "data": {
      "error_type": "CycleDetectedError",
      "message": "Cell creates cycle: abc123 -> def456 -> abc123"
    },
    "timestamp": 1704552505.789
  }
}
```

**Dependency Metadata**:
```json
{
  "type": "cell_notification",
  "cell_id": "abc123",
  "output": {
    "channel": "metadata",
    "mimetype": "application/json",
    "data": {
      "reads": ["x", "y"],
      "writes": ["z"]
    },
    "timestamp": 1704552506.012
  }
}
```

---

## Kernel Output Flow

### Cell Update (Registration)

**User types in cell** → Frontend sends `cell_update` → Coordinator sends `RegisterCellRequest` → Kernel processes:

```python
# In kernel process
if request_data.get('type') == 'register_cell':
    try:
        # Extract dependencies
        reads, writes = extract_dependencies(code)

        # Send status update
        output_queue.put(CellNotification(
            cell_id=cell_id,
            output=CellOutput(
                channel="status",
                mimetype="application/json",
                data={"status": "validating"}
            )
        ).model_dump())

        # Update graph (may detect cycle)
        graph.update_cell(cell_id, reads, writes)

        # Success - send metadata
        output_queue.put(CellNotification(
            cell_id=cell_id,
            output=CellOutput(
                channel="metadata",
                mimetype="application/json",
                data={"reads": list(reads), "writes": list(writes)}
            )
        ).model_dump())

        # Send status update
        output_queue.put(CellNotification(
            cell_id=cell_id,
            output=CellOutput(
                channel="status",
                mimetype="application/json",
                data={"status": "idle"}
            )
        ).model_dump())

    except CycleDetectedError as e:
        # Send error
        output_queue.put(CellNotification(
            cell_id=cell_id,
            output=CellOutput(
                channel="error",
                mimetype="application/json",
                data={
                    "error_type": "CycleDetectedError",
                    "message": str(e)
                }
            )
        ).model_dump())

        # Send status update
        output_queue.put(CellNotification(
            cell_id=cell_id,
            output=CellOutput(
                channel="status",
                mimetype="application/json",
                data={"status": "blocked"}
            )
        ).model_dump())
```

**Output sequence**:
1. `channel="status"` → `"validating"`
2. `channel="metadata"` → `{"reads": [...], "writes": [...]}`
3. `channel="status"` → `"idle"` OR `"blocked"` if cycle
4. `channel="error"` → error details (if cycle)

---

### Cell Execution (With Cascade)

**User runs cell** → Frontend sends `run_cell` → Coordinator sends `ExecuteRequest` → Kernel processes:

```python
# In kernel process
if request_data.get('type') == 'execute':
    # Get execution order (reactive cascade)
    cells_to_run = graph.get_execution_order(cell_id)

    for current_cell_id in cells_to_run:
        cell_code, cell_type = cell_registry[current_cell_id]

        # Send status: running
        output_queue.put(CellNotification(
            cell_id=current_cell_id,
            output=CellOutput(
                channel="status",
                mimetype="application/json",
                data={"status": "running"}
            )
        ).model_dump())

        # Execute cell
        try:
            exec_result = executor.execute(cell_code)

            # Send stdout (if any)
            if exec_result.stdout:
                output_queue.put(CellNotification(
                    cell_id=current_cell_id,
                    output=CellOutput(
                        channel="stdout",
                        mimetype="text/plain",
                        data=exec_result.stdout
                    )
                ).model_dump())

            # Send outputs (plots, tables, etc.)
            for output in exec_result.outputs:
                output_queue.put(CellNotification(
                    cell_id=current_cell_id,
                    output=CellOutput(
                        channel="output",
                        mimetype=output.mime_type,
                        data=output.data
                    )
                ).model_dump())

            # Send status: success
            output_queue.put(CellNotification(
                cell_id=current_cell_id,
                output=CellOutput(
                    channel="status",
                    mimetype="application/json",
                    data={"status": "success"}
                )
            ).model_dump())

        except Exception as e:
            # Send error
            output_queue.put(CellNotification(
                cell_id=current_cell_id,
                output=CellOutput(
                    channel="error",
                    mimetype="application/json",
                    data={
                        "error_type": type(e).__name__,
                        "message": str(e),
                        "traceback": traceback.format_exc()
                    }
                ).model_dump())

            # Send status: error
            output_queue.put(CellNotification(
                cell_id=current_cell_id,
                output=CellOutput(
                    channel="status",
                    mimetype="application/json",
                    data={"status": "error"}
                )
            ).model_dump())
```

**Output sequence (per cell in cascade)**:
1. `channel="status"` → `"running"`
2. `channel="stdout"` → stdout text (if any)
3. `channel="output"` → rich outputs (plots, tables, etc.)
4. `channel="status"` → `"success"` or `"error"`
5. `channel="error"` → error details (if error)

**For 3-cell cascade**: Same sequence repeated 3 times (once per cell).

---

## Coordinator Implementation

### Unified Handler Pattern

**ALL handlers follow the same pattern** - send command and return:

```python
class NotebookCoordinator:
    def __init__(self, broadcaster):
        self.kernel = KernelManager()
        self.kernel.start()
        self.broadcaster = broadcaster
        self.notebook_id: Optional[str] = None
        self.notebook: Optional[NotebookResponse] = None

        # Start background task
        self._output_task = asyncio.create_task(self._process_output_queue())
        self._running = True

    # Pattern 1: Cell Update
    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Update cell code - returns immediately."""
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Optimistic update (frontend already shows new code)
        cell.code = new_code
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Send to kernel
        request = RegisterCellRequest(
            cell_id=cell_id,
            code=new_code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(request.model_dump())

        # Return immediately - background task handles responses

    # Pattern 2: Cell Execution
    async def handle_run_cell(self, cell_id: str):
        """Execute cell - returns immediately."""
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

    # Pattern 3: Cell Creation
    async def handle_cell_create(self, cell_type: str, after_cell_id: Optional[str] = None):
        """Create cell - returns immediately."""
        from uuid import uuid4

        cell_id = str(uuid4())

        # Optimistic update
        new_cell = CellResponse(
            id=cell_id,
            type=cell_type,
            code="",
            status="idle"
        )

        # Insert at position
        if after_cell_id:
            idx = next((i for i, c in enumerate(self.notebook.cells) if c.id == after_cell_id), None)
            if idx is not None:
                self.notebook.cells.insert(idx + 1, new_cell)
            else:
                self.notebook.cells.append(new_cell)
        else:
            self.notebook.cells.append(new_cell)

        NotebookFileStorage.serialize_notebook(self.notebook)

        # Send to kernel
        request = CreateCellRequest(
            cell_id=cell_id,
            cell_type=cell_type
        )
        self.kernel.input_queue.put(request.model_dump())

        # Broadcast immediately (optimistic)
        await self.broadcaster.broadcast({
            'type': 'cell_created',
            'cellId': cell_id,
            'cell': new_cell.model_dump()
        })

        # Return immediately

    # Pattern 4: Cell Deletion
    async def handle_cell_delete(self, cell_id: str):
        """Delete cell - returns immediately."""
        # Optimistic update
        self.notebook.cells = [c for c in self.notebook.cells if c.id != cell_id]
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Send to kernel
        request = DeleteCellRequest(cell_id=cell_id)
        self.kernel.input_queue.put(request.model_dump())

        # Broadcast immediately (optimistic)
        await self.broadcaster.broadcast({
            'type': 'cell_deleted',
            'cellId': cell_id
        })

        # Return immediately
        # Background task will stream cascade execution results
```

---

### Background Task - Single Loop

```python
    async def _process_output_queue(self):
        """
        Background task that continuously processes ALL kernel outputs.
        This is the ONLY place that reads from output_queue.
        """
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read from output queue with timeout
                msg = await loop.run_in_executor(
                    None,
                    lambda: self.kernel.output_queue.get(timeout=1)
                )

                # All messages are CellNotification
                notification = CellNotification(**msg)

                # Update in-memory state
                await self._update_cell_state(notification)

                # Broadcast to clients
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
                continue

    async def _update_cell_state(self, notification: CellNotification):
        """Update in-memory notebook state based on notification."""
        cell = next((c for c in self.notebook.cells if c.id == notification.cell_id), None)
        if not cell:
            return

        channel = notification.output.channel
        data = notification.output.data

        if channel == "status":
            cell.status = data.get("status")
        elif channel == "stdout":
            cell.stdout = data
        elif channel == "output":
            cell.outputs.append(notification.output)
        elif channel == "error":
            cell.error = data.get("message")
        elif channel == "metadata":
            cell.reads = data.get("reads", [])
            cell.writes = data.get("writes", [])

    async def _broadcast_notification(self, notification: CellNotification):
        """Broadcast notification to WebSocket clients."""
        # Convert to frontend message format
        channel = notification.output.channel
        cell_id = notification.cell_id
        data = notification.output.data

        if channel == "status":
            await self.broadcaster.broadcast({
                'type': 'cell_status',
                'cellId': cell_id,
                'status': data.get("status")
            })
        elif channel == "stdout":
            await self.broadcaster.broadcast({
                'type': 'cell_stdout',
                'cellId': cell_id,
                'data': data
            })
        elif channel == "output":
            await self.broadcaster.broadcast({
                'type': 'cell_output',
                'cellId': cell_id,
                'output': {
                    'mimetype': notification.output.mimetype,
                    'data': data
                }
            })
        elif channel == "error":
            await self.broadcaster.broadcast({
                'type': 'cell_error',
                'cellId': cell_id,
                'error': data.get("message"),
                'traceback': data.get("traceback")
            })
        elif channel == "metadata":
            await self.broadcaster.broadcast({
                'type': 'cell_updated',
                'cellId': cell_id,
                'cell': {
                    'reads': data.get("reads", []),
                    'writes': data.get("writes", [])
                }
            })
```

---

## Why This Works - Sequential Processing

### The Key Guarantee

**Kernel processes input_queue sequentially** (FIFO). This provides all synchronization guarantees:

```
User Action                Kernel Processing Order
-----------                -----------------------
1. Type "y = x + z"       → RegisterCellRequest(cell_1, "y = x + z")
2. Click Run              → ExecuteRequest(cell_1)
3. Type "z = 10"          → RegisterCellRequest(cell_2, "z = 10")
4. Click Run cell 2       → ExecuteRequest(cell_2)
```

**Even if all handlers return immediately**, kernel processes in order:
1. Registers cell_1 (updates graph)
2. Executes cell_1 (uses updated graph)
3. Registers cell_2 (updates graph again)
4. Executes cell_2 (uses latest graph)

**No race conditions** because kernel is single-threaded and sequential.

---

### Example: Cycle Detection

**Scenario**: User types code creating cycle, then immediately runs cell.

```
Timeline:
T0: User types "x = y" in cell A (creates cycle: A → B → A)
T1: Frontend sends cell_update
T2: Coordinator.handle_cell_update() returns immediately
T3: User clicks Run (Shift+Enter)
T4: Frontend sends run_cell
T5: Coordinator.handle_run_cell() returns immediately
T6: Kernel reads input_queue → RegisterCellRequest(A, "x = y")
T7: Kernel detects cycle → sends CellNotification(channel="error")
T8: Kernel reads input_queue → ExecuteRequest(A)
T9: Kernel sees cell A is blocked → refuses to execute → sends error
T10: Background task broadcasts both errors to frontend
```

**Frontend sees**:
- Cell status changes to "blocked" (from registration error)
- Error message: "Cell creates cycle: A → B → A"
- Execution error: "Cannot execute blocked cell"

**User experience**: Everything feels instant, errors appear as they're detected.

---

## Simplified Kernel Request Types

Since all responses flow through unified `CellNotification`, requests can be simple:

```python
# kernel/types.py

class RegisterCellRequest(BaseModel):
    """Register cell in dependency graph (updates reads/writes)."""
    type: Literal["register_cell"] = "register_cell"
    cell_id: str
    code: str
    cell_type: CellType


class ExecuteRequest(BaseModel):
    """Execute cell and cascade to dependents."""
    type: Literal["execute"] = "execute"
    cell_id: str
    code: str
    cell_type: CellType


class CreateCellRequest(BaseModel):
    """Create empty cell in kernel registry."""
    type: Literal["create_cell"] = "create_cell"
    cell_id: str
    cell_type: CellType


class DeleteCellRequest(BaseModel):
    """Delete cell and cascade to dependents."""
    type: Literal["delete_cell"] = "delete_cell"
    cell_id: str


class SetDatabaseConfigRequest(BaseModel):
    """Configure database connection."""
    type: Literal["set_database_config"] = "set_database_config"
    connection_string: str


class ShutdownRequest(BaseModel):
    """Shutdown kernel process."""
    type: Literal["shutdown"] = "shutdown"
```

**No separate result types!** All responses use `CellNotification`.

---

## Frontend Pattern - Optimistic Updates

Frontend doesn't wait for confirmation:

```typescript
// User types in cell
const handleCellUpdate = (cellId: string, newCode: string) => {
  // 1. Update UI immediately (optimistic)
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // 2. Send to backend
  ws.send(JSON.stringify({
    type: 'cell_update',
    cellId,
    code: newCode
  }));

  // 3. If kernel detects error, we'll receive notification and show error
};

// Receive notifications
const handleWebSocketMessage = (msg: WSMessage) => {
  switch (msg.type) {
    case "cell_status":
      // Update cell status
      setCells(prev => prev.map(c =>
        c.id === msg.cellId ? { ...c, status: msg.status } : c
      ));
      break;

    case "cell_error":
      // Show error (may be cycle, runtime error, etc.)
      setCells(prev => prev.map(c =>
        c.id === msg.cellId ? { ...c, error: msg.error } : c
      ));
      break;

    case "cell_output":
      // Append output
      setCells(prev => prev.map(c =>
        c.id === msg.cellId
          ? { ...c, outputs: [...c.outputs, msg.output] }
          : c
      ));
      break;
  }
};
```

**Benefits**:
- UI feels instant (no lag)
- Errors appear when detected
- Matches Jupyter/VSCode UX

---

## Performance Benefits

### 1. Zero Thread Pool Consumption

**Old pattern**:
```python
# Handler blocks on queue read
result = await loop.run_in_executor(None, queue.get)  # ← Consumes thread
```

**New pattern**:
```python
# Handler sends and returns
self.kernel.input_queue.put(request)  # ← No thread consumption
return
```

Only **1 thread per coordinator** (the background task).

---

### 2. True Streaming

**Old pattern**: Batch all cascade results, then broadcast
```
Cell A completes → Wait
Cell B completes → Wait
Cell C completes → Wait
Broadcast all 3 at once
```

**New pattern**: Stream as available
```
Cell A completes → Broadcast immediately
Cell B completes → Broadcast immediately
Cell C completes → Broadcast immediately
```

**Latency reduction**: User sees first result ~2 seconds earlier (in 3-cell cascade).

---

### 3. Memory Efficiency

**Old pattern**: Accumulate results in list
```python
results = []
while True:
    result = queue.get()
    results.append(result)  # ← Growing memory usage
```

**New pattern**: Broadcast immediately
```python
while True:
    notification = queue.get()
    broadcast(notification)  # ← Constant memory
```

---

## Error Handling

### Kernel Death

Background task detects and broadcasts:

```python
except queue.Empty:
    if not self.kernel.process.is_alive():
        print("[Coordinator] Kernel died!")

        # Broadcast error to all clients
        await self.broadcaster.broadcast({
            'type': 'kernel_error',
            'error': 'Kernel process died. Please reconnect.'
        })

        break  # Exit background task
```

---

### Malformed Messages

```python
try:
    notification = CellNotification(**msg)
except ValidationError as e:
    print(f"[Coordinator] Invalid message from kernel: {e}")
    print(f"Message: {msg}")
    continue  # Skip invalid message
```

---

### Queue Overflow

If kernel produces messages faster than coordinator can broadcast (unlikely):

```python
# Option 1: Bounded queue with backpressure
output_queue = Queue(maxsize=1000)

# Option 2: Drop old messages (lossy but prevents memory exhaustion)
try:
    output_queue.put_nowait(notification)
except queue.Full:
    # Queue full - drop oldest message
    try:
        output_queue.get_nowait()
        output_queue.put_nowait(notification)
    except queue.Empty:
        pass
```

---

## Comparison: Old vs New

### Old Pattern (Synchronous Registration)

```python
async def handle_cell_update(self, cell_id, code):
    # Create Event for coordination
    event = asyncio.Event()
    pending_ops[cell_id] = event

    # Send to kernel
    kernel.input_queue.put(RegisterCellRequest(...))

    # WAIT for response
    await asyncio.wait_for(event.wait(), timeout=10)

    # Get result
    result = results.pop(cell_id)

    # Process result
    if result.status == 'error':
        # Handle error
    else:
        # Update cell
```

**Problems**:
- Complex Event coordination
- Handler blocks (even if on Event, not queue)
- Timeout handling needed
- More code, more state

---

### New Pattern (Fully Async)

```python
async def handle_cell_update(self, cell_id, code):
    # Optimistic update
    cell.code = code
    NotebookFileStorage.serialize_notebook(self.notebook)

    # Send to kernel
    kernel.input_queue.put(RegisterCellRequest(...))

    # Return immediately
    # Background task handles responses
```

**Benefits**:
- Simple, no coordination
- Handler returns immediately
- No timeout needed
- Less code, less state

---

## Testing Strategy

### Unit Tests

**Test Handler Returns Immediately**:
```python
@pytest.mark.asyncio
async def test_handle_cell_update_returns_immediately():
    coordinator = NotebookCoordinator(MockBroadcaster())
    await coordinator.load_notebook('test-notebook')

    start = time.time()
    await coordinator.handle_cell_update('cell-1', 'x = 10')
    duration = time.time() - start

    # Should return in < 10ms (just puts on queue)
    assert duration < 0.01
```

**Test Background Task Broadcasts**:
```python
@pytest.mark.asyncio
async def test_background_task_broadcasts_notifications():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    # Put notification on output queue
    notification = CellNotification(
        cell_id='test-cell',
        output=CellOutput(
            channel="status",
            mimetype="application/json",
            data={"status": "running"}
        )
    )
    coordinator.kernel.output_queue.put(notification.model_dump())

    # Wait for background task to process
    await asyncio.sleep(0.2)

    # Verify broadcast
    assert any(m['type'] == 'cell_status' for m in broadcaster.messages)
```

---

### Integration Tests

**Test Full Flow**:
```python
@pytest.mark.asyncio
async def test_cell_update_with_cycle_error():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook('test-notebook')

    # Create cells that form cycle
    await coordinator.handle_cell_update('cell-1', 'y = x')
    await coordinator.handle_cell_update('cell-2', 'x = y')  # Creates cycle

    # Wait for kernel to process
    await asyncio.sleep(1)

    # Verify cycle error broadcast
    errors = [m for m in broadcaster.messages if m['type'] == 'cell_error']
    assert len(errors) > 0
    assert 'cycle' in errors[0]['error'].lower()
```

---

## Migration Path

### Phase 1: Unify Message Types
- Create `CellNotification` and `CellOutput` types
- Update kernel to use unified message format
- Keep old handler pattern (synchronous) but use new message types
- Test that old behavior still works

### Phase 2: Simplify Handlers
- Remove Event coordination from handlers
- Make all handlers non-blocking (send and return)
- Test that cycle detection still works
- Test that execution still works

### Phase 3: Cleanup
- Remove old result types (RegisterCellResult, etc.)
- Remove Event coordination code
- Remove cascade metadata (is_last, cascade_index)
- Update tests

---

## Key Insights

### 1. Sequential Processing is Your Friend

**You don't need complex synchronization** because kernel processes commands sequentially. FIFO queue + single-threaded kernel = guaranteed ordering.

### 2. Optimistic Updates Feel Better

**Update UI immediately**, then correct if kernel reports error. This matches how modern editors work (VSCode, Jupyter).

### 3. Unified Message Format is Simpler

**One message type** (`CellNotification`) with channel discriminator is simpler than many result types. Easier to extend (just add new channel), easier to route.

### 4. Status Changes are First-Class

**Status is a channel**, not metadata. Kernel emits status changes explicitly:
- `"validating"` - Checking code
- `"idle"` - Ready to run
- `"running"` - Executing
- `"success"` - Completed successfully
- `"error"` - Runtime error
- `"blocked"` - Cannot run (cycle detected)

Frontend shows status immediately (spinner, checkmark, error icon).

---

## References

- Current coordinator: `backend/app/orchestration/coordinator.py`
- Current kernel: `backend/app/kernel/process.py`
- Message types: `backend/app/kernel/types.py`
- Previous research: `thoughts/shared/research/2026-01-07-async-output-queue-processing-pattern.md`
- Output queue analysis: `thoughts/shared/research/2026-01-07-output-queue-architecture-analysis.md`

---

## Conclusion

**The pattern is radically simple**:

1. ✅ **ALL handlers send and return** (no waiting)
2. ✅ **Kernel emits unified notifications** (status, output, error, metadata)
3. ✅ **Background task streams everything** (one loop, one pattern)
4. ✅ **Frontend reacts optimistically** (instant UI, corrections as needed)

**Kernel's sequential processing provides synchronization** - you don't need Event coordination, correlation IDs, or complex state machines.

**Next Step**: Write implementation plan using this simplified pattern.

---

## Appendix: Reactive Execution Concerns

**Date Added**: 2026-01-07
**Concern Raised By**: Matthew Carter

### The Problem: Auto-Run Race Condition

Given that cells should auto-run reactively (per `the_task.md` and `fresh-start-architecture.md`), there's a potential race condition:

**Scenario**:
1. User types in cell A: `x = 10`
2. Frontend sends `cell_update` (RegisterCellRequest queued)
3. **Auto-run triggers immediately** - Frontend sends `run_cell` (ExecuteRequest queued)
4. Kernel processes RegisterCellRequest → updates graph
5. Kernel processes ExecuteRequest → executes with updated graph ✅

**This works!** FIFO queue guarantees registration happens before execution.

**But what if auto-run is VERY fast?**

Some reactive notebook systems trigger execution on every keystroke with debouncing:
```
User types "x" → debounce timer starts
User types " " → timer resets
User types "=" → timer resets
User types " " → timer resets
User types "1" → timer resets
User types "0" → timer resets
300ms pass → auto-run triggers
```

**Question**: Does frontend send `cell_update` BEFORE auto-run triggers, or could they race?

### Analysis

**Option 1: Frontend Sends Update on Every Keystroke**
```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // Update UI
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // Send to backend immediately
  ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));

  // Auto-run triggers separately (debounced)
  debouncedAutoRun(cellId);  // Waits 300ms
};
```

**Result**: `cell_update` sent immediately on every keystroke, auto-run waits 300ms. By the time auto-run triggers, multiple `cell_update` messages already in kernel's queue. **No race condition.**

**Option 2: Frontend Only Sends Update When Auto-Run Triggers**
```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // Update UI
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // DON'T send to backend yet

  // Auto-run triggers after debounce
  setTimeout(() => {
    // Send update AND run at same time
    ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));
    ws.send(JSON.stringify({ type: 'run_cell', cellId }));
  }, 300);
};
```

**Result**: Both messages sent at "same time" but WebSocket is TCP stream, so messages arrive in order they're sent. `cell_update` arrives first, then `run_cell`. Kernel processes in order. **No race condition.**

**Option 3: Frontend Sends Update AFTER Auto-Run (BROKEN)**
```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // Update UI
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // Auto-run triggers
  setTimeout(() => {
    ws.send(JSON.stringify({ type: 'run_cell', cellId }));  // ❌ WRONG ORDER
    ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));
  }, 300);
};
```

**Result**: Execution happens BEFORE registration. Kernel executes with STALE code. **This is a bug!**

### Recommendation

**Ensure frontend always sends `cell_update` BEFORE `run_cell`:**

```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // 1. Update UI optimistically
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // 2. Send update immediately
  ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));

  // 3. Debounce auto-run
  clearTimeout(autoRunTimers[cellId]);
  autoRunTimers[cellId] = setTimeout(() => {
    ws.send(JSON.stringify({ type: 'run_cell', cellId }));
  }, 300);
};
```

**Guarantees**:
- ✅ Update sent on every keystroke (kernel graph stays fresh)
- ✅ Auto-run waits 300ms (debouncing)
- ✅ By the time auto-run triggers, update is already in kernel's queue
- ✅ Kernel processes update before execution (FIFO)

**Alternative (if update-per-keystroke is too chatty)**:

```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // Update UI
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // Debounce BOTH update and auto-run
  clearTimeout(timers[cellId]);
  timers[cellId] = setTimeout(() => {
    // Send update FIRST, then run
    ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));

    // Small delay to ensure update arrives first (network can reorder)
    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'run_cell', cellId }));
    }, 10);  // 10ms gap ensures TCP ordering
  }, 300);
};
```

**Trade-off**: Less network traffic (only send update when user stops typing), but kernel graph may be stale during typing (doesn't matter since user isn't running yet).

### Kernel-Side Safety

Even if frontend sends messages in wrong order, kernel could detect and handle:

```python
# In kernel process
def handle_execute_request(request: ExecuteRequest):
    cell_id = request.cell_id

    # Check if code matches registered code
    if cell_id not in cell_registry:
        # Cell not registered yet - error
        return error("Cell not registered")

    registered_code, _ = cell_registry[cell_id]

    if registered_code != request.code:
        # Code mismatch - registration didn't happen yet or out of sync
        # Option A: Auto-register (implicit update)
        handle_register_request(RegisterCellRequest(
            cell_id=cell_id,
            code=request.code,
            cell_type=request.cell_type
        ))
        # Then execute

    # Execute with correct code
    execute(cell_id)
```

**This makes kernel more robust** but frontend should still send in correct order.

### Conclusion

**The async pattern works for reactive execution** as long as:
1. ✅ Frontend sends `cell_update` BEFORE `run_cell` (always)
2. ✅ WebSocket/TCP preserves message ordering (it does)
3. ✅ Kernel processes messages sequentially (FIFO)

**Recommendation**: Document frontend message ordering requirements in implementation plan.

USER PREFERENCE: 
- update-per-keystroke is too chatty
- always send update_code before run_cell 
- always send update_code then run_cell after on cell blur

debounce both similar to his 

### Recommendation

**Ensure frontend always sends `cell_update` BEFORE `run_cell`:**

```typescript
const handleCodeChange = (cellId: string, newCode: string) => {
  // 1. Update UI optimistically
  setCells(prev => prev.map(c =>
    c.id === cellId ? { ...c, code: newCode } : c
  ));

  // 2. Send update immediately
  ws.send(JSON.stringify({ type: 'cell_update', cellId, code: newCode }));

  // 3. Debounce auto-run
  clearTimeout(autoRunTimers[cellId]);
  autoRunTimers[cellId] = setTimeout(() => {
    ws.send(JSON.stringify({ type: 'run_cell', cellId }));
  }, 300);
};
```
