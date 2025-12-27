from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph, detect_cycle
from websocket import broadcaster
from scheduler import scheduler
from storage import save_notebook
import uuid

# In-memory storage
NOTEBOOKS: Dict[str, Notebook] = {}

router = APIRouter()

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

# Notebook endpoints

@router.post("/notebooks", response_model=CreateNotebookResponse)
async def create_notebook():
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
        cells=[default_cell]
    )

    NOTEBOOKS[notebook_id] = notebook
    save_notebook(notebook)
    return CreateNotebookResponse(notebook_id=notebook_id)

@router.get("/notebooks/{notebook_id}")
async def get_notebook(notebook_id: str):
    """Get notebook details"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]
    return {
        "id": notebook.id,
        "db_conn_string": notebook.db_conn_string,
        "cells": [
            {
                "id": cell.id,
                "type": cell.type,
                "code": cell.code,
                "status": cell.status,
                "stdout": cell.stdout,
                "outputs": [
                    {
                        "mime_type": output.mime_type,
                        "data": output.data,
                        "metadata": output.metadata
                    }
                    for output in cell.outputs
                ],
                "error": cell.error,
                "reads": list(cell.reads),
                "writes": list(cell.writes)
            }
            for cell in notebook.cells
        ]
    }

@router.put("/notebooks/{notebook_id}/db")
async def update_db_connection(notebook_id: str, request: UpdateDbConnectionRequest):
    """Update database connection string"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]
    notebook.db_conn_string = request.connection_string
    save_notebook(notebook)
    return {"status": "ok"}

# Cell endpoints

@router.post("/notebooks/{notebook_id}/cells")
async def create_cell(notebook_id: str, request: CreateCellRequest):
    """Create a new cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]

    new_cell = Cell(
        id=str(uuid.uuid4()),
        type=request.type,
        code="",
        status=CellStatus.IDLE
    )

    # Insert after specified cell or at end
    if request.after_cell_id:
        insert_idx = next(
            (i + 1 for i, c in enumerate(notebook.cells) if c.id == request.after_cell_id),
            len(notebook.cells)
        )
        notebook.cells.insert(insert_idx, new_cell)
    else:
        notebook.cells.append(new_cell)

    save_notebook(notebook)
    return {"cell_id": new_cell.id}

@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(notebook_id: str, cell_id: str, request: UpdateCellRequest):
    """Update cell code"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]
    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    if not cell:
        raise HTTPException(status_code=404, detail="Cell not found")

    # Update code
    cell.code = request.code
    cell.status = CellStatus.IDLE

    # Re-extract dependencies
    if cell.type == CellType.PYTHON:
        reads, writes = extract_dependencies(cell.code)
        cell.reads = reads
        cell.writes = writes
    elif cell.type == CellType.SQL:
        # SQL cells read variables from templates, write nothing
        reads = extract_sql_dependencies(cell.code)
        cell.reads = reads
        cell.writes = set()

    # Rebuild graph
    rebuild_graph(notebook)

    # Check for cycles
    cycle = detect_cycle(notebook.graph, cell_id)
    if cycle:
        cell.status = CellStatus.ERROR
        cell.error = f"Circular dependency detected: {' -> '.join(cycle)}"

    notebook.revision += 1
    save_notebook(notebook)
    return {"status": "ok"}

@router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
async def delete_cell(notebook_id: str, cell_id: str):
    """Delete a cell"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")

    notebook = NOTEBOOKS[notebook_id]

    # Find cell to get its writes
    cell = next((c for c in notebook.cells if c.id == cell_id), None)

    # Remove cell from list
    notebook.cells = [c for c in notebook.cells if c.id != cell_id]

    # Remove from graph
    notebook.graph.remove_cell(cell_id)

    # Remove variables from kernel
    if cell:
        for var in cell.writes:
            notebook.kernel.globals_dict.pop(var, None)

    notebook.revision += 1
    save_notebook(notebook)
    return {"status": "ok"}

# WebSocket endpoint

@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    """WebSocket endpoint for real-time notebook updates"""
    await websocket.accept()
    await broadcaster.connect(notebook_id, websocket)

    try:
        while True:
            # Receive messages from client
            message = await websocket.receive_json()

            if message["type"] == "run_cell":
                cell_id = message["cellId"]

                if notebook_id not in NOTEBOOKS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Notebook not found"
                    })
                    continue

                notebook = NOTEBOOKS[notebook_id]

                # Enqueue execution
                await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)

    except WebSocketDisconnect:
        await broadcaster.disconnect(notebook_id, websocket)
