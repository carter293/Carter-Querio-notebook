---
date: 2025-12-29T09:55:20Z
planner: Claude
topic: "LLM Assistant Integration for Reactive Notebook"
tags: [planning, implementation, llm-integration, anthropic, concurrency, sse]
status: draft
last_updated: 2025-12-29
last_updated_by: Claude
based_on: "thoughts/shared/research/2025-12-28-llm-assistant-integration-architecture.md"
---

# LLM Assistant Integration Implementation Plan

**Date**: 2025-12-29T09:55:20Z  
**Planner**: Claude  
**Git Commit**: 3d54a8ee8282355a4fd3c2fe18b8bb94136891f5  
**Branch**: main

## Overview

This plan implements an AI assistant that can interact with the reactive notebook through tool-calling capabilities. The assistant will be able to create, update, run, and delete cells safely using the Anthropic Claude API with server-side tool execution. The implementation prioritizes fixing critical concurrency vulnerabilities before adding LLM features.

## Current State Analysis

### What Exists Now

**State Management**:
- `Notebook` dataclass in `backend/models.py:78-87` with fields: `id`, `user_id`, `name`, `db_conn_string`, `cells`, `graph`, `kernel`, `revision`
- In-memory storage in `NOTEBOOKS` dict (`backend/routes.py:18`)
- File-based persistence to `backend/notebooks/{id}.json` (`backend/storage.py:12-34`)

**Concurrency Protection**:
- Per-notebook `asyncio.Lock` in scheduler (`backend/scheduler.py:18-23`)
- **Only protects**: Execution queue operations
- **Does NOT protect**: Cell mutations, graph rebuilding, kernel state, file writes

**Real-Time Communication**:
- WebSocket broadcaster (`backend/websocket.py`) sends 8 event types: `cell_status`, `cell_stdout`, `cell_result`, `cell_error`, `cell_output`, `cell_updated`, `cell_created`, `cell_deleted`
- WebSocket endpoint at `/api/ws/notebooks/{id}` (`backend/routes.py:429-560`)

**Authentication**:
- Clerk JWT authentication (`backend/main.py:36-124`)
- Bearer token required for all REST endpoints
- **Missing**: WebSocket authentication (noted as TODO in code)

### Key Discoveries

1. **Race Condition Vulnerabilities** (`backend/routes.py:309-390`):
   - `update_cell` endpoint modifies `cell.code` and calls `rebuild_graph()` without lock
   - `delete_cell` endpoint modifies `notebook.kernel.globals_dict` without lock
   - Scheduler reads `notebook.graph` during execution without lock
   - **Result**: Lost updates, graph corruption, kernel state corruption

2. **Non-Atomic File Saves** (`backend/storage.py:32-34`):
   ```python
   with open(file_path, 'w') as f:
       json.dump(data, f, indent=2)
   ```
   - Direct file overwrite, no temp file or atomic rename
   - **Result**: Partial writes if process interrupted

3. **Existing Patterns to Leverage**:
   - `revision` field already present for optimistic locking
   - Asyncio-based architecture ready for async locks
   - Dependency tracking via AST parsing (`backend/ast_parser.py`)

## System Context Analysis

The notebook application is a **reactive execution environment** where cells have declared dependencies (reads/writes) that form a DAG. The scheduler ensures correct execution order via topological sort. The system is **single-threaded per notebook** for execution but **multi-actor** for mutations (multiple users/clients can modify the same notebook).

**Current Architecture**:
- **State Source of Truth**: In-memory `NOTEBOOKS` dict
- **Persistence**: Eventually consistent (saved after each mutation)
- **Real-Time Sync**: WebSocket broadcasts mutations to all clients
- **Execution**: Sequential, dependency-aware

**Root Cause vs Symptom**:
This plan addresses the **root cause**: lack of concurrency control for notebook state mutations. Adding LLM tool-calling without fixing this would amplify race conditions. The LLM assistant is a **new actor** that will perform the same mutations as users, making proper locking essential.

## Desired End State

**After Phase 1 (Week 1)**:
- All notebook mutations protected by `asyncio.Lock`
- Atomic file saves (temp file + rename)
- Optimistic locking with revision conflicts
- No race conditions under concurrent load

**After Phase 2 (Week 2)**:
- 5 LLM tools implemented with proper locking:
  - `get_notebook_state` - Read cells and outputs
  - `create_cell` - Add new cell
  - `update_cell` - Modify cell code
  - `run_cell` - Execute cell (wait for completion)
  - `delete_cell` - Remove cell
- Comprehensive test coverage

**After Phase 3 (Week 3)**:
- SSE chat endpoint at `/api/chat/{notebook_id}`
- Streaming LLM responses using Anthropic SDK
- Server-side tool execution with audit logging

**After Phase 4 (Week 4)**:
- ChatPanel React component with SSE streaming
- LLM working indicator (grey out notebook during AI work)
- Conflict toast notifications with undo

**Verification**:
- ✅ Concurrent cell updates don't lose data (load test)
- ✅ LLM can create/update/delete/run cells successfully
- ✅ User sees real-time updates from LLM via WebSocket
- ✅ No race conditions under concurrent user + LLM actions

## What We're NOT Doing

**Out of Scope**:
- ❌ Multi-modal input (image uploads to LLM) - Future enhancement
- ❌ Conversation history persistence - Future enhancement  
- ❌ LLM approval workflow for destructive operations - User approval not required per design decisions
- ❌ Read-write locks (using simple exclusive locks) - Optimization for later
- ❌ Database migration (staying with file-based storage) - Separate effort
- ❌ WebSocket authentication implementation - Separate ticket
- ❌ Modifying database connection strings via LLM - Explicitly restricted

## Implementation Approach

### Strategy

**Phase-Based Delivery**:
1. **Foundation**: Fix concurrency issues (prerequisite for LLM)
2. **Tools**: Build LLM tool interface with locked operations
3. **Streaming**: Implement SSE chat endpoint with Anthropic
4. **UI**: Integrate ChatPanel and conflict resolution UX

**Key Design Decisions** (from research):
- **Streaming**: Native Anthropic SDK + SSE (not Vercel AI SDK due to FastAPI compatibility issues)
- **Context Management**: Lightweight MIME previews (not full images/data)
- **Tool Execution**: Wait for cell completion with 30s timeout
- **Conflict Resolution**: Grey out UI + last-write-wins + undo toast
- **Access Control**: Broad LLM access with audit logging (no approval workflow)

### Technical Approach

**Locking Strategy**:
- Add `_lock: asyncio.Lock` field to `Notebook` dataclass (excluded from serialization)
- Create `notebook_operations.py` module with all locked mutation functions
- Refactor existing endpoints to use locked operations

**Tool Architecture**:
- Define Anthropic tool schemas in `llm_tools.py`
- Each tool calls corresponding locked operation
- Tools broadcast updates via existing WebSocket
- LLM receives lightweight output previews (token-efficient)

**Streaming Architecture**:
```
Frontend → POST /api/chat/{id} (SSE) → Backend
                                          ↓
                                     Anthropic API (streaming)
                                          ↓
                                     Parse tool calls
                                          ↓
                                     Execute tools (with locks)
                                          ↓
                                     Broadcast via WebSocket
                                          ↓
                                     Stream response to chat
```

---

## Phase 1: Concurrency Foundation (Week 1)

### Overview

Fix all race conditions by adding notebook-level locks, implementing atomic file saves, and coordinating scheduler access. This is the **critical prerequisite** before adding LLM features.

### Changes Required

#### 1. Add Lock to Notebook Model

**File**: `backend/models.py`  
**Changes**: Add lock field to Notebook dataclass

```python
from asyncio import Lock

@dataclass
class Notebook:
    id: str
    user_id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
    # Add lock for concurrency control (not serialized)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
```

**Why**: Provides mutual exclusion for all notebook state mutations

#### 2. Create Locked Operations Module

**File**: `backend/notebook_operations.py` (NEW)  
**Changes**: Implement thread-safe notebook operations

```python
"""
Thread-safe notebook operations using asyncio locks.
All mutations to notebook state MUST go through these functions.
"""
from typing import Optional
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph
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
        
        # Increment revision
        notebook.revision += 1
        
        # Save to disk
        save_notebook(notebook)
        
        return cell


async def locked_create_cell(
    notebook: Notebook,
    cell_type: CellType,
    code: str,
    index: Optional[int] = None
) -> Cell:
    """Create new cell with concurrency protection."""
    async with notebook._lock:
        from uuid import uuid4
        
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
        
        # Increment revision
        notebook.revision += 1
        
        # Save
        save_notebook(notebook)
        
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
        
        # Remove variables from kernel
        for var in cell.writes:
            notebook.kernel.globals_dict.pop(var, None)
        
        # Rebuild graph
        rebuild_graph(notebook)
        
        # Increment revision
        notebook.revision += 1
        
        # Save
        save_notebook(notebook)


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
```

#### 3. Refactor REST Endpoints to Use Locks

**File**: `backend/routes.py`  
**Changes**: Replace direct mutations with locked operations

**Update Cell Endpoint** (lines 309-390):
```python
from notebook_operations import (
    locked_update_cell,
    locked_create_cell,
    locked_delete_cell
)

@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(
    notebook_id: str,
    cell_id: str,
    request_body: UpdateCellRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        # Use locked operation (no direct mutation!)
        cell = await locked_update_cell(
            notebook,
            cell_id,
            request_body.code,
            expected_revision=getattr(request_body, 'expected_revision', None)
        )
        
        # Broadcast update via WebSocket
        await broadcaster.broadcast_cell_updated(
            notebook_id,
            cell.id,
            cell.code,
            cell.type.value,
            list(cell.reads),
            list(cell.writes)
        )
        
        return {
            "status": "ok",
            "revision": notebook.revision
        }
    except ValueError as e:
        if "Revision conflict" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
```

**Create Cell Endpoint** (lines 271-307):
```python
@router.post("/notebooks/{notebook_id}/cells")
async def create_cell(
    notebook_id: str,
    request_body: CreateCellRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        cell = await locked_create_cell(
            notebook,
            CellType(request_body.type),
            request_body.code,
            request_body.index
        )
        
        await broadcaster.broadcast_cell_created(
            notebook_id,
            cell.id,
            cell.type.value,
            cell.code,
            list(cell.reads),
            list(cell.writes)
        )
        
        return {"cell_id": cell.id, "revision": notebook.revision}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Delete Cell Endpoint** (lines 363-394):
```python
@router.delete("/notebooks/{notebook_id}/cells/{cell_id}")
async def delete_cell(
    notebook_id: str,
    cell_id: str,
    user_id: str = Depends(get_current_user_dependency)
):
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        await locked_delete_cell(notebook, cell_id)
        
        await broadcaster.broadcast_cell_deleted(notebook_id, cell_id)
        
        return {"status": "ok", "revision": notebook.revision}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

#### 4. Implement Atomic File Saves

**File**: `backend/storage.py`  
**Changes**: Use temp file + atomic rename

```python
import tempfile
import os

def save_notebook(notebook: Notebook) -> None:
    """Save notebook with atomic write (prevents partial writes)."""
    ensure_notebooks_dir()
    
    # Serialize notebook
    data = {
        "id": notebook.id,
        "name": notebook.name,
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
    
    # Write to temporary file first
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
```

#### 5. Coordinate Scheduler with Notebook Lock

**File**: `backend/scheduler.py`  
**Changes**: Acquire notebook lock when reading graph

Update `_drain_queue` method (lines 44-102):
```python
async def _drain_queue(self, notebook_id: str, notebook, broadcaster):
    """Process all pending cell runs with proper locking."""
    while True:
        # Get pending cells (uses scheduler's own lock)
        lock = self.get_lock(notebook_id)
        async with lock:
            if not self.pending_runs.get(notebook_id):
                break
            pending_cells = self.pending_runs[notebook_id].copy()
            self.pending_runs[notebook_id].clear()
        
        # Acquire notebook lock to read graph and plan execution
        async with notebook._lock:
            # Expand to include all dependents
            all_to_run = set(pending_cells)
            for cell_id in pending_cells:
                dependents = get_all_dependents(notebook.graph, cell_id)
                all_to_run.update(dependents)
            
            # Topological sort
            try:
                sorted_cells = topological_sort(notebook.graph, all_to_run)
            except ValueError as e:
                # Cycle detected
                for cell_id in all_to_run:
                    cell = next((c for c in notebook.cells if c.id == cell_id), None)
                    if cell:
                        cell.status = CellStatus.ERROR
                        cell.error = f"Dependency cycle: {str(e)}"
                        await broadcaster.broadcast_cell_status(notebook_id, cell_id, CellStatus.ERROR.value)
                        await broadcaster.broadcast_cell_error(notebook_id, cell_id, cell.error)
                continue
            
            # Create snapshot of cells to execute (copy cell data)
            cells_to_execute = []
            for cell_id in sorted_cells:
                cell = next((c for c in notebook.cells if c.id == cell_id), None)
                if cell:
                    cells_to_execute.append({
                        "id": cell.id,
                        "code": cell.code,
                        "type": cell.type
                    })
        
        # Execute cells (releases lock during execution to allow reads)
        for cell_data in cells_to_execute:
            # Get fresh reference to cell (it may have been modified)
            cell = next((c for c in notebook.cells if c.id == cell_data["id"]), None)
            if cell:
                # Check if dependencies failed
                async with notebook._lock:
                    deps = notebook.graph.reverse_edges.get(cell.id, set())
                    failed_deps = [
                        dep_id for dep_id in deps
                        if any(c.id == dep_id and c.status == CellStatus.ERROR for c in notebook.cells)
                    ]
                
                if failed_deps:
                    cell.status = CellStatus.BLOCKED
                    await broadcaster.broadcast_cell_status(notebook_id, cell.id, CellStatus.BLOCKED.value)
                else:
                    await self._execute_cell(notebook_id, cell, notebook, broadcaster)
```

#### 6. Add Concurrency Tests

**File**: `backend/tests/test_concurrency.py` (NEW)  
**Changes**: Test concurrent mutations

```python
import pytest
import asyncio
from backend.models import Notebook, Cell, CellType, CellStatus, Graph, KernelState
from backend.notebook_operations import locked_update_cell, locked_create_cell


@pytest.mark.asyncio
async def test_concurrent_cell_updates():
    """Test that concurrent updates don't lose data."""
    notebook = Notebook(
        id="test-concurrency",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            Cell(
                id="cell1",
                type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.IDLE,
                reads=set(),
                writes={"x"}
            )
        ],
        graph=Graph(),
        kernel=KernelState(globals_dict={"__builtins__": __builtins__})
    )
    
    # Simulate 50 concurrent updates
    async def update_cell_multiple_times(base_code, count):
        for i in range(count):
            await locked_update_cell(notebook, "cell1", f"{base_code} + {i}")
    
    # Run 5 updaters concurrently, each doing 10 updates
    tasks = [update_cell_multiple_times(f"x = {i}", 10) for i in range(5)]
    await asyncio.gather(*tasks)
    
    # Verify revision incremented correctly (50 total updates)
    assert notebook.revision == 50
    
    # Verify cell has valid code (one of the 50 updates)
    cell = notebook.cells[0]
    assert "x =" in cell.code
    print(f"Final cell code after 50 concurrent updates: {cell.code}")


@pytest.mark.asyncio
async def test_optimistic_locking():
    """Test revision conflict detection."""
    notebook = Notebook(
        id="test-optimistic",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            Cell(
                id="cell1",
                type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.IDLE,
                reads=set(),
                writes={"x"}
            )
        ],
        graph=Graph(),
        kernel=KernelState(globals_dict={"__builtins__": __builtins__}),
        revision=5
    )
    
    # First update succeeds
    await locked_update_cell(notebook, "cell1", "x = 2", expected_revision=5)
    assert notebook.revision == 6
    
    # Second update with stale revision fails
    with pytest.raises(ValueError, match="Revision conflict"):
        await locked_update_cell(notebook, "cell1", "x = 3", expected_revision=5)
    
    # Update with correct revision succeeds
    await locked_update_cell(notebook, "cell1", "x = 4", expected_revision=6)
    assert notebook.revision == 7


@pytest.mark.asyncio
async def test_concurrent_create_and_delete():
    """Test concurrent cell creation and deletion."""
    notebook = Notebook(
        id="test-create-delete",
        user_id="test-user",
        name="Test Notebook",
        cells=[],
        graph=Graph(),
        kernel=KernelState(globals_dict={"__builtins__": __builtins__})
    )
    
    # Create 10 cells concurrently
    async def create_cells():
        for i in range(10):
            await locked_create_cell(notebook, CellType.PYTHON, f"x{i} = {i}")
    
    await create_cells()
    
    assert len(notebook.cells) == 10
    assert notebook.revision == 10
```

### Success Criteria

#### Automated Verification

- [ ] All unit tests pass: `cd backend && pytest tests/`
- [ ] New concurrency tests pass: `cd backend && pytest tests/test_concurrency.py -v`
- [ ] No linting errors: `cd backend && mypy . --exclude venv`
- [ ] Load test: 100 concurrent cell updates complete without data loss
- [ ] Atomic save test: Kill process during save, verify file is not corrupted

#### Manual Verification

- [ ] Open notebook in two browser tabs, edit same cell simultaneously → last write wins, no corruption
- [ ] Delete cell while cell is executing → no kernel corruption, dependent cells blocked
- [ ] Update cell while scheduler is reading graph → no crashes, execution continues correctly
- [ ] Check file integrity: All `.json` files in `notebooks/` directory are valid JSON (no `.tmp` files left behind)

---

## Phase 2: LLM Tool Interface (Week 2)

### Overview

Implement 5 tools that allow the LLM to interact with notebooks: `get_notebook_state`, `create_cell`, `update_cell`, `run_cell`, `delete_cell`. All tools use the locked operations from Phase 1.

### Changes Required

#### 1. Implement Output Preview Function

**File**: `backend/llm_tools.py` (NEW)  
**Changes**: Create lightweight output previews for LLM context

```python
"""
LLM tool implementations for notebook operations.
All tools use locked operations for thread safety.
"""
from typing import Dict, List, Optional
from models import Cell, CellType, CellStatus, Notebook
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
```

#### 2. Implement get_notebook_state Tool

**File**: `backend/llm_tools.py` (continued)

```python
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
```

#### 3. Implement Cell Mutation Tools

**File**: `backend/llm_tools.py` (continued)

```python
async def tool_update_cell(
    notebook: Notebook,
    cell_id: str,
    code: str,
    broadcaster
) -> dict:
    """Update a cell's code."""
    try:
        cell = await locked_update_cell(notebook, cell_id, code)
        
        # Broadcast update
        await broadcaster.broadcast_cell_updated(
            notebook.id,
            cell.id,
            cell.code,
            cell.type.value,
            list(cell.reads),
            list(cell.writes)
        )
        
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
        
        # Broadcast creation
        await broadcaster.broadcast_cell_created(
            notebook.id,
            cell.id,
            cell.type.value,
            cell.code,
            list(cell.reads),
            list(cell.writes)
        )
        
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
```

#### 4. Implement Run Cell Tool with Timeout

**File**: `backend/llm_tools.py` (continued)

```python
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
```

#### 5. Define Anthropic Tool Schemas

**File**: `backend/llm_tools.py` (continued)

```python
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
```

#### 6. Add Tool Tests

**File**: `backend/tests/test_llm_tools.py` (NEW)

```python
import pytest
import asyncio
from backend.models import Notebook, Cell, CellType, CellStatus, Graph, KernelState
from backend.llm_tools import (
    tool_get_notebook_state,
    tool_create_cell,
    tool_update_cell,
    tool_run_cell,
    tool_delete_cell
)


class MockBroadcaster:
    """Mock broadcaster for testing."""
    async def broadcast_cell_created(self, *args, **kwargs):
        pass
    
    async def broadcast_cell_updated(self, *args, **kwargs):
        pass
    
    async def broadcast_cell_deleted(self, *args, **kwargs):
        pass


@pytest.fixture
def notebook():
    """Create test notebook."""
    return Notebook(
        id="test-notebook",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            Cell(
                id="cell1",
                type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.SUCCESS,
                reads=set(),
                writes={"x"}
            )
        ],
        graph=Graph(),
        kernel=KernelState(globals_dict={"__builtins__": __builtins__, "x": 1})
    )


@pytest.fixture
def broadcaster():
    return MockBroadcaster()


@pytest.mark.asyncio
async def test_get_notebook_state(notebook):
    """Test retrieving notebook state."""
    state = await tool_get_notebook_state(notebook)
    
    assert state["cell_count"] == 1
    assert len(state["cells"]) == 1
    assert state["cells"][0]["id"] == "cell1"
    assert state["cells"][0]["code"] == "x = 1"
    assert state["execution_in_progress"] is False


@pytest.mark.asyncio
async def test_create_cell(notebook, broadcaster):
    """Test creating a new cell."""
    result = await tool_create_cell(
        notebook,
        "python",
        "y = 2",
        None,
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert "cell_id" in result
    assert len(notebook.cells) == 2
    assert notebook.revision == 1


@pytest.mark.asyncio
async def test_update_cell(notebook, broadcaster):
    """Test updating a cell."""
    result = await tool_update_cell(
        notebook,
        "cell1",
        "x = 10",
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert notebook.cells[0].code == "x = 10"
    assert notebook.revision == 1


@pytest.mark.asyncio
async def test_delete_cell(notebook, broadcaster):
    """Test deleting a cell."""
    result = await tool_delete_cell(
        notebook,
        "cell1",
        broadcaster
    )
    
    assert result["status"] == "ok"
    assert len(notebook.cells) == 0
    assert notebook.revision == 1
    assert "x" not in notebook.kernel.globals_dict
```

### Success Criteria

#### Automated Verification

- [ ] Tool tests pass: `cd backend && pytest tests/test_llm_tools.py -v`
- [ ] All previous tests still pass: `cd backend && pytest tests/`
- [ ] Type checking passes: `cd backend && mypy llm_tools.py`
- [ ] Output preview function handles all MIME types (plotly, image, html, text)

#### Manual Verification

- [ ] Call `tool_get_notebook_state` on demo notebook → returns all cells with previews
- [ ] Call `tool_create_cell` → new cell appears in notebook
- [ ] Call `tool_update_cell` → cell code updates, dependencies recomputed
- [ ] Call `tool_run_cell` on fast cell (< 1s) → returns success with output
- [ ] Call `tool_run_cell` on slow cell (5-10s) → waits and returns success
- [ ] Call `tool_run_cell` on cell with error → returns error message
- [ ] Call `tool_delete_cell` → cell removed, variables cleared from kernel
- [ ] Verify revision increments after each mutation tool call

---

## Phase 3: Streaming & Chat Endpoint (Week 3)

### Overview

Implement SSE chat endpoint using native Anthropic SDK for streaming LLM responses with tool execution.

### Changes Required

#### 1. Add Dependencies

**File**: `backend/requirements.txt`  
**Changes**: Add Anthropic and SSE libraries

```
anthropic==0.39.0
sse-starlette==2.1.0
```

#### 2. Create Audit Logging Module

**File**: `backend/audit.py` (NEW)

```python
"""Audit logging for LLM actions."""
import json
import logging
from datetime import datetime
from pathlib import Path

AUDIT_LOG_DIR = Path("logs/audit")
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("llm_audit")
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(AUDIT_LOG_DIR / "llm_actions.log")
fh.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(fh)


def log_llm_action(
    notebook_id: str,
    user_id: str,
    action: str,
    details: dict
):
    """Log LLM action for audit trail."""
    logger.info(json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "notebook_id": notebook_id,
        "user_id": user_id,
        "action": action,
        "details": details
    }))
```

#### 3. Implement SSE Chat Endpoint

**File**: `backend/chat.py` (NEW)

```python
"""
LLM chat endpoint with Server-Sent Events streaming.
"""
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from typing import List
import json
import os

from routes import get_current_user_dependency, NOTEBOOKS, scheduler, broadcaster
from llm_tools import TOOL_SCHEMAS, execute_tool, tool_get_notebook_state
from audit import log_llm_action

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/chat/{notebook_id}")
async def chat_with_notebook(
    notebook_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    """
    Stream LLM chat responses with tool execution.
    Uses Server-Sent Events for streaming.
    """
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    async def event_generator():
        """Generate SSE events for chat stream."""
        client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Convert messages to Anthropic format
        anthropic_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        # Build system prompt with notebook context
        notebook_state = await tool_get_notebook_state(notebook, include_outputs=False)
        
        system_prompt = f"""You are an AI assistant helping with a reactive Python/SQL notebook.

Current notebook: "{notebook.name or 'Untitled'}"
Number of cells: {len(notebook_state['cells'])}

Available tools:
- get_notebook_state: See all cells and their outputs
- create_cell: Add new Python or SQL cells
- update_cell: Modify existing cell code
- run_cell: Execute a cell (waits up to 30s for completion)
- delete_cell: Remove a cell

Important:
- Always use get_notebook_state first to understand the current state
- When creating data analysis code, use pandas for data manipulation and plotly for visualization
- For SQL cells, use {{variable}} syntax to reference Python variables
- Be concise and helpful
- If a cell fails, read the error and suggest fixes

Cell statuses:
- idle: Not executed yet
- running: Currently executing
- success: Executed successfully
- error: Execution failed
- blocked: Waiting for dependencies
"""
        
        try:
            # Stream from Anthropic with tools
            async with client.messages.stream(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=anthropic_messages,
                tools=TOOL_SCHEMAS,
                system=system_prompt
            ) as stream:
                # Stream text deltas
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "text":
                            yield {
                                "event": "text_start",
                                "data": json.dumps({})
                            }
                        elif event.content_block.type == "tool_use":
                            yield {
                                "event": "tool_start",
                                "data": json.dumps({
                                    "tool_id": event.content_block.id,
                                    "tool_name": event.content_block.name
                                })
                            }
                    
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield {
                                "event": "text_delta",
                                "data": json.dumps({
                                    "text": event.delta.text
                                })
                            }
                    
                    elif event.type == "content_block_stop":
                        yield {
                            "event": "content_block_stop",
                            "data": json.dumps({})
                        }
                
                # Get final message to execute tools
                final_message = await stream.get_final_message()
                
                # Execute all tool calls
                tool_results = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        yield {
                            "event": "tool_execute",
                            "data": json.dumps({
                                "tool_name": block.name,
                                "tool_input": block.input
                            })
                        }
                        
                        # Log tool execution
                        log_llm_action(
                            notebook_id=notebook_id,
                            user_id=user_id,
                            action=f"tool_{block.name}",
                            details=block.input
                        )
                        
                        # Execute tool (with locks!)
                        result = await execute_tool(
                            block.name,
                            block.input,
                            notebook,
                            scheduler,
                            broadcaster
                        )
                        
                        tool_results.append({
                            "tool_use_id": block.id,
                            "result": result
                        })
                        
                        yield {
                            "event": "tool_result",
                            "data": json.dumps({
                                "tool_name": block.name,
                                "result": result
                            })
                        }
                
                # If tools were used, continue conversation with results
                if tool_results:
                    # Follow-up message with tool results
                    follow_up_messages = anthropic_messages + [
                        {
                            "role": "assistant",
                            "content": final_message.content
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tr["tool_use_id"],
                                    "content": json.dumps(tr["result"])
                                }
                                for tr in tool_results
                            ]
                        }
                    ]
                    
                    # Stream follow-up response
                    async with client.messages.stream(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=4096,
                        messages=follow_up_messages,
                        tools=TOOL_SCHEMAS,
                        system=system_prompt
                    ) as follow_stream:
                        yield {
                            "event": "follow_up_start",
                            "data": json.dumps({})
                        }
                        
                        async for event in follow_stream:
                            if event.type == "content_block_delta":
                                if event.delta.type == "text_delta":
                                    yield {
                                        "event": "text_delta",
                                        "data": json.dumps({
                                            "text": event.delta.text
                                        })
                                    }
                
                # End of stream
                yield {
                    "event": "done",
                    "data": json.dumps({})
                }
        
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(e)
                })
            }
    
    return EventSourceResponse(event_generator())
```

#### 4. Register Chat Router

**File**: `backend/main.py`  
**Changes**: Add chat router

```python
from chat import router as chat_router

# After existing router registration
app.include_router(chat_router, prefix="/api", tags=["chat"])
```

#### 5. Add Environment Variable

**File**: `.env` (add if not exists)  
**Changes**: Add Anthropic API key

```
ANTHROPIC_API_KEY=sk-ant-...
CLERK_SECRET_KEY=...
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Success Criteria

#### Automated Verification

- [ ] Dependencies install: `cd backend && pip install -r requirements.txt`
- [ ] Type checking passes: `cd backend && mypy chat.py`
- [ ] Import check: `cd backend && python -c "import anthropic; import sse_starlette"`
- [ ] Audit log directory created: `ls -la logs/audit/`

#### Manual Verification

- [ ] Start backend with `ANTHROPIC_API_KEY` set
- [ ] Use `curl` to test SSE endpoint:
  ```bash
  curl -N -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Create a cell that prints hello"}]}' \
    http://localhost:8000/api/chat/<notebook_id>
  ```
- [ ] Verify streaming events received: `text_start`, `text_delta`, `tool_start`, `tool_execute`, `tool_result`, `done`
- [ ] Verify tool execution: New cell created in notebook
- [ ] Check audit log: `cat logs/audit/llm_actions.log` shows tool execution
- [ ] Test error handling: Invalid notebook ID returns 404
- [ ] Test auth: Missing token returns 401

---

## Phase 4: Frontend Integration (Week 4)

### Overview

Build React ChatPanel component with SSE streaming and integrate with existing notebook UI.

### Changes Required

#### 1. Create ChatPanel Component

**File**: `frontend/src/components/ChatPanel.tsx` (NEW)

```typescript
import React, { useState, useRef, useEffect } from 'react';

interface ToolCall {
  tool: string;
  input: any;
  result?: any;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
}

interface ChatPanelProps {
  notebookId: string;
  isLLMWorking: boolean;
  onLLMWorkingChange: (working: boolean) => void;
}

export function ChatPanel({ notebookId, isLLMWorking, onLLMWorkingChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hi! I can help you with this notebook. I can create cells, run code, and analyze data.',
    },
  ]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);
    onLLMWorkingChange(true);

    // Create assistant message (will stream content into it)
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      toolCalls: [],
    };
    setMessages((prev) => [...prev, assistantMessage]);

    // Create abort controller for cancellation
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/chat/${notebookId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.event === 'text_delta') {
                // Append text to assistant message
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  lastMsg.content += data.data.text;
                  return updated;
                });
              } else if (data.event === 'tool_execute') {
                // Show tool execution
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  if (!lastMsg.toolCalls) lastMsg.toolCalls = [];
                  lastMsg.toolCalls.push({
                    tool: data.data.tool_name,
                    input: data.data.tool_input,
                  });
                  return updated;
                });
              } else if (data.event === 'tool_result') {
                // Update tool result
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  if (lastMsg.toolCalls) {
                    const lastTool = lastMsg.toolCalls[lastMsg.toolCalls.length - 1];
                    lastTool.result = data.data.result;
                  }
                  return updated;
                });
              } else if (data.event === 'error') {
                // Handle error
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1].content += `\n\n❌ Error: ${data.data.error}`;
                  return updated;
                });
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', line, e);
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('Chat request aborted');
      } else {
        console.error('Chat error:', error);
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1].content = `Error: ${error.message}`;
          return updated;
        });
      }
    } finally {
      setIsStreaming(false);
      onLLMWorkingChange(false);
      abortControllerRef.current = null;
    }
  };

  const stopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  return (
    <div className="flex flex-col h-full border-l border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold">AI Assistant</h2>
        {isLLMWorking && (
          <div className="flex items-center gap-2 mt-1 text-sm text-blue-600">
            <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse" />
            Working...
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>

              {/* Tool calls */}
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="mt-2 space-y-1">
                  {msg.toolCalls.map((tool, i) => (
                    <div
                      key={i}
                      className="text-xs bg-white dark:bg-gray-900 rounded p-2 text-gray-800 dark:text-gray-200"
                    >
                      <div className="font-mono font-semibold">
                        🔧 {tool.tool}
                      </div>
                      {tool.result && (
                        <div className="mt-1">
                          {tool.result.status === 'ok' && (
                            <span className="text-green-600">✓ Success</span>
                          )}
                          {tool.result.status === 'error' && (
                            <span className="text-red-600">✗ {tool.result.error}</span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isStreaming}
            placeholder="Ask me anything about this notebook..."
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={stopGeneration}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
```

#### 2. Update Notebook Component

**File**: `frontend/src/components/Notebook.tsx`  
**Changes**: Integrate ChatPanel

```typescript
import { ChatPanel } from './ChatPanel';
import { useState } from 'react';

export function Notebook({ notebookId, cells, ... }: NotebookProps) {
  const [isLLMWorking, setIsLLMWorking] = useState(false);
  const [showChat, setShowChat] = useState(true);
  
  return (
    <div className="flex h-screen">
      {/* Left: Notebook */}
      <div className={`flex-1 overflow-auto ${isLLMWorking ? 'opacity-50' : ''}`}>
        {/* Existing notebook UI */}
        <div className="p-4">
          {cells.map(cell => (
            <Cell 
              key={cell.id}
              cell={cell}
              disabled={isLLMWorking}
              onRun={() => runCell(cell.id)}
              onUpdate={(code) => updateCell(cell.id, code)}
              onDelete={() => deleteCell(cell.id)}
            />
          ))}
        </div>
        
        {/* LLM Working Overlay */}
        {isLLMWorking && (
          <div className="fixed top-4 right-4 bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700 rounded-lg px-4 py-2 shadow-lg">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-blue-600 rounded-full animate-pulse" />
              <span className="text-sm font-medium">AI Assistant is working...</span>
            </div>
          </div>
        )}
      </div>
      
      {/* Right: Chat Panel */}
      {showChat && (
        <div className="w-96">
          <ChatPanel
            notebookId={notebookId}
            isLLMWorking={isLLMWorking}
            onLLMWorkingChange={setIsLLMWorking}
          />
        </div>
      )}
      
      {/* Toggle Chat Button */}
      <button
        onClick={() => setShowChat(!showChat)}
        className="fixed bottom-4 right-4 bg-blue-600 text-white rounded-full p-3 shadow-lg hover:bg-blue-700"
      >
        {showChat ? '✕' : '💬'}
      </button>
    </div>
  );
}
```

#### 3. Update Cell Component

**File**: `frontend/src/components/Cell.tsx`  
**Changes**: Add disabled prop

```typescript
interface CellProps {
  cell: Cell;
  disabled?: boolean;
  onRun: () => void;
  onUpdate: (code: string) => void;
  onDelete: () => void;
}

export function Cell({ cell, disabled = false, onRun, onUpdate, onDelete }: CellProps) {
  return (
    <div className={`cell ${disabled ? 'pointer-events-none' : ''}`}>
      {/* Existing cell UI */}
      <button
        onClick={onRun}
        disabled={disabled || cell.status === 'running'}
        className="run-button"
      >
        {cell.status === 'running' ? 'Running...' : 'Run'}
      </button>
      {/* ... rest of cell UI */}
    </div>
  );
}
```

### Success Criteria

#### Automated Verification

- [ ] TypeScript compiles: `cd frontend && npm run build`
- [ ] No linting errors: `cd frontend && npm run lint`
- [ ] Type checking passes: `cd frontend && npm run typecheck`

#### Manual Verification

- [ ] Open notebook in browser → Chat panel visible on right side
- [ ] Send message "Create a cell that prints hello" → LLM responds and creates cell
- [ ] Verify notebook greyed out while LLM working
- [ ] Verify "AI Assistant is working..." overlay appears
- [ ] Verify new cell appears in notebook (via WebSocket)
- [ ] Verify tool executions show in chat (🔧 create_cell ✓)
- [ ] Test stop generation button → aborts SSE stream
- [ ] Toggle chat panel button → panel hides/shows
- [ ] Test on mobile → chat panel responsive
- [ ] Test dark mode → chat panel theme adapts

---

## Testing Strategy

### Unit Tests

**Backend**:
- `test_concurrency.py` - Concurrent mutation tests
- `test_llm_tools.py` - Tool function tests
- `test_notebook_operations.py` - Locked operation tests

**Key Edge Cases**:
- Revision conflicts (optimistic locking)
- Cell not found errors
- Tool execution timeout
- Dependency cycles
- Failed dependency blocking

### Integration Tests

**File**: `tests/integration-test.sh`  
**Add LLM integration test**:

```bash
#!/bin/bash
# Test LLM chat endpoint end-to-end

# 1. Start backend
# 2. Create notebook via API
# 3. Send chat message via SSE
# 4. Verify tool execution creates cell
# 5. Verify WebSocket broadcasts update
# 6. Cleanup
```

### Manual Testing Checklist

**Concurrency**:
- [ ] Open notebook in 2 tabs, edit same cell → no data loss
- [ ] User updates cell while LLM updates same cell → conflict handled
- [ ] User deletes cell while scheduler executes it → no crash

**LLM Tools**:
- [ ] LLM creates Python cell → cell appears with correct code
- [ ] LLM creates SQL cell → dependencies extracted correctly
- [ ] LLM updates cell → dependencies recomputed
- [ ] LLM runs cell → waits for completion, returns output
- [ ] LLM runs cell that errors → returns error message
- [ ] LLM runs long cell (> 5s) → waits, then returns
- [ ] LLM runs very long cell (> 30s) → timeout message
- [ ] LLM deletes cell → variables removed from kernel

**Streaming**:
- [ ] Chat streams text character-by-character
- [ ] Tool executions show in real-time
- [ ] Network interruption → graceful error
- [ ] Stop generation button → aborts stream

**UI/UX**:
- [ ] Notebook greys out during LLM work
- [ ] "AI Assistant is working..." overlay shows
- [ ] Run button disabled during LLM work
- [ ] User can still scroll and view cells
- [ ] Chat panel scrolls to bottom on new messages
- [ ] Tool calls render correctly in chat

### Performance Testing

**Load Test**:
- 100 concurrent chat requests → no errors
- 10 concurrent tool executions on same notebook → all succeed (queued by lock)
- Large notebook (100 cells) → get_notebook_state returns in < 1s

**Token Usage**:
- Verify output previews reduce token count (measure with/without previews)
- Large plotly chart → preview is < 100 tokens

---

## Migration Notes

### From Previous System to New System

**No database migration required** - using file-based storage.

**Existing notebooks compatibility**:
- Notebooks without `revision` field → defaults to 0
- Notebooks will gain `_lock` field on load (non-serialized)

**Deployment**:
1. Deploy Phase 1 first (concurrency fixes)
2. Verify no regressions with existing notebooks
3. Deploy Phase 2-3 (LLM features)
4. Gradually roll out to users

### Rollback Plan

**If issues arise**:
1. Set `ANTHROPIC_API_KEY` to empty → disables chat endpoint
2. Remove chat router from `main.py` → endpoint unavailable
3. Revert to previous version if needed

**Phase 1 cannot be rolled back** - concurrency fixes are critical and should remain.

---

## References

- **Research Document**: `thoughts/shared/research/2025-12-28-llm-assistant-integration-architecture.md`
- **Current Codebase**:
  - `backend/models.py:78-87` - Notebook model
  - `backend/scheduler.py:18-102` - Current scheduler with locks
  - `backend/storage.py:12-34` - Non-atomic file saves
  - `backend/routes.py:309-390` - Mutation endpoints
- **Anthropic Docs**: https://docs.anthropic.com/claude/docs/tool-use
- **SSE Starlette**: https://github.com/sysid/sse-starlette

