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
