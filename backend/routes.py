from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List, Union, Literal
from urllib.parse import parse_qs
import httpx
from clerk_backend_api.security.types import AuthenticateRequestOptions
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph, detect_cycle
from websocket import broadcaster
from scheduler import scheduler
from storage import save_notebook, list_notebooks
from demo_notebook import create_demo_notebook
from graph import rebuild_graph
import uuid

# In-memory storage
NOTEBOOKS: Dict[str, Notebook] = {}

router = APIRouter()

# Dependency factory to get current user
# This will be set by main.py after app initialization
def get_current_user_dependency_factory():
    """Factory function that returns a dependency to get current user"""
    async def get_current_user_from_app_state(request: Request):
        """Get current user by calling the auth function from app state"""
        # Get the dependency function from app state and call it
        auth_func = request.app.state.get_current_user
        return await auth_func(request)
    
    return get_current_user_from_app_state

# Create the dependency function
get_current_user_dependency = get_current_user_dependency_factory()

class CreateNotebookRequest(BaseModel):
    pass

class CreateNotebookResponse(BaseModel):
    notebook_id: str

class UpdateDbConnectionRequest(BaseModel):
    connection_string: str

class CreateCellRequest(BaseModel):
    type: CellType

class UpdateCellRequest(BaseModel):
    code: str

class RenameNotebookRequest(BaseModel):
    name: str

# Response models
class TableData(BaseModel):
    """Table data structure for pandas DataFrames and SQL results"""
    type: Literal["table"]  # Required field - must be exactly "table"
    columns: List[str]
    rows: List[List[Union[str, int, float, bool, None]]]
    truncated: Optional[str] = None

class OutputResponse(BaseModel):
    mime_type: str
    data: Union[str, TableData, dict, list]
    metadata: Optional[Dict[str, Union[str, int, float]]] = None

class CellResponse(BaseModel):
    id: str
    type: CellType
    code: str
    status: CellStatus
    stdout: Optional[str] = None
    outputs: List[OutputResponse]  # Required - always provided
    error: Optional[str] = None
    reads: List[str]  # Required - always provided
    writes: List[str]  # Required - always provided

class NotebookMetadataResponse(BaseModel):
    id: str
    name: str

class ListNotebooksResponse(BaseModel):
    notebooks: List[NotebookMetadataResponse]

class NotebookResponse(BaseModel):
    id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[CellResponse]  # Required - always provided

class CreateCellResponse(BaseModel):
    cell_id: str

# Notebook endpoints

@router.post("/notebooks", response_model=CreateNotebookResponse)
async def create_notebook(
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Create a new notebook with one empty Python cell"""
    notebook_id = str(uuid.uuid4())

    # Create default cell
    default_cell = Cell(
        id=str(uuid.uuid4()),
        type=CellType.PYTHON,
        code="",
        status=CellStatus.IDLE
    )

    notebook = Notebook(
        id=notebook_id,
        user_id=user_id,  # Associate with authenticated user
        cells=[default_cell]
    )

    NOTEBOOKS[notebook_id] = notebook
    save_notebook(notebook)
    return CreateNotebookResponse(notebook_id=notebook_id)

@router.get("/notebooks", response_model=ListNotebooksResponse)
async def list_notebooks_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """List all notebooks for the current user"""
    # Ensure user has default notebooks (blank + demo) - create if missing
    user_notebooks_existing = [nb for nb in NOTEBOOKS.values() if nb.user_id == user_id]
    
    # Check if user has a blank notebook
    user_has_blank = any(nb.id.startswith("blank-") and nb.user_id == user_id for nb in NOTEBOOKS.values())
    if not user_has_blank:
        blank_id = f"blank-{user_id}"
        blank_notebook = Notebook(
            id=blank_id,
            user_id=user_id,
            name="Blank Notebook",
            cells=[Cell(
                id=str(uuid.uuid4()),
                type=CellType.PYTHON,
                code="",
                status=CellStatus.IDLE
            )]
        )
        NOTEBOOKS[blank_id] = blank_notebook
        save_notebook(blank_notebook)
    
    # Check if user has a demo notebook
    demo_id = f"demo-{user_id}"
    user_has_demo = any(nb.id == demo_id and nb.user_id == user_id for nb in NOTEBOOKS.values())
    if not user_has_demo:
        demo_notebook = create_demo_notebook(user_id)
        demo_notebook.id = demo_id  # Use user-specific demo ID
        NOTEBOOKS[demo_id] = demo_notebook
        save_notebook(demo_notebook)
    
    # Return all user notebooks
    user_notebooks = [
        NotebookMetadataResponse(id=nb.id, name=nb.name or nb.id)
        for nb in NOTEBOOKS.values()
        if nb.user_id == user_id  # Filter by user
    ]
    return ListNotebooksResponse(notebooks=user_notebooks)

@router.get("/notebooks/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Get a specific notebook"""
    # Handle legacy "demo" ID - redirect to user-specific demo
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    
    # Handle legacy "blank" ID - redirect to user-specific blank
    if notebook_id == "blank":
        notebook_id = f"blank-{user_id}"
    
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )
    
    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to access notebook '{notebook_id}'"
        )
    
    return NotebookResponse(
        id=notebook.id,
        name=notebook.name,
        db_conn_string=notebook.db_conn_string,
        cells=[
            CellResponse(
                id=cell.id,
                type=cell.type,
                code=cell.code,
                status=cell.status,
                stdout=cell.stdout,
                outputs=[
                    OutputResponse(
                        mime_type=output.mime_type,
                        data=output.data,
                        metadata=output.metadata
                    )
                    for output in cell.outputs
                ],
                error=cell.error,
                reads=list(cell.reads),
                writes=list(cell.writes)
            )
            for cell in notebook.cells
        ]
    )

@router.put("/notebooks/{notebook_id}/db")
async def update_db_connection(
    notebook_id: str,
    request_body: UpdateDbConnectionRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Update database connection string"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )

    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to modify notebook '{notebook_id}'"
        )
    
    notebook.db_conn_string = request_body.connection_string
    save_notebook(notebook)
    return {"status": "ok"}

@router.put("/notebooks/{notebook_id}/name")
async def rename_notebook(
    notebook_id: str,
    request_body: RenameNotebookRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Update notebook name"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )
    
    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to rename notebook '{notebook_id}'"
        )
    
    notebook.name = request_body.name.strip() if request_body.name.strip() else None
    save_notebook(notebook)
    return {"status": "ok", "name": notebook.name}

# Cell endpoints

@router.post("/notebooks/{notebook_id}/cells", response_model=CreateCellResponse)
async def create_cell(
    notebook_id: str,
    request_body: CreateCellRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Create a new cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )

    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to modify notebook '{notebook_id}'"
        )

    new_cell = Cell(
        id=str(uuid.uuid4()),
        type=request_body.type,
        code="",
        status=CellStatus.IDLE
    )

    notebook.cells.append(new_cell)
    save_notebook(notebook)
    
    await broadcaster.broadcast_cell_created(notebook_id, {
        "id": new_cell.id,
        "type": new_cell.type.value,
        "code": new_cell.code,
        "status": new_cell.status.value,
        "reads": [],
        "writes": []
    })
    
    return CreateCellResponse(cell_id=new_cell.id)

@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(
    notebook_id: str,
    cell_id: str,
    request_body: UpdateCellRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Update cell code"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )

    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to modify notebook '{notebook_id}'"
        )
    
    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    if not cell:
        raise HTTPException(
            status_code=404,
            detail=f"Cell '{cell_id}' not found in notebook '{notebook_id}'"
        )

    cell.code = request_body.code
    cell.status = CellStatus.IDLE

    if cell.type == CellType.PYTHON:
        reads, writes = extract_dependencies(cell.code)
        cell.reads = reads
        cell.writes = writes
    elif cell.type == CellType.SQL:
        reads = extract_sql_dependencies(cell.code)
        cell.reads = reads
        cell.writes = set()

    rebuild_graph(notebook)

    cycle = detect_cycle(notebook.graph, cell_id)
    if cycle:
        cell.status = CellStatus.ERROR
        cell.error = f"Circular dependency detected: {' -> '.join(cycle)}"

    notebook.revision += 1
    save_notebook(notebook)
    
    await broadcaster.broadcast_cell_updated(notebook_id, cell_id, {
        "code": cell.code,
        "reads": list(cell.reads),
        "writes": list(cell.writes),
        "status": cell.status.value
    })
    
    return {"status": "ok"}

@router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
async def delete_cell(
    notebook_id: str,
    cell_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Delete a cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{notebook_id}' not found. It may have been deleted or you don't have access to it."
        )

    notebook = NOTEBOOKS[notebook_id]
    
    # Check ownership
    if notebook.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: You don't have permission to modify notebook '{notebook_id}'"
        )

    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    notebook.cells = [c for c in notebook.cells if c.id != cell_id]
    notebook.graph.remove_cell(cell_id)

    if cell:
        for var in cell.writes:
            notebook.kernel.globals_dict.pop(var, None)

    notebook.revision += 1
    save_notebook(notebook)
    
    await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
    
    return {"status": "ok"}

# WebSocket endpoint

@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    """WebSocket endpoint for real-time notebook updates"""
    
    # Extract token from query parameters
    query_string = websocket.scope.get("query_string", b"").decode()
    query_params = parse_qs(query_string)
    token = query_params.get("token", [None])[0]
    
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
    
    # Verify token and extract user_id using Clerk
    try:
        # Get Clerk client from app state (WebSocket has app attribute)
        clerk = websocket.app.state.clerk
        
        # Create a synthetic httpx request for token verification
        # Build URL from WebSocket scope
        scheme = websocket.scope.get("scheme", "ws")
        # Headers are a list of (name, value) tuples
        headers_list = websocket.scope.get("headers", [])
        host = "localhost:8000"  # Default
        for name, value in headers_list:
            if name == b"host":
                host = value.decode() if isinstance(value, bytes) else value
                break
        path = websocket.scope.get("path", "")
        url = f"{scheme}://{host}{path}"
        
        auth_header = f"Bearer {token}"
        httpx_request = httpx.Request(
            method="GET",
            url=url,
            headers={"authorization": auth_header}
        )
        
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )
        
        if not request_state.is_signed_in:
            reason = request_state.reason or "Token verification failed"
            await websocket.close(code=1008, reason=f"Authentication failed: {reason}")
            return
        
        # Extract user_id from token
        payload = request_state.payload
        if not payload:
            await websocket.close(code=1008, reason="Invalid token: missing payload")
            return
        
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token: missing user ID")
            return
        
    except Exception as e:
        await websocket.close(code=1008, reason=f"Authentication error: {str(e)}")
        return
    
    # Accept connection after successful authentication
    await websocket.accept()
    
    # Handle legacy notebook IDs (demo -> demo-{user_id}, blank -> blank-{user_id})
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    elif notebook_id == "blank":
        notebook_id = f"blank-{user_id}"
    
    # Check if notebook exists
    # Note: Should always exist because notebooks are provisioned during list call
    if notebook_id not in NOTEBOOKS:
        await websocket.send_json({
            "type": "error",
            "message": "Notebook not found"
        })
        await websocket.close(code=1008, reason="Notebook not found")
        return
    
    # Verify notebook ownership
    notebook = NOTEBOOKS[notebook_id]
    if notebook.user_id != user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Access denied: You don't have permission to access this notebook"
        })
        await websocket.close(code=1008, reason="Access denied")
        return
    
    # Connection established and authenticated
    await broadcaster.connect(notebook_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()

            if message["type"] == "run_cell":
                cell_id = message["cellId"]
                
                # Re-verify notebook ownership before execution
                if notebook_id not in NOTEBOOKS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Notebook not found"
                    })
                    continue
                
                notebook = NOTEBOOKS[notebook_id]
                if notebook.user_id != user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Access denied"
                    })
                    continue

                await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)

    except WebSocketDisconnect:
        await broadcaster.disconnect(notebook_id, websocket)
