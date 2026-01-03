import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState, Output

NOTEBOOKS_DIR = Path("notebooks")

# Flag to disable auto-save during tests
DISABLE_AUTO_SAVE = os.environ.get("DISABLE_AUTO_SAVE", "false").lower() == "true"

# Check if DynamoDB is enabled
DYNAMODB_ENABLED = bool(os.getenv('DYNAMODB_TABLE_NAME'))

def ensure_notebooks_dir(subdirectory: str = None):
    """Ensure the notebooks directory exists.
    
    Args:
        subdirectory: Optional subdirectory within NOTEBOOKS_DIR (e.g., 'test')
    """
    if subdirectory:
        target_dir = NOTEBOOKS_DIR / subdirectory
    else:
        target_dir = NOTEBOOKS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

async def save_notebook(notebook: Notebook, subdirectory: str = None) -> None:
    """Save a notebook to storage (DynamoDB or file).
    
    Args:
        notebook: The notebook to save
        subdirectory: Optional subdirectory within NOTEBOOKS_DIR (e.g., 'test')
    """
    # Skip saving if auto-save is disabled (e.g., during tests)
    if DISABLE_AUTO_SAVE:
        return
    
    if DYNAMODB_ENABLED and not subdirectory:
        # Use DynamoDB for production storage
        from storage_dynamodb import get_dynamodb_storage
        storage = get_dynamodb_storage()
        await storage.save_notebook(notebook)
    else:
        # Use file-based storage (fallback or tests)
        _save_notebook_file(notebook, subdirectory)


def _save_notebook_file(notebook: Notebook, subdirectory: str = None) -> None:
    """Save a notebook to JSON file (fallback).
    
    Args:
        notebook: The notebook to save
        subdirectory: Optional subdirectory within NOTEBOOKS_DIR (e.g., 'test')
    """
    ensure_notebooks_dir(subdirectory)

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

    if subdirectory:
        target_dir = NOTEBOOKS_DIR / subdirectory
        file_path = target_dir / f"{notebook.id}.json"
    else:
        target_dir = NOTEBOOKS_DIR
        file_path = target_dir / f"{notebook.id}.json"
    
    # Write to temporary file first (atomic write)
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=target_dir,
        delete=False,
        suffix='.tmp',
        prefix=f'{notebook.id}_'
    ) as f:
        json.dump(data, f, indent=2)
        temp_path = f.name
    
    # Atomic rename (POSIX guarantees atomicity)
    os.replace(temp_path, file_path)

async def load_notebook(notebook_id: str, user_id: Optional[str] = None, subdirectory: str = None) -> Notebook:
    """Load a notebook from storage (DynamoDB or file).
    
    Args:
        notebook_id: The ID of the notebook to load
        user_id: Optional user ID (for DynamoDB - faster lookup)
        subdirectory: Optional subdirectory within NOTEBOOKS_DIR (e.g., 'test')
    """
    if DYNAMODB_ENABLED and not subdirectory:
        # Use DynamoDB for production storage
        from storage_dynamodb import get_dynamodb_storage
        storage = get_dynamodb_storage()
        
        # Try with user_id first (fastest - GetItem)
        if user_id:
            notebook = await storage.load_notebook(user_id, notebook_id)
            if notebook:
                return notebook
        
        # Fallback to GSI lookup (slightly slower)
        notebook = await storage.load_notebook_by_id(notebook_id)
        if notebook:
            return notebook
        
        raise FileNotFoundError(f"Notebook {notebook_id} not found")
    else:
        # Use file-based storage (fallback or tests)
        return _load_notebook_file(notebook_id, subdirectory)


def _load_notebook_file(notebook_id: str, subdirectory: str = None) -> Notebook:
    """Load a notebook from JSON file (fallback).
    
    Args:
        notebook_id: The ID of the notebook to load
        subdirectory: Optional subdirectory within NOTEBOOKS_DIR (e.g., 'test')
    """
    if subdirectory:
        file_path = NOTEBOOKS_DIR / subdirectory / f"{notebook_id}.json"
    else:
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

async def list_notebooks(user_id: Optional[str] = None) -> List[str]:
    """List notebooks (DynamoDB or file).
    
    Args:
        user_id: Optional user ID (required for DynamoDB)
    """
    if DYNAMODB_ENABLED and user_id:
        from storage_dynamodb import get_dynamodb_storage
        storage = get_dynamodb_storage()
        notebooks = await storage.list_notebooks(user_id)
        return [nb['id'] for nb in notebooks]
    else:
        return _list_notebooks_files()


def _list_notebooks_files() -> List[str]:
    """List notebooks from files (fallback).
    
    Returns:
        List of notebook IDs (excluding test notebooks in subdirectories)
    """
    ensure_notebooks_dir()
    # Only list JSON files in the root notebooks directory, not in subdirectories
    return [f.stem for f in NOTEBOOKS_DIR.glob("*.json") if f.parent == NOTEBOOKS_DIR]

async def delete_notebook(notebook_id: str, user_id: Optional[str] = None) -> None:
    """Delete notebook from storage (DynamoDB or file).
    
    Args:
        notebook_id: The ID of the notebook to delete
        user_id: Optional user ID (required for DynamoDB)
    """
    if DYNAMODB_ENABLED and user_id:
        from storage_dynamodb import get_dynamodb_storage
        storage = get_dynamodb_storage()
        await storage.delete_notebook(user_id, notebook_id)
    else:
        _delete_notebook_file(notebook_id)


def _delete_notebook_file(notebook_id: str) -> None:
    """Delete a notebook file from disk (fallback)."""
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"
    if file_path.exists():
        file_path.unlink()
