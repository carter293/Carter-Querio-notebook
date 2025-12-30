import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Notebook, Cell, CellType, Graph
from graph import rebuild_graph, detect_cycle, topological_sort, get_all_dependents

def test_rebuild_graph_simple():
    nb = Notebook(id="test", user_id="test-user")

    cell_a = Cell(id="a", type=CellType.PYTHON, code="x = 1")
    cell_a.writes = {'x'}

    cell_b = Cell(id="b", type=CellType.PYTHON, code="y = x + 1")
    cell_b.reads = {'x'}
    cell_b.writes = {'y'}

    nb.cells = [cell_a, cell_b]
    rebuild_graph(nb)

    assert 'b' in nb.graph.edges['a']

def test_rebuild_graph_multiple_deps():
    nb = Notebook(id="test", user_id="test-user")

    cell_a = Cell(id="a", type=CellType.PYTHON, code="x = 1")
    cell_a.writes = {'x'}

    cell_b = Cell(id="b", type=CellType.PYTHON, code="y = 2")
    cell_b.writes = {'y'}

    cell_c = Cell(id="c", type=CellType.PYTHON, code="z = x + y")
    cell_c.reads = {'x', 'y'}
    cell_c.writes = {'z'}

    nb.cells = [cell_a, cell_b, cell_c]
    rebuild_graph(nb)

    assert 'c' in nb.graph.edges['a']
    assert 'c' in nb.graph.edges['b']

def test_detect_cycle_simple():
    nb = Notebook(id="test", user_id="test-user")

    cell_a = Cell(id="a", type=CellType.PYTHON, code="")
    cell_b = Cell(id="b", type=CellType.PYTHON, code="")

    nb.cells = [cell_a, cell_b]
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('b', 'a')

    cycle = detect_cycle(nb.graph, 'a')
    assert cycle is not None

def test_detect_cycle_none():
    nb = Notebook(id="test", user_id="test-user")

    cell_a = Cell(id="a", type=CellType.PYTHON, code="")
    cell_b = Cell(id="b", type=CellType.PYTHON, code="")

    nb.cells = [cell_a, cell_b]
    nb.graph.add_edge('a', 'b')

    cycle = detect_cycle(nb.graph, 'a')
    assert cycle is None

def test_topological_sort_linear():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('b', 'c')

    result = topological_sort(nb.graph, {'a', 'b', 'c'})

    # a must come before b, b before c
    assert result.index('a') < result.index('b')
    assert result.index('b') < result.index('c')

def test_topological_sort_diamond():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('a', 'c')
    nb.graph.add_edge('b', 'd')
    nb.graph.add_edge('c', 'd')

    result = topological_sort(nb.graph, {'a', 'b', 'c', 'd'})

    # a must come first, d must come last
    assert result[0] == 'a'
    assert result[-1] == 'd'
    # b and c can be in any order
    assert result.index('b') < result.index('d')
    assert result.index('c') < result.index('d')

def test_topological_sort_cycle():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('b', 'a')

    with pytest.raises(ValueError):
        topological_sort(nb.graph, {'a', 'b'})

def test_get_all_dependents_linear():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('b', 'c')

    deps = get_all_dependents(nb.graph, 'a')
    assert deps == {'b', 'c'}

def test_get_all_dependents_diamond():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')
    nb.graph.add_edge('b', 'c')
    nb.graph.add_edge('a', 'd')

    deps = get_all_dependents(nb.graph, 'a')
    assert deps == {'b', 'c', 'd'}

def test_get_all_dependents_none():
    nb = Notebook(id="test", user_id="test-user")
    nb.graph.add_edge('a', 'b')

    deps = get_all_dependents(nb.graph, 'b')
    assert deps == set()

def test_graph_remove_cell():
    graph = Graph()
    graph.add_edge('a', 'b')
    graph.add_edge('b', 'c')

    graph.remove_cell('b')

    assert 'b' not in graph.edges.get('a', set())
    assert 'b' not in graph.edges
    assert 'b' not in graph.reverse_edges
