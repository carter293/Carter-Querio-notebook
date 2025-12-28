from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List, Union, Any
from enum import Enum

class CellType(str, Enum):
    PYTHON = "python"
    SQL = "sql"

class CellStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"

class MimeType(str, Enum):
    """Known MIME types for output rendering"""
    PNG = "image/png"
    HTML = "text/html"
    PLAIN = "text/plain"
    VEGA_LITE = "application/vnd.vegalite.v6+json"
    JSON = "application/json"
    PLOTLY_JSON = "application/vnd.plotly.v1+json"

@dataclass
class Output:
    """Single output with MIME type metadata"""
    mime_type: str  # Use MimeType enum values
    data: Union[str, dict, list]  # base64 string for images, dict for JSON/tables, HTML string
    metadata: Dict[str, Union[str, int, float]] = field(default_factory=dict)  # Optional: width, height, etc.

@dataclass
class Cell:
    id: str
    type: CellType
    code: str
    status: CellStatus = CellStatus.IDLE
    stdout: str = ""
    outputs: List[Output] = field(default_factory=list)  # NEW: Replaces result
    error: Optional[str] = None
    reads: Set[str] = field(default_factory=set)  # Variables read
    writes: Set[str] = field(default_factory=set)  # Variables written

@dataclass
class Graph:
    edges: Dict[str, Set[str]] = field(default_factory=dict)  # cell_id -> dependents
    reverse_edges: Dict[str, Set[str]] = field(default_factory=dict)  # cell_id -> dependencies

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
        # Remove outgoing edges
        if cell_id in self.edges:
            for dependent in self.edges[cell_id]:
                self.reverse_edges[dependent].discard(cell_id)
            del self.edges[cell_id]

        # Remove incoming edges
        if cell_id in self.reverse_edges:
            for dependency in self.reverse_edges[cell_id]:
                self.edges[dependency].discard(cell_id)
            del self.reverse_edges[cell_id]

@dataclass
class KernelState:
    globals_dict: Dict[str, object] = field(default_factory=lambda: {"__builtins__": __builtins__})

@dataclass
class Notebook:
    id: str
    user_id: str  # Clerk user ID (from JWT 'sub' claim)
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
