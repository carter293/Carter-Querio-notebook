"""
Thread-safe notebook operations using asyncio locks.
All mutations to notebook state MUST go through these functions.
"""
from typing import Optional
from uuid import uuid4
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph, detect_cycle
from storage import save_notebook


async def locked_update_cell(
    notebook: Notebook,
    cell_id: str,
    code: str,
    expected_revision: Optional[int] = None
) -> Cell:
    """
    Update cell code with concurrency protection and optimistic locking.
    
    Raises:
        ValueError: If cell not found or revision conflict
    """
    async with notebook._lock:
        # Optimistic locking check
        if expected_revision is not None and notebook.revision != expected_revision:
            raise ValueError(
                f"Revision conflict: expected {expected_revision}, got {notebook.revision}"
            )
        
        # Find cell
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if not cell:
            raise ValueError(f"Cell {cell_id} not found")
        
        # Update code
        cell.code = code
        cell.status = CellStatus.IDLE
        
        # Extract dependencies
        if cell.type == CellType.PYTHON:
            reads, writes = extract_dependencies(code)
            cell.reads = reads
            cell.writes = writes
        elif cell.type == CellType.SQL:
            reads = extract_sql_dependencies(code)
            cell.reads = reads
        
        # Rebuild dependency graph
        rebuild_graph(notebook)
        
        # Check for cycles
        cycle = detect_cycle(notebook.graph, cell_id)
        if cycle:
            cell.status = CellStatus.ERROR
            cell.error = f"Circular dependency detected: {' -> '.join(cycle)}"
        
        # Increment revision
        notebook.revision += 1
        
        # Save to storage
        await save_notebook(notebook)
        
        return cell


async def locked_create_cell(
    notebook: Notebook,
    cell_type: CellType,
    code: str,
    index: Optional[int] = None
) -> Cell:
    """Create new cell with concurrency protection."""
    async with notebook._lock:
        new_cell = Cell(
            id=str(uuid4()),
            type=cell_type,
            code=code,
            status=CellStatus.IDLE,
            reads=set(),
            writes=set()
        )
        
        # Extract dependencies
        if cell_type == CellType.PYTHON:
            reads, writes = extract_dependencies(code)
            new_cell.reads = reads
            new_cell.writes = writes
        elif cell_type == CellType.SQL:
            reads = extract_sql_dependencies(code)
            new_cell.reads = reads
        
        # Insert at index or append
        if index is not None and 0 <= index <= len(notebook.cells):
            notebook.cells.insert(index, new_cell)
        else:
            notebook.cells.append(new_cell)
        
        # Rebuild graph
        rebuild_graph(notebook)
        
        # Check for cycles
        cycle = detect_cycle(notebook.graph, new_cell.id)
        if cycle:
            new_cell.status = CellStatus.ERROR
            new_cell.error = f"Circular dependency detected: {' -> '.join(cycle)}"
        
        # Increment revision
        notebook.revision += 1
        
        # Save
        await save_notebook(notebook)
        
        return new_cell


async def locked_delete_cell(
    notebook: Notebook,
    cell_id: str
) -> None:
    """Delete cell with concurrency protection."""
    async with notebook._lock:
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if not cell:
            raise ValueError(f"Cell {cell_id} not found")
        
        # Remove from cells list
        notebook.cells = [c for c in notebook.cells if c.id != cell_id]
        
        # Remove from graph
        notebook.graph.remove_cell(cell_id)
        
        # Remove variables from kernel
        for var in cell.writes:
            notebook.kernel.globals_dict.pop(var, None)
        
        # Increment revision
        notebook.revision += 1
        
        # Save
        await save_notebook(notebook)


async def locked_get_notebook_snapshot(notebook: Notebook) -> dict:
    """Get read-only snapshot of notebook state (for LLM context)."""
    async with notebook._lock:
        return {
            "id": notebook.id,
            "name": notebook.name,
            "revision": notebook.revision,
            "cell_count": len(notebook.cells),
            "cells": [
                {
                    "id": c.id,
                    "type": c.type.value,
                    "code": c.code,
                    "status": c.status.value,
                    "reads": list(c.reads),
                    "writes": list(c.writes),
                }
                for c in notebook.cells
            ]
        }

