---
date: 2026-01-07
researcher: Matthew Carter + Claude
topic: "Output Queue Architecture Analysis and Recommendations"
tags: [research, architecture, websocket, coordinator, kernel, ipc, async]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
git_commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Output Queue Architecture Analysis and Recommendations

**Date**: 2026-01-07
**Researchers**: Matthew Carter + Claude

## Executive Summary

This document analyzes the current kernel output queue architecture and proposes improvements based on the principle that **the coordinator should route commands without waiting, and a background processor should handle kernel outputs asynchronously**.

**Key Findings**:
1. Current architecture uses blocking waits in request handlers (anti-pattern for async code)
2. Frontend doesn't use cascade metadata (`is_last`, `cascade_index`) - unnecessary complexity
3. `ExecutionResult` lacks `type` discriminator field (inconsistent with other message types)
4. Output queue processing belongs in Coordinator (orchestration layer), not WebSocket handler (interface layer)
5. Registration operations must remain synchronous for correctness (cycle detection)

**Recommendation**: Implement background task in Coordinator that continuously processes output queue and broadcasts results, while handler methods become non-blocking.

---

## Current Architecture Problems

### Problem 1: Blocking Waits in Async Handlers

**Location**: `backend/app/orchestration/coordinator.py`

**Pattern** (lines 185-208):
```python
async def _execute_via_kernel(self, request: ExecuteRequest) -> List[ExecutionResult]:
    results = []
    loop = asyncio.get_event_loop()

    # Send request to kernel
    self.kernel.input_queue.put(request.model_dump())

    while True:
        # ❌ BLOCKING READ from output queue
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        result = ExecutionResult(**result_data)
        results.append(result)

        # Check if this is the last result in the cascade
        if result.metadata and result.metadata.get('is_last', False):
            break

    return results
```

**Why This Is Bad**:
- Consumes threads from asyncio's thread pool (default: `min(32, os.cpu_count() + 4)`)
- Handler method blocks until entire cascade completes
- No timeout (hangs forever if kernel crashes)
- Higher latency (batches results instead of streaming)
- Thread pool can be exhausted with many concurrent operations

**Impact**: With 10 concurrent cell executions, 10 threads are blocked waiting on `queue.get()`. If each cascade has 5 cells, that's 50 blocking reads.

---

### Problem 2: Unused Cascade Metadata

**Frontend Analysis**: Grep of frontend code shows **zero usage** of cascade metadata fields:
- `cascade_index` - Not used
- `cascade_total` - Not used
- `is_last` - Not used

**Frontend Code** (`frontend/src/components/NotebookApp.tsx:91-171`):
```typescript
const handleWebSocketMessage = (msg: WSMessage) => {
    switch (msg.type) {
        case "cell_status":
            setCells(prev => prev.map(c =>
                c.id === msg.cellId
                    ? { ...c, status: msg.status }
                    : c
            ));
            break;
        case "cell_output":
            setCells(prev => prev.map(c =>
                c.id === msg.cellId
                    ? { ...c, outputs: [...c.outputs, msg.output] }
                    : c
            ));
            break;
    }
}
```

Frontend simply reacts to individual cell updates. It doesn't need to know "this is update 2 of 4 in a cascade".

**Coordinator Usage**: Only uses `is_last` as sentinel flag (`coordinator.py:205`):
```python
if result.metadata and result.metadata.get('is_last', False):
    break  # Stop reading from output queue
```

**Conclusion**: Cascade metadata adds complexity without providing value. Can be replaced with simpler completion message.

---

### Problem 3: Inconsistent Message Type Discriminators

**Current Message Types** (`backend/app/kernel/types.py`):

```python
class RegisterCellResult(BaseModel):
    type: Literal["register_result"] = "register_result"  # ✅ Has type
    cell_id: str
    status: Literal["success", "error"]
    # ...

class SetDatabaseConfigResult(BaseModel):
    type: Literal["config_result"] = "config_result"  # ✅ Has type
    status: Literal["success", "error"]
    # ...

class ExecutionResult(BaseModel):
    # ❌ NO type field!
    cell_id: str
    status: CellStatus
    # ...
```

**Problem**: Type discrimination logic is implicit:
```python
if 'type' in result_data:
    # RegisterCellResult or SetDatabaseConfigResult
else:
    # Must be ExecutionResult
```

**Should Be Explicit**:
```python
msg_type = result_data['type']
if msg_type == 'execution_result':
    # ...
elif msg_type == 'register_result':
    # ...
```

---

### Problem 4: No Correlation Between Requests and Responses

**Current System**: No request IDs, relies on sequential processing.

**Why This Works Now**:
- Coordinator blocks on each request until response received
- Queue FIFO guarantees preserve order
- Only ONE operation in flight at a time per kernel

**Why This Is Fragile**:
- Cannot pipeline requests (must wait for full cascade before next operation)
- Cannot timeout individual requests (only entire blocking wait)
- Cannot cancel in-progress operations
- Difficult to add concurrent request handling

**Example Failure Scenario**:
```python
# User rapidly updates cell code
coordinator.handle_cell_update(cell_id, "x = 1")  # Sends RegisterCellRequest
coordinator.handle_cell_update(cell_id, "x = 2")  # Sends another RegisterCellRequest

# Which RegisterCellResult belongs to which request?
# Current code assumes sequential processing prevents this
```

---

## Message Flow Analysis

### Current Message Types on Output Queue

Based on analysis of `backend/app/kernel/process.py`:

**1. RegisterCellResult** (`type: "register_result"`)
- **Count**: 1 per registration
- **When**: Response to `RegisterCellRequest`
- **Contains**: Dependency info (reads/writes), error status
- **File**: `process.py:55-72`

**2. SetDatabaseConfigResult** (`type: "config_result"`)
- **Count**: 1 per config request
- **When**: Response to `SetDatabaseConfigRequest`
- **Contains**: Success/error status
- **File**: `process.py:92-101`

**3. ExecutionResult** (no `type` field)
- **Count**: N per execution (one per cell in cascade)
- **When**: Response to `ExecuteRequest`
- **Contains**: Stdout, outputs, error, reads/writes, cascade metadata
- **File**: `process.py:118-184`

### Message Flow Patterns

**Pattern 1: Synchronous Single Response** (Registration)
```
Coordinator                    Kernel
    |                              |
    |--RegisterCellRequest-------->|
    |   (input_queue)              |
    |                              | Extract dependencies
    |                              | Update graph
    |<--RegisterCellResult---------|
    |   (output_queue)             |
   Process result                  |
```

**Pattern 2: Asynchronous Multi-Response** (Execution with cascade)
```
Coordinator                    Kernel
    |                              |
    |--ExecuteRequest------------->|
    |   cell_id: "c1"              |
    |                              | Get execution order: [c1, c2, c3]
    |<--ExecutionResult------------|
    |   cell_id: "c1"              | Execute c1
    |   is_last: false             |
    |                              |
    |<--ExecutionResult------------|
    |   cell_id: "c2"              | Execute c2
    |   is_last: false             |
    |                              |
    |<--ExecutionResult------------|
    |   cell_id: "c3"              | Execute c3
    |   is_last: true              |
    |                              |
   Stop reading (is_last=true)     |
```

---

## Architectural Options

### Option A: Keep Current Architecture (Not Recommended)

**No changes** - continue blocking waits in handlers.

**Pros**:
- Already implemented
- Simple to understand
- No refactoring needed

**Cons**:
- Anti-pattern for async code
- Thread pool exhaustion risk
- Higher latency (batches results)
- No timeout handling
- Cannot scale to concurrent operations

---

### Option B: Move Output Processing to WebSocket Handler (Not Recommended)

**Structure**:
```python
# In handler.py
async def handle_message(connection_id, coordinator, message):
    if msg_type == "run_cell":
        coordinator.kernel.input_queue.put(ExecuteRequest(...))

        # WebSocket handler reads queue directly
        while True:
            result = await loop.run_in_executor(None, coordinator.kernel.output_queue.get)
            await manager.send_message(connection_id, format_result(result))
            if result.metadata.get('is_last'):
                break
```

**Pros**:
- Coordinator becomes thinner

**Cons**:
- ❌ Violates separation of concerns (interface layer knows about kernel IPC)
- ❌ REST API can't share code (would need duplicate path)
- ❌ Coordinator loses ability to update in-memory notebook state
- ❌ WebSocket handler becomes bloated with business logic
- ❌ Breaks abstraction - handler shouldn't know about queues

**Verdict**: Architecturally wrong.

---

### Option C: Background Task in Coordinator (RECOMMENDED)

**Structure**:
```python
class NotebookCoordinator:
    def __init__(self, broadcaster):
        self.kernel = KernelManager()
        self.kernel.start()
        self.broadcaster = broadcaster

        # Start background task
        self._output_task = asyncio.create_task(self._process_output_queue())

    async def _process_output_queue(self):
        """Continuously read from kernel output queue and broadcast."""
        loop = asyncio.get_event_loop()

        while True:
            try:
                msg = await loop.run_in_executor(
                    None,
                    lambda: self.kernel.output_queue.get(timeout=1)
                )
                await self._handle_kernel_message(msg)
            except queue.Empty:
                # Timeout - check if kernel alive
                if not self.kernel.process.is_alive():
                    print("[Coordinator] Kernel died!")
                    break
                continue

    async def _handle_kernel_message(self, msg: dict):
        """Route message by type and broadcast."""
        msg_type = msg.get('type')

        if msg_type == 'execution_result':
            result = ExecutionResult(**msg)
            await self._broadcast_execution_result(result)
        elif msg_type == 'register_result':
            result = RegisterCellResult(**msg)
            await self._handle_register_result(result)
        elif msg_type == 'config_result':
            result = SetDatabaseConfigResult(**msg)
            await self._handle_config_result(result)

    async def handle_run_cell(self, cell_id: str):
        """Send execution command - return immediately."""
        request = ExecuteRequest(cell_id=cell_id, code=cell.code, cell_type=cell.type)

        # Send to kernel
        self.kernel.input_queue.put(request.model_dump())

        # Return immediately - results come through background task
```

**Pros**:
- ✅ Handler methods become non-blocking
- ✅ True async streaming (results broadcast as they arrive)
- ✅ Lower latency (no batching)
- ✅ Timeout handling built-in (`queue.get(timeout=1)`)
- ✅ Clean separation (coordinator owns output processing)
- ✅ Works for both WebSocket and REST API
- ✅ Single thread blocked (background task) vs multiple threads per request
- ✅ Coordinator can update in-memory state as results arrive

**Cons**:
- Requires refactoring
- Need coordination mechanism for synchronous operations (registration)
- More complex lifecycle management (cancel task on shutdown)

**Verdict**: Best option - aligns with async patterns and scales better.

---

## Handling Synchronous Operations

### The Registration Problem

**Requirement**: Cell registration MUST be synchronous for cycle detection correctness.

**Why**: If registration is async, race condition occurs:
1. User types code creating cycle
2. Registration sent to kernel (async, returns immediately)
3. User clicks "Run" before registration completes
4. Execution request sent with stale dependency graph
5. Cell executes when it should be blocked

**Solution**: Use `asyncio.Event` for coordination between handler and background task.

### Implementation Pattern

```python
class NotebookCoordinator:
    def __init__(self, broadcaster):
        self.kernel = KernelManager()
        self.kernel.start()
        self.broadcaster = broadcaster

        # Track pending synchronous operations
        self._pending_registrations: Dict[str, asyncio.Event] = {}
        self._registration_results: Dict[str, RegisterCellResult] = {}

        self._output_task = asyncio.create_task(self._process_output_queue())

    async def handle_cell_update(self, cell_id: str, new_code: str):
        """Update cell code - must wait for registration result."""
        cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
        if not cell:
            return

        # Create event for this registration
        event = asyncio.Event()
        self._pending_registrations[cell_id] = event

        # Send to kernel
        request = RegisterCellRequest(
            cell_id=cell_id,
            code=new_code,
            cell_type=cell.type
        )
        self.kernel.input_queue.put(request.model_dump())

        # Wait for background task to process result
        try:
            await asyncio.wait_for(event.wait(), timeout=10)
        except asyncio.TimeoutError:
            del self._pending_registrations[cell_id]
            raise TimeoutError("Registration timed out")

        # Get result (background task stored it)
        result = self._registration_results.pop(cell_id)
        del self._pending_registrations[cell_id]

        if result.status == 'error':
            # Cycle detected - mark cell as blocked
            cell.status = 'blocked'
            cell.error = result.error

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

        # Persist to file storage
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

    async def _handle_register_result(self, result: RegisterCellResult):
        """Called by background task when registration result arrives."""
        cell_id = result.cell_id

        # Check if there's a pending registration waiting for this result
        if cell_id in self._pending_registrations:
            # Store result
            self._registration_results[cell_id] = result

            # Signal waiting coroutine
            self._pending_registrations[cell_id].set()
        else:
            # No one waiting - this shouldn't happen
            print(f"[Coordinator] Received unexpected registration result for {cell_id}")
```

**How It Works**:
1. Handler creates `asyncio.Event` and stores in dict
2. Handler sends request to kernel
3. Handler waits on event (async, doesn't block thread pool)
4. Background task receives result from kernel
5. Background task stores result and signals event
6. Handler wakes up, processes result

**Benefits**:
- ✅ Handler doesn't block thread pool (waits on Event, not queue)
- ✅ Background task handles all queue reads (single pattern)
- ✅ Timeout is explicit (`asyncio.wait_for`)
- ✅ Type-safe result passing

---

## Required Changes

### Change 1: Add Type Discriminator to ExecutionResult

**File**: `backend/app/kernel/types.py`

**Before**:
```python
class ExecutionResult(BaseModel):
    cell_id: str
    status: CellStatus
    # ...
```

**After**:
```python
class ExecutionResult(BaseModel):
    type: Literal["execution_result"] = "execution_result"  # NEW
    cell_id: str
    status: CellStatus
    # ...
```

**Impact**: All message types now have consistent `type` field for discrimination.

---

### Change 2: Remove Cascade Metadata (Optional)

**Current** (`kernel/process.py:178-182`):
```python
metadata={
    'cascade_index': cascade_index,
    'cascade_total': total_cells,
    'is_last': (cascade_index == total_cells - 1)
}
```

**Option A: Remove Entirely**
```python
# No metadata field
```

Kernel sends completion message after cascade:
```python
class ExecutionCompleteResult(BaseModel):
    type: Literal["execution_complete"] = "execution_complete"
    initial_cell_id: str
    total_cells_executed: int
```

**Option B: Keep for Future UI Enhancement**
```python
# Keep metadata but don't use is_last as sentinel
# Background task just broadcasts each result as it arrives
```

**Recommendation**: Option B (keep metadata but change how coordinator uses it). Frontend might want to show "Executing cell 2 of 4" in the future.

---

### Change 3: Background Task in Coordinator

**File**: `backend/app/orchestration/coordinator.py`

**Add**:
```python
class NotebookCoordinator:
    def __init__(self, broadcaster):
        # ... existing init ...

        # Coordination primitives for synchronous operations
        self._pending_registrations: Dict[str, asyncio.Event] = {}
        self._registration_results: Dict[str, RegisterCellResult] = {}

        # Start background output processor
        self._output_task = asyncio.create_task(self._process_output_queue())

    async def _process_output_queue(self):
        """Background task that continuously processes kernel outputs."""
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Read from output queue with timeout
                msg = await loop.run_in_executor(
                    None,
                    lambda: self.kernel.output_queue.get(timeout=1)
                )

                # Route by message type
                await self._handle_kernel_message(msg)

            except queue.Empty:
                # Check if kernel is alive
                if not self.kernel.process.is_alive():
                    print("[Coordinator] Kernel process died!")
                    await self._handle_kernel_death()
                    break
                continue
            except Exception as e:
                print(f"[Coordinator] Error processing output: {e}")
                continue

    async def _handle_kernel_message(self, msg: dict):
        """Route kernel message by type."""
        msg_type = msg.get('type')

        if msg_type == 'execution_result':
            result = ExecutionResult(**msg)
            await self._broadcast_execution_result(result)
        elif msg_type == 'register_result':
            result = RegisterCellResult(**msg)
            await self._handle_register_result(result)
        elif msg_type == 'config_result':
            result = SetDatabaseConfigResult(**msg)
            await self._handle_config_result(result)
        elif msg_type == 'execution_complete':
            # Optional: Handle cascade completion
            pass
        else:
            print(f"[Coordinator] Unknown message type: {msg_type}")

    def shutdown(self):
        """Stop kernel and background task."""
        if self._output_task:
            self._output_task.cancel()
        if self.kernel:
            self.kernel.stop()
```

---

### Change 4: Make Handler Methods Non-Blocking

**File**: `backend/app/orchestration/coordinator.py`

**Cell Execution** (becomes simple):
```python
async def handle_run_cell(self, cell_id: str):
    """Execute a cell - sends command and returns immediately."""
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
```

**Cell Update** (uses Event coordination):
```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Update cell code - waits for registration via Event."""
    # See full implementation in "Handling Synchronous Operations" section above
```

---

## Architecture Diagrams

### Current (Blocking Wait Pattern)

```
┌─────────────────────────────────────────┐
│  WebSocket Handler                       │
│  await coordinator.handle_run_cell()    │ ← Waits here
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Coordinator                             │
│  handle_run_cell():                      │
│    put(ExecuteRequest)                   │
│    while True:                           │
│      result = queue.get()  ← BLOCKS     │ ← Thread consumed
│      if is_last: break                   │
│    return results                        │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Kernel Process                          │
│  for cell in cascade:                    │
│    output_queue.put(result)              │
└─────────────────────────────────────────┘
```

**Problem**: Handler waits, coordinator blocks on queue, thread consumed.

---

### Proposed (Background Task Pattern)

```
┌─────────────────────────────────────────┐
│  WebSocket Handler                       │
│  coordinator.handle_run_cell()          │
│  return ← Returns immediately!          │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Coordinator                             │
│                                          │
│  handle_run_cell():                      │
│    put(ExecuteRequest)                   │
│    return  ← Non-blocking!               │
│                                          │
│  _process_output_queue() [background]:  │
│    while True:                           │
│      msg = queue.get(timeout=1)         │ ← Single thread
│      handle_kernel_message(msg)          │
│      broadcast(msg)                      │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Kernel Process                          │
│  for cell in cascade:                    │
│    output_queue.put(result)              │
└─────────────────────────────────────────┘
```

**Benefits**: Handler returns immediately, single background thread handles all outputs, results stream to frontend as they arrive.

---

## Performance Implications

### Thread Pool Usage

**Current**:
- Each `handle_run_cell` consumes 1+ threads (one per `run_in_executor`)
- With cascades: N threads blocked (reading N results)
- 10 concurrent executions × 5 cells each = 50 threads blocked

**Proposed**:
- Each coordinator has 1 background thread (for output processing)
- Handler methods don't block thread pool
- 10 concurrent executions = still only 1 thread per coordinator

**Savings**: Massive reduction in thread pool pressure.

---

### Latency

**Current**:
- Coordinator collects ALL cascade results before broadcasting
- Frontend sees nothing until cascade completes
- High perceived latency for large cascades

**Proposed**:
- Background task broadcasts each result as it arrives
- Frontend sees first cell complete immediately
- Low perceived latency

**Example**: 5-cell cascade where each takes 1 second:
- Current: 5 seconds until ANY results appear
- Proposed: 1 second until first result, then 1s intervals

---

### Memory

**Current**:
- `_execute_via_kernel` accumulates all results in list
- Memory proportional to cascade size

**Proposed**:
- Results broadcast immediately, not accumulated
- Constant memory usage

---

## Testing Strategy

### Unit Tests

**Test Background Task**:
```python
@pytest.mark.asyncio
async def test_background_task_processes_execution_results():
    """Test that background task reads and broadcasts execution results."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)

    # Manually put result on output queue
    result = ExecutionResult(
        type='execution_result',
        cell_id='test-cell',
        status='success',
        stdout='Hello'
    )
    coordinator.kernel.output_queue.put(result.model_dump())

    # Wait for background task to process
    await asyncio.sleep(2)

    # Check broadcast was called
    assert any(m['type'] == 'cell_stdout' for m in broadcaster.messages)
```

**Test Synchronous Registration**:
```python
@pytest.mark.asyncio
async def test_handle_cell_update_waits_for_registration():
    """Test that cell update waits for registration result."""
    broadcaster = MockBroadcaster()
    coordinator = NotebookCoordinator(broadcaster)
    await coordinator.load_notebook('test-notebook')

    # Update cell - should wait for registration
    await coordinator.handle_cell_update('cell-1', 'x = 10')

    # Cell should be updated
    cell = next(c for c in coordinator.notebook.cells if c.id == 'cell-1')
    assert cell.code == 'x = 10'
```

**Test Timeout**:
```python
@pytest.mark.asyncio
async def test_registration_timeout():
    """Test that registration times out if kernel doesn't respond."""
    coordinator = NotebookCoordinator(MockBroadcaster())

    # Kill kernel so it doesn't respond
    coordinator.kernel.stop()

    # Registration should timeout
    with pytest.raises(TimeoutError):
        await coordinator.handle_cell_update('cell-1', 'x = 10')
```

---

### Integration Tests

**Test Full Flow**:
```python
@pytest.mark.asyncio
async def test_cell_execution_streams_results():
    """Test that execution results are streamed to frontend."""
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

    # Should have received results for both cells
    cell_1_results = [m for m in broadcaster.messages if m.get('cellId') == 'cell-1']
    cell_2_results = [m for m in broadcaster.messages if m.get('cellId') == 'cell-2']

    assert len(cell_1_results) > 0
    assert len(cell_2_results) > 0
```

---

## Migration Path

### Phase 1: Add Type Discriminators
- Add `type` field to `ExecutionResult`
- Update kernel to set `type='execution_result'`
- Test that existing code still works

### Phase 2: Add Background Task
- Add `_process_output_queue` method to coordinator
- Start task in `__init__`
- Keep existing blocking waits in handlers (parallel path)
- Test background task processes messages correctly

### Phase 3: Refactor Registration
- Add Event coordination for registration
- Update `handle_cell_update` to use Event pattern
- Remove blocking wait from registration handler
- Test cycle detection still works

### Phase 4: Refactor Execution
- Update `handle_run_cell` to send and return immediately
- Remove `_execute_via_kernel` method
- Test cascades still work

### Phase 5: Cleanup
- Remove old blocking wait code
- Remove cascade metadata if not needed
- Update tests

---

## Open Questions

### Q1: Should We Keep Cascade Metadata?

**Arguments For**:
- Future UI enhancement ("Executing 2 of 4")
- Debugging (can see execution order)
- Already implemented

**Arguments Against**:
- Frontend doesn't use it
- Adds complexity to kernel
- Coordinator doesn't need it (background task just streams)

**Recommendation**: Keep metadata fields but remove reliance on `is_last` as sentinel. Use completion message instead.

---

### Q2: Should We Add Request Correlation IDs?

**Current**: No correlation, relies on sequential processing.

**With Background Task**: Still sequential per kernel (FIFO queue guarantees), so correlation not strictly needed.

**Future**: If we want concurrent request handling (pipeline multiple operations), would need correlation IDs.

**Recommendation**: Don't add now. Add only if we need concurrent operations in future.

---

### Q3: How to Handle Notebook Loading?

**Current**: Loading waits for each cell registration before continuing.

**Should It Stay Synchronous?**: YES
- Need to detect cycles before allowing execution
- Need to build full dependency graph before connection completes
- Frontend expects notebook to be "ready" when connection succeeds

**Implementation**: Loading can use same Event coordination pattern as cell updates.

---

## Conclusion

**Recommended Architecture**:

1. ✅ **Background task in Coordinator** processes output queue continuously
2. ✅ **Handler methods become non-blocking** (send command and return)
3. ✅ **Event coordination for synchronous ops** (registration, config)
4. ✅ **Add type discriminator to ExecutionResult**
5. ✅ **Stream results** to frontend as they arrive (lower latency)
6. ✅ **Keep cascade metadata** but don't use as sentinel (use completion message)
7. ✅ **Single thread blocked per coordinator** vs N threads per request

**Key Insight**: The coordinator IS the right place for output processing because:
- It owns notebook state (needs to update as results arrive)
- It has broadcaster reference (can send to WebSocket clients)
- It owns kernel lifecycle (background task lifecycle matches kernel)
- Clean separation: WebSocket = interface, Coordinator = orchestration

**Next Steps**: Write implementation plan based on this architecture.

---

## References

- Current coordinator: `backend/app/orchestration/coordinator.py`
- Current kernel process: `backend/app/kernel/process.py`
- WebSocket handler: `backend/app/websocket/handler.py`
- Frontend WebSocket: `frontend/src/useNotebookWebSocket.ts`
- Frontend handler: `frontend/src/components/NotebookApp.tsx`
- Message types: `backend/app/kernel/types.py`
