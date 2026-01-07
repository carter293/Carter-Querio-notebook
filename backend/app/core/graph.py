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
        # We need to simulate adding edges to detect cycles that arise from the combination
        all_new_edges = new_parent_edges + new_child_edges
        temp_edges = []  # Track edges we've "virtually" added for cycle checking

        for from_cell, to_cell in all_new_edges:
            # Check if this edge would create a cycle considering previously checked edges
            if self._would_edge_create_cycle(from_cell, to_cell):
                raise CycleDetectedError(
                    f"Circular dependency detected: adding edge {from_cell}→{to_cell} "
                    f"would create a cycle (path exists {to_cell}→{from_cell})"
                )

            # Temporarily add this edge to the graph so subsequent checks see it
            if not self._graph.has_node(from_cell):
                self._graph.add_node(from_cell)
            if not self._graph.has_node(to_cell):
                self._graph.add_node(to_cell)
            self._graph.add_edge(from_cell, to_cell)
            temp_edges.append((from_cell, to_cell))

        # If we get here, all edges are safe. Remove the temporary edges we added
        for from_cell, to_cell in temp_edges:
            if self._graph.has_edge(from_cell, to_cell):
                self._graph.remove_edge(from_cell, to_cell)

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

    def get_execution_order_with_ancestors(self, cell_id: str) -> List[str]:
        """
        Get the list of cells to execute when a cell is run (including stale ancestors).

        Includes all ancestor cells (dependencies) + the cell itself + all descendants,
        in topological order. This ensures that if a cell depends on variables from
        parent cells, those parents are executed first.

        This is used for manual cell execution (e.g., user clicks "Run" on a cell that
        hasn't been run yet). The ancestors must run first to define variables this cell needs.

        Args:
            cell_id: The cell to execute

        Returns:
            List of cell IDs in the order they should be executed
        """
        if not self._graph.has_node(cell_id):
            return [cell_id]

        # Get ancestors (cells this cell depends on) + self + descendants (cells that depend on this)
        affected = {cell_id}
        try:
            affected |= nx.ancestors(self._graph, cell_id)  # Add parents
            affected |= nx.descendants(self._graph, cell_id)  # Add children
        except nx.NetworkXError:
            pass

        # Create subgraph and sort topologically
        # This ensures parents run before children
        subgraph = self._graph.subgraph(affected)
        try:
            return list(nx.topological_sort(subgraph))
        except nx.NetworkXError:
            return [cell_id]

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
