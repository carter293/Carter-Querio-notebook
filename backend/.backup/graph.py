from typing import List, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Notebook, Cell, Graph
else:
    # Avoid circular import at runtime
    Notebook = 'Notebook'
    Cell = 'Cell'
    Graph = 'Graph'

def rebuild_graph(notebook) -> None:
    """Rebuild dependency graph from scratch based on current cells"""
    from models import Graph
    notebook.graph = Graph()

    # Build mapping: variable -> cells that write it
    writes_map: dict[str, list[str]] = {}
    for cell in notebook.cells:
        for var in cell.writes:
            if var not in writes_map:
                writes_map[var] = []
            writes_map[var].append(cell.id)

    # Create edges: if cell B reads variable written by cell A, add A -> B
    for cell in notebook.cells:
        for var in cell.reads:
            if var in writes_map:
                for writer_cell_id in writes_map[var]:
                    if writer_cell_id != cell.id:  # No self-edges
                        notebook.graph.add_edge(writer_cell_id, cell.id)

def detect_cycle(graph, start_cell: str) -> Optional[List[str]]:
    """
    Detect if there's a cycle starting from start_cell.
    Returns cycle path if found, None otherwise.
    """
    visited = set()
    path = []

    def dfs(cell_id: str) -> bool:
        if cell_id in path:
            # Found cycle
            return True
        if cell_id in visited:
            return False

        visited.add(cell_id)
        path.append(cell_id)

        if cell_id in graph.edges:
            for dependent in graph.edges[cell_id]:
                if dfs(dependent):
                    return True

        path.pop()
        return False

    if dfs(start_cell):
        return path
    return None

def topological_sort(graph, cell_ids: Set[str]) -> List[str]:
    """
    Return topological ordering of given cells.
    Raises ValueError if cycle detected.
    """
    # Kahn's algorithm
    in_degree = {cid: 0 for cid in cell_ids}

    for cid in cell_ids:
        if cid in graph.reverse_edges:
            # Count dependencies within our subset
            in_degree[cid] = len(graph.reverse_edges[cid] & cell_ids)

    queue = [cid for cid in cell_ids if in_degree[cid] == 0]
    result = []

    while queue:
        current = queue.pop(0)
        result.append(current)

        if current in graph.edges:
            for dependent in graph.edges[current]:
                if dependent in cell_ids:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

    if len(result) != len(cell_ids):
        raise ValueError("Cycle detected in dependency graph")

    return result

def get_all_dependents(graph, cell_id: str) -> Set[str]:
    """Get transitive closure of all cells that depend on cell_id"""
    dependents = set()

    def dfs(cid: str):
        if cid in graph.edges:
            for dependent in graph.edges[cid]:
                if dependent not in dependents:
                    dependents.add(dependent)
                    dfs(dependent)

    dfs(cell_id)
    return dependents
