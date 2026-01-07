---
date: 2026-01-07T09:52:44Z
researcher: Matthew Carter
topic: "Kernel and Orchestration Layer Separation of Concerns"
tags: [research, codebase, architecture, kernel, orchestration, separation-of-concerns]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Research: Kernel and Orchestration Layer Separation of Concerns

**Date**: 2026-01-07 09:52:44 GMT  
**Researcher**: Matthew Carter  
**Commit**: 92f84a85908a7d3e509f56c279afceb116a11cd4

## Research Question

After implementing the kernel layer and orchestration layer plans, investigate whether the separation of concerns has been properly completed. According to the architecture document, the kernel should handle dependencies, not the orchestrator. Identify where the layers are not properly separated and how to connect them correctly.

## Summary

**Critical Finding**: The kernel layer (`KernelManager`, `kernel_main`) has been implemented but **is not integrated into the running application**. It exists only in tests. The current WebSocket flow bypasses the kernel entirely, with the `NotebookCoordinator` performing both orchestration AND kernel responsibilities in-process.

**The Problem**: There is significant duplication of responsibilities:
- Both `NotebookCoordinator` and `kernel_main` instantiate their own `DependencyGraph`, `PythonExecutor`, and `SQLExecutor`
- The coordinator extracts dependencies, manages the DAG, executes code, and broadcasts results
- The kernel does the same but is never called by the actual application

**According to the architecture**: The kernel should own the dependency graph and execution, while the orchestrator should only route messages and broadcast results.

## Detailed Findings

### 1. Current Execution Flow (WebSocket → Coordinator, bypassing Kernel)

**Entry Point**: `backend/app/websocket/handler.py`

```python:18:26:backend/app/websocket/handler.py
# Create coordinator for this connection
coordinator = NotebookCoordinator(broadcaster=self)
coordinator.load_notebook(notebook_id)
self.coordinators[connection_id] = coordinator
```

**When "run_cell" message arrives**:

```python:64:67:backend/app/websocket/handler.py
if msg_type == "run_cell":
    cell_id = message.get("cellId")
    if cell_id:
        await coordinator.handle_run_cell(cell_id)
```

The coordinator then:
1. Uses **its own** `DependencyGraph` to compute execution order
2. Uses **its own** `PythonExecutor`/`SQLExecutor` to run code
3. Broadcasts results itself

**No kernel involvement whatsoever.**

### 2. Duplication: Coordinator Has Kernel Responsibilities

**NotebookCoordinator** (`backend/app/orchestration/coordinator.py`):

```python:18:24:backend/app/orchestration/coordinator.py
def __init__(self, broadcaster):
    self.graph = DependencyGraph()
    self.python_executor = PythonExecutor()
    self.sql_executor = SQLExecutor()
    self.broadcaster = broadcaster
    self.notebook_id: Optional[str] = None
    self.notebook: Optional[NotebookResponse] = None
```

The coordinator:
- **Owns a DependencyGraph** (line 19)
- **Owns executors** (lines 20-21)
- **Extracts dependencies** via `_extract_dependencies()` (lines 47-55)
- **Updates the graph** via `self.graph.update_cell()` (line 38, 77)
- **Computes execution order** via `self.graph.get_execution_order()` (line 111)
- **Executes code** via `self.python_executor.execute()` (line 141)
- **Broadcasts results** (lines 133-182)

**This violates the separation of concerns**: The coordinator is doing orchestration, kernel work, and interface work all at once.

### 3. The Kernel Layer Exists But Is Unused

**kernel_main** (`backend/app/kernel/process.py`):

```python:11:21:backend/app/kernel/process.py
def kernel_main(input_queue: Queue, output_queue: Queue):
    """
    Main loop for kernel process.

    Runs in a separate process and handles execution requests.
    """
    # Initialize kernel state
    python_executor = PythonExecutor()
    sql_executor = SQLExecutor()
    graph = DependencyGraph()
    cell_registry: Dict[str, tuple[str, str]] = {}  # cell_id → (code, cell_type)
```

The kernel process:
- **Has its own DependencyGraph** (line 20)
- **Has its own executors** (lines 18-19)
- **Extracts dependencies** (lines 45-49)
- **Updates the graph** (line 53)
- **Computes execution order** (line 67)
- **Executes cells reactively** (lines 69-108)
- **Returns results via queue** (line 108)

**This is exactly what the coordinator is doing**, but this code never runs in production.

### 4. KernelManager Only Used in Tests

**Grep results**:
```
backend/tests/test_reactive_cascade.py:4: from app.kernel.manager import KernelManager
backend/tests/test_kernel_integration.py:4: from app.kernel.manager import KernelManager
backend/app/kernel/manager.py:9: class KernelManager:
```

**NOT imported or used in**:
- `backend/main.py`
- `backend/app/websocket/handler.py`
- `backend/app/orchestration/coordinator.py`
- Any API endpoints

**The kernel layer is dead code from the application's perspective.**

### 5. What the Architecture Document Says

From `thoughts/shared/research/2026-01-06-fresh-start-architecture.md`:

> **Kernel Layer** is a separate process that:
> 1. Maintains user namespace
> 2. Parses AST - Extracts variable reads/writes
> 3. Manages dependency graph - DAG tracking
> 4. Executes code
> 5. Handles reactive cascades

> **Orchestration Layer**:
> 1. Manage kernel process lifecycle
> 2. Route HTTP requests → Kernel commands
> 3. Forward Kernel results → WebSocket broadcasts
> 4. Maintain in-memory notebook state (for REST API)

**Current reality**: The orchestrator does ALL of the kernel's job AND its own job.

### 6. SQL Executor is a Stub (Additional Context)

From `backend/app/core/executor.py`:

```python:103:131:backend/app/core/executor.py
def execute(self, sql: str, variables: Dict[str, Any]) -> ExecutionResult:
    """
    Execute SQL query with variable substitution.

    For now, this is a stub that returns fake data.
    Future: Connect to actual database.
    """
    try:
        # Substitute {variable} templates
        substituted_sql = self._substitute_variables(sql, variables)

        # Stub: Return fake table data
        return ExecutionResult(
            status='success',
            stdout=f'Executed: {substituted_sql}\n',
            outputs=[Output(
                mime_type='application/json',
                data={
                    'type': 'table',
                    'columns': ['id', 'name'],
                    'rows': [[1, 'Alice'], [2, 'Bob']]
                }
            )]
        )
    except Exception as e:
        return ExecutionResult(
            status='error',
            error=str(e)
        )
```

The SQL executor is not connected to a real database. It:
- Substitutes `{variable}` templates from Python globals
- Returns hardcoded fake data
- Does not execute actual SQL

**This is fine for now**, but when real SQL execution is added, it should be in the kernel layer.

## Architecture Insights

### What Should Happen (Per Architecture Document)

```
┌─────────────────────────────────────────────────────┐
│           Orchestration Layer (FastAPI)             │
│  - WebSocket handler receives "run_cell"            │
│  - Puts ExecuteRequest into kernel input_queue      │
│  - Awaits ExecutionResult from output_queue         │
│  - Broadcasts results to WebSocket clients          │
└────────────────┬────────────────────────────────────┘
                 │ (multiprocessing.Queue)
┌────────────────▼────────────────────────────────────┐
│              Kernel Process (Separate)              │
│  while True:                                        │
│    request = input_queue.get()                      │
│    reads, writes = ast_parser.extract(code)         │
│    graph.update_cell(id, reads, writes)             │
│    if graph.has_cycle(): send error                 │
│    cells_to_run = graph.get_execution_order(id)     │
│    for cell in cells_to_run:                        │
│      result = executor.run(cell, user_globals)      │
│      output_queue.put(result)                       │
└─────────────────────────────────────────────────────┘
```

**Key principle**: The kernel owns the dependency graph and execution state. The orchestrator is just a message router and broadcaster.

### What Actually Happens (Current Implementation)

```
┌─────────────────────────────────────────────────────┐
│   WebSocket Handler (handler.py)                    │
│  - Receives "run_cell" message                      │
│  - Calls coordinator.handle_run_cell(cell_id)       │
└────────────────┬────────────────────────────────────┘
                 │ (direct function call)
┌────────────────▼────────────────────────────────────┐
│   NotebookCoordinator (coordinator.py)              │
│  - Has its own DependencyGraph                      │
│  - Has its own PythonExecutor/SQLExecutor           │
│  - Extracts dependencies via ast_parser             │
│  - Updates graph, computes execution order          │
│  - Executes cells directly in-process               │
│  - Broadcasts results                               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│   Kernel Process (process.py) - UNUSED             │
│  - Has DependencyGraph (never consulted)            │
│  - Has executors (never called)                     │
│  - Message loop (never runs)                        │
└─────────────────────────────────────────────────────┘
```

**The kernel is completely bypassed.**

### Why This Happened

Looking at the implementation plans:

1. **Orchestration Layer Plan** (`thoughts/shared/plans/2026-01-06-orchestration-layer-reactive-execution.md`) explicitly states:
   > "For initial implementation, we'll use **in-process execution** with a stub kernel. The separate kernel process can be added later without changing the orchestration layer's interface."

2. The plan implemented `PythonExecutor` and `SQLExecutor` as **in-process classes** first.

3. The **Kernel Layer Plan** (`thoughts/shared/plans/2026-01-06-kernel-layer-reactive-execution-engine.md`) was then implemented, creating `kernel_main` and `KernelManager`.

4. **The integration step was never completed**. The coordinator still uses its in-process executors.

## Code References

### Coordinator Responsibilities (Should Only Orchestrate)

- `backend/app/orchestration/coordinator.py:10-183` - Full coordinator class
- `backend/app/orchestration/coordinator.py:19` - Owns DependencyGraph (should delegate to kernel)
- `backend/app/orchestration/coordinator.py:20-21` - Owns executors (should delegate to kernel)
- `backend/app/orchestration/coordinator.py:38` - Updates graph (should send to kernel)
- `backend/app/orchestration/coordinator.py:111` - Computes execution order (should be kernel's job)
- `backend/app/orchestration/coordinator.py:141-143` - Executes code (should be kernel's job)

### Kernel Responsibilities (Correctly Implemented, But Unused)

- `backend/app/kernel/process.py:11-109` - Kernel main loop (never runs)
- `backend/app/kernel/process.py:20` - Kernel's DependencyGraph (never consulted)
- `backend/app/kernel/process.py:18-19` - Kernel's executors (never called)
- `backend/app/kernel/process.py:53` - Kernel updates graph (never happens)
- `backend/app/kernel/process.py:67` - Kernel computes execution order (never happens)
- `backend/app/kernel/manager.py:9-72` - KernelManager for IPC (only used in tests)

### WebSocket Integration Point

- `backend/app/websocket/handler.py:13-26` - ConnectionManager creates coordinator (should start kernel)
- `backend/app/websocket/handler.py:42-51` - Message loop (should forward to kernel via manager)
- `backend/app/websocket/handler.py:60-67` - Handles "run_cell" (should send ExecuteRequest to kernel)

### Tests That Work (Use Kernel Correctly)

- `backend/tests/test_kernel_integration.py` - Tests that actually use KernelManager
- `backend/tests/test_reactive_cascade.py` - Tests that verify reactive cascades via kernel

These tests demonstrate the kernel works correctly **when used**.

## Recommendations: How to Fix the Separation

### Option 1: Wire Kernel into Coordinator (Recommended)

**Goal**: Make the coordinator use `KernelManager` instead of direct executors.

**Changes needed**:

1. **Modify NotebookCoordinator.__init__**:
   ```python
   def __init__(self, broadcaster):
       self.kernel = KernelManager()
       self.kernel.start()  # Start kernel process
       self.broadcaster = broadcaster
       self.notebook_id: Optional[str] = None
       self.notebook: Optional[NotebookResponse] = None
       # Remove: self.graph, self.python_executor, self.sql_executor
   ```

2. **Modify handle_run_cell**:
   ```python
   async def handle_run_cell(self, cell_id: str):
       if not self.notebook:
           return
       
       cell = next((c for c in self.notebook.cells if c.id == cell_id), None)
       if not cell:
           return
       
       # Send execute request to kernel
       request = ExecuteRequest(
           cell_id=cell_id,
           code=cell.code,
           cell_type=cell.type
       )
       
       # Kernel returns ALL affected cells' results
       result = await self.kernel.execute(request)
       
       # Broadcast result
       await self._broadcast_result(result)
   ```

3. **Remove dependency extraction from coordinator**:
   - Delete `_extract_dependencies` method
   - The kernel already does this

4. **Modify load_notebook**:
   - Send all cells to kernel on load so it can build the graph
   - Remove graph building logic from coordinator

5. **Handle multiple results from kernel**:
   - Kernel sends results for changed cell + all descendants
   - Coordinator should await and broadcast each result

**Benefits**:
- True separation: Coordinator only routes and broadcasts
- Kernel owns all execution state
- Process isolation (crashes don't kill API server)
- Can scale to multiple kernels per notebook later

**Complexity**: Medium (requires refactoring coordinator, handling async IPC)

### Option 2: Remove Kernel Layer Entirely (Not Recommended)

**Goal**: Accept that coordinator does everything in-process.

**Changes needed**:
1. Delete `backend/app/kernel/` directory
2. Delete kernel-related tests
3. Update documentation to reflect in-process architecture

**Benefits**:
- Simpler (no IPC)
- Matches current reality

**Drawbacks**:
- Violates the architecture document's design
- User code crashes kill the API server
- Cannot scale to distributed kernels
- Loses process isolation benefits
- Goes against the stated goal of separation of concerns

### Option 3: Hybrid Approach (Optional)

**Goal**: Keep in-process execution for now, but prepare for kernel integration.

**Changes needed**:
1. Create a `KernelInterface` abstract base class
2. Implement `InProcessKernel` (current coordinator logic)
3. Implement `ProcessKernel` (uses KernelManager)
4. Coordinator uses `KernelInterface`, can swap implementations

**Benefits**:
- Can switch between in-process and separate process
- Maintains flexibility
- Gradual migration path

**Drawbacks**:
- More code to maintain
- Doesn't immediately fix separation issue

## Proposed Implementation Plan (Option 1)

### Phase 1: Refactor Coordinator to Use Kernel

**1.1 Update NotebookCoordinator**:
- Import `KernelManager` and `ExecuteRequest` from kernel layer
- Replace `graph`, `python_executor`, `sql_executor` with `self.kernel = KernelManager()`
- Start kernel in `__init__`
- Stop kernel in a new `shutdown()` method

**1.2 Refactor handle_run_cell**:
- Create `ExecuteRequest` object
- Call `await self.kernel.execute(request)`
- Handle the returned `ExecutionResult`
- Broadcast status, stdout, outputs, errors

**1.3 Refactor load_notebook**:
- For each cell, send `ExecuteRequest` to kernel (to build its graph)
- Don't execute, just let kernel parse dependencies
- Or: Add a new kernel message type `UpdateCell` for code changes without execution

**1.4 Remove unused methods**:
- Delete `_extract_dependencies`
- Delete `_execute_cell` (kernel does this)
- Simplify coordinator to just message routing + broadcasting

### Phase 2: Handle Reactive Cascades

**2.1 Kernel already returns multiple results**:
```python:99:108:backend/app/kernel/process.py
# Send result
result = ExecutionResult(
    cell_id=cell_id,
    status=exec_result.status,
    stdout=exec_result.stdout,
    outputs=kernel_outputs,
    error=exec_result.error,
    reads=list(cell_reads),
    writes=list(cell_writes),
)
output_queue.put(result.model_dump())
```

The kernel sends one result per cell. The coordinator needs to:
- Read multiple results from `output_queue`
- Broadcast each as it arrives
- Know when cascade is complete

**2.2 Modify KernelManager.execute**:
```python
async def execute(self, request: ExecuteRequest) -> List[ExecutionResult]:
    """Execute and return results for all affected cells."""
    if not self._running:
        raise RuntimeError("Kernel not running")
    
    # Send request
    self.input_queue.put(request.model_dump())
    
    # Read results until cascade complete
    results = []
    loop = asyncio.get_event_loop()
    
    # First result tells us how many cells will run
    first_result = await loop.run_in_executor(None, self.output_queue.get)
    results.append(ExecutionResult(**first_result))
    
    # TODO: Need a way to know when cascade is done
    # Option: Kernel sends a "cascade_complete" message
    # Option: First result includes "total_cells" metadata
    
    return results
```

**2.3 Add cascade metadata to kernel**:
- Kernel knows execution order length
- First result includes `cascade_size` metadata
- Manager reads that many results

### Phase 3: Update ConnectionManager

**3.1 Handle kernel lifecycle per connection**:
```python
async def connect(self, websocket: WebSocket, connection_id: str, notebook_id: str):
    await websocket.accept()
    self.active_connections[connection_id] = websocket
    
    # Create coordinator (which starts kernel)
    coordinator = NotebookCoordinator(broadcaster=self)
    coordinator.load_notebook(notebook_id)
    self.coordinators[connection_id] = coordinator

def disconnect(self, connection_id: str):
    if connection_id in self.coordinators:
        coordinator = self.coordinators[connection_id]
        coordinator.shutdown()  # Stop kernel process
        del self.coordinators[connection_id]
    if connection_id in self.active_connections:
        del self.active_connections[connection_id]
```

### Phase 4: Testing

**4.1 Update integration tests**:
- Modify tests to verify kernel is actually used
- Check that kernel process is running
- Verify process isolation (kernel crash doesn't kill server)

**4.2 Manual testing**:
- Start backend, connect frontend
- Run cell A, verify B and C cascade
- Verify status messages arrive in order
- Test cycle detection
- Test kernel restart

### Phase 5: Documentation

**5.1 Update architecture doc**:
- Mark kernel integration as complete
- Document the IPC flow
- Explain how results flow back

**5.2 Add inline comments**:
- Explain why coordinator delegates to kernel
- Document the queue-based IPC pattern

## Open Questions

1. **How should the kernel signal "cascade complete"?**
   - Option A: Send a special `cascade_complete` message after last result
   - Option B: Include `total_cells` in first result's metadata
   - Option C: Include `is_last: bool` in each `ExecutionResult`

2. **Should load_notebook send all cells to kernel?**
   - Currently coordinator builds graph on load
   - Should it send `UpdateCell` messages to kernel instead?
   - Or: Kernel reads from file storage directly (violates separation)

3. **How to handle cell updates via REST API?**
   - PUT `/notebooks/{id}/cells/{cell_id}` updates code
   - Should this send a message to kernel to update graph?
   - Currently coordinator updates its own graph

4. **Should there be one kernel per notebook or one per connection?**
   - Current: One coordinator (with kernel) per WebSocket connection
   - Alternative: One global kernel per notebook, shared by all connections
   - Tradeoff: Sharing vs isolation

5. **How to handle SQL database connections?**
   - SQL executor is currently a stub
   - When real database is added, should kernel manage connection pool?
   - Or: Pass connection string to kernel on startup

## Related Research

- `thoughts/shared/research/2026-01-06-fresh-start-architecture.md` - Architecture design
- `thoughts/shared/plans/2026-01-06-kernel-layer-reactive-execution-engine.md` - Kernel implementation plan
- `thoughts/shared/plans/2026-01-06-orchestration-layer-reactive-execution.md` - Orchestration implementation plan

## Conclusion

**The separation of concerns is incomplete.** The kernel layer exists and works correctly in tests, but the production code bypasses it entirely. The `NotebookCoordinator` performs both orchestration and kernel responsibilities, violating the architecture's design.

**Recommended next steps**:
1. Refactor `NotebookCoordinator` to delegate to `KernelManager`
2. Remove duplicate dependency graph and executor instances from coordinator
3. Update `KernelManager.execute` to handle reactive cascades (return multiple results)
4. Test the integrated system end-to-end
5. Update documentation to reflect the completed integration

This will achieve true separation of concerns:
- **Kernel Layer**: Owns dependency graph, executes code, manages user namespace
- **Orchestration Layer**: Routes messages, manages kernel lifecycle, broadcasts results
- **Interface Layer**: Handles HTTP/WebSocket, validates requests, serves frontend

The architecture will then match the design document's vision.

