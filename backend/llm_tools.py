"""
LLM tool interface for notebook manipulation.
These tools are called by the LLM assistant to interact with notebooks.
"""
from typing import Optional, List
from models import Notebook, Cell, CellType, CellStatus
from notebook_operations import (
    locked_update_cell,
    locked_create_cell,
    locked_delete_cell,
    locked_get_notebook_snapshot
)
import asyncio
import time


def create_output_preview(cell: Cell) -> dict:
    """Create lightweight preview of cell output for LLM context (token-efficient)."""
    if not cell.outputs:
        return {"preview": "", "type": "none", "has_visual": False}
    
    # Get first output
    output = cell.outputs[0]
    mime_type = output.mime_type
    
    # Plotly chart
    if "plotly" in mime_type.lower():
        data = output.data if isinstance(output.data, dict) else {}
        chart_data = data.get("data", [{}])
        chart_type = chart_data[0].get("type", "unknown") if chart_data else "unknown"
        point_count = len(chart_data[0].get("x", [])) if chart_data else 0
        
        return {
            "preview": f"[Plotly {chart_type} chart with {point_count} points]",
            "type": "plotly",
            "has_visual": True,
            "metadata": {
                "chart_type": chart_type,
                "point_count": point_count
            }
        }
    
    # Image (PNG, etc.)
    elif "image/" in mime_type:
        return {
            "preview": f"[Image: {mime_type}]",
            "type": "image",
            "has_visual": True
        }
    
    # HTML
    elif "html" in mime_type.lower():
        html = str(output.data)
        return {
            "preview": f"[HTML output: {len(html)} chars]",
            "type": "html",
            "has_visual": True
        }
    
    # Plain text or JSON
    else:
        text = str(output.data)
        max_len = 500
        return {
            "preview": text[:max_len] + ("..." if len(text) > max_len else ""),
            "type": "text",
            "has_visual": False
        }


async def tool_get_notebook_state(
    notebook: Notebook,
    include_outputs: bool = True,
    cell_ids: Optional[List[str]] = None
) -> dict:
    """
    Get current state of notebook cells.
    
    Args:
        notebook: Notebook instance
        include_outputs: Whether to include output previews
        cell_ids: Optional list of specific cell IDs to retrieve
    
    Returns:
        Dictionary with cells array and execution status
    """
    snapshot = await locked_get_notebook_snapshot(notebook)
    
    # Filter cells if specific IDs requested
    cells = snapshot["cells"]
    if cell_ids:
        cells = [c for c in cells if c["id"] in cell_ids]
    
    # Add output previews
    if include_outputs:
        for cell_data in cells:
            # Find corresponding cell object
            cell = next((c for c in notebook.cells if c.id == cell_data["id"]), None)
            if cell:
                output_info = create_output_preview(cell)
                cell_data["output_preview"] = output_info["preview"]
                cell_data["output_type"] = output_info["type"]
                cell_data["has_visual"] = output_info["has_visual"]
                if "metadata" in output_info:
                    cell_data["output_metadata"] = output_info["metadata"]
                
                # Add stdout if present
                if cell.stdout:
                    max_len = 500
                    cell_data["stdout_preview"] = cell.stdout[:max_len] + ("..." if len(cell.stdout) > max_len else "")
                
                # Add error if present
                if cell.error:
                    cell_data["error"] = cell.error
    
    # Check if any cell is currently executing
    execution_in_progress = any(
        c["status"] == CellStatus.RUNNING.value for c in cells
    )
    
    current_executing = next(
        (c["id"] for c in cells if c["status"] == CellStatus.RUNNING.value),
        None
    )
    
    return {
        "cells": cells,
        "revision": snapshot["revision"],
        "execution_in_progress": execution_in_progress,
        "current_executing_cell": current_executing,
        "cell_count": len(cells)
    }


async def tool_update_cell(
    notebook: Notebook,
    cell_id: str,
    code: str,
    broadcaster
) -> dict:
    """Update a cell's code."""
    try:
        cell = await locked_update_cell(notebook, cell_id, code)
        
        # Broadcast update (using current broadcaster signature)
        await broadcaster.broadcast_cell_updated(notebook.id, cell_id, {
            "code": cell.code,
            "reads": list(cell.reads),
            "writes": list(cell.writes),
            "type": cell.type.value,
            "status": cell.status.value
        })
        
        return {
            "status": "ok",
            "cell_id": cell.id,
            "revision": notebook.revision
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def tool_create_cell(
    notebook: Notebook,
    cell_type: str,
    code: str,
    index: Optional[int],
    broadcaster
) -> dict:
    """Create a new cell."""
    try:
        # Convert string to CellType enum
        cell_type_enum = CellType.PYTHON if cell_type.lower() == "python" else CellType.SQL
        
        cell = await locked_create_cell(notebook, cell_type_enum, code, index)
        
        # Find the actual index where the cell was inserted
        cell_index = next(i for i, c in enumerate(notebook.cells) if c.id == cell.id)
        
        # Broadcast creation (using current broadcaster signature)
        await broadcaster.broadcast_cell_created(notebook.id, {
            "id": cell.id,
            "type": cell.type.value,
            "code": cell.code,
            "reads": list(cell.reads),
            "writes": list(cell.writes),
            "status": cell.status.value
        }, cell_index)
        
        return {
            "status": "ok",
            "cell_id": cell.id,
            "revision": notebook.revision
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def tool_delete_cell(
    notebook: Notebook,
    cell_id: str,
    broadcaster
) -> dict:
    """Delete a cell."""
    try:
        await locked_delete_cell(notebook, cell_id)
        
        # Broadcast deletion
        await broadcaster.broadcast_cell_deleted(notebook.id, cell_id)
        
        return {
            "status": "ok",
            "revision": notebook.revision
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e)
        }


CELL_EXECUTION_TIMEOUT = 30  # seconds
LONG_RUNNING_THRESHOLD = 5   # seconds


async def tool_run_cell(
    notebook: Notebook,
    cell_id: str,
    scheduler,
    broadcaster
) -> dict:
    """
    Run a cell and wait for completion.
    Returns result or timeout error.
    """
    # Enqueue cell for execution
    await scheduler.enqueue_run(notebook.id, cell_id, notebook, broadcaster)
    
    # Wait for completion
    start_time = time.time()
    warned = False
    
    while time.time() - start_time < CELL_EXECUTION_TIMEOUT:
        # Get current cell status (no lock needed for read)
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if not cell:
            return {"status": "error", "error": "Cell not found"}
        
        if cell.status == CellStatus.SUCCESS:
            output_info = create_output_preview(cell)
            return {
                "status": "success",
                "output_preview": output_info["preview"],
                "output_type": output_info["type"],
                "stdout": cell.stdout[:500] if cell.stdout else ""
            }
        
        if cell.status == CellStatus.ERROR:
            return {
                "status": "error",
                "error": cell.error or "Unknown error"
            }
        
        if cell.status == CellStatus.BLOCKED:
            return {
                "status": "blocked",
                "error": "Cell is blocked by failed dependencies"
            }
        
        # Warn if taking long (for LLM awareness)
        elapsed = time.time() - start_time
        if elapsed > LONG_RUNNING_THRESHOLD and not warned:
            warned = True
            # Could send SSE update here in Phase 3
        
        await asyncio.sleep(0.2)
    
    # Timeout
    return {
        "status": "timeout",
        "error": f"Cell execution exceeded {CELL_EXECUTION_TIMEOUT}s timeout. Cell may still be running.",
        "suggestion": "Check cell status with get_notebook_state"
    }


# Anthropic tool schemas for Claude
TOOL_SCHEMAS = [
    {
        "name": "get_notebook_state",
        "description": "Get the current state of all cells in the notebook, including their code, execution status, and output previews. Use this to understand what's currently in the notebook before making changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_outputs": {
                    "type": "boolean",
                    "description": "Whether to include output previews. Default: true"
                },
                "cell_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: specific cell IDs to retrieve. If not provided, returns all cells."
                }
            }
        }
    },
    {
        "name": "update_cell",
        "description": "Update the code of an existing cell. The cell will be marked as IDLE and its dependencies will be re-analyzed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "ID of the cell to update"
                },
                "code": {
                    "type": "string",
                    "description": "New code for the cell"
                }
            },
            "required": ["cell_id", "code"]
        }
    },
    {
        "name": "create_cell",
        "description": "Create a new cell in the notebook. The cell can be Python or SQL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_type": {
                    "type": "string",
                    "enum": ["python", "sql"],
                    "description": "Type of cell to create"
                },
                "code": {
                    "type": "string",
                    "description": "Code for the new cell"
                },
                "index": {
                    "type": "integer",
                    "description": "Optional: position to insert the cell. If not provided, appends to end."
                }
            },
            "required": ["cell_type", "code"]
        }
    },
    {
        "name": "run_cell",
        "description": "Execute a cell and wait for it to complete. Returns the output or error. Times out after 30 seconds for long-running cells.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "ID of the cell to run"
                }
            },
            "required": ["cell_id"]
        }
    },
    {
        "name": "delete_cell",
        "description": "Delete a cell from the notebook. This will also remove any variables defined by this cell from the kernel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "ID of the cell to delete"
                }
            },
            "required": ["cell_id"]
        }
    }
]


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    notebook: Notebook,
    scheduler,
    broadcaster
) -> dict:
    """Dispatch tool execution to appropriate handler."""
    if tool_name == "get_notebook_state":
        return await tool_get_notebook_state(
            notebook,
            include_outputs=tool_input.get("include_outputs", True),
            cell_ids=tool_input.get("cell_ids")
        )
    
    elif tool_name == "update_cell":
        return await tool_update_cell(
            notebook,
            tool_input["cell_id"],
            tool_input["code"],
            broadcaster
        )
    
    elif tool_name == "create_cell":
        return await tool_create_cell(
            notebook,
            tool_input["cell_type"],
            tool_input["code"],
            tool_input.get("index"),
            broadcaster
        )
    
    elif tool_name == "run_cell":
        return await tool_run_cell(
            notebook,
            tool_input["cell_id"],
            scheduler,
            broadcaster
        )
    
    elif tool_name == "delete_cell":
        return await tool_delete_cell(
            notebook,
            tool_input["cell_id"],
            broadcaster
        )
    
    else:
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}

