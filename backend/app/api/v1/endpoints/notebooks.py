from fastapi import APIRouter, HTTPException, Depends, Request
from app.models import Notebook, Cell, CellType, CellStatus
from app.schemas import (
    CreateNotebookRequest, CreateNotebookResponse,
    UpdateDbConnectionRequest, RenameNotebookRequest,
    NotebookMetadataResponse, ListNotebooksResponse,
    NotebookResponse, CellResponse, OutputResponse
)
from app.storage import save_notebook, delete_notebook
from app.utils import create_demo_notebook
from app.api.deps import get_current_user_dependency
from app.api.v1.state import NOTEBOOKS
import uuid

router = APIRouter()


@router.post("/", response_model=CreateNotebookResponse)
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
        user_id=user_id,
        cells=[default_cell]
    )

    NOTEBOOKS[notebook_id] = notebook
    await save_notebook(notebook)
    return CreateNotebookResponse(notebook_id=notebook_id)


@router.get("/", response_model=ListNotebooksResponse)
async def list_notebooks_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    """List all notebooks for the current user"""
    # Ensure user has default notebooks (blank + demo) - create if missing
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
        await save_notebook(blank_notebook)
    
    # Check if user has a demo notebook
    demo_id = f"demo-{user_id}"
    user_has_demo = any(nb.id == demo_id and nb.user_id == user_id for nb in NOTEBOOKS.values())
    if not user_has_demo:
        demo_notebook = create_demo_notebook(user_id)
        demo_notebook.id = demo_id
        NOTEBOOKS[demo_id] = demo_notebook
        await save_notebook(demo_notebook)
    
    # Return all user notebooks
    user_notebooks = [
        NotebookMetadataResponse(id=nb.id, name=nb.name or nb.id)
        for nb in NOTEBOOKS.values()
        if nb.user_id == user_id
    ]
    return ListNotebooksResponse(notebooks=user_notebooks)


@router.get("/{notebook_id}", response_model=NotebookResponse)
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


@router.put("/{notebook_id}/db")
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
    await save_notebook(notebook)
    return {"status": "ok"}


@router.put("/{notebook_id}/name")
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
    await save_notebook(notebook)
    return {"status": "ok", "name": notebook.name}


@router.delete("/{notebook_id}")
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
    
    # Remove from memory and storage
    del NOTEBOOKS[notebook_id]
    await delete_notebook(notebook_id, user_id)
    
    return {"status": "ok", "message": f"Notebook '{notebook_id}' deleted successfully"}
