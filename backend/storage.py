import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List
from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState, Output

NOTEBOOKS_DIR = Path("notebooks")

def ensure_notebooks_dir():
    NOTEBOOKS_DIR.mkdir(exist_ok=True)

def save_notebook(notebook: Notebook) -> None:
    ensure_notebooks_dir()

    data = {
        "id": notebook.id,
        "user_id": notebook.user_id,
        "name": notebook.name,
        "db_conn_string": notebook.db_conn_string,
        "revision": notebook.revision,
        "cells": [
            {
                "id": cell.id,
                "type": cell.type.value,
                "code": cell.code,
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

    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"
    
    # Write to temporary file first (atomic write)
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=NOTEBOOKS_DIR,
        delete=False,
        suffix='.tmp',
        prefix=f'{notebook.id}_'
    ) as f:
        json.dump(data, f, indent=2)
        temp_path = f.name
    
    # Atomic rename (POSIX guarantees atomicity)
    os.replace(temp_path, file_path)

def load_notebook(notebook_id: str) -> Notebook:
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"

    with open(file_path, 'r') as f:
        data = json.load(f)

    cells = [
        Cell(
            id=cell_data["id"],
            type=CellType(cell_data["type"]),
            code=cell_data["code"],
            status=CellStatus.IDLE,
            stdout=cell_data.get("stdout", ""),
            outputs=[
                Output(
                    mime_type=output_data["mime_type"],
                    data=output_data["data"],
                    metadata=output_data.get("metadata", {})
                )
                for output_data in cell_data.get("outputs", [])
            ],
            error=cell_data.get("error"),
            reads=set(cell_data.get("reads", [])),
            writes=set(cell_data.get("writes", []))
        )
        for cell_data in data["cells"]
    ]

    # Extract user_id with backward compatibility
    user_id = data.get("user_id")
    if not user_id:
        # Try to extract from notebook ID pattern: {name}-user_{user_id}
        if "-user_" in notebook_id:
            user_id = notebook_id.split("-user_", 1)[1]
        else:
            # Fallback for legacy notebooks without user_id
            # Use a default system user_id for backward compatibility
            user_id = "system"

    notebook = Notebook(
        id=data["id"],
        user_id=user_id,
        name=data.get("name"), 
        db_conn_string=data.get("db_conn_string"),
        cells=cells,
        revision=data.get("revision", 0)
    )
    # Lock is automatically initialized via default_factory in Notebook dataclass

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook

def list_notebooks() -> List[str]:
    """List all notebooks, excluding test notebooks in subdirectories."""
    ensure_notebooks_dir()
    # Only list JSON files in the root notebooks directory, not in subdirectories
    return [f.stem for f in NOTEBOOKS_DIR.glob("*.json") if f.parent == NOTEBOOKS_DIR]

def delete_notebook(notebook_id: str) -> None:
    """Delete a notebook file from disk."""
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"
    if file_path.exists():
        file_path.unlink()
