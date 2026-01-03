from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class Graph:
    edges: Dict[str, Set[str]] = field(default_factory=dict)
    reverse_edges: Dict[str, Set[str]] = field(default_factory=dict)

    def add_edge(self, from_cell: str, to_cell: str):
        """Add dependency: from_cell writes vars that to_cell reads"""
        if from_cell not in self.edges:
            self.edges[from_cell] = set()
        self.edges[from_cell].add(to_cell)

        if to_cell not in self.reverse_edges:
            self.reverse_edges[to_cell] = set()
        self.reverse_edges[to_cell].add(from_cell)

    def remove_cell(self, cell_id: str):
        """Remove all edges involving this cell"""
        if cell_id in self.edges:
            for dependent in self.edges[cell_id]:
                self.reverse_edges[dependent].discard(cell_id)
            del self.edges[cell_id]

        if cell_id in self.reverse_edges:
            for dependency in self.reverse_edges[cell_id]:
                self.edges[dependency].discard(cell_id)
            del self.reverse_edges[cell_id]

