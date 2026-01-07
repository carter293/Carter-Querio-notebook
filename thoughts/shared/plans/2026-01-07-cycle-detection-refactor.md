# Cycle Detection & Separation of Concerns Refactor

**Date**: 2026-01-07
**Related**: [2026-01-07-integration-summary.md](2026-01-07-integration-summary.md)
**Status**: Ready for implementation

---

## Overview

Refactor the dependency graph's cycle detection to use incremental per-edge checking (marimo-style) instead of full graph copying, and remove auto-registration logic from the kernel execution handler to enforce proper separation of concerns.

---

## Current State Analysis

### Problem 1: Expensive Cycle Detection

**Location**: `backend/app/core/graph.py:25-69`

Current `would_create_cycle()` implementation:
- Creates full graph copy: `temp_graph = self._graph.copy()` - **O(V+E) memory**
- Rebuilds all edges in temporary graph
- Runs full DAG check: `nx.is_directed_acyclic_graph(temp_graph)` - **O(V+E) time**
- Then `update_cell()` repeats the same edge-building logic

**Cost**: O(2×(V+E)) per cell update, where V=number of cells, E=number of dependencies

**Real-world impact**:
- For 100 cells with 200 dependencies: ~400 operations per cell update
- Unnecessary memory pressure from graph copies
- Duplicate work building edges twice

### Problem 2: Auto-Registration in Executor

**Location**: `backend/app/kernel/process.py:86-110`

The kernel's execution handler contains auto-registration logic:

```python
# Auto-register cell if not already registered
if request.cell_id not in cell_registry:
    # Extract dependencies (REGISTRATION CONCERN)
    if request.cell_type == 'python':
        reads, writes = extract_python_dependencies(request.code)

    # Try to register in graph (REGISTRATION CONCERN)
    try:
        graph.update_cell(request.cell_id, reads, writes)
        cell_registry[request.cell_id] = (request.code, request.cell_type)
```

**Problems**:
1. **Violation of single responsibility** - execution handler performing registration
2. **Tests rely on this** - cycle prevention tests pass only because executor registers
3. **Inconsistent with architecture goals** - fresh-start-architecture.md states kernel should be registration-free executor
4. **Duplicate logic** - registration code exists in both handlers

### Key Discoveries from Marimo Analysis

From `thoughts/shared/research/2026-01-07-cycle-prevention-architecture.md`:

**Marimo's approach**:
1. **Incremental cycle detection**: Check each edge as it's added using reachability query
2. **No rollback needed**: Cycles detected before mutation
3. **Zero registration in executor**: Runner and Executor are execution-only, read-only graph access

**Algorithm**: For new edge (parent → child), check if path exists from child → parent in existing graph. If yes, adding edge creates cycle.

**Cost**: O(edges_added × path_length) where edges_added is typically 1-5 per cell

---

## System Context Analysis

This refactor addresses **two architectural debts** introduced during the integration phase:

1. **Performance debt**: The full-graph-copy approach was a quick solution to implement cycle checking without rollback complexity, but it doesn't scale
2. **Architectural debt**: Auto-registration was added to make tests pass without requiring explicit registration calls

The proposed solution aligns with the **original architecture vision** from `fresh-start-architecture.md`:
- Kernel layer should be a pure execution engine
- Registration is an orchestration-layer concern
- Graph operations should be efficient and incremental

---

## Desired End State

### Success Criteria

#### Automated Verification:
- [x] All existing tests pass: `pytest backend/tests/`
- [ ] Performance benchmark: Cell update operations complete in <5ms (vs current ~20ms for 50-cell notebook)
- [x] Memory profiling: No graph copies created during cycle detection
- [ ] Type checking passes: `mypy backend/app/core/graph.py`

#### Manual Verification:
- [ ] Create 100-cell notebook with complex dependencies - updates feel instant
- [ ] Attempt to create cycle - error appears immediately
- [ ] Verify no auto-registration occurs during execution (check kernel logs)

### Behavioral Changes

**Cycle detection**:
- Before: O(V+E) - full graph copy + full DAG check
- After: O(edges × path_length) - incremental per-edge reachability

**Execution behavior**:
- Before: Executor auto-registers cells silently
- After: Executor fails fast if cell not registered (orchestration layer bug)

**Test requirements**:
- Before: Tests could execute cells without registration
- After: Tests must explicitly register cells before execution

---

## What We're NOT Doing

- ❌ Changing the registration API (RegisterCellRequest/Result remain unchanged)
- ❌ Changing the WebSocket protocol
- ❌ Modifying frontend behavior
- ❌ Implementing execution timeouts or cancellation
- ❌ Adding cycle visualization or detailed cycle paths
- ❌ Optimizing NetworkX graph operations (we're just using it better)

---

## Implementation Approach

### Strategy 1: Incremental Cycle Detection

Replace `would_create_cycle()` with per-edge cycle checking that operates directly on the graph without copying.

**Key insight**: When adding edge (A → B), check if path B → A already exists. If yes, adding A → B creates a cycle.

### Strategy 2: Remove Auto-Registration

Delete auto-registration logic from kernel execution handler. This enforces that orchestration layer must register cells before execution.

**Migration path**: Update test fixtures to ensure all cells are registered before execution attempts.

---

## Phase 1: Implement Incremental Cycle Detection

### Overview
Replace `would_create_cycle()` with `_would_edge_create_cycle()` that checks individual edges without copying the graph.

### Changes Required

#### 1. DependencyGraph Core Logic

**File**: `backend/app/core/graph.py`

**Remove**: `would_create_cycle()` method (lines 25-69)

**Add**: Helper method for edge-level cycle detection

```python
def _would_edge_create_cycle(self, from_cell: str, to_cell: str) -> bool:
    """
    Check if adding edge from_cell → to_cell would create a cycle.

    Uses the fact that adding edge A→B creates a cycle iff there's already
    a path B→A in the graph (incremental detection, no graph copy needed).

    Args:
        from_cell: Source cell of the edge
        to_cell: Destination cell of the edge

    Returns:
        True if edge would create a cycle, False otherwise
    """
    if from_cell == to_cell:
        return True  # Self-loop

    if not self._graph.has_node(to_cell):
        return False  # to_cell doesn't exist yet, can't have path back

    if not self._graph.has_node(from_cell):
        return False  # from_cell doesn't exist yet, no path possible

    # Check if there's a path from to_cell back to from_cell
    try:
        return nx.has_path(self._graph, to_cell, from_cell)
    except nx.NodeNotFound:
        return False
```

**Modify**: `update_cell()` method to check edges incrementally

```python
def update_cell(self, cell_id: str, reads: Set[str], writes: Set[str]) -> None:
    """
    Update the graph when a cell's code changes.

    Args:
        cell_id: The cell being updated
        reads: Set of variables this cell reads
        writes: Set of variables this cell writes

    Raises:
        CycleDetectedError: If this update would create a circular dependency
    """
    # Compute what edges we would add BEFORE mutating anything
    new_parent_edges = []  # Edges where other cells write what we read
    new_child_edges = []   # Edges where other cells read what we write

    for var in reads:
        writer = self._var_writers.get(var)
        if writer and writer != cell_id:
            new_parent_edges.append((writer, cell_id))

    for var in writes:
        for other_cell in list(self._graph.nodes()):
            if other_cell == cell_id:
                continue
            other_reads = self._cell_reads.get(other_cell, set())
            if var in other_reads:
                new_child_edges.append((cell_id, other_cell))

    # Check each edge incrementally BEFORE adding anything
    for from_cell, to_cell in new_parent_edges:
        if self._would_edge_create_cycle(from_cell, to_cell):
            raise CycleDetectedError(
                f"Circular dependency detected: adding edge {from_cell}→{to_cell} "
                f"would create a cycle (path exists {to_cell}→{from_cell})"
            )

    for from_cell, to_cell in new_child_edges:
        if self._would_edge_create_cycle(from_cell, to_cell):
            raise CycleDetectedError(
                f"Circular dependency detected: adding edge {from_cell}→{to_cell} "
                f"would create a cycle (path exists {to_cell}→{from_cell})"
            )

    # All edges are safe - now mutate the graph

    # Remove old node and edges
    if self._graph.has_node(cell_id):
        self._graph.remove_node(cell_id)

    # Clear old variable mappings
    if cell_id in self._cell_writes:
        old_writes = self._cell_writes[cell_id]
        for var in old_writes:
            if self._var_writers.get(var) == cell_id:
                del self._var_writers[var]

    # Register new writes and reads
    self._cell_writes[cell_id] = writes
    self._cell_reads[cell_id] = reads
    for var in writes:
        self._var_writers[var] = cell_id

    # Add node
    self._graph.add_node(cell_id)

    # Add all edges (we know they're safe)
    for from_cell, to_cell in new_parent_edges:
        self._graph.add_edge(from_cell, to_cell)

    for from_cell, to_cell in new_child_edges:
        self._graph.add_edge(from_cell, to_cell)
```

### Success Criteria

#### Automated Verification:
- [x] Graph unit tests pass: `pytest backend/tests/test_graph.py -v`
- [x] Cycle detection tests pass: `pytest backend/tests/test_cycle_prevention.py -v`
- [x] No graph copies in cycle detection code (manual code inspection)
- [ ] Performance test: 100 cell updates complete in <500ms

#### Manual Verification:
- [ ] Create cell A: `x = 10`, create cell B: `y = x + 1` - succeeds
- [ ] Update cell A to `x = y + 1` - cycle error appears immediately
- [ ] Cell B still works after A's failed update

---

## Phase 2: Remove Auto-Registration from Executor

### Overview
Delete auto-registration logic from kernel execution handler and ensure all tests explicitly register cells before executing.

### Changes Required

#### 1. Kernel Execution Handler

**File**: `backend/app/kernel/process.py`

**Remove**: Lines 86-110 (auto-registration block)

**Replace with**: Fail-fast check

```python
# Parse execute request
try:
    request = ExecuteRequest(**request_data)
except Exception as e:
    print(f"[Kernel] Invalid request: {e}")
    continue

# Verify cell is registered
if request.cell_id not in cell_registry:
    error_msg = (
        f"Cell {request.cell_id} not registered. "
        "Cells must be registered via RegisterCellRequest before execution."
    )
    result = ExecutionResult(
        cell_id=request.cell_id,
        status='error',
        error=error_msg,
        metadata={'is_last': True}
    )
    output_queue.put(result.model_dump())
    continue

# Get execution order (cell already registered)
cells_to_run = graph.get_execution_order(request.cell_id)
```

**Rationale**: Execution layer should not perform registration. This enforces architectural boundaries and makes bugs visible.

#### 2. Update Test Fixtures

**Files to update**:
- `backend/tests/test_reactive_cascade.py`
- `backend/tests/test_coordinator_kernel_integration.py`
- Any integration tests that don't explicitly register before execute

**Pattern**: Add registration step before first execution

```python
@pytest.fixture
def kernel():
    """Create and manage kernel for tests."""
    manager = KernelManager()
    manager.start()
    yield manager
    manager.stop()


async def register_cell(kernel, cell_id: str, code: str, cell_type: str = 'python'):
    """Helper to register a cell and wait for result."""
    from app.kernel.types import RegisterCellRequest, RegisterCellResult

    req = RegisterCellRequest(cell_id=cell_id, code=code, cell_type=cell_type)
    kernel.input_queue.put(req.model_dump())

    # Read result
    result_data = await asyncio.get_event_loop().run_in_executor(
        None, kernel.output_queue.get
    )
    assert result_data.get('type') == 'register_result'
    result = RegisterCellResult(**result_data)
    assert result.status == 'success', f"Registration failed: {result.error}"
    return result
```

**Update test pattern**:

```python
# BEFORE (relies on auto-registration)
@pytest.mark.asyncio
async def test_reactive_cascade_simple(kernel):
    req1 = ExecuteRequest(cell_id='c1', code='x = 10', cell_type='python')
    result1 = await kernel.execute(req1)

# AFTER (explicit registration)
@pytest.mark.asyncio
async def test_reactive_cascade_simple(kernel):
    # Register cells first
    await register_cell(kernel, 'c1', 'x = 10')

    # Now execute
    req1 = ExecuteRequest(cell_id='c1', code='x = 10', cell_type='python')
    result1 = await kernel.execute(req1)
```

### Success Criteria

#### Automated Verification:
- [x] All tests pass after fixture updates: `pytest backend/tests/ -v`
- [x] No auto-registration code remains in `process.py` (code inspection)
- [x] Attempting to execute unregistered cell returns error (write new test)

#### Manual Verification:
- [ ] Start notebook, try to execute cell without updating code - works (already registered)
- [ ] Kill kernel, restart, try to execute - fails with "not registered" error
- [ ] Update cell code (triggers re-registration), then execute - works

---

## References

- Original architecture: [2026-01-06-fresh-start-architecture.md](../research/2026-01-06-fresh-start-architecture.md)
- Marimo analysis: [2026-01-07-cycle-prevention-architecture.md](../research/2026-01-07-cycle-prevention-architecture.md)
- Integration summary: [2026-01-07-integration-summary.md](2026-01-07-integration-summary.md)
- NetworkX documentation: https://networkx.org/documentation/stable/reference/algorithms/dag.html
