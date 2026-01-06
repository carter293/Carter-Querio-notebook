"""Tests for dependency graph."""
import pytest
from app.core.graph import DependencyGraph, CycleDetectedError


def test_simple_chain():
    """Test A → B → C dependency chain."""
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads={'x'}, writes={'y'})
    graph.update_cell('c3', reads={'y'}, writes={'z'})

    # Changing c1 should trigger c1, c2, c3
    order = graph.get_execution_order('c1')
    assert order == ['c1', 'c2', 'c3']


def test_diamond_pattern():
    """Test A → B, C → D pattern."""
    graph = DependencyGraph()
    graph.update_cell('a', reads=set(), writes={'x'})
    graph.update_cell('b', reads={'x'}, writes={'y'})
    graph.update_cell('c', reads={'x'}, writes={'z'})
    graph.update_cell('d', reads={'y', 'z'}, writes={'result'})

    # Changing 'a' should trigger all cells
    order = graph.get_execution_order('a')
    assert set(order) == {'a', 'b', 'c', 'd'}
    assert order[0] == 'a'  # 'a' comes first
    # 'b' and 'c' can be in any order (both depend on 'a')
    # 'd' must come last (depends on both 'b' and 'c')
    assert order[-1] == 'd'


def test_no_dependencies():
    """Test independent cells."""
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads=set(), writes={'y'})

    # Changing c1 should only trigger c1
    order = graph.get_execution_order('c1')
    assert order == ['c1']


def test_cycle_detection():
    """Test that cycles are detected and rejected."""
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads={'x'}, writes={'y'})

    # Creating a cycle: c1 reads y (which c2 writes)
    with pytest.raises(CycleDetectedError):
        graph.update_cell('c1', reads={'y'}, writes={'x'})


def test_variable_shadowing():
    """Test that variable redefinition works correctly."""
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads={'x'}, writes={'y'})

    # c3 also writes 'x', shadowing c1's definition
    graph.update_cell('c3', reads=set(), writes={'x'})

    # Now c2 should depend on c3 (latest writer of 'x')
    order = graph.get_execution_order('c3')
    assert 'c2' in order


def test_remove_cell():
    """Test that removing a cell updates the graph."""
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads={'x'}, writes={'y'})

    graph.remove_cell('c1')

    # c2 should now have no dependencies
    order = graph.get_execution_order('c2')
    assert order == ['c2']
