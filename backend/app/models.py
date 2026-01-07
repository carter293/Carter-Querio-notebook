from typing import Literal, Optional
from pydantic import BaseModel, Field

# Cell Types
CellType = Literal["python", "sql"]
CellStatus = Literal["idle", "running", "success", "error", "blocked"]

# Output Models
class TableData(BaseModel):
    type: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[str | int | float | bool | None]]
    truncated: Optional[str] = None

class OutputResponse(BaseModel):
    mime_type: str
    data: str | TableData | dict | list
    metadata: Optional[dict[str, str | int]] = None

# Cell Models
class CellResponse(BaseModel):
    id: str
    type: CellType
    code: str
    status: CellStatus = "idle"
    stdout: Optional[str] = None
    outputs: list[OutputResponse] = Field(default_factory=list)
    error: Optional[str] = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)

class CreateCellRequest(BaseModel):
    type: CellType
    after_cell_id: Optional[str] = None

class CreateCellResponse(BaseModel):
    cell_id: str

class UpdateCellRequest(BaseModel):
    code: str

# Notebook Models
class NotebookMetadataResponse(BaseModel):
    id: str
    name: str

class NotebookResponse(BaseModel):
    id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: list[CellResponse] = Field(default_factory=list)

class CreateNotebookResponse(BaseModel):
    notebook_id: str

class ListNotebooksResponse(BaseModel):
    notebooks: list[NotebookMetadataResponse]

class RenameNotebookRequest(BaseModel):
    name: str

class UpdateDbConnectionRequest(BaseModel):
    connection_string: str

# WebSocket Messages
class WSMessageBase(BaseModel):
    type: str

class WSRunCellMessage(WSMessageBase):
    type: Literal["run_cell"] = "run_cell"
    cellId: str
