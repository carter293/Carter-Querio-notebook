from dataclasses import dataclass, field
from typing import Optional, Set, List, Union, Dict
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
    mime_type: str
    data: Union[str, dict, list]
    metadata: Dict[str, Union[str, int, float]] = field(default_factory=dict)


@dataclass
class Cell:
    id: str
    type: CellType
    code: str
    status: CellStatus = CellStatus.IDLE
    stdout: str = ""
    outputs: List[Output] = field(default_factory=list)
    error: Optional[str] = None
    reads: Set[str] = field(default_factory=set)
    writes: Set[str] = field(default_factory=set)

