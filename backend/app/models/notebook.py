from dataclasses import dataclass, field
from asyncio import Lock
from typing import Optional, List, Dict
from .cell import Cell
from .graph import Graph


@dataclass
class KernelState:
    globals_dict: Dict[str, object] = field(default_factory=lambda: {"__builtins__": __builtins__})


@dataclass
class Notebook:
    id: str
    user_id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

