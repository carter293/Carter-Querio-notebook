"""Type definitions for kernel IPC."""
import time
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum

CellType = Literal["python", "sql"]
CellStatus = Literal["idle", "running", "success", "error", "blocked"]


class CellChannel(str, Enum):
    """Channel discriminator for different output types."""
    OUTPUT = "output"           # Cell's final output (rich display)
    STDOUT = "stdout"           # Print statements
    STDERR = "stderr"           # Error output
    STATUS = "status"           # Cell status changes (idle/running/success/error/blocked)
    ERROR = "error"             # Error details (tracebacks, cycle errors)
    METADATA = "metadata"       # Dependency metadata (reads/writes)


class CellOutput(BaseModel):
    """Output payload - discriminated by channel."""
    channel: CellChannel
    mimetype: str
    data: str | dict | list
    timestamp: float = Field(default_factory=lambda: time.time())


class CellNotification(BaseModel):
    """
    Unified message type for ALL kernel outputs.
    Follows observable pattern - kernel emits notifications, frontend reacts.
    """
    type: Literal["cell_notification"] = "cell_notification"
    cell_id: str
    output: CellOutput


class Output(BaseModel):
    """Rich output from code execution."""
    mime_type: str
    data: str | dict | list
    metadata: dict[str, Any] | None = None


class RegisterCellRequest(BaseModel):
    """Request to register a cell in the dependency graph without executing."""
    type: Literal["register_cell"] = "register_cell"
    cell_id: str
    code: str
    cell_type: CellType


class RegisterCellResult(BaseModel):
    """Result of cell registration."""
    type: Literal["register_result"] = "register_result"
    cell_id: str
    status: Literal["success", "error"]
    error: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    """Request to execute a cell."""
    cell_id: str
    code: str
    cell_type: CellType


class ExecutionResult(BaseModel):
    """Result of cell execution."""
    cell_id: str
    status: CellStatus
    stdout: str = ""
    outputs: list[Output] = Field(default_factory=list)
    error: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class ShutdownRequest(BaseModel):
    """Request to shut down the kernel."""
    type: Literal["shutdown"] = "shutdown"


class SetDatabaseConfigRequest(BaseModel):
    """Request to configure database connection in kernel."""
    type: Literal["set_database_config"] = "set_database_config"
    connection_string: str


class SetDatabaseConfigResult(BaseModel):
    """Result of database configuration."""
    type: Literal["config_result"] = "config_result"
    status: Literal["success", "error"]
    error: str | None = None
