import json
import os
from pathlib import Path
from typing import Dict, List
from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState

NOTEBOOKS_DIR = Path("notebooks")

def ensure_notebooks_dir():
    NOTEBOOKS_DIR.mkdir(exist_ok=True)

def save_notebook(notebook: Notebook) -> None:
    ensure_notebooks_dir()

    data = {
        "id": notebook.id,
        "db_conn_string": notebook.db_conn_string,
        "revision": notebook.revision,
        "cells": [
            {
                "id": cell.id,
                "type": cell.type.value,
                "code": cell.code,
                "reads": list(cell.reads),
                "writes": list(cell.writes)
            }
            for cell in notebook.cells
        ]
    }

    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

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
            reads=set(cell_data.get("reads", [])),
            writes=set(cell_data.get("writes", []))
        )
        for cell_data in data["cells"]
    ]

    notebook = Notebook(
        id=data["id"],
        db_conn_string=data.get("db_conn_string"),
        cells=cells,
        revision=data.get("revision", 0)
    )

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook

def list_notebooks() -> List[str]:
    ensure_notebooks_dir()
    return [f.stem for f in NOTEBOOKS_DIR.glob("*.json")]
