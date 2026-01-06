"""Dependency graph for reactive cell execution."""
import networkx as nx
from typing import Set, List, Optional


class CycleDetectedError(Exception):
    """Raised when a circular dependency is detected."""
    pass


class DependencyGraph:
    """
    Manages variable dependencies between cells using a directed acyclic graph (DAG).

    Each node represents a cell. Edges represent dependencies:
    - Edge from A to B means "B depends on A" (B reads variables that A writes)
    """

    def __init__(self):
        self._graph = nx.DiGraph()
        self._cell_writes: dict[str, Set[str]] = {}  # cell_id → variables written
        self._cell_reads: dict[str, Set[str]] = {}   # cell_id → variables read
        self._var_writers: dict[str, str] = {}       # variable → cell_id that writes it

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
            old_writer = self._var_writers.get(var)
            if old_writer and old_writer != cell_id:
                # Variable shadowing: newer definition wins
                # (In practice, this means the cell later in the notebook overwrites the variable)
                pass
            self._var_writers[var] = cell_id

        # Add node
        self._graph.add_node(cell_id)

        # Add edges: if cell reads X, and some other cell writes X, draw edge from writer to this cell
        for var in reads:
            writer = self._var_writers.get(var)
            if writer and writer != cell_id:
                self._graph.add_edge(writer, cell_id)

        # Also check if any OTHER cells read variables that THIS cell writes
        # Those cells depend on this one
        for other_cell in list(self._graph.nodes()):
            if other_cell == cell_id:
                continue
            other_reads = self._cell_reads.get(other_cell, set())
            for var in writes:
                if var in other_reads:
                    self._graph.add_edge(cell_id, other_cell)

        # Check for cycles
        if not nx.is_directed_acyclic_graph(self._graph):
            # Revert changes (remove the node we just added)
            self._graph.remove_node(cell_id)
            raise CycleDetectedError(
                f"Circular dependency detected involving cell {cell_id}"
            )

    def remove_cell(self, cell_id: str) -> None:
        """Remove a cell from the graph."""
        if self._graph.has_node(cell_id):
            self._graph.remove_node(cell_id)

        # Clean up variable mappings
        if cell_id in self._cell_writes:
            old_writes = self._cell_writes[cell_id]
            for var in old_writes:
                if self._var_writers.get(var) == cell_id:
                    del self._var_writers[var]
            del self._cell_writes[cell_id]

        if cell_id in self._cell_reads:
            del self._cell_reads[cell_id]

    def get_execution_order(self, changed_cell_id: str) -> List[str]:
        """
        Get the list of cells to execute when a cell changes.

        Includes the changed cell itself + all descendant cells, in topological order.

        Args:
            changed_cell_id: The cell that was modified

        Returns:
            List of cell IDs in the order they should be executed
        """
        if not self._graph.has_node(changed_cell_id):
            return [changed_cell_id]

        # Get all cells affected by this change (the cell itself + descendants)
        affected = {changed_cell_id}
        try:
            affected |= nx.descendants(self._graph, changed_cell_id)
        except nx.NetworkXError:
            # Node doesn't exist or graph issue
            pass

        # Create subgraph and sort topologically
        subgraph = self._graph.subgraph(affected)
        try:
            return list(nx.topological_sort(subgraph))
        except nx.NetworkXError:
            # Should not happen if DAG is valid, but return changed cell only as fallback
            return [changed_cell_id]

    def _get_cell_reads(self, cell_id: str) -> Set[str]:
        """Get the set of variables a cell reads."""
        return self._cell_reads.get(cell_id, set())

    def get_cell_dependencies(self, cell_id: str) -> dict[str, Set[str]]:
        """
        Get dependency information for a cell.

        Returns:
            Dictionary with 'reads' and 'writes' sets
        """
        return {
            'reads': self._get_cell_reads(cell_id),
            'writes': self._cell_writes.get(cell_id, set())
        }
