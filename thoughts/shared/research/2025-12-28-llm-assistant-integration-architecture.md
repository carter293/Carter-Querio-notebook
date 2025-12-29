---
date: 2025-12-28T17:08:10Z
researcher: Claude
topic: "LLM Assistant Integration Architecture for Reactive Notebook"
tags: [research, codebase, llm-integration, sse, anthropic, concurrency, architecture]
status: complete
last_updated: 2025-12-29
last_updated_by: Claude
decisions_finalized: 2025-12-29
---

# Research: LLM Assistant Integration Architecture for Reactive Notebook

**Date**: 2025-12-28T17:08:10Z
**Researcher**: Claude

## Research Question

How should we implement an LLM assistant with tool-calling capabilities that can interact with the reactive notebook, allowing both the LLM and user to modify cells safely without race conditions or critical errors? The assistant should use simple tool calls (like "update cell", "run cell") and work harmoniously with the frontend display, potentially using the Vercel AI SDK with FastAPI backend.

## Summary

The current reactive notebook implementation has **significant concurrency vulnerabilities** that must be addressed before adding LLM tool calls. The existing architecture uses:
- Per-notebook asyncio locks for execution queue management only
- No protection for notebook state (cells, graph, kernel) during mutations
- WebSocket-based real-time synchronization between frontend and backend
- File-based persistence without atomic write guarantees

**Critical Finding**: Adding LLM tool calls without implementing proper locking will cause:
1. Lost updates when LLM and user modify cells simultaneously
2. Race conditions during graph rebuilding while scheduler reads dependencies
3. Kernel state corruption when variables are deleted during execution
4. Inconsistent WebSocket message ordering to clients

**Final Recommended Architecture** (Decisions Finalized):
1. **Concurrency**: Implement notebook-level asyncio.Lock for all state mutations + optimistic locking with revision field
2. **Context Management**: `get_notebook_state` tool with lightweight MIME previews (not full images)
3. **Tool Execution**: LLM tools wait for cell completion (30s timeout with graceful handling)
4. **Conflict Resolution**: Grey out UI during LLM work + last-write-wins with undo notifications
5. **Access Control**: Broad LLM access (can create/update/delete/run cells) with audit logging
6. **Streaming**: Native Anthropic SDK + SSE (via `sse-starlette`), NOT Vercel AI SDK due to FastAPI compatibility issues

## Detailed Findings

### Current State Management Architecture

**Backend State Container**
- [backend/models.py](../../../backend/models.py) - Core data models
  - `Notebook` dataclass: cells list, dependency graph, kernel state, revision number
  - `Cell` dataclass: id, type, code, status, reads/writes sets
  - `Graph` dataclass: edges, reverse_edges for dependency tracking
  - `KernelState`: globals_dict shared across all cells

**State Mutation Endpoints**
- [backend/routes.py](../../../backend/routes.py) - All REST API endpoints
  - `POST /api/notebooks/{id}/cells` - Create cell (line 271)
  - `PUT /api/notebooks/{id}/cells/{cell_id}` - Update cell code (line 309)
  - `DELETE /api/notebooks/{id}/cells/{cell_id}` - Delete cell (line 363)
  - `WS /api/ws/notebooks/{id}` - WebSocket for execution (line 398)

**Real-time Synchronization**
- [backend/websocket.py](../../../backend/websocket.py) - WebSocket broadcaster
  - Broadcasts: cell_updated, cell_created, cell_deleted, cell_status, cell_stdout, cell_error, cell_output
  - No message ordering guarantees

**Frontend State Management**
- [frontend/src/components/Notebook.tsx](../../../frontend/src/components/Notebook.tsx) - React useState hooks
- [frontend/src/useWebSocket.ts](../../../frontend/src/useWebSocket.ts) - WebSocket connection management
- **Pattern**: No centralized state library, single source of truth in backend, optimistic updates via WebSocket

### Concurrency Analysis: Current Protection Mechanisms

**What Is Protected**
- [backend/scheduler.py:18](../../../backend/scheduler.py#L18) - Per-notebook asyncio.Lock
  ```python
  self.locks: Dict[str, asyncio.Lock] = {}  # notebook_id -> lock
  ```
- Protected operations:
  - Adding cells to `pending_runs` queue (line 29-33)
  - Checking if execution task is running (line 35-37)
  - Creating execution task (line 39-42)
  - Draining queue (line 51-58)

**What Is NOT Protected**
- Reading `notebook.cells` during iteration (scheduler.py:82-102)
- Reading `notebook.graph` during topological sort (scheduler.py:63-75)
- Writing `cell.code`, `cell.status` in update endpoint (routes.py:332-333)
- Calling `rebuild_graph(notebook)` (routes.py:344)
- Modifying `notebook.kernel.globals_dict` (routes.py:385-387)
- File I/O in `save_notebook()` (storage.py:12-34)

### Race Condition Scenarios

**Scenario 1: User Updates Cell While Executing**
1. User triggers execution via WebSocket at [routes.py:428](../../../backend/routes.py#L428)
2. Scheduler sets `cell.status = RUNNING` at [scheduler.py:113](../../../backend/scheduler.py#L113)
3. User updates cell code via `PUT /api/notebooks/{id}/cells/{cell_id}`
4. Update handler sets `cell.status = IDLE` at [routes.py:333](../../../backend/routes.py#L333)
5. Execution completes and overwrites result
6. **Result**: Cell shows IDLE status with execution output, or mixed state

**Scenario 2: Dependency Graph Modified During Execution**
1. Scheduler calls `topological_sort(notebook.graph, all_to_run)` at [scheduler.py:68](../../../backend/scheduler.py#L68)
2. User updates different cell's code
3. Update calls `rebuild_graph(notebook)` at [routes.py:344](../../../backend/routes.py#L344)
4. `rebuild_graph` clears and rebuilds graph edges in [graph.py:9-19](../../../backend/graph.py#L9-L19)
5. **Result**: Topological sort operates on partially-updated graph, may miss dependencies

**Scenario 3: Kernel Globals Deleted During Execution**
1. Scheduler executes cell A which writes `globals_dict['x'] = 1`
2. User deletes cell A via `DELETE /api/notebooks/{id}/cells/{cell_id}`
3. Delete handler pops variables from globals at [routes.py:387](../../../backend/routes.py#L387)
4. Cell B executes and tries to read `x`
5. **Result**: NameError because variable was removed mid-execution

**Scenario 4: File I/O Race (Lost Updates)**
1. User thread calls `save_notebook()` at [routes.py:353](../../../backend/routes.py#L353)
2. LLM tool thread calls `save_notebook()` for same notebook
3. Both serialize notebook state to JSON at [storage.py:14-28](../../../backend/storage.py#L14-L28)
4. Both write to same file path at [storage.py:30-32](../../../backend/storage.py#L30-L32)
5. **Result**: Last write wins, losing one set of updates

### Reactive Execution System

**Dependency Tracking via AST Analysis**
- [backend/ast_parser.py](../../../backend/ast_parser.py) - Variable dependency extraction
  - `extract_dependencies()` - Parses Python AST to find reads/writes
  - `VariableVisitor` class - Tracks variable loads (reads) and stores (writes)
  - `extract_sql_dependencies()` - Finds `{variable}` placeholders in SQL

**Dependency Graph Construction**
- [backend/graph.py:9-19](../../../backend/graph.py#L9-L19) - `rebuild_graph()`
  ```python
  def rebuild_graph(notebook):
      graph = Graph()
      for cell in notebook.cells:
          for var in cell.reads:
              for other_cell in notebook.cells:
                  if var in other_cell.writes:
                      graph.edges[other_cell.id].add(cell.id)
                      graph.reverse_edges[cell.id].add(other_cell.id)
  ```
  - **Issue**: No locking, called from update_cell endpoint while scheduler may be reading

**Reactive Execution Flow**
1. User edits cell → `PUT /api/notebooks/{id}/cells/{cell_id}` endpoint
2. Extract dependencies via AST at [routes.py:336-338](../../../backend/routes.py#L336-L338)
3. Rebuild graph at [routes.py:344](../../../backend/routes.py#L344)
4. Save and broadcast update
5. **Separate action**: User triggers execution via WebSocket message
6. Scheduler enqueues cell + all dependents at [scheduler.py:60-62](../../../backend/scheduler.py#L60-L62)
7. Topological sort orders cells at [scheduler.py:68](../../../backend/scheduler.py#L68)
8. Execute cells sequentially at [scheduler.py:81-102](../../../backend/scheduler.py#L81-L102)

### Frontend-Backend Communication

**REST API (Mutations)**
- [frontend/src/api-client.ts](../../../frontend/src/api-client.ts) - API wrapper over generated client
- [frontend/src/client/](../../../frontend/src/client/) - Auto-generated from OpenAPI spec
- Authentication: Bearer token in Authorization header
- Endpoints:
  - `POST /api/notebooks` - Create notebook
  - `GET /api/notebooks` - List notebooks
  - `POST /api/notebooks/{id}/cells` - Create cell
  - `PUT /api/notebooks/{id}/cells/{cell_id}` - Update cell
  - `DELETE /api/notebooks/{id}/cells/{cell_id}` - Delete cell

**WebSocket (Real-time Updates & Execution)**
- [frontend/src/useWebSocket.ts](../../../frontend/src/useWebSocket.ts) - Custom React hook
- URL Pattern: `ws://[host]/api/ws/notebooks/{notebook_id}`
- Message Types (Client → Server):
  - `{"type": "run_cell", "cellId": "..."}` - Trigger execution
- Message Types (Server → Client):
  - `cell_updated`, `cell_created`, `cell_deleted` - Cell CRUD events
  - `cell_status` - Execution status (running, success, error, blocked)
  - `cell_stdout`, `cell_error`, `cell_output` - Execution results

**Communication Pattern**
- User action → REST API mutation → WebSocket broadcast confirmation → UI update
- No optimistic UI updates, WebSocket is source of truth
- Frontend uses auto-reconnect with exponential backoff

### Execution Engine

**Python Execution**
- [backend/executor.py:13-89](../../../backend/executor.py#L13-L89) - `execute_python_cell()`
- Uses Python's `exec()` and `eval()` in shared `globals_dict`
- Output capture via `io.StringIO` with `contextlib.redirect_stdout`
- No sandboxing or isolation
- Supports expressions (last line evaluated) and statements

**SQL Execution**
- [backend/executor.py:92-129](../../../backend/executor.py#L92-L129) - `execute_sql_cell()`
- Variable substitution: `{variable}` → `globals_dict['variable']`
- PostgreSQL via `asyncpg.connect()`
- Returns table format (columns + rows)

**Kernel State Management**
- [backend/models.py:74-75](../../../backend/models.py#L74-L75) - `KernelState` dataclass
- Single `globals_dict` shared across all cells in notebook
- Initialized with `__builtins__`
- **Issue**: No locking when reading/writing during execution or deletion

## Architecture Insights

### Current Strengths
1. **Clean separation of concerns**: State management, execution, communication well-separated
2. **Reactive execution**: Automatic dependency tracking and re-execution
3. **Real-time synchronization**: WebSocket keeps all clients in sync
4. **Type safety**: OpenAPI-generated TypeScript client ensures type correctness
5. **Sequential execution**: One cell at a time per notebook prevents concurrent execution issues

### Critical Weaknesses for LLM Integration
1. **No notebook-level locking**: Multiple actors can mutate cells/graph simultaneously
2. **No optimistic locking**: No conflict detection using `revision` field
3. **Non-atomic file saves**: `save_notebook()` can corrupt state with concurrent writes
4. **Unprotected graph access**: Scheduler reads graph while update endpoint rebuilds it
5. **No WebSocket authentication**: Current WebSocket endpoint has no auth (noted in code)
6. **No message ordering**: WebSocket broadcasts don't guarantee order

### Existing Patterns to Leverage
1. **Revision field**: Already present in Notebook model, can be used for optimistic locking
2. **Broadcaster pattern**: WebSocketBroadcaster can notify LLM assistant of changes
3. **Asyncio-based**: Already async, can add async locks without major refactor
4. **Stateless endpoints**: REST endpoints are stateless, easy to add locking

## Recommended LLM Integration Architecture

### Option 1: Vercel AI SDK with Server-Side Tools (Recommended)

**Architecture Overview**
```
Frontend (React)
  ↓ Vercel AI SDK useChat hook
  ↓ POST /api/chat (streaming)
Backend (FastAPI)
  → streamText with server-side tools
  → Tools call notebook operations with LOCKS
  → Notebook mutations → WebSocket broadcast
  → Stream LLM response + tool results to frontend
```

**Implementation Steps**

1. **Add Notebook-Level Lock**
   ```python
   # backend/models.py
   @dataclass
   class Notebook:
       # ... existing fields
       _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
   ```

2. **Create Locked Notebook Operations Module**
   ```python
   # backend/notebook_operations.py
   async def locked_update_cell(notebook: Notebook, cell_id: str, code: str):
       async with notebook._lock:
           cell = next((c for c in notebook.cells if c.id == cell_id), None)
           if not cell:
               raise ValueError("Cell not found")
           cell.code = code
           if cell.type == CellType.PYTHON:
               reads, writes = extract_dependencies(code)
               cell.reads = reads
               cell.writes = writes
           rebuild_graph(notebook)
           notebook.revision += 1
           save_notebook(notebook)
           return cell

   async def locked_create_cell(notebook: Notebook, cell_type: CellType, code: str, index: int):
       async with notebook._lock:
           # ... create cell logic
           notebook.revision += 1
           save_notebook(notebook)
           return new_cell

   async def locked_run_cell(notebook: Notebook, cell_id: str, scheduler, broadcaster):
       # No lock needed - scheduler has its own lock for queue
       await scheduler.enqueue_run(notebook.id, cell_id, notebook, broadcaster)
   ```

3. **Update Existing Endpoints to Use Locks**
   ```python
   # backend/routes.py
   @router.put("/notebooks/{notebook_id}/cells/{cell_id}")
   async def update_cell(...):
       notebook = NOTEBOOKS[notebook_id]
       cell = await locked_update_cell(notebook, cell_id, request_body.code)
       await broadcaster.broadcast_cell_updated(...)
       return {"status": "ok"}
   ```

4. **Create LLM Tools Interface**
   ```python
   # backend/llm_tools.py
   from ai import tool
   from zod import z

   def create_notebook_tools(notebook_id: str):
       notebook = NOTEBOOKS[notebook_id]

       return {
           "updateCell": tool({
               "description": "Update a cell's code",
               "inputSchema": z.object({
                   "cellId": z.string(),
                   "code": z.string()
               }),
               "execute": async (input) => {
                   cell = await locked_update_cell(notebook, input["cellId"], input["code"])
                   await broadcaster.broadcast_cell_updated(notebook_id, cell.id, {...})
                   return {"status": "ok", "cellId": cell.id}
               }
           }),
           "createCell": tool({
               "description": "Create a new cell",
               "inputSchema": z.object({
                   "type": z.enum(["python", "sql"]),
                   "code": z.string(),
                   "index": z.number().optional()
               }),
               "execute": async (input) => {
                   cell = await locked_create_cell(...)
                   await broadcaster.broadcast_cell_created(...)
                   return {"cellId": cell.id}
               }
           }),
           "runCell": tool({
               "description": "Execute a cell",
               "inputSchema": z.object({
                   "cellId": z.string()
               }),
               "execute": async (input) => {
                   await locked_run_cell(notebook, input["cellId"], scheduler, broadcaster)
                   return {"status": "queued"}
               }
           }),
           "deleteCell": tool({
               "description": "Delete a cell",
               "inputSchema": z.object({
                   "cellId": z.string()
               }),
               "execute": async (input) => {
                   async with notebook._lock:
                       # ... delete logic
                   await broadcaster.broadcast_cell_deleted(...)
                   return {"status": "ok"}
               }
           })
       }
   ```

5. **Create Chat Endpoint**
   ```python
   # backend/routes.py
   from ai import streamText
   from llm_tools import create_notebook_tools

   @router.post("/chat/{notebook_id}")
   async def chat_with_notebook(
       notebook_id: str,
       messages: List[UIMessage],
       user_id: str = Depends(get_current_user_dependency)
   ):
       notebook = NOTEBOOKS.get(notebook_id)
       if not notebook:
           raise HTTPException(status_code=404)

       tools = create_notebook_tools(notebook_id)

       result = streamText({
           "model": anthropic("claude-3-5-sonnet-20241022"),
           "messages": await convertToModelMessages(messages),
           "tools": tools,
           "system": f"""You are an AI assistant helping with a reactive notebook.
           Current notebook state:
           - {len(notebook.cells)} cells
           - Cells: {[{{"id": c.id, "type": c.type, "code": c.code[:50]}} for c in notebook.cells]}

           You can create, update, run, and delete cells using your tools.
           Be careful to maintain valid Python/SQL syntax.
           """
       })

       return result.toUIMessageStreamResponse()
   ```

6. **Frontend Integration**
   ```typescript
   // frontend/src/components/ChatPanel.tsx
   import { useChat } from '@ai-sdk/react';

   export function ChatPanel({ notebookId }: { notebookId: string }) {
     const { messages, sendMessage, input, setInput } = useChat({
       api: `/api/chat/${notebookId}`,
       initialMessages: [
         { role: 'assistant', content: 'Hi! I can help you with this notebook.' }
       ]
     });

     return (
       <div>
         {messages.map(msg => (
           <div key={msg.id}>
             <strong>{msg.role}:</strong>
             {msg.parts.map(part => {
               if (part.type === 'text') return part.text;
               if (part.type === 'tool-updateCell') {
                 return <div>Updated cell {part.input.cellId}</div>;
               }
               // ... handle other tool types
             })}
           </div>
         ))}
         <form onSubmit={e => { e.preventDefault(); sendMessage({ text: input }); }}>
           <input value={input} onChange={e => setInput(e.target.value)} />
         </form>
       </div>
     );
   }
   ```

**Pros**
- Tool executions are server-side (safe, with locking)
- Streaming LLM responses to frontend
- Type-safe tool definitions
- Frontend sees tool executions via message parts
- WebSocket still broadcasts to all clients (user sees LLM changes in real-time)

**Cons**
- Requires Vercel AI SDK (or equivalent streaming AI library)
- FastAPI doesn't natively support Vercel AI SDK's Python version (would need custom integration)

### Option 2: FastAPI SSE Endpoint with Custom Tool Execution

**Architecture**
```
Frontend (React)
  ↓ POST /api/chat/{notebook_id} (SSE)
Backend (FastAPI)
  → Call LLM API (Anthropic/OpenAI)
  → Parse tool calls from response
  → Execute tools with LOCKS
  → Stream events to frontend via SSE
  → Notebook mutations → WebSocket broadcast
```

**Implementation**
```python
# backend/routes.py
from sse_starlette.sse import EventSourceResponse
import anthropic

@router.post("/chat/{notebook_id}")
async def chat_with_notebook_sse(
    notebook_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    notebook = NOTEBOOKS.get(notebook_id)

    async def event_generator():
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build tool definitions
        tools = [
            {
                "name": "updateCell",
                "description": "Update a cell's code",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cellId": {"type": "string"},
                        "code": {"type": "string"}
                    },
                    "required": ["cellId", "code"]
                }
            },
            # ... other tools
        ]

        # Call LLM with streaming
        async with client.messages.stream(
            model="claude-3-5-sonnet-20241022",
            messages=request.messages,
            tools=tools,
            max_tokens=4096
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    # Stream text delta
                    yield {"event": "text", "data": json.dumps({"delta": event.delta.text})}

                elif event.type == "message_stop":
                    # Execute tool calls
                    message = await stream.get_final_message()

                    for block in message.content:
                        if block.type == "tool_use":
                            # Execute tool with lock
                            if block.name == "updateCell":
                                cell = await locked_update_cell(
                                    notebook,
                                    block.input["cellId"],
                                    block.input["code"]
                                )
                                await broadcaster.broadcast_cell_updated(...)

                                yield {
                                    "event": "tool_result",
                                    "data": json.dumps({
                                        "tool": "updateCell",
                                        "result": {"status": "ok", "cellId": cell.id}
                                    })
                                }

    return EventSourceResponse(event_generator())
```

**Pros**
- No dependency on Vercel AI SDK
- Full control over tool execution
- Works with any LLM provider (Anthropic, OpenAI, etc.)
- FastAPI-native SSE support

**Cons**
- More manual work (parsing tool calls, managing conversation state)
- Need to implement retry logic, error handling manually
- Frontend needs custom SSE handling

### Option 3: WebSocket-Based Chat (Simple but Less Scalable)

**Architecture**
```
Frontend (React)
  ↓ WS /api/chat/{notebook_id}
Backend (FastAPI)
  → Receive message via WebSocket
  → Call LLM API
  → Execute tools with LOCKS
  → Send response via same WebSocket
  → Notebook mutations → broadcast to all WebSocket clients
```

**Pros**
- Simple implementation
- Reuses existing WebSocket infrastructure
- Bidirectional communication

**Cons**
- WebSocket per chat session (higher resource usage)
- No built-in authentication on current WebSocket endpoint
- Harder to manage conversation history

## Concurrency Solution: Required Changes

### 1. Add Notebook-Level Lock to All Mutations

**Before (Unsafe)**
```python
@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(...):
    notebook = NOTEBOOKS[notebook_id]
    cell.code = request_body.code  # RACE CONDITION
    rebuild_graph(notebook)  # RACE CONDITION
```

**After (Safe)**
```python
@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(...):
    notebook = NOTEBOOKS[notebook_id]
    async with notebook._lock:
        cell.code = request_body.code
        rebuild_graph(notebook)
        notebook.revision += 1
        save_notebook(notebook)
    await broadcaster.broadcast_cell_updated(...)
```

### 2. Implement Optimistic Locking

```python
@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(
    ...
    expected_revision: Optional[int] = None
):
    notebook = NOTEBOOKS[notebook_id]
    async with notebook._lock:
        if expected_revision is not None and notebook.revision != expected_revision:
            raise HTTPException(
                status_code=409,
                detail=f"Conflict: expected revision {expected_revision}, got {notebook.revision}"
            )

        # Perform mutation
        cell.code = request_body.code
        rebuild_graph(notebook)
        notebook.revision += 1
        save_notebook(notebook)

    return {"revision": notebook.revision}
```

### 3. Make File Saves Atomic

```python
# backend/storage.py
import tempfile
import os

def save_notebook(notebook: Notebook) -> None:
    data = {...}  # serialize notebook

    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"

    # Write to temp file first
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=NOTEBOOKS_DIR,
        delete=False,
        suffix='.tmp'
    ) as f:
        json.dump(data, f, indent=2)
        temp_path = f.name

    # Atomic rename
    os.replace(temp_path, file_path)
```

### 4. Coordinate Scheduler and Mutation Locks

**Issue**: Scheduler reads `notebook.graph` outside lock, update endpoint modifies graph

**Solution**: Scheduler should acquire notebook lock when reading graph

```python
# backend/scheduler.py
async def _drain_queue(self, notebook_id: str, notebook, broadcaster):
    while True:
        # Get pending cells (already uses scheduler lock)
        lock = self.get_lock(notebook_id)
        async with lock:
            if not self.pending_runs.get(notebook_id):
                break
            pending_cells = self.pending_runs[notebook_id].copy()
            self.pending_runs[notebook_id].clear()

        # Acquire notebook lock for graph access
        async with notebook._lock:
            all_to_run = set(pending_cells)
            for cell_id in pending_cells:
                dependents = get_all_dependents(notebook.graph, cell_id)
                all_to_run.update(dependents)

            try:
                sorted_cells = topological_sort(notebook.graph, all_to_run)
            except ValueError:
                # Handle cycle
                ...

        # Execute cells (release lock during execution to allow reads)
        for cell_id in sorted_cells:
            cell = self._get_cell(notebook, cell_id)
            await self._execute_cell(notebook_id, cell, notebook, broadcaster)
```

**Alternative**: Use read-write lock to allow concurrent reads but exclusive writes

## Open Questions - RESOLVED

### 1. LLM Context Management
**Decision**: Implement a `get_notebook_state` tool that returns cells and outputs on-demand

**Rationale**:
- After researching existing patterns (Context Conveyor pattern), the most practical approach is Option C: LLM queries notebook state via read-only tools
- Avoids token-heavy full state dumps in every request
- Simpler than streaming changes to LLM via WebSocket
- LLM can request updates when needed

**Implementation Details**:
```python
{
    "name": "get_notebook_state",
    "description": "Get current state of all cells including code, outputs, and execution status",
    "input_schema": {
        "type": "object",
        "properties": {
            "include_outputs": {"type": "boolean", "default": True},
            "cell_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional: specific cells to retrieve"}
        }
    }
}
```

**MIME Type Handling**:
- For images (plotly, matplotlib): Return base64-encoded PNG by default
- For text outputs: Return as-is
- For tables: Return as structured data (columns + rows)
- Add `output_preview` field with truncated text representation for context
- Full MIME data available but LLM receives lightweight preview

**Tool Response Format**:
```json
{
    "cells": [
        {
            "id": "cell-123",
            "type": "python",
            "code": "import pandas as pd\ndf = pd.read_csv('data.csv')",
            "status": "success",
            "execution_order": 1,
            "output_preview": "[DataFrame with 100 rows x 5 columns]",
            "output_type": "dataframe",
            "has_image": false,
            "reads": [],
            "writes": ["df"]
        },
        {
            "id": "cell-456",
            "type": "python",
            "code": "df.plot()",
            "status": "success",
            "execution_order": 2,
            "output_preview": "[Plotly chart: scatter plot]",
            "output_type": "plotly",
            "has_image": true,
            "image_url": "data:image/png;base64,...",  // Optional: small preview
            "reads": ["df"],
            "writes": []
        }
    ],
    "execution_in_progress": false,
    "current_executing_cell": null
}
```

### 2. Tool Execution Latency
**Decision**: LLM tools should wait for cell execution completion before returning

**Rationale**:
- Prevents LLM from continuing conversation without knowing execution results
- Allows LLM to see errors and adjust approach
- User experience: LLM says "Running cell..." then reports success/failure
- Implementation: `run_cell` tool uses `asyncio.wait_for()` with timeout

**Implementation**:
```python
async def locked_run_cell(notebook: Notebook, cell_id: str, scheduler, broadcaster, timeout=30):
    """Run cell and wait for completion"""
    # Enqueue the cell
    await scheduler.enqueue_run(notebook.id, cell_id, notebook, broadcaster)
    
    # Wait for status change to success/error
    start_time = time.time()
    while time.time() - start_time < timeout:
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if cell.status in [CellStatus.SUCCESS, CellStatus.ERROR]:
            return {
                "status": cell.status,
                "output": cell.output,
                "error": cell.error if cell.status == CellStatus.ERROR else None
            }
        await asyncio.sleep(0.1)
    
    raise TimeoutError(f"Cell execution exceeded {timeout}s timeout")
```

**Alternative for long-running cells**:
- Add `run_cell_async` tool that returns immediately with "queued" status
- LLM can poll with `get_cell_status` tool
- Better for cells that take >30 seconds

### 3. Conflict Resolution
**Decision**: Disable user interactions during LLM execution + last-write-wins for actual conflicts

**Frontend UX**:
- Grey out notebook or disable "Run" button when LLM is actively executing
- Show indicator: "AI Assistant is working..." with spinner
- User can still view cells but cannot trigger execution
- User CAN still edit cell code (collaborative editing)

**Conflict Strategy**:
- **Last-Write-Wins**: When both user and LLM edit same cell, most recent change wins
- **Optimistic Locking**: Use `revision` field to detect conflicts
- **Conflict Detection**: If user edits cell while LLM tool is modifying it, LLM tool fails with 409 Conflict
- **LLM Handling**: LLM receives error, queries current state, re-attempts with updated code

**Why this approach**:
- Simpler than git-style merging (overkill for notebook cells)
- Users expect real-time collaboration behavior (like Google Docs)
- LLM can recover from conflicts by re-reading state
- Disable execution button prevents most dangerous conflicts (double-execution)

**Conflict Notification**:
```typescript
// Frontend shows toast notification
"AI Assistant updated this cell. Your edits were overwritten."
// With undo button that restores user's version
```

### 4. LLM Access Control
**Decision**: Grant LLM broad access with specific restrictions

**Allowed Operations**:
- ✅ Create cells (unlimited)
- ✅ Update cell code (any cell)
- ✅ Delete cells (any cell)
- ✅ Run cells
- ✅ Create new notebooks
- ✅ Read notebook state

**Restricted Operations**:
- ❌ Modify database connection strings (if stored in backend config)
- ❌ Access user credentials or API keys
- ❌ Modify system-level settings

**Implementation Strategy**:
- No user approval workflow (streamlined UX)
- All LLM actions logged for audit trail
- LLM operates within same permissions as authenticated user
- Database connection strings should be environment variables, not cell code
- If user puts credentials in cell code, LLM can see/modify them (user responsibility)

**Security Considerations**:
- LLM has full access to notebook execution environment
- Trust model: User trusts LLM as collaborative partner
- Future enhancement: "Restricted mode" where user approves destructive operations

### 5. Streaming Strategy
**Decision**: Use native Anthropic/OpenAI streaming with SSE + `sse-starlette`

**Research Findings**:
- Vercel AI SDK + FastAPI integration exists but has reported issues (GitHub issue #7496)
- `fastapi-ai-sdk` library available but adds dependency complexity
- Native SSE with FastAPI is well-supported and mature
- WebSocket would require auth implementation (currently missing)

**Recommended Architecture**:
```
Frontend (React)
  ↓ POST /api/chat/{notebook_id} (fetch EventSource)
  ↓ Receive SSE stream
Backend (FastAPI)
  → Native anthropic.AsyncAnthropic client
  → Stream text deltas via SSE
  → Execute tools server-side with locks
  → Broadcast tool results via existing WebSocket
  → Return tool results in SSE stream
```

**Why SSE over Vercel AI SDK**:
1. **Fewer dependencies**: Only need `sse-starlette` + `anthropic`/`openai`
2. **Better compatibility**: No integration issues with FastAPI
3. **Full control**: Custom tool execution logic, error handling
4. **Authentication**: Works with existing Bearer token auth
5. **Proven pattern**: SSE is standard for LLM streaming

**Why SSE over WebSocket**:
1. **Simpler**: Unidirectional streaming, no complex protocol
2. **Auto-reconnect**: Browser handles reconnection automatically
3. **HTTP-based**: Works with existing load balancers, proxies
4. **Separate concerns**: SSE for LLM chat, existing WebSocket for notebook updates

**Implementation Example**:
```python
from sse_starlette.sse import EventSourceResponse
import anthropic

@router.post("/chat/{notebook_id}")
async def chat_with_notebook(
    notebook_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    async def event_generator():
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        async with client.messages.stream(
            model="claude-3-5-sonnet-20241022",
            messages=request.messages,
            tools=[...],
            max_tokens=4096
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"text": event.delta.text})
                    }
                elif event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        yield {
                            "event": "tool_start",
                            "data": json.dumps({
                                "tool": event.content_block.name,
                                "input": event.content_block.input
                            })
                        }
                        
            # Execute tools after stream completes
            final_message = await stream.get_final_message()
            for block in final_message.content:
                if block.type == "tool_use":
                    result = await execute_tool(notebook_id, block.name, block.input)
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({"tool": block.name, "result": result})
                    }
    
    return EventSourceResponse(event_generator())
```

**Frontend Integration**:
```typescript
// Use native EventSource API or fetch with streaming
const eventSource = new EventSource(`/api/chat/${notebookId}`);
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Handle text_delta, tool_start, tool_result events
};
```

## Additional Analysis & Recommendations

### Conflict Resolution: My Thoughts

I think your **last-write-wins** approach with **UI disabling** is the right balance. Here's why:

**Pros of This Approach**:
1. **Simple Mental Model**: Users understand "latest change wins" - it's like Google Docs
2. **Avoids Analysis Paralysis**: No complex merge UI or conflict resolution dialogs
3. **LLM Can Self-Correct**: If LLM's change gets overwritten, it can detect this via `get_notebook_state` and adapt
4. **Prevents Execution Conflicts**: Greying out run button during LLM work prevents the most critical issue (concurrent execution)

**Potential Edge Cases**:
1. **Rapid User Edits During LLM Work**: User types while LLM updates same cell
   - Solution: Add debouncing on user edits (300ms) before saving
   - Show "Saving..." indicator
   - If conflict occurs, show toast with undo option

2. **LLM Deletes Cell User Is Editing**:
   - Frontend should detect cell deletion via WebSocket
   - Show modal: "AI deleted this cell. Restore it?" with one-click undo
   - Keep deleted cell in "trash" for 30 seconds

3. **Multiple LLM Requests in Parallel** (if you allow this):
   - Use the notebook lock to serialize LLM tool executions
   - Each tool call waits for lock before modifying state
   - This is already handled by the locking architecture

**UI/UX Recommendations**:
```typescript
// When LLM is working
<div className="llm-working-overlay">
  <Spinner />
  <p>AI Assistant is working...</p>
  <button onClick={forceStop}>Stop AI</button>
</div>

// Grey out cells but keep them visible
<Cell 
  disabled={isLLMWorking} 
  className={isLLMWorking ? "opacity-50 pointer-events-none" : ""}
/>

// Show conflict toast with undo
<Toast>
  AI updated this cell. Your changes were overwritten.
  <button onClick={undoToMyVersion}>Undo</button>
</Toast>
```

### Context Management: Image Handling Strategy

For your concern about MIME types and image rendering:

**Problem**: Images (plotly, matplotlib) can be large, eating up LLM context tokens

**Solution**: Multi-tier context strategy
1. **Lightweight Preview** (always sent to LLM):
   ```json
   {
       "output_preview": "[Plotly scatter plot: 150 points, x='date', y='price']",
       "output_type": "plotly",
       "has_image": true
   }
   ```

2. **Metadata Only** (for LLM reasoning):
   ```json
   {
       "chart_type": "scatter",
       "data_shape": {"rows": 150, "columns": 2},
       "axes": {"x": "date", "y": "price"}
   }
   ```

3. **Full Data** (optional tool):
   - Add `get_cell_image` tool that returns base64 PNG
   - LLM requests image only when needed (e.g., "show me the chart")
   - User can also share screenshot via chat if using multi-modal LLM

**For Different Output Types**:
- **DataFrames**: Send shape + column names, not full data
  ```json
  "output_preview": "DataFrame(100 rows, 5 columns: ['name', 'age', 'city', 'income', 'score'])"
  ```
  
- **Plotly**: Send chart type + data summary
  ```json
  "output_preview": "Scatter plot: 200 points showing correlation between X and Y (R²=0.85)"
  ```

- **Text/Stdout**: Send first 500 chars
  ```json
  "output_preview": "Hello World\nProcessed 1000 records...\n[truncated]"
  ```

- **Errors**: Send full error message (important for LLM debugging)

**Implementation in `get_notebook_state` tool**:
```python
def create_output_preview(cell):
    if cell.output_type == "plotly":
        # Extract metadata from plotly JSON
        return {
            "preview": f"[{cell.output.get('data', [{}])[0].get('type', 'unknown')} chart]",
            "has_image": True,
            "metadata": extract_plotly_metadata(cell.output)
        }
    elif cell.output_type == "dataframe":
        # Parse DataFrame shape
        return {
            "preview": f"[DataFrame: {cell.output['shape'][0]} rows x {cell.output['shape'][1]} cols]",
            "columns": cell.output.get('columns', [])
        }
    elif cell.output_type == "text":
        return {
            "preview": cell.output[:500] + ("..." if len(cell.output) > 500 else "")
        }
```

### Streaming: SSE Implementation Details

Based on research, here's the cleanest implementation path:

**Why NOT Vercel AI SDK**:
- GitHub issue #7496 shows data streaming problems with FastAPI
- Adds unnecessary abstraction layer
- You'd need `fastapi-ai-sdk` library (another dependency)
- Tool execution happens server-side anyway, so frontend SDK benefits are minimal

**Why YES to native Anthropic SDK + SSE**:
- `anthropic` Python SDK has excellent async streaming support
- `sse-starlette` is mature and FastAPI-compatible
- Full control over tool execution flow
- Can use Claude's native tool-calling format

**Hybrid Approach** (Recommended):
1. **SSE for LLM chat stream** (`/api/chat/{notebook_id}`)
   - Sends text deltas from LLM
   - Sends tool execution events
   - One-way: Server → Frontend

2. **Existing WebSocket for notebook updates** (`/api/ws/notebooks/{notebook_id}`)
   - Broadcasts cell updates from LLM tools
   - Broadcasts cell updates from user
   - Two-way: Server ↔ Frontend

3. **REST API for user actions** (existing endpoints)
   - User creates/updates/deletes cells
   - User triggers cell execution

**Why This Is Clean**:
- Each channel has single responsibility
- SSE handles LLM conversation (sequential, text-heavy)
- WebSocket handles real-time notebook sync (event-driven)
- REST handles user mutations (CRUD operations)

**Event Flow Example**:
```
User: "Create a chart showing sales over time"
  ↓
Frontend: POST /api/chat/{notebook_id} (SSE connection)
  ↓
Backend: Stream LLM response
  → SSE: {"event": "text_delta", "data": "I'll create a chart..."}
  → LLM calls updateCell tool
  → SSE: {"event": "tool_start", "data": {"tool": "updateCell", ...}}
  → Execute tool (with lock)
  → WebSocket broadcast: cell_updated
  → SSE: {"event": "tool_result", "data": {"status": "ok"}}
  → LLM calls runCell tool
  → Execute cell (with lock)
  → WebSocket broadcast: cell_status, cell_output
  → SSE: {"event": "text_delta", "data": "Chart created!"}
  ↓
Frontend: 
  - Displays LLM message via SSE
  - Updates notebook UI via WebSocket
```

### Tool Execution Latency: Timeout Strategy

For your decision to wait for cell completion:

**Timeout Handling**:
```python
CELL_EXECUTION_TIMEOUT = 30  # seconds
LONG_RUNNING_THRESHOLD = 5   # seconds

async def locked_run_cell_with_timeout(notebook, cell_id, scheduler, broadcaster):
    """Run cell and wait, but handle timeouts gracefully"""
    start_time = time.time()
    
    # Enqueue
    await scheduler.enqueue_run(notebook.id, cell_id, notebook, broadcaster)
    
    # Poll for completion
    while time.time() - start_time < CELL_EXECUTION_TIMEOUT:
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        
        if cell.status == CellStatus.SUCCESS:
            return {"status": "success", "output": cell.output}
        
        if cell.status == CellStatus.ERROR:
            return {"status": "error", "error": cell.error}
        
        # Warn LLM if taking long
        elapsed = time.time() - start_time
        if elapsed > LONG_RUNNING_THRESHOLD and not getattr(cell, '_warned', False):
            # Send intermediate update via SSE
            await broadcast_sse_event({
                "event": "tool_update",
                "data": {"message": f"Cell still running ({elapsed:.0f}s)..."}
            })
            cell._warned = True
        
        await asyncio.sleep(0.2)
    
    # Timeout
    return {
        "status": "timeout",
        "error": f"Cell execution exceeded {CELL_EXECUTION_TIMEOUT}s timeout. Cell may still be running."
    }
```

**LLM Prompt Engineering**:
```python
system_prompt = """
You are an AI assistant helping with a reactive notebook.

When you run cells:
- Cells have a 30 second timeout
- If a cell times out, you can check status with get_cell_status tool
- For long-running operations, warn the user first
- You can create async cells (e.g., database queries) and check back later

Current notebook state:
{notebook_state}
"""
```

### Access Control: Future Enhancements

While you've decided on broad access now, consider these for future:

**Audit Logging**:
```python
# backend/audit_log.py
async def log_llm_action(notebook_id: str, action: str, details: dict):
    """Log all LLM actions for security audit"""
    await db.execute(
        "INSERT INTO llm_audit_log (notebook_id, action, details, timestamp) VALUES ($1, $2, $3, $4)",
        notebook_id, action, json.dumps(details), datetime.utcnow()
    )
```

**Rate Limiting**:
```python
# Prevent runaway LLM tool calls
from fastapi_limiter.depends import RateLimiter

@router.post("/chat/{notebook_id}")
@limiter.limit("20/minute")  # Max 20 tool calls per minute
async def chat_with_notebook(...):
    ...
```

**Dangerous Operation Detection**:
```python
# Flag potentially dangerous operations
DANGEROUS_PATTERNS = [
    r"os\.system",
    r"subprocess",
    r"__import__",
    r"eval\(",
    r"exec\(",
]

def is_code_safe(code: str) -> bool:
    """Check for dangerous patterns"""
    return not any(re.search(pattern, code) for pattern in DANGEROUS_PATTERNS)

# In updateCell tool:
if not is_code_safe(new_code):
    # Log warning but still allow (user responsibility)
    await log_warning(f"LLM created cell with potentially dangerous code: {cell_id}")
```

## Implementation Priority & Timeline

Based on the resolved questions, here's the recommended implementation order:

**Week 1: Concurrency Foundation** (CRITICAL)
1. Add notebook-level `asyncio.Lock` to Notebook model
2. Refactor all mutation endpoints to use locks
3. Implement atomic file saves with temp files
4. Add optimistic locking with revision checks
5. Coordinate scheduler with notebook lock
6. Write concurrency tests

**Week 2: LLM Tool Interface**
1. Create `notebook_operations.py` with locked operations
2. Implement `get_notebook_state` tool with MIME handling
3. Implement `updateCell`, `createCell`, `deleteCell`, `runCell` tools
4. Add tool execution timeout handling
5. Write tool integration tests

**Week 3: Streaming & Chat Endpoint**
1. Add `anthropic` and `sse-starlette` dependencies
2. Implement `/api/chat/{notebook_id}` SSE endpoint
3. Implement tool dispatch and execution
4. Add error handling and retry logic
5. Test streaming with real LLM

**Week 4: Frontend Integration**
1. Build `ChatPanel.tsx` component with SSE handling
2. Add LLM working indicator (grey out UI)
3. Implement conflict toast notifications with undo
4. Add tool execution visualization in chat
5. Integrate with existing WebSocket updates

**Week 5: Polish & Advanced Features**
1. Add audit logging for LLM actions
2. Implement undo/trash for deleted cells
3. Add rate limiting for tool calls
4. Improve error messages and user feedback
5. Add conversation history persistence

## Code References

**Core Files to Modify**:
- [backend/models.py:64](../../../backend/models.py#L64) - Add `_lock` field to Notebook
- [backend/routes.py:309-361](../../../backend/routes.py#L309-L361) - Add locks to update_cell
- [backend/routes.py:271-307](../../../backend/routes.py#L271-L307) - Add locks to create_cell
- [backend/routes.py:363-394](../../../backend/routes.py#L363-L394) - Add locks to delete_cell
- [backend/scheduler.py:44-102](../../../backend/scheduler.py#L44-L102) - Coordinate notebook lock with scheduler lock
- [backend/storage.py:12-34](../../../backend/storage.py#L12-L34) - Implement atomic file saves

**New Files to Create**:
- `backend/notebook_operations.py` - Locked notebook mutation functions
- `backend/llm_tools.py` - LLM tool definitions and execution
- `backend/chat.py` - Chat endpoint (SSE or WebSocket based)
- `frontend/src/components/ChatPanel.tsx` - LLM chat UI component

**Dependencies to Add**:
- Backend: `anthropic` or `openai` (LLM client), `sse-starlette` (if using SSE)
- Frontend: `@ai-sdk/react` (if using Vercel AI SDK), or custom SSE/fetch handling

## Related Research

No existing research documents found related to LLM integration. This is the first exploration of AI assistant features for this notebook application.

## Implementation Documents

**All open questions have been resolved. See the following documents for implementation details:**

1. **Decisions Summary** - `thoughts/shared/plans/2025-12-29-llm-integration-decisions-summary.md`
   - Quick reference for all key decisions
   - Executive summary of choices and rationale
   - Dependencies and environment setup

2. **Implementation Plan** - `thoughts/shared/plans/2025-12-29-llm-assistant-implementation-plan.md`
   - Complete step-by-step implementation guide
   - Full code examples for all phases
   - Testing checklist and deployment notes

3. **Architecture Diagram** - `thoughts/shared/plans/2025-12-29-llm-architecture-diagram.md`
   - Visual system architecture
   - Message flow diagrams
   - Concurrency protection patterns
   - Output preview strategy

## Next Steps

**READY TO IMPLEMENT** - All design decisions finalized.

Start with Phase 1 (Week 1): Concurrency Foundation
1. Add notebook-level lock to Notebook model
2. Create locked operations module
3. Refactor all mutation endpoints to use locks
4. Implement atomic file saves
5. Coordinate scheduler with notebook lock
6. Write concurrency tests

See implementation plan for complete roadmap.
