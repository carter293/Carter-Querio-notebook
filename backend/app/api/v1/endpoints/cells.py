from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas import CreateCellRequest, UpdateCellRequest, CreateCellResponse
from app.services import locked_create_cell, locked_update_cell, locked_delete_cell
from app.websocket import broadcaster
from app.api.deps import get_current_user_dependency
from app.api.v1.state import NOTEBOOKS

router = APIRouter()


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
