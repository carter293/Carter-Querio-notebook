# Fresh Start: Reactive Kernel Architecture & Implementation Plan

**Date:** 2026-01-06  
**Purpose:** Comprehensive architecture document for rebuilding the reactive notebook backend from scratch, focusing purely on the core reactive execution engine with zero bloat.

---

## Executive Summary

This document outlines the complete architecture for a **production-grade reactive notebook kernel** based on Principal-level engineering principles. The goal is to build a system that:

1. **Focuses exclusively on reactivity** - No auth, no storage, no LLM chat, no deployment infrastructure
2. **Demonstrates architectural excellence** - Separation of concerns, type safety, defensive programming
3. **Is technically impressive** - Actor model, DAG-based execution, proper concurrency control
4. **Works with the existing frontend** - Maintains the current API contract and WebSocket protocol

---

## Part 1: Current State Analysis

### 1.1 Frontend Expectations

The current simplified frontend (`frontend/src/components/NotebookApp.tsx`) expects:

#### API Contract (TypeScript Types from `types.gen.ts`)

```typescript
// Cell structure
type CellResponse = {
  id: string;
  type: 'python' | 'sql';
  code: string;
  status: 'idle' | 'running' | 'success' | 'error' | 'blocked';
  stdout?: string | null;
  outputs: Array<OutputResponse>;
  error?: string | null;
  reads: Array<string>;   // Variables this cell reads
  writes: Array<string>;  // Variables this cell writes
}

// Output structure
type OutputResponse = {
  mime_type: string;
  data: string | TableData | { [key: string]: unknown } | Array<unknown>;
  metadata?: { [key: string]: string | number } | null;
}

// Table data (for pandas/SQL)
type TableData = {
  type: 'table';
  columns: Array<string>;
  rows: Array<Array<string | number | boolean | null>>;
  truncated?: string | null;
}
```

#### Required HTTP Endpoints

```
POST   /api/v1/notebooks/                           → { notebook_id: string }
GET    /api/v1/notebooks/                           → { notebooks: NotebookMetadata[] }
GET    /api/v1/notebooks/{notebook_id}              → NotebookResponse
PUT    /api/v1/notebooks/{notebook_id}/db           → void
POST   /api/v1/notebooks/{notebook_id}/cells        → { cell_id: string }
PUT    /api/v1/notebooks/{notebook_id}/cells/{id}   → void
DELETE /api/v1/notebooks/{notebook_id}/cells/{id}   → void
```

#### WebSocket Protocol

**Client → Server:**
```json
{ "type": "authenticate" }
{ "type": "run_cell", "cellId": "<cell_id>" }
```

**Server → Client:**
```json
{ "type": "authenticated" }
{ "type": "cell_status", "cellId": "<id>", "status": "running|success|error|blocked" }
{ "type": "cell_stdout", "cellId": "<id>", "data": "<text>" }
{ "type": "cell_output", "cellId": "<id>", "output": { "mime_type": "...", "data": ... } }
{ "type": "cell_error", "cellId": "<id>", "error": "<message>" }
{ "type": "cell_updated", "cellId": "<id>", "cell": { "code": "...", "reads": [...], "writes": [...] } }
{ "type": "cell_created", "cellId": "<id>", "cell": {...}, "index": 0 }
{ "type": "cell_deleted", "cellId": "<id>" }
```

### 1.2 Current Backend State

- **Empty shell**: `backend/main.py` contains only a hello world
- **pyproject.toml**: Initialized with `uv` but no dependencies yet
- **Frontend hardcoded notebook ID**: `"RESET AFTER UPDATING BACKEND AND RERUNNING HEY API"`

### 1.3 MIME Types to Support

The frontend's `OutputRenderer.tsx` handles:

| MIME Type | Data Format | Use Case |
|-----------|-------------|----------|
| `text/plain` | string | Simple text output |
| `image/png` | base64 string | Matplotlib figures |
| `application/vnd.plotly.v1+json` | Plotly spec object | Plotly charts |
| `application/vnd.vegalite.v6+json` | Vega-Lite spec | Altair charts |
| `application/json` | TableData or generic JSON | Pandas DataFrames, SQL results |
| `text/html` | HTML string | Rich HTML output |

---

## Part 2: Architecture Design

### 2.1 System Architecture Overview

Based on the "new-and-improved" document, we use a **3-layer hexagonal architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                   INTERFACE LAYER (FastAPI)                  │
│  - HTTP REST API (CRUD operations)                          │
│  - WebSocket Gateway (real-time updates)                    │
│  - Request validation (Pydantic)                            │
│  - Simplified auth (no-op initially, JWT later)             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              ORCHESTRATION LAYER (Coordinator)               │
│  - Kernel lifecycle management                              │
│  - WebSocket message broadcasting                           │
│  - In-memory notebook storage (single notebook for v1)      │
│  - Queue management between HTTP/WS and Kernel              │
└────────────────────────┬────────────────────────────────────┘
                         │ (Queues / Messages)
┌────────────────────────▼────────────────────────────────────┐
│                 KERNEL LAYER (The Engine)                    │
│  - Separate OS process (multiprocessing)                    │
│  - Event loop consuming ExecuteRequest commands             │
│  - AST Parser (dependency extraction)                       │
│  - DependencyGraph (DAG + topological sort)                 │
│  - Executor (code execution + output capture)               │
│  - User namespace (globals dict persistence)                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Core Components

#### 2.2.1 Kernel Process (The Actor)

**Responsibility:** Execute code in strict sequential order while maintaining user state.

**Why a separate process?**
- Isolation: Crashes don't kill the API server
- Clean namespace: Fresh Python interpreter
- Future-proof: Can swap to ZeroMQ/gRPC for distributed deployment

**The Kernel Loop:**

```python
# Pseudocode
while True:
    command = input_queue.get()  # Blocking wait
    
    match command.type:
        case "execute":
            # 1. Parse AST → extract reads/writes
            reads, writes = ast_parser.extract(command.code)
            
            # 2. Update DAG
            graph.update_cell(command.cell_id, reads, writes)
            
            # 3. Detect cycles
            if graph.has_cycle():
                output_queue.put(ErrorResult(cycle_detected=True))
                continue
            
            # 4. Topological sort (reactive cascade)
            cells_to_run = graph.get_execution_order(command.cell_id)
            
            # 5. Execute in order
            for cell_id in cells_to_run:
                result = executor.execute(cell_id, user_globals)
                output_queue.put(result)
        
        case "shutdown":
            break
```

**Key Properties:**
- **Single-threaded** (no race conditions on `user_globals`)
- **Stateful** (variables persist between executions)
- **Deterministic** (topological order guarantees correctness)

#### 2.2.2 AST Parser

**Responsibility:** Extract variable dependencies from Python code.

**Implementation Strategy:**

Use Python's `ast` module with a custom `NodeVisitor`:

```python
class DependencyExtractor(ast.NodeVisitor):
    def __init__(self):
        self.reads: Set[str] = set()
        self.writes: Set[str] = set()
        self.scope_stack: List[Set[str]] = [set()]  # Track local scopes
    
    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            # Reading a variable
            if not self._is_local(node.id):
                self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            # Writing a variable (module-level only)
            if len(self.scope_stack) == 1:  # Top-level scope
                self.writes.add(node.id)
                self.scope_stack[0].add(node.id)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Functions define a name but don't expose internal assignments
        if len(self.scope_stack) == 1:
            self.writes.add(node.name)
        # Don't descend into function body
    
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.writes.add(name)
```

**Challenge:** Distinguishing between module-level variables and local function variables.

**Solution:** Only track assignments at the top level of the module's AST (ignore nested `FunctionDef`/`ClassDef` bodies).

**For SQL cells:**
```python
def extract_sql_dependencies(sql: str) -> Set[str]:
    """Extract {variable} templates from SQL."""
    return set(re.findall(r'\{(\w+)\}', sql))
```

#### 2.2.3 Dependency Graph (DAG)

**Responsibility:** Track variable dependencies and compute execution order.

**Why NetworkX?**
- Battle-tested cycle detection
- Built-in topological sort
- Descendant tracking (`nx.descendants()`)
- Fast enough for <1000 cells

**Implementation:**

```python
import networkx as nx

class DependencyGraph:
    def __init__(self):
        self._graph = nx.DiGraph()
        self._cell_writes: Dict[str, Set[str]] = {}  # cell_id → variables written
        self._var_writers: Dict[str, str] = {}       # variable → cell_id that writes it
    
    def update_cell(self, cell_id: str, reads: Set[str], writes: Set[str]):
        """Update the graph when a cell's code changes."""
        # Remove old edges
        self._graph.remove_node(cell_id)
        
        # Register new writes
        self._cell_writes[cell_id] = writes
        for var in writes:
            old_writer = self._var_writers.get(var)
            if old_writer and old_writer != cell_id:
                # Variable shadowing: newer definition wins
                pass
            self._var_writers[var] = cell_id
        
        # Add edges: if cell reads X, and some other cell writes X, draw edge
        for var in reads:
            writer = self._var_writers.get(var)
            if writer and writer != cell_id:
                self._graph.add_edge(writer, cell_id)
        
        # Check for cycles
        if not nx.is_directed_acyclic_graph(self._graph):
            raise CycleDetectedError(f"Circular dependency involving {cell_id}")
    
    def get_execution_order(self, changed_cell_id: str) -> List[str]:
        """
        Returns cells to execute when `changed_cell_id` is modified.
        Includes the cell itself + all descendants, in topological order.
        """
        affected = {changed_cell_id} | nx.descendants(self._graph, changed_cell_id)
        subgraph = self._graph.subgraph(affected)
        return list(nx.topological_sort(subgraph))
```

**Cycle Handling:**
- On cycle detection, raise `CycleDetectedError`
- Kernel sends error result to orchestrator
- Orchestrator broadcasts `cell_status: error` to frontend
- Frontend shows "Blocked" badge with error message

#### 2.2.4 Executor

**Responsibility:** Execute Python/SQL code and capture outputs.

**Python Execution:**

```python
async def execute_python(code: str, globals_dict: Dict[str, Any]) -> ExecutionResult:
    """
    Execute Python code, capturing:
    - stdout (via redirect_stdout)
    - Last expression value (converted to MIME output)
    - Errors (formatted traceback)
    """
    stdout_buffer = StringIO()
    outputs: List[Output] = []
    
    try:
        tree = ast.parse(code)
        
        # Check if last statement is an expression
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            # Split into statements + final expression
            statements = ast.Module(body=tree.body[:-1], type_ignores=[])
            expression = ast.Expression(body=tree.body[-1].value)
            
            with redirect_stdout(stdout_buffer):
                exec(compile(statements, '<cell>', 'exec'), globals_dict)
                result = eval(compile(expression, '<cell>', 'eval'), globals_dict)
            
            # Convert result to MIME output
            if result is not None:
                output = to_mime_bundle(result)
                if output:
                    outputs.append(output)
        else:
            # Pure statements, no expression
            with redirect_stdout(stdout_buffer):
                exec(compile(tree, '<cell>', 'exec'), globals_dict)
        
        return ExecutionResult(
            status='success',
            stdout=stdout_buffer.getvalue(),
            outputs=outputs
        )
    
    except Exception as e:
        return ExecutionResult(
            status='error',
            error=''.join(traceback.format_exception(type(e), e, e.__traceback__))
        )
```

**MIME Conversion:**

```python
def to_mime_bundle(obj: Any) -> Optional[Output]:
    """Convert Python objects to MIME representations."""
    
    # Matplotlib figures
    try:
        import matplotlib.pyplot as plt
        if isinstance(obj, plt.Figure):
            buffer = BytesIO()
            obj.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            png_b64 = base64.b64encode(buffer.read()).decode('utf-8')
            return Output(mime_type='image/png', data=png_b64)
    except ImportError:
        pass
    
    # Plotly figures
    try:
        import plotly.graph_objects as go
        if isinstance(obj, go.Figure):
            import json
            spec = json.loads(obj.to_json())
            return Output(
                mime_type='application/vnd.plotly.v1+json',
                data=spec
            )
    except ImportError:
        pass
    
    # Altair charts
    try:
        import altair as alt
        if isinstance(obj, alt.Chart):
            return Output(
                mime_type='application/vnd.vegalite.v6+json',
                data=obj.to_dict()
            )
    except ImportError:
        pass
    
    # Pandas DataFrames
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return Output(
                mime_type='application/json',
                data={
                    'type': 'table',
                    'columns': obj.columns.tolist(),
                    'rows': obj.values.tolist()
                }
            )
    except ImportError:
        pass
    
    # Fallback: plain text
    return Output(mime_type='text/plain', data=str(obj))
```

**SQL Execution:**

```python
async def execute_sql(code: str, conn_string: str, globals_dict: Dict[str, Any]) -> ExecutionResult:
    """
    Execute SQL with template variable substitution.
    Example: SELECT * FROM users WHERE id = {user_id}
    """
    if not conn_string:
        return ExecutionResult(
            status='error',
            error='Database connection string not configured'
        )
    
    try:
        import asyncpg
        
        # Substitute {variable} templates
        substituted_sql = substitute_sql_vars(code, globals_dict)
        
        # Execute
        conn = await asyncpg.connect(conn_string)
        try:
            records = await conn.fetch(substituted_sql)
            
            if records:
                columns = list(records[0].keys())
                rows = [list(record.values()) for record in records]
                
                return ExecutionResult(
                    status='success',
                    outputs=[Output(
                        mime_type='application/json',
                        data={
                            'type': 'table',
                            'columns': columns,
                            'rows': rows
                        }
                    )]
                )
            else:
                return ExecutionResult(status='success', stdout='Query returned 0 rows')
        finally:
            await conn.close()
    
    except Exception as e:
        return ExecutionResult(status='error', error=str(e))
```

### 2.3 Process Communication

**Queue-based IPC (multiprocessing):**

```python
# Shared data structures
from multiprocessing import Process, Queue
from pydantic import BaseModel

class ExecuteRequest(BaseModel):
    cell_id: str
    code: str
    cell_type: Literal['python', 'sql']

class ExecutionResult(BaseModel):
    cell_id: str
    status: Literal['success', 'error']
    stdout: str = ''
    outputs: List[Output] = []
    error: Optional[str] = None
    reads: List[str] = []
    writes: List[str] = []

# In orchestrator
input_queue = Queue()
output_queue = Queue()
kernel_process = Process(target=kernel_main, args=(input_queue, output_queue))
kernel_process.start()

# Send execution request
input_queue.put(ExecuteRequest(cell_id='c1', code='x=1', cell_type='python').model_dump())

# Receive results
result = output_queue.get()  # Blocking
```

**Why Queues instead of REST?**
- Lower latency (no HTTP overhead)
- Type-safe serialization (Pydantic)
- Easy to swap for ZeroMQ/Redis later

### 2.4 Orchestration Layer

**Responsibilities:**
1. Manage kernel process lifecycle (start, restart on crash)
2. Route HTTP requests → Kernel commands
3. Forward Kernel results → WebSocket broadcasts
4. Maintain in-memory notebook state (for REST API)

**Key Classes:**

```python
class NotebookOrchestrator:
    def __init__(self):
        self.kernel = KernelManager()
        self.broadcaster = WebSocketBroadcaster()
        self.notebook = Notebook(id='default', cells=[])
    
    async def handle_cell_update(self, cell_id: str, code: str):
        """HTTP PUT /cells/{cell_id} handler."""
        # Update in-memory notebook
        cell = self.notebook.get_cell(cell_id)
        cell.code = code
        
        # Broadcast code change to all connected clients
        await self.broadcaster.broadcast_cell_updated(cell_id, cell)
    
    async def handle_run_cell(self, cell_id: str):
        """WebSocket run_cell handler."""
        cell = self.notebook.get_cell(cell_id)
        
        # Send to kernel
        result = await self.kernel.execute(
            cell_id=cell_id,
            code=cell.code,
            cell_type=cell.type
        )
        
        # Broadcast status
        await self.broadcaster.broadcast_cell_status(cell_id, 'running')
        
        # Stream outputs as they arrive
        await self.broadcaster.broadcast_cell_stdout(cell_id, result.stdout)
        for output in result.outputs:
            await self.broadcaster.broadcast_cell_output(cell_id, output)
        
        # Final status
        await self.broadcaster.broadcast_cell_status(cell_id, result.status)
        
        # Update cell metadata (reads/writes)
        cell.reads = result.reads
        cell.writes = result.writes
        await self.broadcaster.broadcast_cell_updated(cell_id, cell)
```

### 2.5 Type Safety & Error Handling

**Strict Typing with Pydantic V2:**

```python
from pydantic import BaseModel, Field
from typing import Literal

class Output(BaseModel):
    mime_type: str
    data: str | dict | list
    metadata: dict[str, Any] | None = None

class Cell(BaseModel):
    id: str
    type: Literal['python', 'sql']
    code: str
    status: Literal['idle', 'running', 'success', 'error', 'blocked'] = 'idle'
    stdout: str = ''
    outputs: list[Output] = []
    error: str | None = None
    reads: list[str] = []
    writes: list[str] = []

class Notebook(BaseModel):
    id: str
    name: str = 'Untitled'
    db_conn_string: str = ''
    cells: list[Cell] = []
```

**Exception Hierarchy:**

```python
class KernelError(Exception):
    """Base exception for kernel errors."""
    pass

class CycleDetectedError(KernelError):
    """Raised when a circular dependency is detected."""
    pass

class ExecutionError(KernelError):
    """Raised when code execution fails."""
    pass

class TimeoutError(KernelError):
    """Raised when execution exceeds timeout."""
    pass
```

---

## Part 3: Implementation Plan

### Phase 1: Core Kernel (Day 1-2)

**Goal:** Working DAG execution engine with 100% test coverage, no API.

**Tasks:**
1. ✅ Setup project structure
   ```
   backend/
   ├── core/
   │   ├── ast_parser.py      # Dependency extraction
   │   ├── graph.py            # DAG with NetworkX
   │   └── executor.py         # Code execution
   ├── kernel/
   │   ├── process.py          # Kernel main loop
   │   └── types.py            # Pydantic models
   └── tests/
       ├── test_ast_parser.py
       ├── test_graph.py
       └── test_executor.py
   ```

2. ✅ Implement `ASTParser.extract_dependencies(code: str) -> (reads, writes)`
   - Handle variables, imports, functions
   - Ignore local scopes
   - Test with 20+ edge cases

3. ✅ Implement `DependencyGraph`
   - `update_cell(id, reads, writes)`
   - `get_execution_order(changed_id) -> List[str]`
   - Cycle detection with `nx.is_directed_acyclic_graph()`
   - Test cycle detection, topological sort, reactive cascades

4. ✅ Implement `Executor.execute_python(code, globals_dict) -> Result`
   - Stdout capture with `redirect_stdout`
   - Last expression evaluation
   - MIME conversion (matplotlib, plotly, pandas)
   - Error handling with full traceback

5. ✅ Write comprehensive tests
   - Unit tests for each component
   - Integration test: 3-cell chain where A→B→C updates correctly

**Success Criteria:**
- `pytest` shows 100% pass rate
- Running cell A triggers cascade to B and C
- Circular dependencies are detected and rejected

### Phase 2: Kernel Process (Day 2-3)

**Goal:** Kernel runs as a separate process, communicates via queues.

**Tasks:**
1. ✅ Create `KernelProcess` with event loop
   - Read `ExecuteRequest` from `input_queue`
   - Write `ExecutionResult` to `output_queue`
   - Maintain `user_globals: dict` between executions

2. ✅ Create `KernelManager` (orchestrator side)
   - Start/stop kernel process
   - Async methods that wrap queue communication
   - Timeout handling (5 second default)
   - Watchdog to restart on crash

3. ✅ Test process communication
   - Send execution request
   - Receive result with correct outputs
   - Test process restart on crash

**Success Criteria:**
- Kernel survives syntax errors without crashing
- Variables persist across executions (`x=1` then `print(x)` works)
- Process can be restarted without losing orchestrator state

### Phase 3: HTTP API (Day 3-4)

**Goal:** REST API for notebook CRUD operations.

**Tasks:**
1. ✅ Setup FastAPI app with OpenAPI spec
   ```python
   from fastapi import FastAPI
   from pydantic import BaseModel
   
   app = FastAPI()
   orchestrator = NotebookOrchestrator()
   
   @app.post("/api/v1/notebooks/")
   async def create_notebook(): ...
   
   @app.get("/api/v1/notebooks/")
   async def list_notebooks(): ...
   
   @app.get("/api/v1/notebooks/{notebook_id}")
   async def get_notebook(notebook_id: str): ...
   
   @app.post("/api/v1/notebooks/{notebook_id}/cells")
   async def create_cell(notebook_id: str, req: CreateCellRequest): ...
   
   @app.put("/api/v1/notebooks/{notebook_id}/cells/{cell_id}")
   async def update_cell(notebook_id: str, cell_id: str, req: UpdateCellRequest): ...
   
   @app.delete("/api/v1/notebooks/{notebook_id}/cells/{cell_id}")
   async def delete_cell(notebook_id: str, cell_id: str): ...
   ```

2. ✅ Implement in-memory notebook storage
   - Single notebook for v1 (hardcoded ID)
   - CRUD operations update notebook state
   - No persistence (restart = fresh state)

3. ✅ Test with `httpx` client
   - Create cells, update code, delete cells
   - Verify reads/writes are populated
   - Verify cell order is maintained

**Success Criteria:**
- `curl` commands work for all endpoints
- OpenAPI docs are auto-generated at `/docs`
- Frontend can load notebook via REST

### Phase 4: WebSocket Integration (Day 4-5)

**Goal:** Real-time execution with WebSocket broadcasting.

**Tasks:**
1. ✅ Implement `WebSocketBroadcaster`
   ```python
   class WebSocketBroadcaster:
       def __init__(self):
           self.connections: Dict[str, Set[WebSocket]] = {}
       
       async def connect(self, notebook_id: str, ws: WebSocket):
           await ws.accept()
           self.connections.setdefault(notebook_id, set()).add(ws)
       
       async def broadcast(self, notebook_id: str, message: dict):
           for ws in self.connections.get(notebook_id, []):
               try:
                   await ws.send_json(message)
               except:
                   # Remove dead connection
                   self.connections[notebook_id].discard(ws)
   ```

2. ✅ Add WebSocket endpoint
   ```python
   @app.websocket("/api/v1/ws/notebook")
   async def notebook_websocket(websocket: WebSocket):
       await broadcaster.connect('default', websocket)
       
       try:
           while True:
               message = await websocket.receive_json()
               
               if message['type'] == 'authenticate':
                   await websocket.send_json({'type': 'authenticated'})
               
               elif message['type'] == 'run_cell':
                   asyncio.create_task(orchestrator.handle_run_cell(message['cellId']))
       
       except WebSocketDisconnect:
           await broadcaster.disconnect('default', websocket)
   ```

3. ✅ Implement execution broadcasting
   - Before execution: `cell_status: running`
   - During execution: `cell_stdout` (if any)
   - After execution: `cell_output` (for each output)
   - After execution: `cell_status: success|error`
   - After parse: `cell_updated` (with reads/writes)

4. ✅ Test with WebSocket client
   - Connect, authenticate, run cell
   - Verify all messages are received in order
   - Test reactive cascade (run A, see B and C update)

**Success Criteria:**
- Frontend connects successfully
- Running a cell shows "Running" status immediately
- Outputs appear in real-time
- Dependent cells auto-execute

### Phase 5: Polish & Edge Cases (Day 5-6)

**Goal:** Handle edge cases and improve UX.

**Tasks:**
1. ✅ Cell status management
   - Set to `blocked` if dependency failed
   - Set to `error` on cycle detection
   - Clear outputs on new execution

2. ✅ SQL support
   - Implement `execute_sql` with `asyncpg`
   - Template variable substitution
   - Error handling for missing variables

3. ✅ MIME output refinements
   - Handle large DataFrames (limit to 1000 rows)
   - Support numpy arrays (convert to list)
   - Handle non-JSON-serializable types (dates, Decimals)

4. ✅ Error messages
   - Syntax errors with line numbers
   - Runtime errors with full traceback
   - Cycle errors with involved cells

5. ✅ Testing
   - Integration test with frontend
   - Test all MIME types render correctly
   - Test cycle detection with 3+ cells

**Success Criteria:**
- All frontend features work end-to-end
- Error messages are helpful
- No crashes on edge cases

---

## Part 4: Testing Strategy

### 4.1 Unit Tests

```python
# test_ast_parser.py
def test_simple_assignment():
    code = "x = 10"
    reads, writes = extract_dependencies(code)
    assert reads == set()
    assert writes == {'x'}

def test_dependency_chain():
    code = "y = x * 2"
    reads, writes = extract_dependencies(code)
    assert reads == {'x'}
    assert writes == {'y'}

def test_function_definition_not_tracked():
    code = """
def foo():
    local_var = 10
    return local_var
"""
    reads, writes = extract_dependencies(code)
    assert reads == set()
    assert writes == {'foo'}  # Only the function name

# test_graph.py
def test_topological_sort():
    graph = DependencyGraph()
    graph.update_cell('c1', reads=set(), writes={'x'})
    graph.update_cell('c2', reads={'x'}, writes={'y'})
    graph.update_cell('c3', reads={'y'}, writes={'z'})
    
    order = graph.get_execution_order('c1')
    assert order == ['c1', 'c2', 'c3']

def test_cycle_detection():
    graph = DependencyGraph()
    graph.update_cell('c1', reads={'y'}, writes={'x'})
    
    with pytest.raises(CycleDetectedError):
        graph.update_cell('c2', reads={'x'}, writes={'y'})

# test_executor.py
@pytest.mark.asyncio
async def test_stdout_capture():
    globals_dict = {}
    result = await execute_python("print('hello')", globals_dict)
    
    assert result.status == 'success'
    assert result.stdout == 'hello\n'
    assert result.outputs == []

@pytest.mark.asyncio
async def test_expression_output():
    globals_dict = {}
    result = await execute_python("2 + 2", globals_dict)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'text/plain'
    assert result.outputs[0].data == '4'
```

### 4.2 Integration Tests

```python
@pytest.mark.asyncio
async def test_reactive_cascade():
    """Test that changing A causes B and C to re-execute."""
    orchestrator = NotebookOrchestrator()
    
    # Create cells: A → B → C
    c1 = await orchestrator.create_cell('python')
    c2 = await orchestrator.create_cell('python')
    c3 = await orchestrator.create_cell('python')
    
    # Set code
    await orchestrator.update_cell(c1, 'x = 10')
    await orchestrator.update_cell(c2, 'y = x * 2')
    await orchestrator.update_cell(c3, 'z = y + 5')
    
    # Run A
    await orchestrator.run_cell(c1)
    
    # Verify all three executed
    assert orchestrator.notebook.get_cell(c1).status == 'success'
    assert orchestrator.notebook.get_cell(c2).status == 'success'
    assert orchestrator.notebook.get_cell(c3).status == 'success'
    
    # Verify final values
    assert orchestrator.kernel.globals_dict['x'] == 10
    assert orchestrator.kernel.globals_dict['y'] == 20
    assert orchestrator.kernel.globals_dict['z'] == 25
```

---

## Part 5: Dependencies

**Minimal `pyproject.toml`:**

```toml
[project]
name = "querio-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "pydantic>=2.0.0",
    "networkx>=3.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
viz = [
    "matplotlib>=3.8.0",
    "plotly>=5.18.0",
    "altair>=5.0.0",
]
data = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "asyncpg>=0.29.0",
]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "httpx>=0.25.0",
    "mypy>=1.7.0",
    "ruff>=0.1.0",
]
```

**Why these dependencies?**
- `fastapi` + `uvicorn`: Modern async web framework
- `pydantic`: Data validation and serialization
- `networkx`: DAG operations (topological sort, cycle detection)
- `websockets`: Real-time communication
- Optional visualization libraries: Only imported when used (duck typing)

---

## Part 6: Key Design Decisions

### 6.1 Why NOT Use the Old Backend Code?

**Reasons:**
1. **Cluttered with bloat**: Auth, storage, LLM chat, deployment logic
2. **Mixed concerns**: Business logic tangled with infrastructure
3. **Difficult to extract**: Safer to rebuild with clear architecture
4. **Learning opportunity**: Demonstrates architectural thinking

### 6.2 Why Separate Kernel Process?

**Benefits:**
1. **Isolation**: User code crashes don't kill the API server
2. **Clean state**: Fresh Python interpreter with no pollution
3. **Scalability**: Can distribute later (multiple workers, ZeroMQ)
4. **Restart logic**: Can restart kernel without affecting connections

**Tradeoffs:**
- Slightly more complex (IPC vs direct function calls)
- Serialization overhead (Pydantic models)
- Worth it for production systems

### 6.3 Why NetworkX Instead of Custom DAG?

**Reasons:**
1. **Correctness**: Topological sort is a solved problem
2. **Features**: Cycle detection, descendants, transitive closure
3. **Performance**: Fast enough for <1000 nodes (microseconds)
4. **Focus**: Spend time on business logic, not algorithms

**Encapsulation:**
- Wrap NetworkX in `DependencyGraph` class
- Can swap implementation later without changing consumers

### 6.4 Why Single Notebook for V1?

**Reasons:**
1. **Scope reduction**: Focus on reactive execution
2. **Simpler testing**: No multi-tenancy concerns
3. **Frontend expectation**: Current UI assumes single notebook
4. **Easy upgrade**: Can add multi-notebook later

---

## Part 7: Success Metrics

### 7.1 Functional Requirements

- [ ] Create, update, delete cells via REST API
- [ ] Execute Python cells with reactive cascades
- [ ] Execute SQL cells with template variables
- [ ] Real-time WebSocket updates for all events
- [ ] Cycle detection with clear error messages
- [ ] MIME outputs for matplotlib, plotly, pandas, altair
- [ ] Persistent user namespace (variables live between executions)
- [ ] Cell status tracking (idle, running, success, error, blocked)

### 7.2 Non-Functional Requirements

- [ ] **Type Safety**: `mypy --strict` passes with no errors
- [ ] **Test Coverage**: >90% line coverage
- [ ] **Performance**: Cell execution triggers in <100ms
- [ ] **Error Handling**: No crashes on invalid input
- [ ] **Documentation**: Clear README with examples
- [ ] **Code Quality**: Passes `ruff` linter

### 7.3 Demo Scenarios

**Scenario 1: Simple Reactive Chain**
```python
# Cell 1
x = 10

# Cell 2
y = x * 2

# Cell 3
print(f"Result: {y}")
```
✅ Changing Cell 1 → auto-runs Cells 2 and 3

**Scenario 2: Cycle Detection**
```python
# Cell 1
x = y + 1

# Cell 2
y = x + 1
```
❌ Shows "Circular dependency" error

**Scenario 3: Matplotlib Output**
```python
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
fig
```
✅ Displays PNG image in frontend

**Scenario 4: SQL with Variables**
```python
# Cell 1
user_id = 42

# Cell 2 (SQL)
SELECT * FROM users WHERE id = {user_id}
```
✅ Executes query with substituted value

---

## Part 8: Future Enhancements (Out of Scope)

These are intentionally NOT included in v1:

- ❌ Authentication (no users, no JWT)
- ❌ Persistence (no database, no file storage)
- ❌ Multiple notebooks (single hardcoded notebook)
- ❌ LLM chat integration
- ❌ Deployment infrastructure (no Docker, Terraform, AWS)
- ❌ Cell reordering / drag-and-drop
- ❌ Output history / time-travel debugging
- ❌ Execution interrupts (Ctrl+C)
- ❌ Package installation (`pip install` in cells)

**Why exclude these?**
The feedback was clear: "remove absolutely all of the bloat, and focus on shipping a reactive notebook to be proud of."

These features can be added incrementally after the core reactive engine is proven.

---

## Conclusion

This document provides a complete blueprint for building a production-grade reactive notebook kernel from scratch. The architecture follows Principal-level engineering patterns:

1. **Separation of Concerns**: Clear boundaries between Interface, Orchestration, and Kernel layers
2. **Type Safety**: Pydantic models everywhere, `mypy --strict` compliance
3. **Defensive Programming**: Comprehensive error handling with custom exception hierarchy
4. **Architectural Foresight**: Process-based design allows future distribution
5. **Focus**: Zero bloat, pure reactive execution excellence

The implementation plan is structured into 5 phases over 5-6 days, with clear success criteria for each phase.

**Next Steps:**
1. Initialize `pyproject.toml` with dependencies
2. Create project structure (`core/`, `kernel/`, `server/`)
3. Implement Phase 1 (Core Kernel) with TDD approach
4. Iterate through phases 2-5
5. Test with frontend integration

