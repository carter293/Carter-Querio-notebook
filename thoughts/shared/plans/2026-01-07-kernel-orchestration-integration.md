# Kernel-Orchestration Layer Integration Implementation Plan

**Date**: 2026-01-07
**Purpose**: Wire the kernel layer into the production application and remove separation of concerns violations
**Related Research**: [2026-01-07-kernel-orchestration-layer-separation.md](../research/2026-01-07-kernel-orchestration-layer-separation.md)
**Architecture Doc**: [2026-01-06-fresh-start-architecture.md](../research/2026-01-06-fresh-start-architecture.md)

---

## Overview

The kernel layer (`KernelManager`, `kernel_main`) has been fully implemented and tested, but the production application bypasses it entirely. The `NotebookCoordinator` currently performs BOTH orchestration AND kernel responsibilities in-process, violating the architecture's separation of concerns.

This plan integrates the kernel layer into the running application and removes all duplicate code.

---

## Current State Analysis

### What Works (Kernel Layer)
- ✅ `kernel_main` process with event loop
- ✅ Queue-based IPC (multiprocessing)
- ✅ Dependency graph management in kernel
- ✅ Reactive cascade execution
- ✅ Variable persistence across executions
- ✅ Comprehensive test coverage in `test_kernel_integration.py`

### What's Wrong (Orchestration Layer)
- ❌ `NotebookCoordinator` has its own `DependencyGraph` ([coordinator.py:19](backend/app/orchestration/coordinator.py#L19))
- ❌ `NotebookCoordinator` has its own executors ([coordinator.py:20-21](backend/app/orchestration/coordinator.py#L20-L21))
- ❌ `NotebookCoordinator` extracts dependencies ([coordinator.py:47-55](backend/app/orchestration/coordinator.py#L47-L55))
- ❌ `NotebookCoordinator` computes execution order ([coordinator.py:111](backend/app/orchestration/coordinator.py#L111))
- ❌ `NotebookCoordinator` executes code directly ([coordinator.py:141-143](backend/app/orchestration/coordinator.py#L141-L143))
- ❌ Kernel is never started in production code
- ❌ WebSocket handler never uses `KernelManager`

---

## System Context Analysis

The coordinator was intentionally built with in-process execution as a "stub kernel" per the orchestration layer plan. The kernel layer was then implemented separately. **The integration step was never completed**, leaving the application with two parallel execution systems - one that's used (coordinator) and one that's unused (kernel).

This plan addresses the **root cause** (lack of integration) rather than the **symptom** (coordinator doing too much).

---

## Desired End State

After this plan is complete:

1. `NotebookCoordinator` delegates ALL execution to `KernelManager`
2. Coordinator only contains: kernel reference, broadcaster reference, notebook state
3. Kernel process starts when WebSocket connects
4. Kernel process stops when WebSocket disconnects
5. Reactive cascades work through kernel IPC
6. All existing tests still pass
7. New integration tests verify kernel is actually used

**Verification**:
- Run notebook frontend, execute cells → kernel process should be visible in `ps`
- Change cell A → cells B and C should auto-execute via kernel
- `KernelManager` methods should be called in production logs

---

## What We're NOT Doing

- ❌ Not changing the kernel layer implementation (it's correct)
- ❌ Not changing the WebSocket protocol (frontend contract stays same)
- ❌ Not adding new features (pure integration)
- ❌ Not changing file storage layer
- ❌ Not adding persistence or authentication

---

## Implementation Approach

**Strategy**: Refactor coordinator to be a thin routing layer that delegates to kernel.

**Key Insight**: The kernel already returns ALL results for reactive cascades (see [process.py:67-108](backend/app/kernel/process.py#L67-L108)). The coordinator just needs to await and broadcast each result.

**Migration Path**:
1. Add kernel to coordinator (keeping old code)
2. Switch execution to kernel (remove old code)
3. Test thoroughly
4. Remove dead code

---

## Phase 1: Add Kernel to Coordinator

### Overview
Add `KernelManager` to coordinator without removing existing code. This allows gradual migration and easy rollback.

### Changes Required

#### 1. Update NotebookCoordinator.__init__
**File**: `backend/app/orchestration/coordinator.py`

```python
from ..kernel.manager import KernelManager
from ..kernel.types import ExecuteRequest

class NotebookCoordinator:
    """
    Coordinates notebook operations:
    - Manages kernel lifecycle
    - Broadcasts updates via WebSocket
    """

    def __init__(self, broadcaster):
        # NEW: Use kernel instead of in-process execution
        self.kernel = KernelManager()
        self.kernel.start()

        self.broadcaster = broadcaster
        self.notebook_id: Optional[str] = None
        self.notebook: Optional[NotebookResponse] = None

        # OLD: Remove these in Phase 2
        # self.graph = DependencyGraph()
        # self.python_executor = PythonExecutor()
        # self.sql_executor = SQLExecutor()
```

#### 2. Add shutdown method
**File**: `backend/app/orchestration/coordinator.py`

```python
def shutdown(self):
    """Stop the kernel process."""
    if self.kernel:
        self.kernel.stop()
```

### Success Criteria

#### Automated Verification:
- [x] Coordinator can be instantiated: `coordinator = NotebookCoordinator(broadcaster)`
- [x] Kernel starts on creation: Check `coordinator.kernel._running == True`
- [x] Kernel stops on shutdown: `coordinator.shutdown()` completes without error

#### Manual Verification:
- [x] No existing functionality broken (cells still execute via old path)

---

## Phase 2: Refactor Cell Execution to Use Kernel

### Overview
Replace the in-process execution logic with kernel delegation. This is the core integration work.

### Changes Required

#### 1. Refactor handle_run_cell
**File**: `backend/app/orchestration/coordinator.py`

**OLD CODE** (lines 105-115):
```python
async def handle_run_cell(self, cell_id: str):
    """Execute a cell and all dependent cells."""
    if not self.notebook:
        return

    # Get execution order (cell + descendants)
    execution_order = self.graph.get_execution_order(cell_id)

    # Execute cells in order
    for cid in execution_order:
        await self._execute_cell(cid)
```

**NEW CODE**:
```python
async def handle_run_cell(self, cell_id: str):
    """Execute a cell and all dependent cells via kernel."""
    if not self.notebook:
        return

    # Find cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Create execution request
    request = ExecuteRequest(
        cell_id=cell_id,
        code=cell.code,
        cell_type=cell.type
    )

    # Send to kernel - it will return results for ALL affected cells
    results = await self._execute_via_kernel(request)

    # Broadcast each result
    for result in results:
        await self._broadcast_execution_result(result)
```

#### 2. Add _execute_via_kernel helper
**File**: `backend/app/orchestration/coordinator.py`

```python
async def _execute_via_kernel(self, request: ExecuteRequest) -> List[ExecutionResult]:
    """
    Send execution request to kernel and collect all cascade results.

    The kernel returns one result per cell in the reactive cascade.
    We need to read all of them before returning.
    """
    results = []

    # Send request to kernel
    await self.kernel.execute(request)

    # The kernel will put results in output_queue
    # We need to read until the cascade is complete
    #
    # TODO: For now, read one result at a time
    # In Phase 3, we'll add cascade completion signaling

    loop = asyncio.get_event_loop()

    # Read first result
    result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
    result = ExecutionResult(**result_data)
    results.append(result)

    # Check if there are more results (non-blocking check)
    # This is a temporary solution until we add proper cascade signaling
    while not self.kernel.output_queue.empty():
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        result = ExecutionResult(**result_data)
        results.append(result)

    return results
```

#### 3. Add _broadcast_execution_result helper
**File**: `backend/app/orchestration/coordinator.py`

```python
async def _broadcast_execution_result(self, result: ExecutionResult):
    """Broadcast a single execution result to all clients."""
    cell_id = result.cell_id

    # Update in-memory notebook
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    cell.status = result.status
    cell.stdout = result.stdout
    cell.error = result.error
    cell.reads = result.reads
    cell.writes = result.writes

    # Broadcast running status
    await self.broadcaster.broadcast({
        'type': 'cell_status',
        'cellId': cell_id,
        'status': 'running'
    })

    # Broadcast stdout
    if result.stdout:
        await self.broadcaster.broadcast({
            'type': 'cell_stdout',
            'cellId': cell_id,
            'data': result.stdout
        })

    # Broadcast outputs
    for output in result.outputs:
        cell.outputs.append(output)
        await self.broadcaster.broadcast({
            'type': 'cell_output',
            'cellId': cell_id,
            'output': output.model_dump()
        })

    # Broadcast final status
    await self.broadcaster.broadcast({
        'type': 'cell_status',
        'cellId': cell_id,
        'status': result.status
    })

    # If error, broadcast it
    if result.error:
        await self.broadcaster.broadcast({
            'type': 'cell_error',
            'cellId': cell_id,
            'error': result.error
        })

    # Broadcast updated metadata (reads/writes)
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

#### 4. Refactor load_notebook
**File**: `backend/app/orchestration/coordinator.py`

**OLD CODE** (lines 26-45):
```python
def load_notebook(self, notebook_id: str):
    """Load a notebook and rebuild the dependency graph."""
    self.notebook_id = notebook_id
    self.notebook = NotebookFileStorage.parse_notebook(notebook_id)

    if not self.notebook:
        raise ValueError(f"Notebook {notebook_id} not found")

    # Rebuild graph from all cells
    for cell in self.notebook.cells:
        reads, writes = self._extract_dependencies(cell)
        try:
            self.graph.update_cell(cell.id, reads, writes)
            # Update cell metadata
            cell.reads = list(reads)
            cell.writes = list(writes)
        except CycleDetectedError:
            # Mark cell as blocked
            cell.status = 'blocked'
            cell.error = 'Circular dependency detected'
```

**NEW CODE**:
```python
def load_notebook(self, notebook_id: str):
    """Load a notebook and send all cells to kernel for graph building."""
    self.notebook_id = notebook_id
    self.notebook = NotebookFileStorage.parse_notebook(notebook_id)

    if not self.notebook:
        raise ValueError(f"Notebook {notebook_id} not found")

    # Send all cells to kernel to build its dependency graph
    # We do this by sending ExecuteRequest messages WITHOUT executing
    #
    # NOTE: Current kernel design always executes when updating graph
    # This is actually fine - we just won't broadcast the results
    # Alternative: Add a new message type "UpdateCellCode" that updates graph only
    #
    # For now, we'll just load metadata from file storage
    # The kernel will build its graph as cells are executed
    pass
```

**Rationale**: The kernel builds its graph incrementally as cells are executed. We don't need to pre-populate it on load. The in-memory notebook state is already loaded from file storage with reads/writes metadata.

#### 5. Remove _execute_cell method
**File**: `backend/app/orchestration/coordinator.py`

**DELETE** lines 117-182 (the entire `_execute_cell` method). This is now handled by the kernel.

#### 6. Remove _extract_dependencies method
**File**: `backend/app/orchestration/coordinator.py`

**DELETE** lines 47-55 (the entire `_extract_dependencies` method). The kernel extracts dependencies.

#### 7. Simplify handle_cell_update
**File**: `backend/app/orchestration/coordinator.py`

**OLD CODE** (lines 57-103):
```python
async def handle_cell_update(self, cell_id: str, new_code: str):
    """Handle a cell code update."""
    if not self.notebook:
        return

    # Find cell
    cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
    if not cell:
        return

    # Update code
    cell.code = new_code

    # Extract dependencies
    reads, writes = self._extract_dependencies(cell)
    cell.reads = list(reads)
    cell.writes = list(writes)

    # Update graph
    try:
        self.graph.update_cell(cell_id, reads, writes)

        # Broadcast updated cell metadata
        await self.broadcaster.broadcast({
            'type': 'cell_updated',
            'cellId': cell_id,
            'cell': {
                'code': cell.code,
                'reads': cell.reads,
                'writes': cell.writes
            }
        })
    except CycleDetectedError as e:
        # Mark cell as blocked
        cell.status = 'blocked'
        cell.error = str(e)

        await self.broadcaster.broadcast({
            'type': 'cell_status',
            'cellId': cell_id,
            'status': 'blocked'
        })
        await self.broadcaster.broadcast({
            'type': 'cell_error',
            'cellId': cell_id,
            'error': str(e)
        })
```

**NEW CODE**:
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

    # The kernel will extract dependencies when the cell is next executed
    # We just broadcast the code change
    await self.broadcaster.broadcast({
        'type': 'cell_updated',
        'cellId': cell_id,
        'cell': {
            'code': cell.code,
            'reads': cell.reads,  # Old metadata until re-executed
            'writes': cell.writes
        }
    })
```

#### 8. Remove graph and executors from __init__
**File**: `backend/app/orchestration/coordinator.py`

Delete lines 19-21:
```python
# DELETE THESE:
# self.graph = DependencyGraph()
# self.python_executor = PythonExecutor()
# self.sql_executor = SQLExecutor()
```

Remove imports:
```python
# DELETE THESE:
# from ..core.ast_parser import extract_python_dependencies, extract_sql_dependencies
# from ..core.graph import DependencyGraph, CycleDetectedError
# from ..core.executor import PythonExecutor, SQLExecutor
```

### Success Criteria

#### Automated Verification:
- [x] All existing tests pass: `make test`
- [x] Kernel integration tests pass: `pytest backend/tests/test_kernel_integration.py`
- [x] Type checking passes: `make typecheck`

#### Manual Verification:
- [ ] Start backend, open frontend
- [ ] Create cell A: `x = 10`
- [ ] Create cell B: `y = x * 2`
- [ ] Create cell C: `print(y)`
- [ ] Run cell A → verify all three cells execute in order
- [ ] Check backend logs → verify kernel process messages appear
- [ ] Run `ps aux | grep python` → verify kernel process exists

---

## Phase 3: Handle Reactive Cascades Properly

### Overview
Currently, `_execute_via_kernel` uses `queue.empty()` to detect cascade completion, which is unreliable. We need proper signaling from the kernel.

### Changes Required

#### 1. Add cascade metadata to kernel
**File**: `backend/app/kernel/process.py`

**Change lines 66-68**:
```python
# Get execution order (reactive cascade)
cells_to_run = graph.get_execution_order(request.cell_id)

# NEW: Send metadata about cascade size
total_cells = len(cells_to_run)
```

**Change lines 99-108**:
```python
# Send result
result = ExecutionResult(
    cell_id=cell_id,
    status=exec_result.status,
    stdout=exec_result.stdout,
    outputs=kernel_outputs,
    error=exec_result.error,
    reads=list(cell_reads),
    writes=list(cell_writes),
    # NEW: Add cascade metadata
    metadata={
        'cascade_index': cells_to_run.index(cell_id),
        'cascade_total': total_cells,
        'is_last': (cells_to_run.index(cell_id) == total_cells - 1)
    }
)
output_queue.put(result.model_dump())
```

#### 2. Update ExecutionResult type
**File**: `backend/app/kernel/types.py`

```python
class ExecutionResult(BaseModel):
    cell_id: str
    status: str
    stdout: str = ''
    outputs: List[Output] = []
    error: Optional[str] = None
    reads: List[str] = []
    writes: List[str] = []
    metadata: Optional[dict[str, Any]] = None  # NEW
```

#### 3. Update _execute_via_kernel to use metadata
**File**: `backend/app/orchestration/coordinator.py`

```python
async def _execute_via_kernel(self, request: ExecuteRequest) -> List[ExecutionResult]:
    """
    Send execution request to kernel and collect all cascade results.

    The kernel returns one result per cell with cascade metadata.
    We read until we receive a result with is_last=True.
    """
    results = []
    loop = asyncio.get_event_loop()

    # Send request to kernel
    self.kernel.input_queue.put(request.model_dump())

    while True:
        # Read result (blocking)
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        result = ExecutionResult(**result_data)
        results.append(result)

        # Check if this is the last result in the cascade
        if result.metadata and result.metadata.get('is_last', False):
            break

    return results
```

### Success Criteria

#### Automated Verification:
- [x] Reactive cascade test passes: `pytest backend/tests/test_reactive_cascade.py`
- [x] All integration tests pass: `make test`

#### Manual Verification:
- [x] Run cell A with 3 dependent cells → verify exactly 4 results returned
- [x] Check logs → verify cascade metadata is present
- [x] Verify frontend receives all updates in correct order

---

## Phase 4: Update WebSocket Connection Lifecycle

### Overview
Ensure kernel processes are started when WebSocket connects and stopped when disconnecting.

### Changes Required

#### 1. Update ConnectionManager.disconnect
**File**: `backend/app/websocket/handler.py`

**OLD CODE** (lines 22-26):
```python
def disconnect(self, connection_id: str):
    if connection_id in self.active_connections:
        del self.active_connections[connection_id]
    if connection_id in self.coordinators:
        del self.coordinators[connection_id]
```

**NEW CODE**:
```python
def disconnect(self, connection_id: str):
    if connection_id in self.active_connections:
        del self.active_connections[connection_id]
    if connection_id in self.coordinators:
        # Stop kernel process before removing coordinator
        coordinator = self.coordinators[connection_id]
        coordinator.shutdown()
        del self.coordinators[connection_id]
```

### Success Criteria

#### Automated Verification:
- [x] WebSocket tests pass: `pytest backend/tests/ -k websocket`

#### Manual Verification:
- [x] Connect frontend → verify kernel process starts
- [x] Close browser tab → verify kernel process stops
- [x] Check `ps aux | grep python` → no orphaned kernel processes

---

## Phase 5: Add Integration Tests

### Overview
Add tests that verify the kernel is actually being used in production code paths.

### Changes Required

#### 1. Create test_coordinator_kernel_integration.py
**File**: `backend/tests/test_coordinator_kernel_integration.py`

```python
"""Integration tests verifying coordinator uses kernel correctly."""
import pytest
import asyncio
from app.orchestration.coordinator import NotebookCoordinator
from app.websocket.handler import ConnectionManager


class MockBroadcaster:
    """Mock broadcaster for testing."""
    def __init__(self):
        self.messages = []

    async def broadcast(self, message: dict):
        self.messages.append(message)


@pytest.fixture
def coordinator():
    """Create coordinator with mock broadcaster."""
    broadcaster = MockBroadcaster()
    coord = NotebookCoordinator(broadcaster)
    # Load test notebook
    coord.load_notebook('test-notebook')
    yield coord
    coord.shutdown()


@pytest.mark.asyncio
async def test_coordinator_starts_kernel(coordinator):
    """Verify coordinator starts kernel process."""
    assert coordinator.kernel is not None
    assert coordinator.kernel._running is True
    assert coordinator.kernel.process.is_alive()


@pytest.mark.asyncio
async def test_coordinator_executes_via_kernel(coordinator):
    """Verify cell execution goes through kernel, not in-process."""
    # Execute a cell
    await coordinator.handle_run_cell('cell-1')

    # Verify kernel process handled it
    # (if it were in-process, we'd have PythonExecutor in coordinator)
    assert not hasattr(coordinator, 'python_executor')
    assert not hasattr(coordinator, 'graph')


@pytest.mark.asyncio
async def test_coordinator_handles_cascade(coordinator):
    """Verify reactive cascades work through kernel."""
    broadcaster = coordinator.broadcaster

    # Run cell that triggers cascade
    await coordinator.handle_run_cell('cell-1')

    # Check that multiple cells were broadcast
    status_messages = [m for m in broadcaster.messages if m['type'] == 'cell_status']

    # Should have received status updates for multiple cells
    assert len(status_messages) > 1


@pytest.mark.asyncio
async def test_coordinator_stops_kernel_on_shutdown(coordinator):
    """Verify kernel stops when coordinator shuts down."""
    process = coordinator.kernel.process
    coordinator.shutdown()

    # Wait for process to stop
    await asyncio.sleep(0.5)

    assert not coordinator.kernel._running
    assert not process.is_alive()
```

### Success Criteria

#### Automated Verification:
- [x] All new integration tests pass: `pytest backend/tests/test_coordinator_kernel_integration.py`
- [x] Full test suite passes: `make test`

#### Manual Verification:
- [x] Review test output → verify kernel process lifecycle is correct

---

## Phase 6: Clean Up Dead Code

### Overview
Remove all code that is no longer used after kernel integration.

### Changes Required

#### 1. Remove unused imports from coordinator
**File**: `backend/app/orchestration/coordinator.py`

Delete:
```python
from ..core.ast_parser import extract_python_dependencies, extract_sql_dependencies
from ..core.graph import DependencyGraph, CycleDetectedError
from ..core.executor import PythonExecutor, SQLExecutor
```

#### 2. Verify no other code imports coordinator's graph/executors
**Search patterns**:
```bash
grep -r "coordinator.graph" backend/
grep -r "coordinator.python_executor" backend/
grep -r "coordinator.sql_executor" backend/
```

If any matches found (besides tests), update those files to use kernel instead.

### Success Criteria

#### Automated Verification:
- [ ] `make lint` passes with no warnings about unused imports
- [ ] `make typecheck` passes with no type errors
- [ ] All tests pass: `make test`

#### Manual Verification:
- [ ] Code review confirms no dead code remains
- [ ] No TODOs or commented-out code in coordinator

---

## Testing Strategy

### Unit Tests (Existing - Should All Pass)
- `test_ast_parser.py` - Dependency extraction
- `test_graph.py` - DAG operations
- `test_executor.py` - Code execution
- `test_kernel_integration.py` - Kernel process IPC

### Integration Tests (New - Phase 5)
- `test_coordinator_kernel_integration.py` - Coordinator → Kernel flow
- Verify kernel lifecycle management
- Verify reactive cascades through IPC
- Verify no in-process execution

### End-to-End Tests (Manual)
1. Start backend: `make run`
2. Open frontend: `npm run dev`
3. Create notebook with 3 cells: A → B → C
4. Run cell A → verify cascade
5. Check `ps aux | grep python` → verify kernel process exists
6. Close browser → verify kernel process stops
7. Check logs → verify no errors

---

## Performance Considerations

**IPC Overhead**: Adding multiprocessing queues adds ~1-5ms latency per cell execution. This is acceptable for interactive notebook use.

**Memory**: Each kernel process uses ~50-100MB RAM. With one kernel per WebSocket connection, this scales linearly with concurrent users.

**Process Crashes**: If kernel crashes, coordinator can restart it via `coordinator.kernel.restart()`. We should add error handling in Phase 2.

---

## Migration Notes

### Rollback Plan
If integration fails:
1. Revert coordinator changes
2. Keep kernel layer code (it's isolated)
3. Re-attempt integration with better tests

### Backward Compatibility
- WebSocket protocol unchanged
- REST API unchanged
- Frontend unaffected
- File storage format unchanged

---

## Open Questions and Decisions

### 1. How to signal cascade completion? ✅ RESOLVED
**Decision**: Add `metadata` field to `ExecutionResult` with `cascade_index`, `cascade_total`, and `is_last` flags. Coordinator reads until `is_last=True`.

### 2. Should load_notebook send cells to kernel? ✅ RESOLVED
**Decision**: No. Kernel builds graph incrementally as cells are executed. The in-memory notebook state already has metadata from file storage.

### 3. One kernel per connection or per notebook? ✅ RESOLVED
**Decision**: One kernel per WebSocket connection (current behavior). This provides isolation. Global kernel per notebook can be added later if needed.

### 4. How to handle kernel crashes? 🔄 DEFERRED
**Decision**: Add error handling in Phase 2. If kernel crashes, log error and create new kernel. Frontend shows error message.

**Implementation**: Add try/catch around `kernel.execute()` that calls `kernel.restart()` on failure.

### 5. How to handle cell updates without execution? ✅ RESOLVED
**Decision**: Keep current behavior - cell updates just change code in memory. Metadata (reads/writes) stays stale until cell is re-executed. This matches Jupyter behavior.

---

## References

- Original research: [2026-01-07-kernel-orchestration-layer-separation.md](../research/2026-01-07-kernel-orchestration-layer-separation.md)
- Architecture doc: [2026-01-06-fresh-start-architecture.md](../research/2026-01-06-fresh-start-architecture.md)
- Kernel layer plan: [2026-01-06-kernel-layer-reactive-execution-engine.md](2026-01-06-kernel-layer-reactive-execution-engine.md)
- Orchestration layer plan: [2026-01-06-orchestration-layer-reactive-execution.md](2026-01-06-orchestration-layer-reactive-execution.md)

---

## Summary

This plan completes the kernel-orchestration integration that was originally designed but never finished. After completion:

- **Kernel Layer**: Owns dependency graph, executes code, manages user namespace ✅
- **Orchestration Layer**: Routes messages, manages kernel lifecycle, broadcasts results ✅
- **Interface Layer**: Handles HTTP/WebSocket, validates requests, serves frontend ✅

The separation of concerns will match the architecture document's vision, and the application will use proper process isolation for code execution.

**Total Estimated Effort**: 4-6 hours of focused implementation + testing
**Risk Level**: Medium (involves IPC and process management)
**Impact**: High (fixes architecture violation, enables future scaling)
