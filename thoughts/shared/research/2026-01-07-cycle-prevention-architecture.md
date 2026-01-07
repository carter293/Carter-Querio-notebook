# Cycle Prevention Architecture - Separation of Concerns

**Date**: 2026-01-07
**Context**: Discovered during kernel-orchestration integration
**Related**: [2026-01-07-kernel-orchestration-integration.md](../plans/2026-01-07-kernel-orchestration-integration.md)

---

## Problem Statement

The original `DependencyGraph.update_cell()` implementation violated separation of concerns by attempting to both mutate state AND validate constraints, with complex rollback logic when validation failed.

### Original Flawed Approach

```python
def update_cell(self, cell_id: str, reads: Set[str], writes: Set[str]):
    # 1. Mutate state
    self._graph.remove_node(cell_id)
    self._cell_writes[cell_id] = writes
    self._cell_reads[cell_id] = reads
    self._var_writers[var] = cell_id
    self._graph.add_node(cell_id)
    self._graph.add_edges(...)

    # 2. Validate
    if not nx.is_directed_acyclic_graph(self._graph):
        # 3. Attempt rollback
        self._graph.remove_node(cell_id)  # Only reverts graph!
        # BUG: _cell_writes, _cell_reads, _var_writers still corrupted
        raise CycleDetectedError(...)
```

### Issues

1. **State Corruption**: Rollback only reverted graph node, not the dictionaries
2. **Order Dependency**: Mutation before validation meant state could be left inconsistent
3. **Complex Logic**: Rollback logic was error-prone and hard to maintain
4. **Hidden Bugs**: Tests passed but state was corrupted on cycle detection

---

## Solution: Check-Then-Mutate Pattern

Separate the validation from mutation using a two-phase approach:

### Phase 1: Non-Mutating Check

```python
def would_create_cycle(self, cell_id: str, reads: Set[str], writes: Set[str]) -> bool:
    """
    Check if updating a cell would create a cycle, without modifying the graph.

    Returns:
        True if the update would create a cycle, False otherwise
    """
    # Create temporary graph copy
    temp_graph = self._graph.copy()
    temp_var_writers = self._var_writers.copy()
    temp_cell_reads = self._cell_reads.copy()

    # Simulate the update
    if temp_graph.has_node(cell_id):
        temp_graph.remove_node(cell_id)

    for var in writes:
        temp_var_writers[var] = cell_id

    temp_graph.add_node(cell_id)

    for var in reads:
        writer = temp_var_writers.get(var)
        if writer and writer != cell_id:
            temp_graph.add_edge(writer, cell_id)

    for other_cell in list(temp_graph.nodes()):
        if other_cell == cell_id:
            continue
        other_reads = temp_cell_reads.get(other_cell, set())
        for var in writes:
            if var in other_reads:
                temp_graph.add_edge(cell_id, other_cell)

    # Check without mutating
    return not nx.is_directed_acyclic_graph(temp_graph)
```

### Phase 2: Mutating Update

```python
def update_cell(self, cell_id: str, reads: Set[str], writes: Set[str]) -> None:
    """
    Update the graph when a cell's code changes.

    Raises:
        CycleDetectedError: If this update would create a circular dependency
    """
    # Check BEFORE mutating
    if self.would_create_cycle(cell_id, reads, writes):
        raise CycleDetectedError(
            f"Circular dependency detected involving cell {cell_id}"
        )

    # Now mutate (knowing it's safe)
    if self._graph.has_node(cell_id):
        self._graph.remove_node(cell_id)

    if cell_id in self._cell_writes:
        old_writes = self._cell_writes[cell_id]
        for var in old_writes:
            if self._var_writers.get(var) == cell_id:
                del self._var_writers[var]

    self._cell_writes[cell_id] = writes
    self._cell_reads[cell_id] = reads

    for var in writes:
        self._var_writers[var] = cell_id

    self._graph.add_node(cell_id)

    for var in reads:
        writer = self._var_writers.get(var)
        if writer and writer != cell_id:
            self._graph.add_edge(writer, cell_id)

    for other_cell in list(self._graph.nodes()):
        if other_cell == cell_id:
            continue
        other_reads = self._cell_reads.get(other_cell, set())
        for var in writes:
            if var in other_reads:
                self._graph.add_edge(cell_id, other_cell)
```

---

## Benefits

### 1. Separation of Concerns

**Check Phase** (`would_create_cycle`):
- Pure function (no side effects)
- Can be called multiple times safely
- Easy to test
- Clear purpose: validation only

**Mutation Phase** (`update_cell`):
- Only called after validation passes
- No rollback needed
- State always consistent
- Clear purpose: update only

### 2. Correctness

- **No state corruption**: Either update succeeds completely or fails with no changes
- **Atomic operations**: All-or-nothing semantics
- **Predictable behavior**: Easy to reason about control flow

### 3. Maintainability

- **Simple logic**: Each method has one responsibility
- **No complex rollback**: Less code, fewer bugs
- **Clear contracts**: Function signatures express intent

### 4. Performance

- **Acceptable overhead**: Temporary graph copy is O(N) where N = number of cells
- **Typical case**: Notebooks have 10-100 cells, copy takes <1ms
- **Optimization possible**: Could cache validation results if needed

---

## Integration with Kernel Layer

The kernel process uses this pattern for cell registration:

```python
# Registration handler in kernel process
if request_data.get('type') == 'register_cell':
    register_req = RegisterCellRequest(**request_data)

    # Extract dependencies
    reads, writes = extract_dependencies(register_req.code, register_req.cell_type)

    # Try to register
    try:
        graph.update_cell(register_req.cell_id, reads, writes)

        # Success - store cell code
        cell_registry[register_req.cell_id] = (register_req.code, register_req.cell_type)

        # Send success result
        result = RegisterCellResult(
            cell_id=register_req.cell_id,
            status='success',
            reads=list(reads),
            writes=list(writes)
        )
        output_queue.put(result.model_dump())

    except CycleDetectedError as e:
        # Failed - send error result
        result = RegisterCellResult(
            cell_id=register_req.cell_id,
            status='error',
            error=str(e),
            reads=list(reads),
            writes=list(writes)
        )
        output_queue.put(result.model_dump())
```

---

## Comparison to Alternatives

### Alternative 1: Rollback with Full State Save

**Approach**: Save complete state before mutation, restore on error

```python
def update_cell(self, cell_id, reads, writes):
    # Save entire state
    old_graph = self._graph.copy()
    old_writes = self._cell_writes.copy()
    old_reads = self._cell_reads.copy()
    old_var_writers = self._var_writers.copy()

    # Mutate
    # ... complex mutation logic ...

    # Check
    if not nx.is_directed_acyclic_graph(self._graph):
        # Restore entire state
        self._graph = old_graph
        self._cell_writes = old_writes
        self._cell_reads = old_reads
        self._var_writers = old_var_writers
        raise CycleDetectedError(...)
```

**Problems**:
- More memory usage (copying all state)
- Still complex (mutation interleaved with validation)
- Error-prone (easy to forget to save/restore a field)

### Alternative 2: Transactions

**Approach**: Use transaction-like semantics

**Problems**:
- Over-engineering for this use case
- Adds complexity without clear benefit
- Python doesn't have built-in transaction support

### Our Approach: Check-Then-Mutate

**Advantages**:
- Minimal code changes
- Clear separation of concerns
- No rollback needed
- Easy to understand and maintain

---

## Lessons Learned

### 1. Validate Before Mutate

When a method both validates AND mutates, consider splitting it:
- Validation method: Pure, no side effects
- Mutation method: Assumes validation passed

### 2. Avoid Complex Rollback

If you need complex rollback logic, it's a sign that validation should happen first.

### 3. Test for State Corruption

The original bug passed tests because we only checked the exception, not the state after the exception. Tests should verify state remains consistent on error paths.

### 4. Separation of Concerns Applies to Methods Too

Not just classes and modules - individual methods benefit from single responsibility principle.

---

## References

- Implementation: [backend/app/core/graph.py](../../../backend/app/core/graph.py)
- Tests: [backend/tests/test_cycle_prevention.py](../../../backend/tests/test_cycle_prevention.py)
- Integration plan: [2026-01-07-kernel-orchestration-integration.md](../plans/2026-01-07-kernel-orchestration-integration.md)
