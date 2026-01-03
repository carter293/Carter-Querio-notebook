from pydantic import BaseModel
from typing import Optional, List, Union, Literal
from app.models import CellType, CellStatus


class CreateCellRequest(BaseModel):
    type: CellType
    after_cell_id: Optional[str] = None


class UpdateCellRequest(BaseModel):
    code: str


class CreateCellResponse(BaseModel):
    cell_id: str


class TableData(BaseModel):
    """Table data structure for pandas DataFrames and SQL results"""
    type: Literal["table"]
    columns: List[str]
    rows: List[List[Union[str, int, float, bool, None]]]
    truncated: Optional[str] = None


class OutputResponse(BaseModel):
    mime_type: str
    data: Union[str, TableData, dict, list]
    metadata: Optional[dict[str, Union[str, int, float]]] = None


class CellResponse(BaseModel):
    id: str
    type: CellType
    code: str
    status: CellStatus
    stdout: Optional[str] = None
    outputs: List[OutputResponse]
    error: Optional[str] = None
    reads: List[str]
    writes: List[str]


class NotebookResponse(BaseModel):
    id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[CellResponse]

