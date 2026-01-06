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
async def list_notebooks_endpoint():
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
async def delete_notebook_endpoint(notebook_id: str):
    """Delete a notebook."""
    if not NotebookFileStorage.delete_notebook(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"status": "ok"}
