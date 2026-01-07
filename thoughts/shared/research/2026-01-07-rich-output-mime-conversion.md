# Rich Output MIME Conversion Architecture Research

**Date:** 2026-01-07  
**Purpose:** Complete analysis of output flow and architectural placement for rich MIME type conversion (matplotlib, plotly, altair, pandas)

---

## Executive Summary

This document provides a comprehensive analysis of how outputs flow through the reactive notebook system, from Python object execution to frontend rendering. The research identifies where MIME conversion logic should be placed while respecting the existing 3-layer architecture (Interface → Orchestration → Kernel).

**Key Findings:**
- Output conversion belongs in the **Executor layer** (`backend/app/core/executor.py`)
- Current implementation only supports `text/plain` and `application/json` (SQL tables)
- Frontend already has full rendering support for 6 MIME types
- No changes needed to orchestration, WebSocket, or frontend layers
- Implementation is a **single-file change** to add `to_mime_bundle()` helper

---

## Part 1: Output Flow Architecture

### 1.1 Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: KERNEL / EXECUTOR (backend/app/core/executor.py)      │
│                                                                  │
│  Python Object (e.g., plt.Figure, pd.DataFrame, str)           │
│         ↓                                                        │
│  _to_output() / to_mime_bundle()  [MIME CONVERSION HERE]       │
│         ↓                                                        │
│  Output(mime_type='image/png', data=base64_string)             │
│         ↓                                                        │
│  ExecutionResult(outputs=[Output, ...])                        │
└─────────────────────────────────────────────────────────────────┘
                         ↓ (multiprocessing.Queue)
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2: KERNEL PROCESS (backend/app/kernel/process.py)        │
│                                                                  │
│  Kernel converts executor outputs → kernel outputs              │
│  output_queue.put(ExecutionResult.model_dump())                │
└─────────────────────────────────────────────────────────────────┘
                         ↓ (multiprocessing.Queue)
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: ORCHESTRATION (backend/app/orchestration/            │
│                          coordinator.py)                        │
│                                                                  │
│  _broadcast_execution_result()                                 │
│  for output in result.outputs:                                 │
│    broadcaster.broadcast({                                     │
│      'type': 'cell_output',                                    │
│      'cellId': cell_id,                                        │
│      'output': output.model_dump()                             │
│    })                                                          │
└─────────────────────────────────────────────────────────────────┘
                         ↓ (WebSocket)
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: WEBSOCKET (backend/app/websocket/handler.py)          │
│                                                                  │
│  ConnectionManager.broadcast()                                 │
│  for websocket in active_connections:                          │
│    websocket.send_json(message)                                │
└─────────────────────────────────────────────────────────────────┘
                         ↓ (WebSocket)
┌─────────────────────────────────────────────────────────────────┐
│ Layer 5: FRONTEND (frontend/src/components/                    │
│                     OutputRenderer.tsx)                         │
│                                                                  │
│  switch (output.mime_type):                                    │
│    case 'image/png': <img src="data:image/png;base64,..." />  │
│    case 'application/vnd.plotly.v1+json': <PlotlyRenderer />   │
│    case 'application/vnd.vegalite.v6+json': <VegaLiteRenderer/>│
│    case 'application/json': <table> or <pre>                   │
│    case 'text/html': <div dangerouslySetInnerHTML />           │
│    case 'text/plain': <pre>                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Architectural Principle

**Separation of Concerns:**
- **Executor**: Business logic (convert Python objects to MIME representations)
- **Kernel Process**: IPC bridge (serialize/deserialize, maintain globals)
- **Orchestration**: Routing & broadcasting (distribute to WebSocket clients)
- **WebSocket**: Transport (send JSON to connected clients)
- **Frontend**: Presentation (render MIME types as UI components)

**Critical Insight:** MIME conversion must happen in the **Executor** layer because:
1. It has access to the Python runtime and can inspect object types
2. It operates within the kernel process (can import matplotlib, pandas, etc.)
3. It already has the pattern: `_to_output()` method in `PythonExecutor`
4. All downstream layers are transport/presentation—they don't inspect Python objects

---

## Part 2: Current Implementation Analysis

### 2.1 Executor Layer (MIME Conversion Point)

**File:** `backend/app/core/executor.py`

#### Current Output Model

```python
class Output(BaseModel):
    mime_type: str                          # e.g., 'text/plain', 'image/png'
    data: str | dict | list                 # Payload (flexible union type)
    metadata: Optional[dict[str, Any]]      # Optional metadata
```

**Supported Types:**
- ✅ `text/plain` - via `str(obj)` in `_to_output()`
- ✅ `application/json` - via SQLExecutor for table data
- ❌ `image/png` - matplotlib figures (NOT IMPLEMENTED)
- ❌ `application/vnd.plotly.v1+json` - plotly charts (NOT IMPLEMENTED)
- ❌ `application/vnd.vegalite.v6+json` - altair charts (NOT IMPLEMENTED)
- ❌ Enhanced pandas support (currently falls back to text/plain)

#### Current `_to_output()` Implementation

Location: `backend/app/core/executor.py:94-101`

```python
def _to_output(self, obj: Any) -> Optional[Output]:
    """Convert Python object to Output."""
    # TODO: Add support for rich outputs (matplotlib, plotly, pandas)
    return Output(
        mime_type='text/plain',
        data=str(obj)
    )
```

**Limitation:** All objects are converted to plain text strings, losing rich visualization capabilities.

### 2.2 Kernel Process (IPC Bridge)

**File:** `backend/app/kernel/process.py`

**Role:** Converts executor outputs to kernel IPC format

Location: `backend/app/kernel/process.py:81-88`

```python
# Convert executor outputs to kernel outputs
kernel_outputs = [
    Output(
        mime_type=out.mime_type,    # Preserves MIME type from executor
        data=out.data,              # Preserves data as-is
        metadata=out.metadata
    )
    for out in exec_result.outputs
]
```

**Key Point:** This is a **transparent bridge**—it preserves whatever MIME type the executor generates. No changes needed here.

### 2.3 Orchestration Layer (Broadcasting)

**File:** `backend/app/orchestration/coordinator.py`

**Role:** Broadcasts outputs to all connected WebSocket clients

Location: `backend/app/orchestration/coordinator.py:155-160`

```python
# Broadcast each output object
for output in result.outputs:
    cell.outputs.append(output)
    await self.broadcaster.broadcast({
        'type': 'cell_output',
        'cellId': cell_id,
        'output': output.model_dump()    # Serializes Output model to dict
    })
```

**Key Point:** Generic broadcasting—works for any MIME type. No changes needed here.

### 2.4 WebSocket Handler (Transport)

**File:** `backend/app/websocket/handler.py`

**Role:** Fan out messages to all active WebSocket connections

Location: `backend/app/websocket/handler.py:30-35`

```python
async def broadcast(self, message: dict):
    """Send message to all connected clients."""
    for websocket in self.active_connections.values():
        await websocket.send_json(message)
```

**Key Point:** Pure transport layer—agnostic to message content. No changes needed here.

### 2.5 Frontend (Rendering)

**File:** `frontend/src/components/OutputRenderer.tsx`

**Role:** Render MIME types as React components

```typescript
export function OutputRenderer({ output }: OutputRendererProps) {
  switch (output.mime_type) {
    case 'image/png':
      return <img src={`data:image/png;base64,${output.data}`} />
    
    case 'text/html':
      return <div dangerouslySetInnerHTML={{ __html: output.data }} />
    
    case 'application/vnd.vegalite.v6+json':
      return <VegaLiteRenderer spec={output.data} />    // Uses vega-embed
    
    case 'application/vnd.plotly.v1+json':
      return <PlotlyRenderer spec={output.data} />      // Uses react-plotly.js
    
    case 'application/json':
      if (isTableData(output.data)) {
        return <table>...</table>    // Renders columns/rows
      }
      return <pre>{JSON.stringify(output.data, null, 2)}</pre>
    
    case 'text/plain':
      return <pre>{output.data}</pre>
    
    default:
      return <div>Unsupported output type: {output.mime_type}</div>
  }
}
```

**Supported MIME Types (Frontend):**

| MIME Type | Data Format | Rendering | Library |
|-----------|-------------|-----------|---------|
| `image/png` | base64 string | `<img>` tag | Native |
| `text/html` | HTML string | `dangerouslySetInnerHTML` | Native |
| `application/vnd.vegalite.v6+json` | Vega-Lite spec (JSON) | Vega-Embed | `vega-embed` |
| `application/vnd.plotly.v1+json` | Plotly spec (JSON) | Plotly React | `react-plotly.js` |
| `application/json` | TableData or generic object | Table or `<pre>` | Native |
| `text/plain` | String | `<pre>` | Native |

**Key Point:** Frontend is **fully implemented** for all target MIME types. No changes needed here.

---

## Part 3: Required Implementation

### 3.1 What Needs to Change

**Answer:** Only the `_to_output()` method in `backend/app/core/executor.py`

**Rationale:**
1. All other layers are transport/presentation—they work with any MIME type
2. Executor already has the pattern (`_to_output()` method)
3. Executor runs in kernel process with access to Python runtime
4. Matches architecture document design ([2026-01-06-fresh-start-architecture.md:358-415](thoughts/shared/research/2026-01-06-fresh-start-architecture.md))

### 3.2 Target MIME Conversion Logic

**File:** `backend/app/core/executor.py`  
**Method:** `PythonExecutor._to_output()`

```python
def _to_output(self, obj: Any) -> Optional[Output]:
    """
    Convert Python object to MIME bundle output.
    
    Supports:
    - Matplotlib figures → image/png (base64)
    - Plotly figures → application/vnd.plotly.v1+json
    - Altair charts → application/vnd.vegalite.v6+json
    - Pandas DataFrames → application/json (table format)
    - Generic objects → text/plain (str fallback)
    """
    
    # Matplotlib figures
    try:
        import matplotlib.pyplot as plt
        if isinstance(obj, plt.Figure):
            from io import BytesIO
            import base64
            
            buf = BytesIO()
            obj.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            
            return Output(
                mime_type='image/png',
                data=img_base64
            )
    except ImportError:
        pass  # matplotlib not installed
    
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
        pass  # plotly not installed
    
    # Altair charts
    try:
        import altair as alt
        if isinstance(obj, alt.Chart):
            vega_json = obj.to_dict()
            
            return Output(
                mime_type='application/vnd.vegalite.v6+json',
                data=vega_json
            )
    except ImportError:
        pass  # altair not installed
    
    # Pandas DataFrames
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            # Convert to table format (matches SQLExecutor output)
            return Output(
                mime_type='application/json',
                data={
                    'type': 'table',
                    'columns': obj.columns.tolist(),
                    'rows': obj.values.tolist()
                }
            )
    except ImportError:
        pass  # pandas not installed
    
    # Fallback: convert to plain text
    return Output(
        mime_type='text/plain',
        data=str(obj)
    )
```

### 3.3 Why This Pattern Works

**Duck Typing / Try-Except Pattern:**
- Each library check is wrapped in `try/except ImportError`
- If a library isn't installed, its type check is skipped
- This allows the notebook to work even if visualization libraries are missing
- Users only need libraries they actually use

**Execution Order:**
- Most specific types checked first (matplotlib, plotly, altair, pandas)
- Generic fallback last (`text/plain`)
- Mirrors IPython/Jupyter's `_repr_mimebundle_` protocol

**Type Safety:**
- Uses `isinstance()` checks after confirming imports succeed
- Returns `Optional[Output]` for clarity
- Pydantic `Output` model ensures schema consistency

---

## Part 4: Dependencies Analysis

### 4.1 Current Dependencies

**File:** `backend/pyproject.toml`

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "python-multipart>=0.0.20",
    "asyncpg>=0.29.0",          # SQL execution (being added now)
]
```

### 4.2 Visualization Libraries (Optional)

These should be **optional dependencies** because:
1. Not all users need all visualization types
2. Large install size (matplotlib is ~50MB)
3. Notebook works without them (falls back to text/plain)

**Recommended approach:**

```toml
[project.optional-dependencies]
viz = [
    "matplotlib>=3.8.0",
    "plotly>=5.18.0",
]
data = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "altair>=5.0.0",
]
```

**Installation:**
```bash
# Full installation with all visualization support
uv sync --extra viz --extra data

# Minimal installation (text/plain outputs only)
uv sync
```

**ImportError Handling:**
- User runs `x = plt.figure()` without matplotlib installed
- Python raises `ImportError: No module named 'matplotlib'`
- Error is caught by executor and returned as `ExecutionResult(status='error', error=traceback)`
- Frontend displays error message in cell
- User installs matplotlib and re-runs cell

### 4.3 Why Not Required Dependencies?

**Justification:**
1. **Use case diversity**: Not every notebook needs plots
2. **Install speed**: Faster onboarding for simple Python notebooks
3. **Container size**: Leaner Docker images for deployment
4. **Optional enhancement**: Works great without them, better with them

**Precedent:** Jupyter follows this pattern—`jupyter/minimal-notebook` vs `jupyter/scipy-notebook` vs `jupyter/datascience-notebook`

---

## Part 5: Testing Strategy

### 5.1 Unit Tests

**File:** `backend/tests/test_executor.py`

```python
@pytest.mark.asyncio
async def test_matplotlib_figure_output():
    """Test matplotlib figure converts to PNG."""
    pytest.importorskip('matplotlib')  # Skip if not installed
    
    import matplotlib.pyplot as plt
    
    executor = PythonExecutor()
    
    # Create a simple figure
    code = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
fig
"""
    
    result = executor.execute(code)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'image/png'
    assert isinstance(result.outputs[0].data, str)  # base64 string
    assert len(result.outputs[0].data) > 100  # Non-trivial image


@pytest.mark.asyncio
async def test_plotly_figure_output():
    """Test plotly figure converts to JSON spec."""
    pytest.importorskip('plotly')
    
    executor = PythonExecutor()
    
    code = """
import plotly.graph_objects as go
fig = go.Figure(data=[go.Bar(x=[1, 2, 3], y=[1, 4, 9])])
fig
"""
    
    result = executor.execute(code)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'application/vnd.plotly.v1+json'
    assert isinstance(result.outputs[0].data, dict)
    assert 'data' in result.outputs[0].data


@pytest.mark.asyncio
async def test_pandas_dataframe_output():
    """Test pandas DataFrame converts to table."""
    pytest.importorskip('pandas')
    
    executor = PythonExecutor()
    
    code = """
import pandas as pd
df = pd.DataFrame({'id': [1, 2], 'name': ['Alice', 'Bob']})
df
"""
    
    result = executor.execute(code)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'application/json'
    
    data = result.outputs[0].data
    assert data['type'] == 'table'
    assert data['columns'] == ['id', 'name']
    assert data['rows'] == [[1, 'Alice'], [2, 'Bob']]


@pytest.mark.asyncio
async def test_altair_chart_output():
    """Test altair chart converts to Vega-Lite spec."""
    pytest.importorskip('altair')
    
    executor = PythonExecutor()
    
    code = """
import altair as alt
import pandas as pd

df = pd.DataFrame({'x': [1, 2, 3], 'y': [1, 4, 9]})
chart = alt.Chart(df).mark_line().encode(x='x', y='y')
chart
"""
    
    result = executor.execute(code)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'application/vnd.vegalite.v6+json'
    assert isinstance(result.outputs[0].data, dict)
    assert 'mark' in result.outputs[0].data or '$schema' in result.outputs[0].data


@pytest.mark.asyncio
async def test_fallback_to_text_plain():
    """Test unknown types fall back to text/plain."""
    executor = PythonExecutor()
    
    code = """
class CustomObject:
    def __repr__(self):
        return '<CustomObject>'

CustomObject()
"""
    
    result = executor.execute(code)
    
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'text/plain'
    assert result.outputs[0].data == '<CustomObject>'
```

### 5.2 Integration Tests

**File:** `backend/tests/test_rich_output_integration.py`

```python
"""Integration tests for rich outputs through kernel and orchestration."""

@pytest.mark.asyncio
async def test_matplotlib_end_to_end():
    """Test matplotlib output flows through kernel to WebSocket."""
    pytest.importorskip('matplotlib')
    
    coordinator = NotebookCoordinator(broadcaster=MockBroadcaster())
    
    # Create and register cell
    cell = Cell(id='c1', type='python', code='''
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
fig
''')
    coordinator.notebook.cells.append(cell)
    
    # Execute cell
    await coordinator.handle_run_cell('c1')
    
    # Verify WebSocket broadcast
    messages = coordinator.broadcaster.messages
    
    # Should have: cell_status(running), cell_output, cell_status(success), cell_updated
    cell_output_msg = next(m for m in messages if m['type'] == 'cell_output')
    
    assert cell_output_msg['cellId'] == 'c1'
    assert cell_output_msg['output']['mime_type'] == 'image/png'
    assert isinstance(cell_output_msg['output']['data'], str)
```

### 5.3 Manual Testing Workflow

**Setup:**
```bash
# Install with visualization libraries
cd backend
uv sync --extra viz --extra data

# Start backend
uv run uvicorn backend.main:app --reload
```

**Test Cells:**

1. **Matplotlib Test:**
```python
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)

fig, ax = plt.subplots()
ax.plot(x, y)
ax.set_title('Sine Wave')
fig
```

2. **Plotly Test:**
```python
import plotly.graph_objects as go

fig = go.Figure(data=[
    go.Bar(x=['A', 'B', 'C'], y=[3, 7, 2])
])
fig.update_layout(title='Bar Chart')
fig
```

3. **Altair Test:**
```python
import altair as alt
import pandas as pd

data = pd.DataFrame({
    'x': [1, 2, 3, 4, 5],
    'y': [1, 4, 9, 16, 25]
})

alt.Chart(data).mark_line().encode(
    x='x',
    y='y'
).properties(title='Quadratic')
```

4. **Pandas Test:**
```python
import pandas as pd
import numpy as np

df = pd.DataFrame({
    'Name': ['Alice', 'Bob', 'Charlie'],
    'Age': [25, 30, 35],
    'Score': [92.5, 87.3, 95.1]
})
df
```

5. **Reactive Cascade Test:**
```python
# Cell 1:
n = 10

# Cell 2:
import pandas as pd
import numpy as np

df = pd.DataFrame({
    'x': np.arange(n),
    'y': np.random.rand(n)
})
df

# Cell 3:
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot(df['x'], df['y'])
ax.set_title(f'Random Data (n={n})')
fig
```
Expected: Changing `n = 20` in Cell 1 → Cells 2 and 3 auto-update with new data

---

## Part 6: Edge Cases and Error Handling

### 6.1 Missing Libraries

**Scenario:** User tries to create matplotlib plot without matplotlib installed

**Behavior:**
```python
# User code:
import matplotlib.pyplot as plt  # This line fails

# ExecutionResult:
{
  "status": "error",
  "error": "ModuleNotFoundError: No module named 'matplotlib'\n..."
}
```

**Frontend displays:** Error message in cell output area

**User action:** Install library (`pip install matplotlib`) and re-run cell

### 6.2 Large Outputs

**Scenario:** User creates 10,000-row DataFrame

**Current behavior:** All rows sent to frontend

**Potential issue:** WebSocket message size, frontend rendering lag

**Mitigation (future enhancement):**
```python
# In _to_output() for pandas:
MAX_ROWS = 1000

if isinstance(obj, pd.DataFrame):
    truncated = None
    rows = obj.values.tolist()
    
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS]
        truncated = f"Showing first {MAX_ROWS} of {len(obj)} rows"
    
    return Output(
        mime_type='application/json',
        data={
            'type': 'table',
            'columns': obj.columns.tolist(),
            'rows': rows,
            'truncated': truncated
        }
    )
```

**Not implementing now:** Out of scope, but noted for future

### 6.3 Non-JSON-Serializable Types

**Scenario:** DataFrame contains `datetime` or `Decimal` values

**Issue:** `json.dumps()` fails on these types

**Solution:** Convert in `_to_output()`:
```python
import pandas as pd
import json

if isinstance(obj, pd.DataFrame):
    # Convert problematic types
    df_copy = obj.copy()
    for col in df_copy.columns:
        if df_copy[col].dtype == 'datetime64[ns]':
            df_copy[col] = df_copy[col].astype(str)
    
    return Output(
        mime_type='application/json',
        data={
            'type': 'table',
            'columns': df_copy.columns.tolist(),
            'rows': df_copy.values.tolist()
        }
    )
```

### 6.4 Matplotlib State Management

**Scenario:** User creates multiple figures without displaying them

**Issue:** Matplotlib accumulates figures in memory

**Solution:** Auto-close figures after converting to PNG:
```python
if isinstance(obj, plt.Figure):
    buf = BytesIO()
    obj.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    
    plt.close(obj)  # Free memory
    
    return Output(mime_type='image/png', data=img_base64)
```

---

## Part 7: Implementation Checklist

### 7.1 Phase 1: Core MIME Conversion (MVP)

- [ ] Update `_to_output()` in `backend/app/core/executor.py`
  - [ ] Add matplotlib → `image/png` conversion
  - [ ] Add plotly → `application/vnd.plotly.v1+json` conversion
  - [ ] Add altair → `application/vnd.vegalite.v6+json` conversion
  - [ ] Add pandas → `application/json` (table) conversion
  - [ ] Keep `text/plain` fallback

- [ ] Add optional dependencies to `backend/pyproject.toml`
  - [ ] Create `[project.optional-dependencies]` section
  - [ ] Add `viz = ["matplotlib>=3.8.0", "plotly>=5.18.0"]`
  - [ ] Add `data = ["pandas>=2.0.0", "numpy>=1.24.0", "altair>=5.0.0"]`

- [ ] Install optional dependencies
  - [ ] Run `uv sync --extra viz --extra data`

### 7.2 Phase 2: Testing

- [ ] Add unit tests to `backend/tests/test_executor.py`
  - [ ] `test_matplotlib_figure_output()`
  - [ ] `test_plotly_figure_output()`
  - [ ] `test_altair_chart_output()`
  - [ ] `test_pandas_dataframe_output()`
  - [ ] `test_fallback_to_text_plain()`

- [ ] Add integration test
  - [ ] Create `backend/tests/test_rich_output_integration.py`
  - [ ] Test matplotlib through kernel → WebSocket flow

- [ ] Run test suite
  - [ ] `uv run pytest backend/tests/test_executor.py -v`
  - [ ] `uv run pytest backend/tests/test_rich_output_integration.py -v`

### 7.3 Phase 3: Manual Verification

- [ ] Start backend with viz libraries
  - [ ] `uv run uvicorn backend.main:app --reload`

- [ ] Test each visualization type in frontend
  - [ ] Create matplotlib plot cell → verify PNG renders
  - [ ] Create plotly chart cell → verify interactive chart renders
  - [ ] Create altair chart cell → verify Vega-Lite renders
  - [ ] Create pandas DataFrame cell → verify table renders

- [ ] Test reactive cascade with visualization
  - [ ] Cell 1: variable definition
  - [ ] Cell 2: DataFrame depending on variable
  - [ ] Cell 3: Plot depending on DataFrame
  - [ ] Verify changing Cell 1 triggers cascade with updated plot

### 7.4 Phase 4: Documentation

- [ ] Update `backend/README.md`
  - [ ] Document optional dependencies
  - [ ] Add visualization examples
  - [ ] List supported output types

- [ ] Add docstring to `_to_output()`
  - [ ] List all supported types
  - [ ] Document fallback behavior
  - [ ] Note optional library dependencies

---

## Part 8: No Changes Needed

The following components require **zero modifications** because they are transport/presentation layers:

### 8.1 Models (`backend/app/models.py`)
- `OutputResponse` already supports flexible `data: str | TableData | dict | list`
- `mime_type: str` is already generic
- **Status:** ✅ Complete

### 8.2 Kernel Process (`backend/app/kernel/process.py`)
- Transparently passes executor outputs to orchestration
- No MIME-specific logic
- **Status:** ✅ Complete

### 8.3 Kernel Types (`backend/app/kernel/types.py`)
- `Output` model matches executor's `Output`
- **Status:** ✅ Complete

### 8.4 Orchestration (`backend/app/orchestration/coordinator.py`)
- Generic broadcasting of any output type
- **Status:** ✅ Complete

### 8.5 WebSocket Handler (`backend/app/websocket/handler.py`)
- Transport layer, agnostic to content
- **Status:** ✅ Complete

### 8.6 API Endpoints (`backend/app/api/notebooks.py`)
- REST CRUD operations don't touch outputs
- **Status:** ✅ Complete

### 8.7 Frontend (`frontend/src/`)
- `OutputRenderer.tsx` already implements all target MIME types
- `NotebookApp.tsx` already handles `cell_output` messages
- `useNotebookWebSocket.ts` already includes `cell_output` in type union
- **Status:** ✅ Complete

---

## Part 9: Architectural Validation

### 9.1 Separation of Concerns: ✅ Maintained

**Executor Layer:**
- Responsibility: Convert Python objects to MIME representations
- Change: Add rich MIME conversion logic
- Justification: Only layer with access to Python runtime

**Kernel Process:**
- Responsibility: IPC bridge between executor and orchestration
- Change: None
- Justification: Already generic—preserves any MIME type

**Orchestration Layer:**
- Responsibility: Route results to WebSocket clients
- Change: None
- Justification: Content-agnostic broadcasting

**WebSocket Layer:**
- Responsibility: Transport JSON messages
- Change: None
- Justification: Pure transport, no business logic

**Frontend:**
- Responsibility: Render MIME types as UI components
- Change: None
- Justification: Already supports all target types

### 9.2 Type Safety: ✅ Maintained

- All models use Pydantic for runtime validation
- `Output.data` union type supports all formats (`str | dict | list`)
- `mypy --strict` compliance maintained

### 9.3 Testability: ✅ Enhanced

- Executor layer is pure Python—easily unit tested
- Each visualization type can be tested independently
- `pytest.importorskip()` allows optional library tests

### 9.4 Extensibility: ✅ Future-Proof

**Adding new output types:**
1. Add `isinstance()` check in `_to_output()`
2. Add `case` in `OutputRenderer.tsx`
3. No changes to kernel, orchestration, or WebSocket layers

**Example:** Adding seaborn support
```python
# In _to_output():
try:
    import seaborn as sns
    if isinstance(obj, sns.axisgrid.FacetGrid):
        return self._matplotlib_figure_to_output(obj.fig)
except ImportError:
    pass
```

---

## Part 10: References

### 10.1 Architecture Documents
- [2026-01-06-fresh-start-architecture.md](thoughts/shared/research/2026-01-06-fresh-start-architecture.md) - Original architecture design
- [2026-01-06-new-and-improved.md](thoughts/shared/research/2026-01-06-new-and-improved.md) - 3-layer architecture
- [the_task.md](the_task.md) - Core requirements

### 10.2 Implementation Files
- `backend/app/core/executor.py` - **Primary change location**
- `backend/app/models.py` - Output model definitions
- `backend/app/kernel/process.py` - IPC bridge
- `backend/app/orchestration/coordinator.py` - Broadcasting
- `frontend/src/components/OutputRenderer.tsx` - Frontend rendering

### 10.3 External References
- Jupyter MIME protocol: https://jupyter-client.readthedocs.io/en/stable/messaging.html#display-data
- IPython display system: https://ipython.readthedocs.io/en/stable/config/integrating.html
- Matplotlib backends: https://matplotlib.org/stable/users/explain/figure/backends.html
- Plotly JSON format: https://plotly.com/javascript/plotlyjs-function-reference/
- Vega-Lite spec: https://vega.github.io/vega-lite/docs/spec.html

---

## Conclusion

This research establishes that **rich output support requires only a single-file change** to `backend/app/core/executor.py`. The existing architecture is well-designed for this enhancement:

1. **Executor layer** is the correct location for MIME conversion (access to Python runtime)
2. **All downstream layers** are generic transport/presentation (no changes needed)
3. **Frontend** is already fully implemented for all target MIME types
4. **Type safety** is maintained through Pydantic models
5. **Testability** is enhanced with isolated unit tests
6. **Extensibility** is preserved for future output types

The implementation is **low-risk, high-value**, and aligns perfectly with the separation of concerns established in the original architecture document.

**Next Steps:**
1. Implement `to_mime_bundle()` in `_to_output()` method
2. Add optional visualization dependencies
3. Write unit tests with `pytest.importorskip()`
4. Perform manual end-to-end testing
5. Document supported output types in README

