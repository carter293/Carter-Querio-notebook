---
date: 2026-01-07
researcher: Matthew Carter + Claude
topic: "Async Output Queue Processing Pattern for Reactive Notebooks"
tags: [research, architecture, async, queue, websocket, ipc, background-task]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Async Output Queue Processing Pattern for Reactive Notebooks

**Date**: 2026-01-07
**Researchers**: Matthew Carter + Claude

## Executive Summary

This document describes the **background task pattern** for processing kernel output queues in an async web application context. This pattern decouples request handlers from blocking IPC operations, enabling true streaming of execution results with lower latency and better resource utilization.

**Key Pattern**: A dedicated asyncio task continuously reads from the kernel's output queue and broadcasts messages to connected clients, while request handlers send commands and return immediately without waiting.

---

## The Pattern

### Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    WebSocket Handler                             │
│  - Receives client messages                                      │
│  - Routes to coordinator                                         │
│  - Returns immediately                                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ async function call
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Coordinator (Orchestration)                   │
│                                                                  │
│  Command Handlers (non-blocking):                               │
│    handle_run_cell(cell_id):                                    │
│      kernel.input_queue.put(ExecuteRequest)                     │
│      return  # ← Returns immediately!                           │
│                                                                  │
│  Background Task (runs continuously):                            │
│    _process_output_queue():                                     │
│      while True:                                                 │
│        msg = output_queue.get(timeout=1)                        │
│        route_and_broadcast(msg)                                 │
│                                                                  │
│  Synchronous Operations (use Event coordination):               │
│    handle_cell_update(cell_id, code):                           │
│      event = asyncio.Event()                                    │
│      pending_ops[cell_id] = event                               │
│      kernel.input_queue.put(RegisterCellRequest)                │
│      await event.wait()  # ← Waits on Event, not queue         │
│      result = results.pop(cell_id)                              │
│      process(result)                                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ IPC via multiprocessing.Queue
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kernel Process                                │
│  - Reads from input_queue (blocking)                            │
│  - Processes commands                                            │
│  - Writes results to output_queue                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Message Flow

### Asynchronous Execution (Non-Blocking)

```
Client                 Coordinator               Kernel Process
  |                         |                          |
  |--run_cell-------------->|                          |
  |                         |                          |
  |                         |--ExecuteRequest--------->|
  |                         |   (input_queue)          |
  |<--ACK (immediate)-------|                          |
  |                         |                          |
  |                         |    Background Task:      | Execute cells
  |                         |    while True:           | in cascade
  |                         |      msg = queue.get()   |
  |                         |                          |
  |                         |<--ExecutionResult--------|
  |                         |   (output_queue)         |
  |                         |                          |
  |                         | broadcast(result)        |
  |<--cell_status-----------|                          |
  |<--cell_output-----------|                          |
  |                         |                          |
  |                         |<--ExecutionResult--------|
  |                         |   (next cell)            |
  |                         |                          |
  |<--cell_status-----------|                          |
  |<--cell_output-----------|                          |
```

**Key Characteristics**:
- Handler returns immediately after sending command
- Background task streams results as they arrive
- Client sees updates in real-time (low latency)
- No blocking waits in request handlers

---

### Synchronous Operations (Event Coordination)

For operations that MUST wait for kernel response (e.g., cycle detection during cell registration):

```
Client                 Coordinator               Kernel Process
  |                         |                          |
  |--cell_update----------->|                          |
  |                         |                          |
  |                         | event = Event()          |
  |                         | pending_ops[id] = event  |
  |                         |                          |
  |                         |--RegisterCellRequest---->|
  |                         |   (input_queue)          |
  |                         |                          |
  |                         | await event.wait()       | Process
  |                         | (handler blocks here)    | registration
  |                         |                          |
  |                         |    Background Task:      |
  |                         |<--RegisterCellResult-----|
  |                         |   (output_queue)         |
  |                         |                          |
  |                         | results[id] = result     |
  |                         | event.set()              |
  |                         |                          |
  |                         | (handler wakes up)       |
  |                         | result = results.pop(id) |
  |                         | process(result)          |
  |                         |                          |
  |<--cell_updated----------|                          |
```

**Key Characteristics**:
- Handler creates Event before sending command
- Background task signals Event when result arrives
- Handler blocks on Event (async wait, no thread consumed)
- Timeout handled with `asyncio.wait_for(event.wait(), timeout=10)`

---

## Implementation Details

### Background Task Structure

```python
class NotebookCoordinator:
    def __init__(self, broadcaster):
        self.kernel = KernelManager()
        self.kernel.start()
        self.broadcaster = broadcaster
        self.notebook_id: Optional[str] = None
        self.notebook: Optional[NotebookResponse] = None

        # Coordination primitives for synchronous operations
        self._pending_operations: Dict[str, asyncio.Event] = {}
        self._operation_results: Dict[str, Any] = {}

        # Start background task
        self._output_task = asyncio.create_task(self._process_output_queue())
        self._running = True

    async def _process_output_queue(self):
        """
        Background task that continuously processes kernel outputs.

        This is the ONLY place that reads from output_queue.
        Runs for the lifetime of the coordinator.
        """
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read from output queue with timeout (non-blocking for asyncio)
                msg = await loop.run_in_executor(
                    None,
                    lambda: self.kernel.output_queue.get(timeout=1)
                )

                # Route message by type
                await self._handle_kernel_message(msg)

            except queue.Empty:
                # Timeout expired - check if kernel is alive
                if not self.kernel.process.is_alive():
                    print("[Coordinator] Kernel process died!")
                    await self._handle_kernel_death()
                    break
                continue

            except Exception as e:
                print(f"[Coordinator] Error processing output: {e}")
                continue

    async def _handle_kernel_message(self, msg: dict):
        """
        Route kernel message by type and process accordingly.

        For synchronous operations (registration, config), signals waiting Events.
        For asynchronous operations (execution), broadcasts immediately.
        """
        msg_type = msg.get('type')

        if msg_type == 'execution_result':
            # Execution results are always async - broadcast immediately
            result = ExecutionResult(**msg)
            await self._broadcast_execution_result(result)

        elif msg_type == 'register_result':
            # Registration is synchronous - signal waiting handler
            result = RegisterCellResult(**msg)
            await self._complete_pending_operation(result.cell_id, result)

        elif msg_type == 'config_result':
            # Config is synchronous - signal waiting handler
            result = SetDatabaseConfigResult(**msg)
            await self._complete_pending_operation('db_config', result)

        elif msg_type == 'execution_complete':
            # Optional: Handle cascade completion
            print(f"[Coordinator] Execution complete: {msg.get('initial_cell_id')}")

        else:
            print(f"[Coordinator] Unknown message type: {msg_type}")

    async def _complete_pending_operation(self, operation_id: str, result: Any):
        """
        Complete a pending synchronous operation by storing result and signaling Event.

        Args:
            operation_id: ID used to track this operation (e.g., cell_id)
            result: The result to store
        """
        if operation_id in self._pending_operations:
            # Store result
            self._operation_results[operation_id] = result

            # Signal waiting coroutine
            self._pending_operations[operation_id].set()
        else:
            # No one waiting - log warning
            print(f"[Coordinator] Received unexpected result for operation: {operation_id}")

    def shutdown(self):
        """Stop background task and kernel."""
        self._running = False

        if self._output_task:
            self._output_task.cancel()

        if self.kernel:
            self.kernel.stop()
```

---

### Asynchronous Handler Pattern (Execution)

```python
async def handle_run_cell(self, cell_id: str):
    """
    Execute a cell - sends command and returns immediately.
    Results come through background task and are broadcast to clients.
    """
    if not self.notebook:
        return

    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Create execution request
    request = ExecuteRequest(
        cell_id=cell_id,
        code=cell.code,
        cell_type=cell.type
    )

    # Send to kernel
    self.kernel.input_queue.put(request.model_dump())

    # Return immediately - results come through background task
    # Handler does NOT wait for execution to complete
```

**Benefits**:
- Handler returns immediately (low latency)
- No thread pool consumption
- Can handle many concurrent execution requests
- Results stream to frontend as they arrive

---

### Synchronous Handler Pattern (Registration)

```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """
    Update cell code - must wait for registration result to detect cycles.
    Uses Event coordination with background task.
    """
    if not self.notebook:
        return

    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    try:
        # Create event for this operation
        event = asyncio.Event()
        self._pending_operations[cell_id] = event

        # Send registration request to kernel
        request = RegisterCellRequest(
            cell_id=cell_id,
            code=new_code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(request.model_dump())

        # Wait for background task to process result (with timeout)
        await asyncio.wait_for(event.wait(), timeout=10)

        # Get result (background task stored it)
        result = self._operation_results.pop(cell_id)
        del self._pending_operations[cell_id]

        if result.status == 'error':
            # Cycle detected - mark cell as blocked
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

        # Success - update cell
        cell.code = new_code
        cell.reads = result.reads
        cell.writes = result.writes

        # Persist to file storage AFTER kernel confirms
        NotebookFileStorage.serialize_notebook(self.notebook)

        # Broadcast update
        await self.broadcaster.broadcast({
            'type': 'cell_updated',
            'cellId': cell_id,
            'cell': {
                'code': cell.code,
                'reads': cell.reads,
                'writes': cell.writes
            }
        })

    except asyncio.TimeoutError:
        # Cleanup
        if cell_id in self._pending_operations:
            del self._pending_operations[cell_id]

        # Broadcast timeout error
        await self.broadcaster.broadcast({
            'type': 'cell_error',
            'cellId': cell_id,
            'error': 'Registration timed out - kernel may be unresponsive'
        })

        raise TimeoutError(f"Cell registration timed out for {cell_id}")
```

**Benefits**:
- Correctness guaranteed (waits for cycle detection)
- No thread pool consumption (waits on Event, not queue)
- Explicit timeout handling
- Clean error propagation

---

## Message Type Structure

### Add Type Discriminators to All Messages

**Current Problem**: `ExecutionResult` lacks `type` field, making discrimination implicit.

**Solution**: Add `type` field to all result types.

```python
# kernel/types.py

class ExecutionResult(BaseModel):
    type: Literal["execution_result"] = "execution_result"  # NEW
    cell_id: str
    status: CellStatus
    stdout: str = ""
    outputs: list[Output] = Field(default_factory=list)
    error: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None  # Optional: Keep for future UI


class RegisterCellResult(BaseModel):
    type: Literal["register_result"] = "register_result"
    cell_id: str
    status: Literal["success", "error"]
    error: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)


class SetDatabaseConfigResult(BaseModel):
    type: Literal["config_result"] = "config_result"
    status: Literal["success", "error"]
    error: str | None = None


class ExecutionCompleteResult(BaseModel):
    """
    Optional: Sent after all cascade cells complete execution.
    Allows coordinator to know cascade is done without relying on is_last sentinel.
    """
    type: Literal["execution_complete"] = "execution_complete"
    initial_cell_id: str
    total_cells_executed: int
```

**Message Routing**:
```python
async def _handle_kernel_message(self, msg: dict):
    msg_type = msg.get('type')

    if msg_type == 'execution_result':
        # ...
    elif msg_type == 'register_result':
        # ...
    elif msg_type == 'config_result':
        # ...
    elif msg_type == 'execution_complete':
        # ...
    else:
        print(f"Unknown message type: {msg_type}")
```

---

## Cascade Metadata: Keep or Remove?

### Current State

Kernel adds cascade metadata to `ExecutionResult`:
```python
metadata={
    'cascade_index': 0,       # Position in cascade (0, 1, 2, ...)
    'cascade_total': 3,       # Total cells in cascade
    'is_last': False          # Sentinel flag
}
```

Coordinator uses `is_last` to know when to stop reading from queue.

### Analysis

**Frontend Usage**: Zero. Frontend doesn't use cascade metadata - it just reacts to individual cell updates.

**Coordinator Usage**: Only uses `is_last` as sentinel to stop reading queue in blocking wait pattern.

**With Background Task**: Don't need `is_last` sentinel because background task runs continuously. It doesn't need to know when a cascade "ends".

### Recommendation

**Option A: Remove Entirely**
- Remove all cascade metadata fields
- Add `ExecutionCompleteResult` message sent after cascade finishes
- Background task logs completion but doesn't use it for control flow

**Option B: Keep for Future UI Enhancement**
- Keep metadata fields in ExecutionResult
- Don't use `is_last` for control flow
- Frontend could display "Executing cell 2 of 4" in future

**Choose Option B**: Metadata is cheap to include and might be useful for UX improvements. Just don't rely on it for control flow.

---

## Performance Implications

### Thread Pool Usage

**Current Pattern** (blocking waits in handlers):
```
10 concurrent executions = 10 threads blocked
Each cascade with 5 cells = 5 queue reads = 5 threads blocked
Total: 10 × 5 = 50 threads consumed
```

**Background Task Pattern**:
```
10 concurrent executions = 0 extra threads (handlers return immediately)
1 coordinator = 1 background task = 1 thread
Total: 1 thread per coordinator
```

**Savings**: Massive reduction. Default asyncio thread pool has ~32 threads - can exhaust quickly with blocking pattern.

---

### Latency

**Current Pattern** (batch and broadcast):
```
5-cell cascade, 1 second per cell:
- Client sees nothing for 5 seconds
- All results arrive at once
- Perceived latency: HIGH
```

**Background Task Pattern** (stream as available):
```
5-cell cascade, 1 second per cell:
- Client sees first result at 1 second
- Results arrive every 1 second
- Perceived latency: LOW
```

**User Experience**: Feels much more responsive. Similar to Jupyter's behavior where cell outputs appear incrementally.

---

### Memory

**Current Pattern**:
```python
results = []
while True:
    result = queue.get()
    results.append(result)  # Accumulate in memory
    if result.metadata.get('is_last'):
        break
return results  # All results held in memory
```

**Background Task Pattern**:
```python
while True:
    result = queue.get()
    await broadcast(result)  # Broadcast immediately, don't accumulate
```

**Savings**: Constant memory usage vs O(cascade_size).

---

## Error Handling

### Kernel Death Detection

Background task continuously checks kernel health:

```python
async def _process_output_queue(self):
    while self._running:
        try:
            msg = await loop.run_in_executor(
                None,
                lambda: self.kernel.output_queue.get(timeout=1)
            )
            await self._handle_kernel_message(msg)

        except queue.Empty:
            # Check if kernel died
            if not self.kernel.process.is_alive():
                print("[Coordinator] Kernel died!")
                await self._handle_kernel_death()
                break
            continue
```

**Kernel Death Handler**:
```python
async def _handle_kernel_death(self):
    """Handle kernel process death."""
    # Signal all pending operations with error
    for operation_id, event in self._pending_operations.items():
        self._operation_results[operation_id] = {
            'status': 'error',
            'error': 'Kernel process died'
        }
        event.set()

    # Clear pending operations
    self._pending_operations.clear()

    # Broadcast error to all clients
    await self.broadcaster.broadcast({
        'type': 'kernel_error',
        'error': 'Kernel process has died. Please reconnect.'
    })

    # Stop background task
    self._running = False
```

---

### Timeout Handling

Synchronous operations have explicit timeouts:

```python
try:
    await asyncio.wait_for(event.wait(), timeout=10)
except asyncio.TimeoutError:
    # Clean up pending operation
    if operation_id in self._pending_operations:
        del self._pending_operations[operation_id]

    # Broadcast timeout error
    await self.broadcaster.broadcast({
        'type': 'cell_error',
        'cellId': cell_id,
        'error': 'Operation timed out'
    })

    raise TimeoutError(f"Operation timed out: {operation_id}")
```

**Benefits**:
- User sees timeout error immediately
- Doesn't hang forever if kernel is stuck
- Clean resource cleanup

---

## Lifecycle Management

### Startup

```python
def __init__(self, broadcaster):
    self.kernel = KernelManager()
    self.kernel.start()  # Start kernel process

    # ... initialize state ...

    # Start background task
    self._output_task = asyncio.create_task(self._process_output_queue())
    self._running = True
```

**Order**:
1. Start kernel process (creates queues)
2. Initialize coordinator state
3. Start background task (begins reading output queue)

---

### Shutdown

```python
def shutdown(self):
    """Clean shutdown of coordinator and kernel."""
    # 1. Stop background task
    self._running = False
    if self._output_task:
        self._output_task.cancel()

    # 2. Signal any pending operations (so they don't hang)
    for operation_id, event in self._pending_operations.items():
        self._operation_results[operation_id] = {
            'status': 'error',
            'error': 'Coordinator shutting down'
        }
        event.set()

    # 3. Stop kernel process
    if self.kernel:
        self.kernel.stop()
```

**Order**:
1. Stop background task (no more queue reads)
2. Signal pending operations (prevent hangs)
3. Stop kernel process (kills Python subprocess)

---

### Cancellation

Background task uses `asyncio.CancelledError` for graceful cancellation:

```python
async def _process_output_queue(self):
    try:
        while self._running:
            # ... process messages ...
    except asyncio.CancelledError:
        print("[Coordinator] Background task cancelled")
        raise  # Re-raise to complete cancellation
```

---

## Testing Strategy

### Unit Tests

**Test Background Task Processes Messages**:
```python
@pytest.mark.asyncio
async def test_background_task_processes_execution_results():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    # Manually put result on output queue
    result = ExecutionResult(
        type='execution_result',
        cell_id='test-cell',
        status='success',
        stdout='Hello World'
    )
    coordinator.kernel.output_queue.put(result.model_dump())

    # Wait for background task to process
    await asyncio.sleep(0.2)

    # Verify broadcast was called
    assert any(m['type'] == 'cell_stdout' for m in broadcaster.messages)
```

**Test Event Coordination**:
```python
@pytest.mark.asyncio
async def test_handle_cell_update_waits_for_registration():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook('test-notebook')

    # Update cell - should wait for registration
    update_task = asyncio.create_task(
        coordinator.handle_cell_update('cell-1', 'x = 10')
    )

    # Simulate kernel response (in background task)
    await asyncio.sleep(0.1)
    result = RegisterCellResult(
        type='register_result',
        cell_id='cell-1',
        status='success',
        reads=[],
        writes=['x']
    )
    coordinator.kernel.output_queue.put(result.model_dump())

    # Wait for update to complete
    await update_task

    # Verify cell was updated
    cell = next(c for c in coordinator.notebook.cells if c.id == 'cell-1')
    assert cell.code == 'x = 10'
    assert cell.writes == ['x']
```

**Test Timeout**:
```python
@pytest.mark.asyncio
async def test_registration_timeout():
    coordinator = NotebookCoordinator(MockBroadcaster())

    # Kill kernel so it doesn't respond
    coordinator.kernel.stop()

    # Registration should timeout
    with pytest.raises(TimeoutError):
        await coordinator.handle_cell_update('cell-1', 'x = 10')
```

**Test Kernel Death Detection**:
```python
@pytest.mark.asyncio
async def test_background_task_detects_kernel_death():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    # Kill kernel
    coordinator.kernel.stop()

    # Wait for background task to detect death
    await asyncio.sleep(2)

    # Verify error broadcast
    assert any(m['type'] == 'kernel_error' for m in broadcaster.messages)
    assert not coordinator._running
```

---

### Integration Tests

**Test Full Execution Flow**:
```python
@pytest.mark.asyncio
async def test_cell_execution_streams_results():
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook('test-notebook')

    # Create cells with dependencies
    await coordinator.handle_cell_update('cell-1', 'x = 10')
    await coordinator.handle_cell_update('cell-2', 'y = x + 5')

    broadcaster.messages.clear()

    # Run cell 1 (triggers cascade to cell 2)
    await coordinator.handle_run_cell('cell-1')

    # Wait for cascade to complete
    await asyncio.sleep(2)

    # Verify results for both cells
    cell_1_msgs = [m for m in broadcaster.messages if m.get('cellId') == 'cell-1']
    cell_2_msgs = [m for m in broadcaster.messages if m.get('cellId') == 'cell-2']

    assert len(cell_1_msgs) > 0
    assert len(cell_2_msgs) > 0

    # Verify execution order (cell-1 before cell-2)
    cell_1_idx = next(i for i, m in enumerate(broadcaster.messages)
                     if m.get('cellId') == 'cell-1')
    cell_2_idx = next(i for i, m in enumerate(broadcaster.messages)
                     if m.get('cellId') == 'cell-2')
    assert cell_1_idx < cell_2_idx
```

---

## Comparison with Other Patterns

### Pattern 1: Blocking Wait in Handler (Current)

```python
async def handle_run_cell(self, cell_id: str):
    self.kernel.input_queue.put(request)

    results = []
    while True:
        result = await loop.run_in_executor(None, queue.get)
        results.append(result)
        if result.metadata.get('is_last'):
            break

    for result in results:
        await broadcast(result)
```

**Pros**: Simple, sequential, easy to reason about
**Cons**: Blocks thread pool, high latency, batches results, can't scale

---

### Pattern 2: Background Task (Recommended)

```python
# Handler
async def handle_run_cell(self, cell_id: str):
    self.kernel.input_queue.put(request)
    return  # Immediate

# Background task
async def _process_output_queue(self):
    while True:
        result = await loop.run_in_executor(None, queue.get)
        await broadcast(result)
```

**Pros**: Non-blocking, low latency, streams results, scales well
**Cons**: More complex, requires Event coordination for sync ops

---

### Pattern 3: Callback-Based

```python
async def handle_run_cell(self, cell_id: str, callback):
    self.kernel.input_queue.put(request)
    self._callbacks[cell_id] = callback

# Background task calls callback
async def _process_output_queue(self):
    while True:
        result = await loop.run_in_executor(None, queue.get)
        if result.cell_id in self._callbacks:
            await self._callbacks[result.cell_id](result)
```

**Pros**: Explicit control flow
**Cons**: Callback hell, difficult error handling, harder to test

---

## Key Insights

### 1. Separation of Concerns

**Command Channel** (input_queue):
- Handlers send commands
- Handlers return immediately
- No response correlation needed (FIFO guarantees order)

**Output Channel** (output_queue):
- Background task reads continuously
- Routes by message type
- Broadcasts to all clients

**Clean separation**: Handlers don't read from output queue. Background task doesn't write to input queue.

---

### 2. Event Coordination for Synchronous Operations

**Problem**: Some operations MUST wait for kernel response (cycle detection, config validation).

**Solution**: Use `asyncio.Event` as rendezvous point:
- Handler creates Event, sends request, waits on Event
- Background task receives response, stores result, signals Event
- Handler wakes up, processes result

**Benefits**:
- Handler doesn't block thread pool (waits on Event, not queue)
- Timeout is explicit (`asyncio.wait_for`)
- Clean error handling

---

### 3. Single Reader for Output Queue

**Rule**: Only ONE task reads from output queue (the background task).

**Why**:
- Prevents message loss (two readers would steal messages from each other)
- Guarantees message ordering
- Simplifies reasoning about message flow

**Enforcement**: Don't expose output_queue to handlers. Only background task has access.

---

### 4. Graceful Degradation

**Kernel Death**: Background task detects and broadcasts error to all clients.

**Timeout**: Synchronous operations timeout and return error to caller.

**Cancellation**: Background task handles `CancelledError` gracefully.

**Result**: System fails gracefully rather than hanging or crashing.

---

## When to Use This Pattern

### Good Fit

✅ **Multiple message types** from kernel (execution, registration, config)
✅ **Some operations must be synchronous** (cycle detection, validation)
✅ **Want streaming results** (low latency, real-time updates)
✅ **Async web framework** (FastAPI, Sanic, aiohttp)
✅ **Multiprocessing IPC** (separate kernel process)

### Not Needed

❌ **Synchronous framework** (Flask, Django without async)
❌ **All operations are async** (no need for Event coordination)
❌ **Single-threaded execution** (no concurrency)
❌ **Simple request/response** (no streaming, no cascades)

---

## Future Enhancements

### 1. Request Correlation IDs

**Current**: No correlation, relies on sequential processing.

**Enhancement**: Add `request_id` to all requests and results.

**Benefit**: Could pipeline multiple operations concurrently.

**Tradeoff**: More complex, not needed for current use case (one operation at a time per kernel).

---

### 2. Priority Queue

**Current**: FIFO queue (first-in, first-out).

**Enhancement**: Priority queue where certain operations (e.g., cancellation) jump ahead.

**Benefit**: More responsive to user interrupts.

**Tradeoff**: More complex queue management.

---

### 3. Backpressure

**Current**: Kernel writes to unbounded queue.

**Enhancement**: Bounded queue with backpressure (kernel blocks if queue full).

**Benefit**: Prevents memory exhaustion if frontend disconnects.

**Tradeoff**: Kernel can block, need deadlock prevention.

---

## References

- Current coordinator: `backend/app/orchestration/coordinator.py`
- Current kernel process: `backend/app/kernel/process.py`
- WebSocket handler: `backend/app/websocket/handler.py`
- Message types: `backend/app/kernel/types.py`
- Previous research: `thoughts/shared/research/2026-01-07-output-queue-architecture-analysis.md`

---

## Conclusion

The **background task pattern** provides:

1. ✅ **Non-blocking handlers** - Return immediately, don't consume thread pool
2. ✅ **Streaming results** - Low latency, real-time updates to frontend
3. ✅ **Event coordination** - Synchronous operations handled cleanly
4. ✅ **Graceful error handling** - Timeouts, kernel death detection
5. ✅ **Scalability** - One thread per coordinator vs N threads per request

This pattern is well-suited for reactive notebook applications where:
- Kernel executes code in separate process
- Results must stream to frontend in real-time
- Some operations require synchronous validation (cycle detection)
- System must gracefully handle kernel failures

**Next Step**: Write implementation plan using this pattern.
