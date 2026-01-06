# Interface Layer - File-Based Notebooks Implementation Plan

## Overview

Implement the FastAPI Interface Layer for the reactive notebook backend with file-based notebook storage. Notebooks are stored as `.py` files with comment-based cell separators, providing version control friendliness and multi-notebook support.

## Current State Analysis

The frontend expects:
- REST API endpoints for CRUD operations (auto-generated OpenAPI client)
- WebSocket gateway for real-time execution updates
- Specific TypeScript types defined in `frontend/src/client/types.gen.ts`
- Discriminated union WebSocket messages for cell updates

Key frontend patterns:
- Server-authoritative state (no optimistic updates)
- Save-on-blur pattern for cell editing
- WebSocket authentication handshake required
- Streaming stdout via incremental messages

## System Context Analysis

This plan implements the **Interface Layer** from the fresh-start architecture, which sits above the Orchestration Layer. The Interface Layer is responsible for:

1. **HTTP REST API** - CRUD operations on notebooks and cells
2. **WebSocket Gateway** - Real-time execution updates and commands
3. **Request Validation** - Pydantic models matching frontend expectations
4. **File-Based Storage** - Parse and serialize `.py` files with cell separators

This addresses the **root requirement** of building a clean, file-based reactive notebook system. We're implementing the external interface that the frontend depends on, which will later delegate to the Orchestration Layer (reactive graph + execution engine).

## Desired End State

A working FastAPI backend that:
- Serves all REST endpoints the frontend expects (`/api/v1/notebooks`, `/api/v1/cells`)
- Handles WebSocket connections with authentication handshake
- Stores notebooks as `.py` files in a `notebooks/` directory
- Parses cell separators (`# %%`) to construct in-memory cell structures
- Serializes cell edits back to `.py` files
- Broadcasts execution updates via WebSocket (using stub execution initially)

### Verification
- Frontend can connect, create notebooks, edit cells, and receive updates
- Notebooks persist as readable `.py` files with proper cell markers
- OpenAPI spec generates TypeScript types matching `types.gen.ts`

## What We're NOT Doing

- Actual Python/SQL execution (stub responses for now - Orchestration Layer handles this later)
- Reactive dependency graph (Orchestration Layer responsibility)
- Database connections (placeholder in file metadata)
- LLM/chat integration (future enhancement)
- Authentication beyond basic handshake (simplified auth structure only)
- Concurrent editing conflict resolution (single-user assumption for now)

## Implementation Approach

**File Format:**
```python
# Notebook: my-analysis
# DB: postgresql://localhost/mydb

# %% python [cell-id-1]
import pandas as pd
df = pd.read_csv('data.csv')

# %% sql [cell-id-2]
SELECT * FROM users LIMIT 10

# %% python [cell-id-3]
print(df.head())
```

**Storage:**
- Directory: `backend/notebooks/`
- Filename: `{notebook_id}.py` (e.g., `abc-123.py`)
- Cell ID: UUID in square brackets after cell type
- Notebook metadata: Top-of-file comments

**Tech Stack:**
- FastAPI for REST + WebSocket
- Pydantic for validation
- File I/O for persistence
- In-memory state for active sessions

## Phase 1: Project Structure & Models

### Overview
Set up the backend project structure, Pydantic models, and file parsing/serialization utilities.

### Changes Required:

#### 1. Project Structure
**Directory**: `backend/`

Create:
```
backend/
├── main.py                    # FastAPI app entry point
├── pyproject.toml            # Poetry/uv dependencies
├── notebooks/                # Notebook storage (gitignored except .gitkeep)
│   └── .gitkeep
├── app/
│   ├── __init__.py
│   ├── models.py             # Pydantic models
│   ├── file_storage.py       # File parsing/serialization
│   ├── api/
│   │   ├── __init__.py
│   │   ├── notebooks.py      # Notebook CRUD endpoints
│   │   └── cells.py          # Cell CRUD endpoints
│   └── websocket/
│       ├── __init__.py
│       └── handler.py        # WebSocket connection handler
```

#### 2. Dependencies
**File**: `backend/pyproject.toml`

```toml
[project]
name = "notebook-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "python-multipart>=0.0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "httpx>=0.28.0",
    "pytest-asyncio>=0.24.0",
]
```

#### 3. Pydantic Models
**File**: `backend/app/models.py`

```python
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

class WSAuthenticateMessage(WSMessageBase):
    type: Literal["authenticate"] = "authenticate"
```

#### 4. File Storage Utilities
**File**: `backend/app/file_storage.py`

```python
import re
import uuid
from pathlib import Path
from typing import Optional
from .models import NotebookResponse, CellResponse, CellType

NOTEBOOKS_DIR = Path(__file__).parent.parent / "notebooks"
CELL_SEPARATOR_PATTERN = re.compile(r"^# %% (python|sql)(?: \[([^\]]+)\])?$")

class NotebookFileStorage:
    """Parse and serialize notebooks as .py files."""

    @staticmethod
    def parse_notebook(notebook_id: str) -> Optional[NotebookResponse]:
        """Parse a .py file into a NotebookResponse."""
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        if not file_path.exists():
            return None

        content = file_path.read_text()
        lines = content.splitlines()

        # Parse metadata from top comments
        name = None
        db_conn_string = None
        i = 0
        while i < len(lines) and lines[i].startswith("#"):
            if lines[i].startswith("# Notebook:"):
                name = lines[i].replace("# Notebook:", "").strip()
            elif lines[i].startswith("# DB:"):
                db_conn_string = lines[i].replace("# DB:", "").strip()
            i += 1

        # Parse cells
        cells = []
        current_cell: Optional[dict] = None

        for line in lines[i:]:
            match = CELL_SEPARATOR_PATTERN.match(line)
            if match:
                # Save previous cell
                if current_cell:
                    cells.append(CellResponse(**current_cell))

                # Start new cell
                cell_type = match.group(1)
                cell_id = match.group(2) or str(uuid.uuid4())
                current_cell = {
                    "id": cell_id,
                    "type": cell_type,
                    "code": "",
                    "status": "idle",
                }
            elif current_cell is not None:
                # Append to current cell code
                if current_cell["code"]:
                    current_cell["code"] += "\n"
                current_cell["code"] += line

        # Save last cell
        if current_cell:
            cells.append(CellResponse(**current_cell))

        return NotebookResponse(
            id=notebook_id,
            name=name or notebook_id,
            db_conn_string=db_conn_string,
            cells=cells,
        )

    @staticmethod
    def serialize_notebook(notebook: NotebookResponse) -> None:
        """Write a NotebookResponse to a .py file."""
        file_path = NOTEBOOKS_DIR / f"{notebook.id}.py"

        lines = []

        # Write metadata
        if notebook.name:
            lines.append(f"# Notebook: {notebook.name}")
        if notebook.db_conn_string:
            lines.append(f"# DB: {notebook.db_conn_string}")

        if lines:
            lines.append("")  # Blank line after metadata

        # Write cells
        for cell in notebook.cells:
            lines.append(f"# %% {cell.type} [{cell.id}]")
            lines.append(cell.code)
            lines.append("")  # Blank line between cells

        file_path.write_text("\n".join(lines))

    @staticmethod
    def list_notebooks() -> list[NotebookMetadataResponse]:
        """List all notebooks in the directory."""
        notebooks = []
        for file_path in NOTEBOOKS_DIR.glob("*.py"):
            notebook_id = file_path.stem
            notebook = NotebookFileStorage.parse_notebook(notebook_id)
            if notebook:
                notebooks.append(NotebookMetadataResponse(
                    id=notebook.id,
                    name=notebook.name or notebook.id,
                ))
        return notebooks

    @staticmethod
    def delete_notebook(notebook_id: str) -> bool:
        """Delete a notebook file."""
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        if file_path.exists():
            file_path.unlink()
            return True
        return False
```

### Success Criteria:

#### Automated Verification:
- [x] Dependencies install successfully: `cd backend && uv sync`
- [x] Python imports work: `python -c "from app.models import CellResponse; from app.file_storage import NotebookFileStorage"`
- [x] File parsing works: Create a test `.py` file and verify it parses correctly
- [ ] Type checking passes: `mypy backend/app/` (if using mypy)

#### Manual Verification:
- [x] Directory structure matches the plan
- [x] Models match TypeScript types in `frontend/src/client/types.gen.ts`
- [x] File parser correctly extracts cells with IDs and metadata

---

## Phase 2: REST API Endpoints

### Overview
Implement all REST endpoints the frontend expects for notebook and cell operations.

### Changes Required:

#### 1. Notebook Endpoints
**File**: `backend/app/api/notebooks.py`

```python
from fastapi import APIRouter, HTTPException
from uuid import uuid4
from ..models import (
    CreateNotebookResponse,
    ListNotebooksResponse,
    NotebookResponse,
    RenameNotebookRequest,
    UpdateDbConnectionRequest,
)
from ..file_storage import NotebookFileStorage

router = APIRouter(prefix="/api/v1/notebooks", tags=["notebooks"])

@router.post("/", response_model=CreateNotebookResponse)
async def create_notebook():
    """Create a new notebook."""
    notebook_id = str(uuid4())
    notebook = NotebookResponse(id=notebook_id, name=f"Untitled-{notebook_id[:8]}")
    NotebookFileStorage.serialize_notebook(notebook)
    return CreateNotebookResponse(notebook_id=notebook_id)

@router.get("/", response_model=ListNotebooksResponse)
async def list_notebooks():
    """List all notebooks."""
    notebooks = NotebookFileStorage.list_notebooks()
    return ListNotebooksResponse(notebooks=notebooks)

@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(notebook_id: str):
    """Get a specific notebook."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook

@router.put("/{notebook_id}/name")
async def rename_notebook(notebook_id: str, request: RenameNotebookRequest):
    """Rename a notebook."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook.name = request.name
    NotebookFileStorage.serialize_notebook(notebook)
    return {"status": "ok"}

@router.put("/{notebook_id}/db")
async def update_db_connection(notebook_id: str, request: UpdateDbConnectionRequest):
    """Update database connection string."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook.db_conn_string = request.connection_string
    NotebookFileStorage.serialize_notebook(notebook)
    return {"status": "ok"}

@router.delete("/{notebook_id}")
async def delete_notebook(notebook_id: str):
    """Delete a notebook."""
    if not NotebookFileStorage.delete_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"status": "ok"}
```

#### 2. Cell Endpoints
**File**: `backend/app/api/cells.py`

```python
from fastapi import APIRouter, HTTPException
from uuid import uuid4
from ..models import (
    CreateCellRequest,
    CreateCellResponse,
    UpdateCellRequest,
    CellResponse,
)
from ..file_storage import NotebookFileStorage

router = APIRouter(prefix="/api/v1/notebooks/{notebook_id}/cells", tags=["cells"])

@router.post("/", response_model=CreateCellResponse)
async def create_cell(notebook_id: str, request: CreateCellRequest):
    """Create a new cell in a notebook."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Create new cell
    cell_id = str(uuid4())
    new_cell = CellResponse(
        id=cell_id,
        type=request.type,
        code="",
        status="idle",
    )

    # Insert cell at the correct position
    if request.after_cell_id:
        # Find the index of the cell to insert after
        insert_index = None
        for i, cell in enumerate(notebook.cells):
            if cell.id == request.after_cell_id:
                insert_index = i + 1
                break

        if insert_index is None:
            raise HTTPException(status_code=404, detail="after_cell_id not found")

        notebook.cells.insert(insert_index, new_cell)
    else:
        # Append to end
        notebook.cells.append(new_cell)

    NotebookFileStorage.serialize_notebook(notebook)
    return CreateCellResponse(cell_id=cell_id)

@router.put("/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update a cell's code."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Find and update cell
    for cell in notebook.cells:
        if cell.id == cell_id:
            cell.code = request.code
            NotebookFileStorage.serialize_notebook(notebook)
            return {"status": "ok"}

    raise HTTPException(status_code=404, detail="Cell not found")

@router.delete("/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """Delete a cell."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Find and remove cell
    for i, cell in enumerate(notebook.cells):
        if cell.id == cell_id:
            notebook.cells.pop(i)
            NotebookFileStorage.serialize_notebook(notebook)
            return {"status": "ok"}

    raise HTTPException(status_code=404, detail="Cell not found")
```

#### 3. FastAPI Application
**File**: `backend/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from app.api import notebooks, cells

# Ensure notebooks directory exists
NOTEBOOKS_DIR = Path(__file__).parent / "notebooks"
NOTEBOOKS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Reactive Notebook API",
    version="0.1.0",
    description="File-based reactive notebook backend",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(notebooks.router)
app.include_router(cells.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### Success Criteria:

#### Automated Verification:
- [x] Server starts successfully: `cd backend && uvicorn main:app --reload`
- [x] OpenAPI docs accessible: `curl http://localhost:8000/docs`
- [x] Health check works: `curl http://localhost:8000/health`
- [x] Create notebook works: `curl -X POST http://localhost:8000/api/v1/notebooks/`
- [x] List notebooks works: `curl http://localhost:8000/api/v1/notebooks/`

#### Manual Verification:
- [x] All endpoints return correct status codes
- [x] Notebook files are created in `backend/notebooks/` directory
- [ ] OpenAPI schema matches frontend expectations (check `/openapi.json`)
- [ ] Frontend can generate types: `npm run generate:api` in `frontend/`

---

## Phase 3: WebSocket Gateway

### Overview
Implement WebSocket connection handling with authentication handshake and cell execution commands.

### Changes Required:

#### 1. WebSocket Handler
**File**: `backend/app/websocket/handler.py`

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import json
import asyncio
from ..models import CellResponse
from ..file_storage import NotebookFileStorage

class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

    async def send_message(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await websocket.send_json(message)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for websocket in self.active_connections.values():
            await websocket.send_json(message)

manager = ConnectionManager()

async def handle_websocket(websocket: WebSocket, connection_id: str):
    """Handle WebSocket connection lifecycle."""
    await manager.connect(websocket, connection_id)

    try:
        # Wait for authentication
        auth_message = await websocket.receive_json()
        if auth_message.get("type") != "authenticate":
            await websocket.close(code=1008, reason="Authentication required")
            return

        # Send authentication success
        await manager.send_message(connection_id, {"type": "authenticated"})

        # Message loop
        while True:
            message = await websocket.receive_json()
            await handle_message(connection_id, message)

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(connection_id)

async def handle_message(connection_id: str, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "run_cell":
        cell_id = message.get("cellId")
        if cell_id:
            await run_cell_stub(connection_id, cell_id)
    else:
        print(f"Unknown message type: {msg_type}")

async def run_cell_stub(connection_id: str, cell_id: str):
    """Stub implementation of cell execution."""
    # Send status: running
    await manager.send_message(connection_id, {
        "type": "cell_status",
        "cellId": cell_id,
        "status": "running",
    })

    # Simulate execution delay
    await asyncio.sleep(0.5)

    # Send stub stdout
    await manager.send_message(connection_id, {
        "type": "cell_stdout",
        "cellId": cell_id,
        "data": "Execution stub: Cell executed successfully\n",
    })

    # Send status: success
    await manager.send_message(connection_id, {
        "type": "cell_status",
        "cellId": cell_id,
        "status": "success",
    })
```

#### 2. WebSocket Endpoint
**File**: `backend/main.py` (additions)

```python
from fastapi import WebSocket
from uuid import uuid4
from app.websocket.handler import handle_websocket

# Add after router includes:

@app.websocket("/api/v1/ws/notebook")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time notebook updates."""
    connection_id = str(uuid4())
    await handle_websocket(websocket, connection_id)
```

### Success Criteria:

#### Automated Verification:
- [x] WebSocket endpoint exists: Check `/openapi.json` includes WebSocket route
- [x] Server handles WebSocket connections without crashing
- [ ] Can connect via `websocat`: `websocat ws://localhost:8000/api/v1/ws/notebook`

#### Manual Verification:
- [ ] Frontend connects successfully to WebSocket
- [ ] Authentication handshake completes (receives `authenticated` message)
- [ ] Running a cell sends `cell_status`, `cell_stdout`, and final status messages
- [ ] WebSocket reconnects after temporary disconnection
- [ ] No console errors in frontend during WebSocket communication

---

## Phase 4: Integration & Testing

### Overview
Connect the frontend to the new backend, test all flows, and verify file persistence.

### Changes Required:

#### 1. Frontend Configuration
**File**: `frontend/.env` or `frontend/.env.local`

```env
VITE_API_BASE_URL=http://localhost:8000
```

#### 2. Update Hardcoded Notebook ID
**File**: `frontend/src/components/NotebookApp.tsx`

**Change**: Replace hardcoded notebook ID with dynamic selection

Currently (line 23):
```typescript
const notebookId = "RESET AFTER UPDATING BACKEND AND RERUNNING HEY API";
```

Update to:
```typescript
const [notebookId, setNotebookId] = useState<string | null>(null);
const [notebooks, setNotebooks] = useState<NotebookMetadataResponse[]>([]);

useEffect(() => {
  // Load notebook list on mount
  apiClient.listNotebooks().then(response => {
    setNotebooks(response.notebooks);
    if (response.notebooks.length > 0) {
      setNotebookId(response.notebooks[0].id);
    }
  });
}, []);
```

#### 3. Regenerate TypeScript Types
**Command**: In `frontend/` directory

```bash
npm run generate:api
```

This will fetch the OpenAPI spec from `http://localhost:8000/openapi.json` and regenerate types.

#### 4. Test Script
**File**: `backend/test_integration.py`

```python
#!/usr/bin/env python3
"""Integration test for notebook API."""
import httpx
import asyncio
from pathlib import Path

BASE_URL = "http://localhost:8000"
NOTEBOOKS_DIR = Path(__file__).parent / "notebooks"

async def test_integration():
    async with httpx.AsyncClient() as client:
        # Create notebook
        print("Creating notebook...")
        resp = await client.post(f"{BASE_URL}/api/v1/notebooks/")
        assert resp.status_code == 200
        notebook_id = resp.json()["notebook_id"]
        print(f"✓ Created notebook: {notebook_id}")

        # Verify file exists
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        assert file_path.exists()
        print(f"✓ File created: {file_path}")

        # Create cell
        print("Creating cell...")
        resp = await client.post(
            f"{BASE_URL}/api/v1/notebooks/{notebook_id}/cells",
            json={"type": "python"}
        )
        assert resp.status_code == 200
        cell_id = resp.json()["cell_id"]
        print(f"✓ Created cell: {cell_id}")

        # Update cell
        print("Updating cell code...")
        resp = await client.put(
            f"{BASE_URL}/api/v1/notebooks/{notebook_id}/cells/{cell_id}",
            json={"code": "print('Hello, World!')"}
        )
        assert resp.status_code == 200
        print("✓ Cell updated")

        # Verify file content
        content = file_path.read_text()
        assert "print('Hello, World!')" in content
        assert f"# %% python [{cell_id}]" in content
        print("✓ File content correct")

        # Get notebook
        print("Fetching notebook...")
        resp = await client.get(f"{BASE_URL}/api/v1/notebooks/{notebook_id}")
        assert resp.status_code == 200
        notebook = resp.json()
        assert len(notebook["cells"]) == 1
        assert notebook["cells"][0]["code"] == "print('Hello, World!')"
        print("✓ Notebook fetched correctly")

        # Delete notebook
        print("Deleting notebook...")
        resp = await client.delete(f"{BASE_URL}/api/v1/notebooks/{notebook_id}")
        assert resp.status_code == 200
        assert not file_path.exists()
        print("✓ Notebook deleted")

        print("\n✅ All integration tests passed!")

if __name__ == "__main__":
    asyncio.run(test_integration())
```

### Success Criteria:

#### Automated Verification:
- [x] Integration test passes: `python backend/test_integration.py`
- [x] Frontend builds without errors: `cd frontend && npm run build`
- [x] TypeScript types are up-to-date: No type errors in VSCode

#### Manual Verification:
- [x] Can create a new notebook from frontend
- [x] Can add Python and SQL cells
- [x] Can edit cell code and it saves to `.py` file
- [x] Can run cells and see "running" → "success" status changes
- [x] Can view stub stdout output
- [x] Notebook persists after page refresh
- [x] Can open `.py` files in editor and see readable cell structure
- [x] Can manually edit `.py` file and changes reflect in frontend after reload

---

## Testing Strategy

### Unit Tests
- File parser: Test cell extraction with various comment formats
- File serializer: Test round-trip (parse → serialize → parse)
- Edge cases: Empty cells, cells with no ID, malformed separators

### Integration Tests
- Full CRUD flow: Create notebook → add cells → update → delete
- WebSocket flow: Connect → authenticate → run cell → receive updates
- File persistence: Verify `.py` files match expected format

### Manual Testing Steps
1. Start backend: `cd backend && uvicorn main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173` in browser
4. Create a new notebook
5. Add a Python cell with code: `print("test")`
6. Run the cell (Shift+Enter)
7. Verify status changes: idle → running → success
8. Verify stdout appears
9. Open `backend/notebooks/{notebook-id}.py` in editor
10. Verify file contains: `# %% python [cell-id]\nprint("test")`
11. Manually edit file to add a new cell
12. Refresh browser and verify new cell appears

## Performance Considerations

- **File I/O**: Currently synchronous - acceptable for small notebooks (<100 cells)
- **Future optimization**: Use async file I/O (`aiofiles`) for large notebooks
- **Caching**: Consider in-memory cache of parsed notebooks to avoid re-parsing on every request
- **Concurrency**: Current design assumes single-user editing - no conflict resolution for concurrent edits

## Migration Notes

**From old backend to new:**
- No migration needed - fresh start with file-based storage
- Old JSON notebook files can be converted via script if needed

**Future considerations:**
- When adding reactive graph (Orchestration Layer), cell dependencies (`reads`/`writes`) will be computed dynamically
- Execution engine will replace stub implementation in Phase 3

## References

- Architecture doc: `thoughts/shared/research/2026-01-06-fresh-start-architecture.md`
- Frontend types: `frontend/src/client/types.gen.ts`
- Frontend API client: `frontend/src/api-client.ts`
- Frontend WebSocket hook: `frontend/src/useNotebookWebSocket.ts`
- Cell separator format: VS Code-style `# %%` (common Python convention)
