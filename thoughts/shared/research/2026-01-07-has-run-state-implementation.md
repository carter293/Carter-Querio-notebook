---
date: 2026-01-07T20:32:48Z
researcher: Matthew Carter
topic: "Implementing has_run State for Cell Execution Tracking"
tags: [research, codebase, kernel, execution-state, marimo, dependency-graph]
status: complete
last_updated: 2026-01-07
last_updated_by: Matthew Carter
commit: 92f84a85908a7d3e509f56c279afceb116a11cd4
branch: querio-take-home-but-i-dont-hate-myself-looking-at-it
---

# Research: Implementing has_run State for Cell Execution Tracking

**Date**: 2026-01-07 20:32:48 GMT  
**Researcher**: Matthew Carter  
**Commit**: 92f84a85908a7d3e509f56c279afceb116a11cd4

## Research Question

How should we implement a `has_run` state per cell in the kernel to match Marimo's behavior, where only STALE ancestors are run instead of ALL ancestors every time a cell is manually executed?

## Summary

**Current Behavior**: `get_execution_order_with_ancestors()` runs ALL ancestors + self + descendants every time, even if ancestors have already executed successfully. This is inefficient and doesn't match Marimo's semantics.

**Marimo's Approach**: They track a `stale` predicate per cell and only run ancestors that are stale (haven't been executed yet or need re-execution due to upstream changes).

**Proposed Solution**: Add `has_run: dict[str, bool]` state tracking in the kernel process to track which cells have successfully executed. Modify `get_execution_order_with_ancestors()` to only include ancestors that haven't run yet. Invalidate `has_run` state when cells are updated or their dependencies change.

**Key Insight**: This is purely a kernel-level concern. The state lives in `kernel_main`, gets invalidated during `register_cell`, and is consumed during `execute`.

## Detailed Findings

### 1. Current Execution Flow Analysis

From `backend/app/kernel/process.py` analysis:

**Cell Registration** (lines 34-102):
- When a `register_cell` request arrives, the kernel:
  1. Extracts dependencies (`extract_python_dependencies` / `extract_sql_dependencies`)
  2. Updates the graph: `graph.update_cell(cell_id, reads, writes)`
  3. Stores code in `cell_registry[cell_id] = (code, cell_type)`
  4. Emits METADATA and STATUS notifications

**Cell Execution** (lines 142-269):
- When an `execute` request arrives, the kernel:
  1. Verifies cell is registered
  2. **Gets execution order**: `cells_to_run = graph.get_execution_order_with_ancestors(request.cell_id)`
  3. Iterates through `cells_to_run` and executes each one
  4. For each cell: emits STATUS "running" → executes code → emits outputs → emits STATUS "success/error"

**The Problem**: Step 2 always includes ALL ancestors, regardless of whether they've already been executed.

### 2. Marimo's Stale Cell Tracking Approach

From user-provided Marimo research notes:

```python
# Runner always runs stale ancestors, if any.
cells_to_run = roots.union(
    dataflow.transitive_closure(
        graph,
        roots,
        children=False,
        inclusive=False,
        predicate=lambda cell: cell.stale,  # ← Only STALE ancestors
    )
)
```

**Key insights from Marimo**:
1. They track a `stale` boolean per cell
2. When computing ancestors to run, they filter by `cell.stale`
3. Only stale ancestors are included in the execution order
4. If a parent hasn't run, trying to use its variables results in `NameError` (wrapped as `MarimoMissingRefError`)

**In Normal Marimo Execution**: Automatically runs stale parent cells first to satisfy dependencies

**In AppKernelRunner**: Deliberately prevents ancestor execution by setting all cells to `stale=False` and using lazy mode

### 3. Where Execution State Should Live

From architecture analysis and state management pattern research:

**Current State Architecture**:
- **Backend models** (`app/models.py`): Define schema for `CellResponse` with `status`, `outputs`, `error`, etc.
- **Coordinator** (`app/orchestration/coordinator.py`): Explicitly stateless for execution results
  ```python
  # The coordinator is STATELESS for execution results - it just routes
  # messages from kernel to clients. All execution state (status, outputs,
  # errors) lives only in the frontend.
  ```
- **Frontend** (`NotebookApp.tsx`): Source of truth for current cell execution state via React state

**Conclusion**: `has_run` state is NOT part of the ephemeral execution state that lives in the frontend. It's part of the **kernel's internal execution state** used to make intelligent scheduling decisions.

**Where `has_run` should live**: In `kernel_main`, alongside `cell_registry`, `graph`, and executors.

### 4. Integration Points for `has_run` State

From codebase locator analysis:

**State Initialization** - `backend/app/kernel/process.py:11-23`:
```python
def kernel_main(input_queue: Queue, output_queue: Queue):
    # Initialize kernel state
    python_executor = PythonExecutor()
    sql_executor = SQLExecutor()
    graph = DependencyGraph()
    cell_registry: Dict[str, tuple[str, str]] = {}  # cell_id → (code, cell_type)
    
    # NEW: Add has_run tracking
    # has_run: Dict[str, bool] = {}  # cell_id → has executed successfully
```

**State Invalidation Point 1** - Cell registration (`process.py:34-102`):
When a cell's code changes (via `register_cell`):
```python
# After successful graph.update_cell()
cell_registry[register_req.cell_id] = (register_req.code, register_req.cell_type)

# NEW: Invalidate has_run for this cell AND its descendants
# has_run[register_req.cell_id] = False
# for descendant in graph.get_descendants(register_req.cell_id):
#     has_run[descendant] = False
```

**State Setting Point** - Cell execution success (`process.py:233-242`):
After successful execution:
```python
# Send status: success or error
status = "success" if exec_result.status == "success" else "error"
output_queue.put(CellNotification(...))

# NEW: Mark as has_run if successful
# if exec_result.status == "success":
#     has_run[cell_id] = True
```

**State Consumption Point** - Computing execution order (`process.py:172`):
```python
# Currently:
cells_to_run = graph.get_execution_order_with_ancestors(request.cell_id)

# Should become:
# cells_to_run = graph.get_execution_order_with_stale_ancestors(
#     request.cell_id, 
#     stale_predicate=lambda cid: not has_run.get(cid, False)
# )
```

### 5. Implementation Options

#### Option 1: Track has_run in kernel_main (Recommended)

**Pros**:
- Simple dictionary alongside existing kernel state
- Easy to invalidate on cell updates
- No changes to graph structure
- Matches Marimo's architecture (runner tracks stale state, graph is pure DAG)

**Cons**:
- State is lost on kernel restart (acceptable - fresh start makes sense)

**Implementation**:
```python
# In kernel_main
has_run: Dict[str, bool] = {}

# On register_cell (after successful graph update):
has_run[cell_id] = False
# Invalidate descendants too
for desc in nx.descendants(graph._graph, cell_id):
    has_run[desc] = False

# On successful execution:
if exec_result.status == "success":
    has_run[cell_id] = True

# On execute request:
def get_stale_ancestors(cell_id: str) -> Set[str]:
    """Get ancestors that haven't run yet."""
    ancestors = nx.ancestors(graph._graph, cell_id)
    return {a for a in ancestors if not has_run.get(a, False)}

cells_to_run = graph.get_execution_order_with_stale_ancestors(
    cell_id, 
    stale_ancestors=get_stale_ancestors(cell_id)
)
```

#### Option 2: Add stale tracking to DependencyGraph

**Pros**:
- Encapsulates state with the graph
- Could persist across kernel restarts if desired

**Cons**:
- Mixes concerns (graph should be pure DAG operations)
- More complex implementation
- Harder to reason about when state gets invalidated

**Not recommended** based on Marimo analysis - they keep graph pure and track stale state separately.

#### Option 3: Hybrid - Single boolean per cell for "first run"

**Pros**:
- Simpler than full stale tracking
- Only runs ancestors if the requested cell has NEVER been run before

**Cons**:
- Less precise than Marimo
- Doesn't handle case where ancestor fails and needs rerun

**Could be good first step**, but Option 1 is more correct.

### 6. Dependency Graph Method Changes

Need to add new method to `backend/app/core/graph.py`:

```python
def get_execution_order_with_stale_ancestors(
    self, 
    cell_id: str, 
    stale_ancestors: Set[str]
) -> List[str]:
    """
    Get the list of cells to execute when a cell is run (including only stale ancestors).

    Includes stale ancestor cells (dependencies that haven't run) + the cell itself + 
    all descendants, in topological order.

    Args:
        cell_id: The cell to execute
        stale_ancestors: Set of ancestor cell IDs that are stale (haven't run yet)

    Returns:
        List of cell IDs in the order they should be executed
    """
    if not self._graph.has_node(cell_id):
        return [cell_id]

    # Get descendants (always run these for reactive cascade)
    affected = {cell_id}
    try:
        affected |= nx.descendants(self._graph, cell_id)  # Add children
        affected |= stale_ancestors  # Add only STALE ancestors
    except nx.NetworkXError:
        pass

    # Create subgraph and sort topologically
    subgraph = self._graph.subgraph(affected)
    try:
        return list(nx.topological_sort(subgraph))
    except nx.NetworkXError:
        return [cell_id]
```

**Alternative**: Keep existing method and add filtering logic in kernel_main. Simpler and doesn't couple graph to execution state.

### 7. Edge Cases to Handle

**Case 1: Cell execution fails**
- Don't set `has_run[cell_id] = True` on error
- Leave as `False` so it runs again next time
- Descendants should also remain stale

**Case 2: Cell code is updated**
- Set `has_run[cell_id] = False` in register_cell handler
- Invalidate ALL descendants (they depend on potentially changed output)

**Case 3: Kernel restart**
- All `has_run` state is lost (dictionary is cleared)
- First execution of any cell will run all its ancestors
- This is correct behavior - kernel restart = fresh start

**Case 4: Circular dependencies detected**
- Don't update `has_run` state
- Cell remains in previous state
- Error is broadcast to frontend

**Case 5: Cell is deleted**
- Remove from `has_run` dictionary
- Graph already handles node removal

## Code References

- `backend/app/kernel/process.py:11-269` - Kernel main loop and execution flow
- `backend/app/core/graph.py:185-220` - `get_execution_order_with_ancestors` method
- `backend/app/core/graph.py:154-184` - `get_execution_order` method (for reactive cascades)
- `backend/app/models.py:1-72` - Cell and execution state models
- `backend/app/orchestration/coordinator.py:1-327` - Coordinator (explicitly stateless for execution)
- `frontend/src/components/NotebookApp.tsx:66-148` - Frontend execution state management

## Architecture Insights

### Separation of Concerns

The codebase follows a clear pattern:
1. **Kernel**: Pure execution engine with internal scheduling state (`has_run`)
2. **Coordinator**: Stateless message router
3. **Frontend**: UI state manager (receives execution events, renders state)

`has_run` is a **scheduling concern**, not an execution result. It belongs in the kernel.

### Execution State vs Scheduling State

Two types of state:
1. **Execution state** (ephemeral, lives in frontend):
   - `status: "running" | "success" | "error"`
   - `outputs: Output[]`
   - `stdout: string`
   - These are UI concerns, broadcast via WebSocket, rebuilt on reconnect

2. **Scheduling state** (kernel-internal, not exposed):
   - `has_run: boolean` per cell
   - Used to make smart execution order decisions
   - Lost on kernel restart (intentional)

### Marimo Alignment

This approach closely matches Marimo's architecture:
- Pure DAG in `DependencyGraph` (like Marimo's dataflow graph)
- Separate `stale` tracking in executor/runner (like Marimo's cell state)
- Incremental cycle detection (implemented in cycle-detection-refactor.md)
- Only stale ancestors are executed (this research)

## Historical Context

From `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md`:
- The kernel layer was designed to own all execution state
- The coordinator should be a pure message router
- Current implementation correctly follows this pattern
- `has_run` state fits naturally into existing kernel state management

From `thoughts/shared/plans/2026-01-07-cycle-detection-refactor.md`:
- Incremental cycle detection was implemented (Marimo-style)
- Cells must be registered before execution
- This provides the foundation for tracking `has_run` state

## Related Research

- `thoughts/shared/research/2026-01-06-fresh-start-architecture.md` - Original architecture vision
- `thoughts/shared/research/2026-01-07-kernel-orchestration-layer-separation.md` - Kernel owns execution state
- `thoughts/shared/plans/2026-01-07-cycle-detection-refactor.md` - Marimo-inspired cycle detection

## Implementation Plan

### Phase 1: Add has_run State Tracking

**File**: `backend/app/kernel/process.py`

1. Add state dictionary after line 21:
```python
has_run: Dict[str, bool] = {}  # cell_id → has executed successfully
```

2. Invalidate on registration (after line 52):
```python
# Mark cell as not run when code changes
has_run[register_req.cell_id] = False

# Invalidate all descendants
for descendant in nx.descendants(graph._graph, register_req.cell_id):
    has_run[descendant] = False
```

3. Mark as run on success (after line 239):
```python
# Mark cell as successfully run if execution succeeded
if status == "success":
    has_run[cell_id] = True
```

### Phase 2: Modify Execution Order Computation

**File**: `backend/app/kernel/process.py`

Replace line 172:
```python
# OLD:
cells_to_run = graph.get_execution_order_with_ancestors(request.cell_id)

# NEW:
# Get all ancestors
all_ancestors = nx.ancestors(graph._graph, request.cell_id) if graph._graph.has_node(request.cell_id) else set()

# Filter to only stale (not run) ancestors
stale_ancestors = {a for a in all_ancestors if not has_run.get(a, False)}

# Get execution order with only stale ancestors
affected = {request.cell_id} | stale_ancestors | nx.descendants(graph._graph, request.cell_id)
subgraph = graph._graph.subgraph(affected)
cells_to_run = list(nx.topological_sort(subgraph)) if affected else [request.cell_id]
```

### Phase 3: Add Helper Method (Optional)

**File**: `backend/app/core/graph.py`

Add method after `get_execution_order_with_ancestors`:
```python
def get_stale_ancestors(self, cell_id: str) -> Set[str]:
    """
    Get all ancestor cells of the given cell.
    
    Returns:
        Set of ancestor cell IDs (cells this cell transitively depends on)
    """
    if not self._graph.has_node(cell_id):
        return set()
    
    try:
        return set(nx.ancestors(self._graph, cell_id))
    except nx.NetworkXError:
        return set()
```

### Phase 4: Add Tests

**File**: `backend/tests/test_kernel_has_run_state.py` (new file)

```python
import pytest
from app.kernel.manager import KernelManager
from app.kernel.types import RegisterCellRequest, ExecuteRequest

@pytest.mark.asyncio
async def test_first_run_executes_ancestors():
    """First time running C2 should execute C1 first."""
    kernel = KernelManager()
    kernel.start()
    
    # Register cells
    kernel.input_queue.put(RegisterCellRequest(
        cell_id='c1', code='x = 10', cell_type='python'
    ).model_dump())
    
    kernel.input_queue.put(RegisterCellRequest(
        cell_id='c2', code='y = x + 5', cell_type='python'
    ).model_dump())
    
    # Execute c2 - should also run c1
    kernel.input_queue.put(ExecuteRequest(
        cell_id='c2', code='y = x + 5', cell_type='python'
    ).model_dump())
    
    # Verify execution order by collecting status messages
    # Should see: c1 running, c1 success, c2 running, c2 success
    
    kernel.stop()

@pytest.mark.asyncio
async def test_second_run_skips_executed_ancestors():
    """Second time running C2 should NOT re-execute C1."""
    kernel = KernelManager()
    kernel.start()
    
    # Register and run c1
    kernel.input_queue.put(RegisterCellRequest(
        cell_id='c1', code='x = 10', cell_type='python'
    ).model_dump())
    
    kernel.input_queue.put(ExecuteRequest(
        cell_id='c1', code='x = 10', cell_type='python'
    ).model_dump())
    
    # Register c2
    kernel.input_queue.put(RegisterCellRequest(
        cell_id='c2', code='y = x + 5', cell_type='python'
    ).model_dump())
    
    # Execute c2 - should NOT re-run c1
    kernel.input_queue.put(ExecuteRequest(
        cell_id='c2', code='y = x + 5', cell_type='python'
    ).model_dump())
    
    # Verify execution order: only c2 running, c2 success
    
    kernel.stop()

@pytest.mark.asyncio
async def test_code_change_invalidates_has_run():
    """Changing C1 code should invalidate has_run for C1 and C2."""
    kernel = KernelManager()
    kernel.start()
    
    # Register and execute c1, c2
    # ... (setup)
    
    # Update c1 code
    kernel.input_queue.put(RegisterCellRequest(
        cell_id='c1', code='x = 20', cell_type='python'
    ).model_dump())
    
    # Execute c2 - should re-run c1 because it changed
    kernel.input_queue.put(ExecuteRequest(
        cell_id='c2', code='y = x + 5', cell_type='python'
    ).model_dump())
    
    # Verify c1 was re-executed
    
    kernel.stop()
```

### Phase 5: Update Documentation

Update `backend/README.md` with:
- Explanation of `has_run` state tracking
- When ancestors are re-executed vs skipped
- How kernel restart affects execution

## Open Questions

1. **Should we expose has_run state to the frontend?**
   - Probably not initially - it's an internal optimization
   - Could be useful for debugging or showing "cell needs to run" indicator
   - Decision: Keep it internal for now

2. **What happens if execution times out?**
   - Currently no timeout mechanism
   - Should timeout count as failure (don't set has_run=True)?
   - Decision: Handle in future timeout implementation

3. **Should has_run be cleared when database connection changes?**
   - SQL cells depend on the database state
   - Probably not - database changes aren't tracked by dependency graph
   - Decision: Keep current behavior (SQL cells track variable deps only)

4. **Should we add a "force re-run" option?**
   - Useful for debugging or refreshing stale data
   - Could be a separate execute request type
   - Decision: Add if users request it

## Relevance Assessment

This research directly addresses the user's question about implementing Marimo-style stale cell tracking. The findings show:

1. **Clear implementation path**: Track `has_run` state in kernel_main
2. **Integration points identified**: Registration, execution, and order computation
3. **Architecture alignment**: Fits naturally into existing kernel state management
4. **Marimo compatibility**: Matches their approach of separate stale tracking

The implementation is straightforward and requires changes in only 2 files:
- `backend/app/kernel/process.py` (add state, invalidation, and filtering logic)
- `backend/tests/test_kernel_has_run_state.py` (new tests)

Optional enhancement: Add helper method to `backend/app/core/graph.py` for cleaner code.

