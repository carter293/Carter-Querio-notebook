# Reactive Notebook

A production-grade reactive notebook system where cells automatically re-execute when their dependencies change, like a spreadsheet for code. Built for [Querio's take-home assignment](the_task.md).

**Live Demo:** [Try it here →](#) *(if deployed)*

## What Makes This Special

Unlike traditional notebooks (Jupyter, Observable) where you manually re-run cells, this system:

- **Automatically tracks dependencies** using AST analysis and graph algorithms
- **Reactively cascades execution** when upstream values change
- **Detects circular dependencies** before they cause problems
- **Isolates execution in separate processes** so crashes don't kill your session
- **Supports both Python and SQL** with template variable interpolation
- **Renders multiple output formats** (tables, charts, images, HTML)

### Demo: Reactive Execution in Action

```python
# Cell 1
x = 10

# Cell 2 (depends on x)
y = x * 2

# Cell 3 (depends on y)
print(f"Result: {y}")  # Output: "Result: 20"
```

**Change Cell 1 to `x = 20` → Cells 2 and 3 automatically re-run → Output: "Result: 40"**

No manual re-execution needed. The system tracks that Cell 2 reads `x`, Cell 3 reads `y`, and executes them in the correct topological order.

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────┐
│  Frontend (React + Monaco Editor)               │
│  - Cell editing with syntax highlighting        │
│  - Real-time output rendering                   │
│  - WebSocket connection management              │
└────────────────┬────────────────────────────────┘
                 │ HTTP + WebSocket
┌────────────────▼────────────────────────────────┐
│  FastAPI Server (Orchestration Layer)           │
│  - REST API for CRUD operations                 │
│  - WebSocket gateway for real-time updates      │
│  - Per-connection kernel lifecycle management   │
└────────────────┬────────────────────────────────┘
                 │ multiprocessing.Queue
┌────────────────▼────────────────────────────────┐
│  Kernel Process (Isolated Execution)            │
│  - AST parser for dependency extraction         │
│  - NetworkX DAG with cycle detection            │
│  - Python/SQL execution with output capture     │
│  - Persistent user namespace (globals dict)     │
└─────────────────────────────────────────────────┘
```

### Key Components

#### 1. AST Parser (`backend/app/core/ast_parser.py`)
Extracts variable dependencies from Python code using Python's `ast` module:

```python
# Example
code = "y = x * 2"
reads, writes = extract_dependencies(code)
# reads = {'x'}, writes = {'y'}
```

**Handles:**
- Simple assignments (`x = 10`)
- Augmented assignments (`x += 5` → reads AND writes `x`)
- Function definitions (tracks name, ignores local variables)
- Imports (`import pandas as pd` → writes `pd`)
- SQL template variables (`{user_id}` → reads `user_id`)

#### 2. Dependency Graph (`backend/app/core/graph.py`)
Uses NetworkX to build a directed acyclic graph (DAG) where edges represent dependencies:

```
Cell A writes {x} → Cell B reads {x}  ⟹  Edge: A → B
```

**Features:**
- **Incremental cycle detection** - Tests each edge before adding to graph
- **Topological sort** - Computes correct execution order
- **Descendant tracking** - Finds all downstream cells for reactive cascades
- **Stale ancestor detection** - Only re-runs cells that haven't been executed yet

**Cycle Rejection Example:**
```python
# Cell 1: x = y + 1  (reads y, writes x)
# Cell 2: y = x + 1  (reads x, writes y)
# Result: Circular dependency error! Both cells marked as "blocked"
```

#### 3. Executor (`backend/app/core/executor.py`)
Executes code and captures outputs in multiple formats:

**Python Execution:**
- Splits code into statements + final expression
- Executes statements with `exec()`, evaluates expression with `eval()`
- Captures `stdout` using `contextlib.redirect_stdout`
- Converts result to MIME bundle (PNG, Plotly JSON, Vega-Lite, tables, text)

**SQL Execution:**
- Parameterizes template variables (`{var}` → `$1, $2, ...`)
- Executes via `asyncpg` connection pool
- Serializes results to table format (`{type: "table", columns: [...], rows: [...]}`)
- Handles datetime/date/time serialization to ISO format

**Supported Output Formats:**
| MIME Type | Use Case | Library |
|-----------|----------|---------|
| `text/plain` | Simple values | Built-in `str()` |
| `image/png` | Matplotlib figures | `matplotlib` → base64 PNG |
| `application/vnd.plotly.v1+json` | Interactive charts | `plotly` → JSON spec |
| `application/vnd.vegalite.v6+json` | Declarative viz | `altair` → Vega-Lite spec |
| `application/json` | DataFrames, SQL results | `pandas` → table format |
| `text/html` | Rich HTML output | Direct HTML passthrough |

#### 4. Kernel Process (`backend/app/kernel/process.py`)
Runs in a separate process (via `multiprocessing.Process`) to isolate user code:

**Event Loop:**
1. Reads `ExecuteRequest` from input queue (blocking)
2. Parses dependencies via AST
3. Updates dependency graph (rejects if cycle detected)
4. Computes execution order (changed cell + descendants, topologically sorted)
5. Executes each cell in order, streaming results to output queue
6. Maintains persistent namespace (`globals_dict`) between executions

**Why a separate process?**
- Crashes in user code don't kill the web server
- Clean Python interpreter state
- Can restart kernel without affecting HTTP connections
- Future-proof for distributed deployment (swap queues for ZeroMQ/Redis)

#### 5. Coordinator (`backend/app/orchestration/coordinator.py`)
Manages kernel lifecycle and broadcasts results:

- Creates one `KernelManager` per WebSocket connection
- Runs background task to read from kernel's output queue
- Broadcasts notifications to all connected WebSocket clients
- **Stateless design** - does NOT store cell outputs/status (clients are source of truth)

#### 6. WebSocket Protocol (`backend/app/websocket/handler.py`)
Real-time bidirectional communication:

**Client → Server:**
```json
{"type": "cell_update", "cellId": "...", "code": "..."}
{"type": "run_cell", "cellId": "..."}
{"type": "create_cell", "cellType": "python|sql", "afterCellId": "..."}
{"type": "delete_cell", "cellId": "..."}
{"type": "update_db_connection", "connectionString": "postgresql://..."}
```

**Server → Client:**
```json
{"type": "cell_status", "cellId": "...", "status": "idle|running|success|error|blocked"}
{"type": "cell_stdout", "cellId": "...", "data": "..."}
{"type": "cell_output", "cellId": "...", "output": {"mime_type": "...", "data": ...}}
{"type": "cell_error", "cellId": "...", "error": "..."}
{"type": "cell_updated", "cellId": "...", "cell": {"reads": [...], "writes": [...]}}
{"type": "cell_created", "cellId": "...", "cell": {...}, "index": 0}
{"type": "cell_deleted", "cellId": "..."}
```

## Quick Start

### Prerequisites
- **Python 3.11+** with `uv` package manager ([install uv](https://github.com/astral-sh/uv))
- **Node.js 18+** with npm
- **PostgreSQL** (optional, for SQL cells)

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/reactive-notebook.git
cd reactive-notebook

# Install backend dependencies
cd backend
uv sync  # installs from pyproject.toml

# Install frontend dependencies
cd ../frontend
npm install
```

### Running Locally

**Terminal 1 - Backend:**
```bash
cd backend
uv run python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Server running at http://localhost:8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
# Dev server running at http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

### Optional: Configure Database for SQL Cells

Set a PostgreSQL connection string in the notebook settings:

```
postgresql://username:password@localhost:5432/database_name
```

Now SQL cells can query your database with template variables:

```sql
-- Cell 1 (Python)
user_id = 42

-- Cell 2 (SQL)
SELECT * FROM users WHERE id = {user_id}
```

## Project Structure

```
├── backend/
│   ├── main.py                      # FastAPI app entry point
│   ├── app/
│   │   ├── api/
│   │   │   └── notebooks.py         # HTTP endpoints (CRUD)
│   │   ├── core/
│   │   │   ├── ast_parser.py        # Dependency extraction
│   │   │   ├── graph.py             # DAG + topological sort
│   │   │   └── executor.py          # Code execution
│   │   ├── kernel/
│   │   │   ├── process.py           # Kernel event loop
│   │   │   ├── manager.py           # Process lifecycle management
│   │   │   └── types.py             # Pydantic models
│   │   ├── orchestration/
│   │   │   └── coordinator.py       # WebSocket broadcasting
│   │   ├── websocket/
│   │   │   └── handler.py           # WebSocket endpoint
│   │   └── file_storage.py          # Notebook persistence
│   ├── notebooks/                   # Stored notebooks (.py files)
│   ├── tests/                       # Unit + integration tests
│   └── pyproject.toml               # Dependencies (uv format)
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── NotebookApp.tsx      # Main notebook UI
│   │   │   ├── NotebookCell.tsx     # Cell component (Monaco editor)
│   │   │   ├── OutputRenderer.tsx   # Multi-format output display
│   │   │   └── NotebookList.tsx     # Notebook selector
│   │   ├── useNotebookWebSocket.ts  # WebSocket hook
│   │   └── api-client.ts            # HTTP client
│   ├── package.json                 # Dependencies
│   └── vite.config.ts               # Build config
│
├── the_task.md                      # Assignment requirements
└── thoughts/shared/research/
    └── 2026-01-06-fresh-start-architecture.md  # Architecture doc
```

## Features

### Core Requirements (from Assignment)
- ✅ **Cell Management** - Add, edit, delete cells via UI
- ✅ **Python & SQL Cells** - Native support for both types
- ✅ **Visual Feedback** - Status indicators (idle/running/success/error/blocked)
- ✅ **Display Outputs** - Text, DataFrames, charts, errors
- ✅ **Reactive Updates** - Automatic downstream execution
- ✅ **Database Connection** - PostgreSQL connection string configuration

### Advanced Features (Beyond Requirements)
- ✅ **Multi-Process Architecture** - Kernel isolation prevents crashes
- ✅ **Cycle Detection** - Blocks circular dependencies with clear error messages
- ✅ **Stale Ancestor Detection** - Only re-runs cells that haven't been executed
- ✅ **Multiple Output Formats** - PNG, Plotly JSON, Vega-Lite, HTML, tables
- ✅ **Real-Time Broadcasting** - All connected clients see updates via WebSocket
- ✅ **File-Based Persistence** - Notebooks stored as readable `.py` files
- ✅ **Keyboard Shortcuts** - `Shift+Enter` to run, `Cmd/Ctrl+Shift+Up/Down` to navigate
- ✅ **Auto-Save** - Debounced save (1.5s) + save-on-blur
- ✅ **Notebook Management** - Create, rename, delete, switch between notebooks
- ✅ **Monaco Editor** - Full VSCode-powered code editor with syntax highlighting
- ✅ **Dependency Metadata** - Shows reads/writes for each cell (inspect element to see)

## Usage Examples

### Example 1: Simple Reactive Chain

```python
# Cell 1
x = 10

# Cell 2 (automatically depends on Cell 1)
y = x * 2

# Cell 3 (automatically depends on Cell 2)
print(f"Result: {y}")  # Output: "Result: 20"
```

**What happens when you change Cell 1 to `x = 20`:**
1. System detects Cell 1 writes `x`, Cell 2 reads `x` → Cell 2 depends on Cell 1
2. System detects Cell 2 writes `y`, Cell 3 reads `y` → Cell 3 depends on Cell 2
3. When Cell 1 changes, system executes: Cell 1 → Cell 2 → Cell 3 (in topological order)
4. Output updates to: "Result: 40"

### Example 2: Data Analysis Pipeline

```python
# Cell 1: Load data
import pandas as pd
df = pd.read_csv('data.csv')
df  # Renders as HTML table

# Cell 2: Filter data (depends on df)
filtered = df[df['age'] > 30]
filtered

# Cell 3: Visualize (depends on filtered)
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.hist(filtered['salary'], bins=20)
fig  # Renders as PNG image
```

### Example 3: SQL + Python Integration

```python
# Cell 1: Set filter value
min_price = 100

# Cell 2: Query database (SQL cell, depends on min_price)
SELECT product_name, price
FROM products
WHERE price > {min_price}
ORDER BY price DESC

# Cell 3: Process results (depends on Cell 2)
# SQL results are stored in a special variable
import pandas as pd
df = pd.DataFrame(result)  # 'result' injected by system
df['price_with_tax'] = df['price'] * 1.1
df
```

### Example 4: Interactive Charts

```python
# Cell 1: Generate data
import numpy as np
x = np.linspace(0, 10, 100)
y = np.sin(x)

# Cell 2: Create Plotly chart (depends on x, y)
import plotly.graph_objects as go
fig = go.Figure()
fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='sin(x)'))
fig.update_layout(title='Sine Wave', xaxis_title='x', yaxis_title='y')
fig  # Renders as interactive Plotly chart
```

## Testing

### Run All Tests

```bash
cd backend
uv run pytest tests/ -v
```

### Test Structure

```
tests/
├── test_ast_parser.py              # Unit: Dependency extraction
├── test_graph.py                   # Unit: DAG operations, cycle detection
├── test_executor.py                # Unit: Python execution
├── test_sql_executor_integration.py # Integration: SQL with real DB
├── test_websocket_commands.py      # Integration: WebSocket messages
├── test_websocket_crud_operations.py # Integration: Cell CRUD
└── test_kernel_has_run.py          # Integration: Stale ancestor detection
```

### Example Test Notebooks

Located in `backend/notebooks/`:
- `test-reactive.py` - Simple chain: A → B → C
- `test-diamond.py` - Diamond pattern: A → B,C → D
- `test-cycle.py` - Circular dependency detection
- `test-matplotlib.py` - Matplotlib PNG output
- `test-plotly.py` - Plotly JSON output
- `test-pandas.py` - DataFrame table output
- `test-sql.py` - SQL query execution

## Technical Deep Dives

### How Reactive Execution Works

**Step 1: User Edits Cell Code**
- Frontend: Monaco editor fires `onChange` event
- Debounced save after 1.5s OR immediate save on blur
- WebSocket message: `{type: "cell_update", cellId: "c1", code: "x = 20"}`

**Step 2: Backend Registers Cell**
- Coordinator receives message, forwards to kernel via input queue
- Kernel parses code with AST walker, extracts `reads: []`, `writes: ['x']`
- Updates dependency graph: adds node `c1`, draws edges to cells that read `x`

**Step 3: Cycle Detection**
- For each new edge (writer → reader), check `nx.has_path(reader, writer)`
- If path exists, adding edge would create cycle → reject entire update
- Send error notification: `{type: "cell_status", status: "blocked"}`

**Step 4: User Runs Cell**
- WebSocket message: `{type: "run_cell", cellId: "c1"}`
- Kernel computes execution order:
  1. Get all ancestors of `c1` (cells it depends on)
  2. Filter to only stale ancestors (haven't run yet)
  3. Get all descendants of `c1` (cells that depend on it)
  4. Topologically sort: ancestors → `c1` → descendants

**Step 5: Execute in Order**
- For each cell in execution order:
  1. Send status notification: `{type: "cell_status", status: "running"}`
  2. Execute code: `exec(code, globals_dict)` or `await conn.fetch(sql)`
  3. Stream outputs: `{type: "cell_output", output: {mime_type, data}}`
  4. Send final status: `{type: "cell_status", status: "success|error"}`
  5. Mark cell as "has run" (won't re-execute if downstream cell runs)

**Step 6: Frontend Updates UI**
- WebSocket hook receives messages, updates React state
- Cell components re-render with new status, outputs, metadata
- OutputRenderer dispatches on MIME type, renders appropriate component

### Why Separate Kernel Process?

**Traditional Approach (Same Process):**
```
User Code → exec() → Web Server Memory
```
- 🔴 Infinite loop crashes entire server
- 🔴 Memory leak affects all users
- 🔴 Namespace pollution (imports leak between sessions)

**Our Approach (Separate Process):**
```
User Code → Queue → Kernel Process → Queue → Web Server
```
- ✅ Crash only kills kernel, server stays up
- ✅ Can restart kernel without affecting connections
- ✅ Clean Python interpreter per connection
- ✅ Easy to scale (swap queues for ZeroMQ/Redis)

### File-Based Storage Format

Notebooks are stored as executable Python files in `backend/notebooks/`:

```python
# Notebook: My Analysis
# DB: postgresql://localhost/mydb

# %% python [cell-id-1]
import pandas as pd
df = pd.read_csv('data.csv')

# %% python [cell-id-2]
filtered = df[df['age'] > 30]

# %% sql [cell-id-3]
SELECT * FROM users WHERE id = {user_id}
```

**Benefits:**
- Human-readable and editable outside the app
- Version control friendly (git diffs work)
- Can be executed directly with Python (`python notebook.py`)
- Easy backup and migration

## API Reference

### HTTP Endpoints

**Base URL:** `http://localhost:8000/api/v1`

#### `POST /notebooks`
Create a new notebook.

**Response:**
```json
{
  "notebook_id": "my-notebook"
}
```

#### `GET /notebooks`
List all notebooks.

**Response:**
```json
{
  "notebooks": [
    {"id": "notebook-1", "name": "My Analysis"},
    {"id": "notebook-2", "name": "SQL Demo"}
  ]
}
```

#### `GET /notebooks/{id}`
Get notebook with all cells.

**Response:**
```json
{
  "id": "my-notebook",
  "name": "My Analysis",
  "db_conn_string": "postgresql://...",
  "cells": [
    {
      "id": "c1",
      "type": "python",
      "code": "x = 10",
      "status": "success",
      "outputs": [...],
      "reads": [],
      "writes": ["x"]
    }
  ]
}
```

#### `PUT /notebooks/{id}/name`
Rename notebook.

**Request:**
```json
{
  "name": "New Name"
}
```

#### `DELETE /notebooks/{id}`
Delete notebook.

### WebSocket Endpoint

**URL:** `ws://localhost:8000/api/v1/ws/notebook/{notebook_id}`

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/notebook/my-notebook');
ws.onopen = () => {
  // Connection established, start sending messages
};
```

**Client Messages:**
```typescript
// Update cell code (triggers dependency re-parse, NO execution)
{type: 'cell_update', cellId: string, code: string}

// Execute cell (runs cell + all descendants)
{type: 'run_cell', cellId: string}

// Create new cell
{type: 'create_cell', cellType: 'python'|'sql', afterCellId?: string}

// Delete cell
{type: 'delete_cell', cellId: string}

// Configure database connection
{type: 'update_db_connection', connectionString: string}
```

**Server Messages:**
```typescript
// Cell status changed
{type: 'cell_status', cellId: string, status: 'idle'|'running'|'success'|'error'|'blocked'}

// Cell printed to stdout
{type: 'cell_stdout', cellId: string, data: string}

// Cell produced output
{type: 'cell_output', cellId: string, output: {mime_type: string, data: any}}

// Cell execution failed
{type: 'cell_error', cellId: string, error: string}

// Cell dependencies updated
{type: 'cell_updated', cellId: string, cell: {reads: string[], writes: string[]}}

// Cell created
{type: 'cell_created', cellId: string, cell: {...}, index: number}

// Cell deleted
{type: 'cell_deleted', cellId: string}

// Database config updated
{type: 'db_connection_updated', connectionString: string, status: 'success'|'error'}

// Kernel error (e.g., crash)
{type: 'kernel_error', error: string}
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Shift+Enter` | Run current cell |
| `Cmd/Ctrl+Shift+Up` | Focus previous cell |
| `Cmd/Ctrl+Shift+Down` | Focus next cell |
| `Cmd/Ctrl+K` | Show keyboard shortcuts |

## Limitations & Future Work

### Current Limitations
- **No mutation tracking** - `df.append()`, `list.pop()` not detected (would need runtime tracking)
- **No cell reordering** - Cells maintain insertion order (drag-and-drop UI planned)
- **No output history** - Only current execution state stored (time-travel debugging planned)
- **No execution interrupts** - Can't cancel running cell (requires signal handling)
- **Single connection = single kernel** - No shared kernel pool (planned for collaboration)
- **No package installation** - Can't run `pip install` in cells (sandboxing needed)

### Potential Enhancements
- **Shared kernel mode** - Multiple clients connect to same kernel for collaboration
- **Cell reordering** - Drag-and-drop with automatic graph update
- **Execution history** - Store all past outputs with timestamps
- **Interrupt execution** - Send SIGINT to kernel process
- **Variable inspector** - Show all variables in namespace with types/values
- **Code completion** - LSP integration for autocomplete
- **Git integration** - Commit notebooks with version history
- **Export** - Convert to Jupyter `.ipynb`, HTML, PDF

## License

MIT

## Credits

Built by [Matthew Carter](https://github.com/yourusername) for Querio's take-home assignment.

**Technology Stack:**
- **Backend:** FastAPI, Pydantic, NetworkX, asyncpg
- **Frontend:** React 19, TypeScript, Monaco Editor, Plotly, Vega-Lite
- **Build Tools:** uv (Python), Vite (frontend)

**Architecture Inspiration:**
- [Observable Framework](https://observablehq.com/@observablehq/observable-for-jupyter-users) - Reactive execution model
- [Jupyter Protocol](https://jupyter-client.readthedocs.io/en/stable/messaging.html) - Message-based kernel communication
- [Hex.tech](https://hex.tech/) - SQL + Python integration patterns
