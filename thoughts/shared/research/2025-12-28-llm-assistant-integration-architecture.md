---
date: 2025-12-28T17:08:10Z
researcher: Claude
topic: "LLM Assistant Integration Architecture for Reactive Notebook"
tags: [research, codebase, llm-integration, vercel-ai-sdk, concurrency, architecture]
status: complete
last_updated: 2025-12-28
last_updated_by: Claude
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

**Recommended Architecture**:
1. Implement notebook-level read-write lock for all state mutations
2. Add optimistic locking using the existing `revision` field
3. Create LLM tool interface as FastAPI endpoints with same locking semantics
4. Use Vercel AI SDK on frontend with server-side tools for notebook operations
5. Stream LLM responses via SSE or WebSocket while maintaining lock discipline

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

## Open Questions

1. **LLM Context Management**: How to keep LLM updated with current notebook state?
   - Option A: Include full notebook state in system prompt on each request (simple but token-heavy)
   - Option B: Stream notebook changes to LLM via WebSocket (complex but efficient)
   - Option C: LLM queries notebook state via read-only tools

2. **Tool Execution Latency**: What happens if LLM executes tool while cell is already running?
   - Current behavior: `enqueue_run` adds to pending queue, will run after current execution
   - Should LLM tools wait for execution completion before returning?

3. **Conflict Resolution**: How should conflicts be presented to user?
   - Show modal: "LLM modified cell X, your changes conflict"
   - Merge changes (complex, like git merge)
   - Last-write-wins with notification

4. **LLM Access Control**: Should LLM have restrictions on what it can do?
   - Can LLM delete cells?
   - Can LLM modify database connection string?
   - Should user approve certain tool calls?

5. **Streaming Strategy**: SSE vs WebSocket vs Vercel AI SDK?
   - SSE: Standard HTTP, unidirectional, easy to implement
   - WebSocket: Bidirectional, reuses existing infrastructure, need auth
   - Vercel AI SDK: Best DX but requires Python port or JS backend for tool execution

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

## Next Steps

1. **Phase 1: Fix Concurrency Issues (Prerequisite)**
   - Add notebook-level lock to Notebook model
   - Refactor all mutation endpoints to use locks
   - Implement atomic file saves
   - Coordinate scheduler with notebook lock
   - Add optimistic locking with revision checks

2. **Phase 2: Design LLM Tool Interface**
   - Define tool schemas (create_cell, update_cell, run_cell, delete_cell, get_notebook_state)
   - Implement locked tool execution functions
   - Add tool execution tests

3. **Phase 3: Choose Streaming Strategy**
   - Evaluate: Vercel AI SDK vs SSE vs WebSocket
   - Prototype chosen approach
   - Implement chat endpoint

4. **Phase 4: Frontend Integration**
   - Build ChatPanel component
   - Handle streaming responses
   - Display tool executions in UI
   - Synchronize with existing WebSocket updates

5. **Phase 5: Advanced Features**
   - LLM context management (include cell outputs, errors)
   - Conflict resolution UI
   - Tool approval workflow for sensitive operations
   - Multi-turn conversation with notebook state awareness
