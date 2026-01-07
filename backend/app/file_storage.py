import re
import uuid
from pathlib import Path
from typing import Optional
from .models import NotebookResponse, CellResponse, CellType, NotebookMetadataResponse

NOTEBOOKS_DIR = Path(__file__).parent.parent / "notebooks"
CELL_SEPARATOR_PATTERN = re.compile(r"^# %% (python|sql)(?: \[([^\]]+)\])?$")

class NotebookFileStorage:
    """Parse and serialize notebooks as .py files."""

    @staticmethod
    def parse_notebook(notebook_id: str) -> Optional[NotebookResponse]:
        """Parse a .py file into a NotebookResponse."""
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        if not file_path.exists():
            return None

        content = file_path.read_text()
        lines = content.splitlines()

        # Parse metadata from top comments
        name = None
        db_conn_string = None
        i = 0
        while i < len(lines) and lines[i].startswith("#"):
            if lines[i].startswith("# Notebook:"):
                name = lines[i].replace("# Notebook:", "").strip()
            elif lines[i].startswith("# DB:"):
                db_conn_string = lines[i].replace("# DB:", "").strip()
            i += 1

        # Parse cells
        cells = []
        current_cell: Optional[dict] = None

        for line in lines[i:]:
            match = CELL_SEPARATOR_PATTERN.match(line)
            if match:
                # Save previous cell
                if current_cell:
                    cells.append(CellResponse(**current_cell))

                # Start new cell
                cell_type = match.group(1)
                cell_id = match.group(2) or str(uuid.uuid4())
                current_cell = {
                    "id": cell_id,
                    "type": cell_type,
                    "code": "",
                    "status": "idle",
                }
            elif current_cell is not None:
                # Append to current cell code
                if current_cell["code"]:
                    current_cell["code"] += "\n"
                current_cell["code"] += line

        # Save last cell
        if current_cell:
            cells.append(CellResponse(**current_cell))

        return NotebookResponse(
            id=notebook_id,
            name=name or notebook_id,
            db_conn_string=db_conn_string,
            cells=cells,
        )

    @staticmethod
    def serialize_notebook(notebook: NotebookResponse) -> None:
        """Write a NotebookResponse to a .py file."""
        file_path = NOTEBOOKS_DIR / f"{notebook.id}.py"

        lines = []

        # Write metadata
        if notebook.name:
            lines.append(f"# Notebook: {notebook.name}")
        if notebook.db_conn_string:
            lines.append(f"# DB: {notebook.db_conn_string}")

        if lines:
            lines.append("")  # Blank line after metadata

        # Write cells
        for cell in notebook.cells:
            lines.append(f"# %% {cell.type} [{cell.id}]")
            lines.append(cell.code)
            lines.append("")  # Blank line between cells

        file_path.write_text("\n".join(lines))

    @staticmethod
    def list_notebooks() -> list[NotebookMetadataResponse]:
        """List all notebooks in the directory."""
        notebooks = []
        for file_path in NOTEBOOKS_DIR.glob("*.py"):
            notebook_id = file_path.stem
            notebook = NotebookFileStorage.parse_notebook(notebook_id)
            if notebook:
                notebooks.append(NotebookMetadataResponse(
                    id=notebook.id,
                    name=notebook.name or notebook.id,
                ))
        return notebooks

    @staticmethod
    def delete_notebook(notebook_id: str) -> bool:
        """Delete a notebook file."""
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        if file_path.exists():
            file_path.unlink()
            return True
        return False
