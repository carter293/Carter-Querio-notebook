from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, List, Union, Literal
from urllib.parse import parse_qs
import jwt
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph, detect_cycle
from websocket import broadcaster
from scheduler import scheduler
from storage import save_notebook, list_notebooks, delete_notebook
from demo_notebook import create_demo_notebook
from graph import rebuild_graph
from notebook_operations import (
    locked_update_cell,
    locked_create_cell,
    locked_delete_cell
)
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

# ============================================================================
# WebSocket Authentication Helpers
# ============================================================================

async def verify_clerk_token(token: str, jwks_client) -> Optional[str]:
    """
    Verify Clerk JWT token and extract user_id.
    
    Args:
        token: JWT token string (without "Bearer " prefix)
        jwks_client: PyJWKClient instance for JWT verification
        
    Returns:
        user_id if token is valid, None otherwise
    """
    try:
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify JWT token
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
                "verify_iss": False,
                "verify_iat": True,
            },
            leeway=0,
        )
        
        # Extract user_id from 'sub' claim
        return decoded_token.get("sub")
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return None

class CreateNotebookRequest(BaseModel):
    pass

class CreateNotebookResponse(BaseModel):
    notebook_id: str

class UpdateDbConnectionRequest(BaseModel):
    connection_string: str

class CreateCellRequest(BaseModel):
    type: CellType
    after_cell_id: Optional[str] = None 

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

@router.delete("/notebooks/{notebook_id}")
async def delete_notebook_endpoint(
    notebook_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """Delete a notebook"""
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
            detail=f"Access denied: You don't have permission to delete notebook '{notebook_id}'"
        )
    
    # Remove from memory
    del NOTEBOOKS[notebook_id]
    
    # Remove from disk
    delete_notebook(notebook_id)
    
    return {"status": "ok"}

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

    try:
        # Determine insertion index
        index = None
        if request_body.after_cell_id:
            # Find the index of the cell we want to insert after
            for i, cell in enumerate(notebook.cells):
                if cell.id == request_body.after_cell_id:
                    index = i + 1  # Insert after this cell
                    break
            if index is None:
                raise HTTPException(status_code=404, detail=f"Cell '{request_body.after_cell_id}' not found")
        
        # Use locked operation
        new_cell = await locked_create_cell(
            notebook,
            request_body.type,
            "",  # Empty code for new cell
            index  # Insert at specified index, or None to append to end
        )
        
        # Find the actual index where the cell was inserted
        cell_index = next(i for i, cell in enumerate(notebook.cells) if cell.id == new_cell.id)
        
        await broadcaster.broadcast_cell_created(notebook_id, {
            "id": new_cell.id,
            "type": new_cell.type.value,
            "code": new_cell.code,
            "status": new_cell.status.value,
            "reads": list(new_cell.reads),
            "writes": list(new_cell.writes)
        }, cell_index)
        
        return CreateCellResponse(cell_id=new_cell.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    
    try:
        # Use locked operation (no direct mutation!)
        # Check for expected_revision in request body if provided
        expected_revision = getattr(request_body, 'expected_revision', None)
        cell = await locked_update_cell(
            notebook,
            cell_id,
            request_body.code,
            expected_revision=expected_revision
        )
        
        await broadcaster.broadcast_cell_updated(notebook_id, cell_id, {
            "code": cell.code,
            "reads": list(cell.reads),
            "writes": list(cell.writes),
            "status": cell.status.value,
            "error": cell.error
        })
        
        return {"status": "ok", "revision": notebook.revision}
    except ValueError as e:
        if "Revision conflict" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

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

    try:
        await locked_delete_cell(notebook, cell_id)
        
        await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
        
        return {"status": "ok", "revision": notebook.revision}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# WebSocket endpoint

@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    """
    WebSocket endpoint for real-time notebook updates.
    
    Authentication Flow:
    1. Accept connection
    2. Wait for authentication message: {"type": "authenticate", "token": "..."}
    3. Verify token and extract user_id
    4. Send confirmation: {"type": "authenticated"}
    5. Proceed with normal message handling
    """
    
    # Accept connection immediately (auth happens in-band)
    await websocket.accept()
    
    # Step 1: Wait for authentication message
    try:
        # Set timeout for auth message (10 seconds)
        import asyncio
        auth_message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "error",
            "message": "Authentication timeout"
        })
        await websocket.close(code=1008, reason="Authentication timeout")
        return
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to receive authentication: {str(e)}"
        })
        await websocket.close(code=1008, reason="Invalid message format")
        return
    
    # Step 2: Validate authentication message format
    if not isinstance(auth_message, dict) or auth_message.get("type") != "authenticate":
        await websocket.send_json({
            "type": "error",
            "message": "Expected authentication message"
        })
        await websocket.close(code=1008, reason="Expected authentication message")
        return
    
    token = auth_message.get("token")
    if not token:
        await websocket.send_json({
            "type": "error",
            "message": "Missing authentication token"
        })
        await websocket.close(code=1008, reason="Missing token")
        return
    
    # Step 3: Verify token using JWT
    jwks_client = websocket.app.state.jwks_client
    user_id = await verify_clerk_token(token, jwks_client)
    
    if not user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid authentication token"
        })
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Step 4: Send authentication confirmation
    await websocket.send_json({
        "type": "authenticated",
        "user_id": user_id
    })
    
    # Handle legacy notebook IDs
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    elif notebook_id == "blank":
        notebook_id = f"blank-{user_id}"
    
    # Check if notebook exists
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
            
            elif message["type"] == "refresh_auth":
                # Support mid-connection token refresh
                new_token = message.get("token")
                if not new_token:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing token in refresh request"
                    })
                    continue
                
                new_user_id = await verify_clerk_token(new_token, jwks_client)
                
                if not new_user_id or new_user_id != user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Token refresh failed: user mismatch"
                    })
                    # Don't close connection - keep using old auth
                    continue
                
                await websocket.send_json({
                    "type": "auth_refreshed"
                })

    except WebSocketDisconnect:
        await broadcaster.disconnect(notebook_id, websocket)
