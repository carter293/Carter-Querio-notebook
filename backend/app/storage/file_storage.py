import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional
from app.models import Notebook, Cell, CellType, CellStatus, Graph, KernelState, Output
from app.core import settings
from .base import StorageBackend


class FileStorage(StorageBackend):
    """File-based storage backend for local development"""
    
    def __init__(self, notebook_dir: str = None):
        self.notebooks_dir = Path(notebook_dir or settings.NOTEBOOK_STORAGE_DIR)
        self.notebooks_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, notebook_id: str, subdirectory: str = None) -> Path:
        """Get file path for a notebook"""
        if subdirectory:
            target_dir = self.notebooks_dir / subdirectory
            target_dir.mkdir(parents=True, exist_ok=True)
            return target_dir / f"{notebook_id}.json"
        return self.notebooks_dir / f"{notebook_id}.json"
    
    async def save_notebook(self, notebook: Notebook, subdirectory: str = None) -> None:
        """Save a notebook to JSON file"""
        # Skip saving if auto-save is disabled (e.g., during tests)
        if os.environ.get("DISABLE_AUTO_SAVE", "false").lower() == "true":
            return
        
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
        
        file_path = self._get_file_path(notebook.id, subdirectory)
        target_dir = file_path.parent
        
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
    
    async def load_notebook(self, user_id: str, notebook_id: str, subdirectory: str = None) -> Optional[Notebook]:
        """Load a notebook from JSON file"""
        file_path = self._get_file_path(notebook_id, subdirectory)
        
        if not file_path.exists():
            return None
        
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
        stored_user_id = data.get("user_id")
        if not stored_user_id:
            # Try to extract from notebook ID pattern: {name}-user_{user_id}
            if "-user_" in notebook_id:
                stored_user_id = notebook_id.split("-user_", 1)[1]
            else:
                # Fallback for legacy notebooks without user_id
                stored_user_id = "system"
        
        notebook = Notebook(
            id=data["id"],
            user_id=stored_user_id,
            name=data.get("name"),
            db_conn_string=data.get("db_conn_string"),
            cells=cells,
            revision=data.get("revision", 0)
        )
        
        # Rebuild dependency graph
        from app.execution.dependencies import rebuild_graph
        rebuild_graph(notebook)
        
        return notebook
    
    async def list_notebooks(self, user_id: Optional[str] = None) -> List[str]:
        """List notebooks from files"""
        # Only list JSON files in the root notebooks directory, not in subdirectories
        return [f.stem for f in self.notebooks_dir.glob("*.json") if f.parent == self.notebooks_dir]
    
    async def delete_notebook(self, notebook_id: str, user_id: str) -> None:
        """Delete a notebook file from disk"""
        file_path = self._get_file_path(notebook_id)
        if file_path.exists():
            file_path.unlink()

