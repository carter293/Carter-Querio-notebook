# Reactive Notebook Enhancements Implementation Plan

## Overview

Enhance the reactive notebook with professional chart rendering capabilities (matplotlib, plotly, altair), persistent storage, and critical bug fixes. This implementation follows marimo's proven MIME bundle architecture for output transport, enabling rich data visualizations while maintaining the reactive dependency execution model.

## Current State Analysis

The reactive notebook currently implements:
- **Core reactive execution:** Cells automatically re-execute when dependencies change ([scheduler.py:44-102](backend/scheduler.py#L44))
- **Dependency tracking:** AST-based analysis extracts variable reads/writes ([ast_parser.py:44-71](backend/ast_parser.py#L44))
- **SQL integration:** Cells can query PostgreSQL with Python variable substitution ([executor.py:66-135](backend/executor.py#L66))
- **WebSocket updates:** Real-time cell status and output streaming ([websocket.py:42-68](backend/websocket.py#L42))

### Key Limitations Discovered:

1. **No Chart Support:**
   - [executor.py:43](backend/executor.py#L43) - Comment shows `result` field unused for Python cells
   - Only text stdout and SQL tables are captured
   - No MIME type system for rich outputs

2. **No Persistence:**
   - [routes.py:12](backend/routes.py#L12) - `NOTEBOOKS: Dict[str, Notebook] = {}` is pure in-memory storage
   - All notebook state lost on server restart
   - No demo/template notebooks for new users

3. **Double-Run Output Bug:**
   - [Notebook.tsx:36](frontend/src/components/Notebook.tsx#L36) - Stdout appends instead of replaces: `stdout: (cell.stdout || '') + msg.data`
   - [scheduler.py:113-116](backend/scheduler.py#L113) - Outputs cleared server-side but not broadcasted to frontend
   - Running cell twice shows duplicate output

4. **Poor Error Messages:**
   - [executor.py:32](backend/executor.py#L32) - Tracebacks show `<cell-{cell.id}>` with UUIDs
   - User-facing errors leak implementation details

## System Context Analysis

This plan addresses **both symptoms and root causes**:

**Root Cause:** The output system was designed for simple text/table results. The `ExecutionResult` class ([executor.py:13-19](backend/executor.py#L13)) has a single untyped `result` field with no MIME type metadata. This architectural limitation prevents rich outputs like charts.

**Systemic Solution:** We're introducing a proper MIME bundle system modeled after marimo's architecture, which separates output transport (MIME types + data) from rendering (frontend renderers per type). This enables extensibility for future output types (images, videos, widgets) without core architecture changes.

**Symptom Fixes:** The double-run bug and traceback issues are genuine bugs with targeted fixes, not architectural problems.

## Desired End State

After implementation, the notebook will:

1. **Render Charts Professionally:**
   - Matplotlib charts as PNG images with proper sizing
   - Plotly interactive charts with zoom/pan controls
   - Altair/Vega-Lite charts with declarative specifications
   - Pandas DataFrames as formatted tables

2. **Persist Reliably:**
   - Auto-save notebooks to JSON files on every change
   - Load notebooks on server startup
   - Provide demo notebook with examples on first run

3. **Behave Correctly:**
   - No duplicate outputs on re-run
   - Clear error messages with cell positions (Cell[0], Cell[1])
   - Proper output clearing between executions

### Verification:
- Manual testing with all chart libraries
- Server restart preserves notebook state
- Demo notebook loads with working examples

## What We're NOT Doing

To maintain focused scope and reasonable timeline:

1. **Expression-only outputs** (e.g., typing `123`) - Would require complex AST manipulation; limited value
2. **Interactive chart selections** - marimo's reactive chart features (click selections feeding back to Python)
3. **Full IPython display protocol** - Complete compatibility with `IPython.display.display()`, display IDs, update mechanisms
4. **Multiple outputs per cell** - Support for multiple `display()` calls creating separate output areas
5. **Kernel state persistence** - Saving Python object state to disk (will re-execute on load instead)
6. **Output streaming** - Progressive output updates for long-running cells
7. **Chart size limits** - Automatic compression/resizing of large charts
8. **ANSI color codes** - Terminal color support in stdout
9. **Binary file outputs** - PDFs, Excel files, etc.

## Implementation Approach

**Strategy:** Clean break - no existing users to support

1. **Remove legacy fields:** Delete `result` field entirely, use only `outputs: List[Output]`
2. **MIME-based dispatch:** Use MIME types for renderer selection, not hardcoded type checks
3. **Backend-first:** Establish output data flow before frontend rendering
4. **Quick wins first:** Fix bugs (Phases 4-5) before complex features (Phase 1)
5. **Manual testing:** Chart rendering requires visual verification; automated tests optional

**Dependencies:**
- Phase 2 must complete before Phase 1 testing (need packages installed)
- Phase 3 depends on stable output model from Phase 1
- Phases 4-5 are independent and can run in parallel

---

## Phase 1: MIME Bundle Output System

### Overview
Implement a MIME bundle architecture to transport rich outputs (charts, images, formatted data) from Python execution to frontend rendering. Based on marimo's proven pattern of separating output types via MIME metadata.

### Changes Required:

#### 1.1 Output Data Model
**File**: `backend/models.py`
**Changes**: Add new dataclass and extend Cell model

```python
from typing import List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

class MimeType(str, Enum):
    """Known MIME types for output rendering"""
    PNG = "image/png"
    HTML = "text/html"
    PLAIN = "text/plain"
    VEGA_LITE = "application/vnd.vegalite.v5+json"
    JSON = "application/json"

@dataclass
class Output:
    """Single output with MIME type metadata"""
    mime_type: str  # Use MimeType enum values
    data: str | dict | list  # base64 string for images, dict for JSON/tables, HTML string
    metadata: Dict[str, str | int | float] = field(default_factory=dict)  # Optional: width, height, etc.

# Update Cell dataclass - REMOVE result field, ADD outputs
@dataclass
class Cell:
    id: str
    type: CellType
    code: str
    status: CellStatus = CellStatus.IDLE
    stdout: str = ""
    # REMOVED: result field (replaced by outputs)
    outputs: List[Output] = field(default_factory=list)  # NEW
    error: Optional[str] = None
    reads: Set[str] = field(default_factory=set)
    writes: Set[str] = field(default_factory=set)
```

**Line references:**
- Insert MimeType and Output after [models.py:15](backend/models.py#L15)
- **REMOVE** `result` field from Cell at [models.py:23](backend/models.py#L23)
- **ADD** `outputs` field to Cell at [models.py:26](backend/models.py#L26)

---

#### 1.2 MIME Bundle Conversion
**File**: `backend/executor.py`
**Changes**: Add conversion functions for chart libraries

```python
import base64
from io import BytesIO
from typing import Optional, Union, Dict, List

def to_mime_bundle(obj: object) -> Optional['Output']:
    """Convert Python object to MIME bundle output"""
    from models import Output, MimeType

    # Matplotlib figure
    try:
        import matplotlib.pyplot as plt
        if isinstance(obj, plt.Figure):
            buf = BytesIO()
            obj.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return Output(mime_type=MimeType.PNG, data=img_base64)
    except ImportError:
        pass

    # Plotly figure
    try:
        import plotly.graph_objects as go
        if isinstance(obj, go.Figure):
            html = obj.to_html(include_plotlyjs='cdn', div_id=None)
            return Output(mime_type=MimeType.HTML, data=html)
    except ImportError:
        pass

    # Altair chart
    try:
        import altair as alt
        if isinstance(obj, alt.Chart):
            vega_json = obj.to_dict()
            return Output(mime_type=MimeType.VEGA_LITE, data=vega_json)
    except ImportError:
        pass

    # Pandas DataFrame
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            table_data = {
                "type": "table",
                "columns": obj.columns.tolist(),
                "rows": obj.values.tolist()
            }
            return Output(mime_type=MimeType.JSON, data=table_data)
    except ImportError:
        pass

    # Fallback: convert to string
    return Output(mime_type=MimeType.PLAIN, data=str(obj))
```

**Insert location:** After imports at [executor.py:11](backend/executor.py#L11)

---

#### 1.3 Update ExecutionResult
**File**: `backend/executor.py`
**Changes**: Add outputs field

```python
from typing import List, Optional
from models import CellStatus, Output

class ExecutionResult:
    def __init__(
        self,
        status: CellStatus,
        stdout: str = "",
        error: Optional[str] = None,
        outputs: Optional[List[Output]] = None
    ):
        self.status: CellStatus = status
        self.stdout: str = stdout
        self.error: Optional[str] = error
        self.outputs: List[Output] = outputs or []
```

**Replace:** [executor.py:13-19](backend/executor.py#L13)
**Note:** Remove `result` parameter and field entirely

---

#### 1.4 Capture Last Expression Value
**File**: `backend/executor.py`
**Changes**: Modify `execute_python_cell()` to capture expression results

```python
from typing import Dict, List
from models import Cell, CellStatus, Output

async def execute_python_cell(
    cell: Cell,
    globals_dict: Dict[str, object],
    cell_index: int = 0
) -> ExecutionResult:
    """
    Execute Python code in cell, capturing stdout and last expression value.
    """
    stdout_capture = StringIO()
    outputs: List[Output] = []

    try:
        # Try to parse as expression first
        try:
            compiled = compile(cell.code, f"Cell[{cell_index}]", "eval")
            with redirect_stdout(stdout_capture):
                result_value = eval(compiled, globals_dict)

            # Convert result to MIME bundle
            if result_value is not None:
                output = to_mime_bundle(result_value)
                if output:
                    outputs.append(output)

        except SyntaxError:
            # Not a simple expression, compile as statements
            import ast
            tree = ast.parse(cell.code)

            if tree.body and isinstance(tree.body[-1], ast.Expr):
                # Last statement is an expression
                exec_code = compile(ast.Module(body=tree.body[:-1], type_ignores=[]),
                                   f"Cell[{cell_index}]", "exec")
                eval_code = compile(ast.Expression(body=tree.body[-1].value),
                                   f"Cell[{cell_index}]", "eval")

                with redirect_stdout(stdout_capture):
                    exec(exec_code, globals_dict)
                    result_value = eval(eval_code, globals_dict)

                if result_value is not None:
                    output = to_mime_bundle(result_value)
                    if output:
                        outputs.append(output)
            else:
                # No trailing expression
                compiled = compile(cell.code, f"Cell[{cell_index}]", "exec")
                with redirect_stdout(stdout_capture):
                    exec(compiled, globals_dict)

        stdout_text = stdout_capture.getvalue()
        return ExecutionResult(
            status=CellStatus.SUCCESS,
            stdout=stdout_text,
            outputs=outputs
        )

    except SyntaxError as e:
        error_msg = f"SyntaxError on line {e.lineno}: {e.msg}"
        if e.text:
            error_msg += f"\n{e.text.rstrip()}"
            if e.offset:
                error_msg += f"\n{' ' * (e.offset - 1)}^"
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=error_msg
        )

    except Exception as e:
        error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=error_msg
        )
```

**Replace:** [executor.py:21-64](backend/executor.py#L21)

---

#### 1.5 WebSocket Broadcasting
**File**: `backend/websocket.py`
**Changes**: Add broadcast method for outputs

```python
from typing import Dict, Union

async def broadcast_cell_output(
    self,
    notebook_id: str,
    cell_id: str,
    output: Dict[str, Union[str, dict, list]]
) -> None:
    """Broadcast a single output (MIME bundle) for a cell"""
    message: Dict[str, Union[str, dict]] = {
        "type": "cell_output",
        "cellId": cell_id,
        "output": output
    }
    await self.broadcast(notebook_id, message)
```

**Insert after:** [websocket.py:68](backend/websocket.py#L68)

---

#### 1.6 Scheduler Output Broadcasting
**File**: `backend/scheduler.py`
**Changes**: Broadcast outputs after execution

```python
# At line 104, add cell_index calculation
cell_index = notebook.cells.index(cell)

# Clear outputs at line 113-116
cell.stdout = ""
cell.outputs = []
cell.error = None

# After line 131-134, store results
cell.status = result.status
cell.stdout = result.stdout
cell.error = result.error
cell.outputs = result.outputs

# After line 145, add output broadcasting
for output in result.outputs:
    await broadcaster.broadcast_cell_output(notebook_id, cell.id, {
        "mime_type": output.mime_type,
        "data": output.data,
        "metadata": output.metadata
    })
```

**Modify locations:** Lines 104, 114, 134, after 145

---

#### 1.7 Frontend Types
**File**: `frontend/src/api.ts`
**Changes**: Add Output interface and update Cell

```typescript
// Table data structure for pandas DataFrames and SQL results
export interface TableData {
  type: 'table';
  columns: string[];
  rows: (string | number | boolean | null)[][];
  truncated?: string;
}

// Output data can be string (base64, HTML) or structured (JSON, table)
export type OutputData = string | TableData | Record<string, unknown>;

export interface Output {
  mime_type: string;
  data: OutputData;
  metadata?: Record<string, string | number | boolean>;
}

export type CellType = 'python' | 'sql';
export type CellStatus = 'idle' | 'running' | 'success' | 'error' | 'blocked';

export interface Cell {
  id: string;
  type: CellType;
  code: string;
  status: CellStatus;
  stdout?: string;
  // REMOVED: result field
  outputs?: Output[];  // NEW: Replaces result
  error?: string;
  reads: string[];
  writes: string[];
}
```

**Modify:** [api.ts:3-13](frontend/src/api.ts#L3)

---

#### 1.8 WebSocket Message Types
**File**: `frontend/src/useWebSocket.ts`
**Changes**: Add cell_output message type

```typescript
import { Output, CellStatus } from './api';

export type WSMessage =
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  // REMOVED: cell_result (replaced by cell_output)
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: Output };
```

**Modify:** [useWebSocket.ts:3-7](frontend/src/useWebSocket.ts#L3)

---

#### 1.9 Frontend Message Handling
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Handle cell_output messages and fix double-run bug

```typescript
const handleWSMessage = useCallback((msg: WSMessage) => {
  setNotebook(prev => {
    if (!prev) return prev;

    const cells = prev.cells.map(cell => {
      if (cell.id !== msg.cellId) return cell;

      switch (msg.type) {
        case 'cell_status':
          if (msg.status === 'running') {
            // Clear outputs when execution starts
            return { ...cell, status: 'running', stdout: '', outputs: [], error: undefined };
          }
          return { ...cell, status: msg.status };

        case 'cell_stdout':
          return { ...cell, stdout: msg.data };

        case 'cell_error':
          return { ...cell, error: msg.error };

        case 'cell_output':
          const outputs = cell.outputs || [];
          return { ...cell, outputs: [...outputs, msg.output] };

        default:
          return cell;
      }
    });

    return { ...prev, cells };
  });
}, []);
```

**Replace:** [Notebook.tsx:25-48](frontend/src/components/Notebook.tsx#L25)

---

#### 1.10 Output Renderer Component
**File**: `frontend/src/components/OutputRenderer.tsx` (NEW FILE)

```typescript
import React from 'react';
import { Output, TableData } from '../api';

interface OutputRendererProps {
  output: Output;
}

// Type guard for TableData
function isTableData(data: unknown): data is TableData {
  return (
    typeof data === 'object' &&
    data !== null &&
    'type' in data &&
    data.type === 'table' &&
    'columns' in data &&
    'rows' in data
  );
}

export function OutputRenderer({ output }: OutputRendererProps) {
  switch (output.mime_type) {
    case 'image/png':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected base64 string for PNG image</div>;
      }
      return (
        <img
          src={`data:image/png;base64,${output.data}`}
          alt="Chart output"
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      );

    case 'text/html':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected HTML string</div>;
      }
      return (
        <div
          dangerouslySetInnerHTML={{ __html: output.data }}
          style={{ width: '100%' }}
        />
      );

    case 'application/vnd.vegalite.v5+json':
      return (
        <div style={{
          backgroundColor: '#f3f4f6',
          padding: '8px',
          borderRadius: '4px'
        }}>
          <pre>{JSON.stringify(output.data, null, 2)}</pre>
        </div>
      );

    case 'application/json':
      if (isTableData(output.data)) {
        return (
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '12px'
          }}>
            <thead>
              <tr style={{ backgroundColor: '#e5e7eb' }}>
                {output.data.columns.map((col) => (
                  <th key={col} style={{
                    border: '1px solid #d1d5db',
                    padding: '4px 8px',
                    textAlign: 'left'
                  }}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {output.data.rows.map((row, idx) => (
                <tr key={idx}>
                  {row.map((val, i) => (
                    <td key={i} style={{
                      border: '1px solid #d1d5db',
                      padding: '4px 8px'
                    }}>{val === null ? 'null' : String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      return <pre>{JSON.stringify(output.data, null, 2)}</pre>;

    case 'text/plain':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected string for plain text</div>;
      }
      return (
        <pre style={{
          backgroundColor: '#f3f4f6',
          padding: '8px',
          borderRadius: '4px',
          fontSize: '13px',
          overflow: 'auto',
          whiteSpace: 'pre-wrap'
        }}>
          {output.data}
        </pre>
      );

    default:
      return (
        <div style={{ color: '#6b7280', fontSize: '12px' }}>
          Unsupported output type: {output.mime_type}
        </div>
      );
  }
}
```

---

#### 1.11 Update Cell Component
**File**: `frontend/src/components/Cell.tsx`
**Changes**: Render outputs using OutputRenderer

```typescript
import { OutputRenderer } from './OutputRenderer';

// In output section (around line 154):
{cell.status !== 'idle' && (
  <div style={{ marginTop: '12px' }}>
    {/* Stdout */}
    {cell.stdout && (
      <pre style={{
        backgroundColor: '#f3f4f6',
        padding: '8px',
        borderRadius: '4px',
        fontSize: '13px',
        overflow: 'auto',
        margin: '8px 0'
      }}>
        {cell.stdout}
      </pre>
    )}

    {/* NEW: Rich outputs */}
    {cell.outputs && cell.outputs.map((output, idx) => (
      <div key={idx} style={{
        backgroundColor: '#f3f4f6',
        padding: '8px',
        borderRadius: '4px',
        marginTop: '8px'
      }}>
        <OutputRenderer output={output} />
      </div>
    ))}

    {/* Error */}
    {cell.error && (
      <pre style={{
        backgroundColor: '#fef2f2',
        color: '#991b1b',
        padding: '8px',
        borderRadius: '4px',
        fontSize: '13px',
        overflow: 'auto',
        marginTop: '8px'
      }}>
        {cell.error}
      </pre>
    )}

    {/* Blocked status */}
    {cell.status === 'blocked' && !cell.error && (
      <div style={{
        backgroundColor: '#fffbeb',
        color: '#92400e',
        padding: '8px',
        borderRadius: '4px',
        fontSize: '13px',
        marginTop: '8px'
      }}>
        ⚠️ Upstream dependency failed.
      </div>
    )}
  </div>
)}
```

**Modify section:** Around [Cell.tsx:154](frontend/src/components/Cell.tsx#L154)

---

### Success Criteria:

#### Automated Verification:
- None (chart rendering requires visual verification)

#### Manual Verification:
- [x] **COMPLETED** - Backend implementation complete
- [x] **COMPLETED** - Frontend implementation complete
- [ ] Run `import matplotlib.pyplot as plt; plt.plot([1,2,3]); plt.gcf()` - Chart displays as PNG
- [ ] Run `import plotly.express as px; px.bar(x=['a','b','c'], y=[4,5,6])` - Interactive chart displays
- [ ] Run pandas DataFrame - displays as table
- [ ] Charts have appropriate sizing
- [ ] Print statements and charts both appear

---

## Phase 2: Standard Package Set

### Overview
Install required data science packages and frontend libraries.

### Changes Required:

#### 2.1 Python Packages
**File**: `requirements.txt`

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
asyncpg==0.29.0
pydantic==2.5.0
websockets==12.0
pytest==7.4.3
pytest-asyncio==0.21.1
mypy==1.7.1
matplotlib>=3.8.0
pandas>=2.1.0
numpy>=1.26.0
plotly>=5.18.0
altair>=5.2.0
```

---

#### 2.2 Frontend Vega Libraries
**File**: `frontend/package.json`

Add to dependencies:
```json
"vega": "^5.27.0",
"vega-lite": "^5.16.0",
"vega-embed": "^6.24.0"
```

---

#### 2.3 Update OutputRenderer for Vega
**File**: `frontend/src/components/OutputRenderer.tsx`

```typescript
import embed from 'vega-embed';
import { useEffect, useRef } from 'react';
import type { VisualizationSpec } from 'vega-embed';

// Replace vegalite case with:
case 'application/vnd.vegalite.v5+json':
  if (typeof output.data === 'object' && output.data !== null) {
    return <VegaLiteRenderer spec={output.data as VisualizationSpec} />;
  }
  return <div>Error: Expected Vega-Lite spec object</div>;

// Add at end:
interface VegaLiteRendererProps {
  spec: VisualizationSpec;
}

function VegaLiteRenderer({ spec }: VegaLiteRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      embed(containerRef.current, spec, {
        actions: false,
        renderer: 'svg'
      }).catch(err => {
        console.error('Vega-Lite rendering error:', err);
      });
    }
  }, [spec]);

  return <div ref={containerRef} style={{ width: '100%' }} />;
}
```

---

### Success Criteria:

#### Automated Verification:
- [x] **COMPLETED** - `pip install -r requirements.txt` succeeds
- [x] **COMPLETED** - `cd frontend && npm install` succeeds
- [x] **COMPLETED** - `python -c "import matplotlib, pandas, numpy, plotly, altair"` succeeds

#### Manual Verification:
- [ ] All packages import in notebook cells
- [ ] Altair charts render as interactive SVG

---

## Phase 3: Notebook Persistence

### Overview
Implement file-based persistence with auto-save and demo notebook.

### Changes Required:

#### 3.1 Storage Layer
**File**: `backend/storage.py` (NEW FILE)

```python
import json
import os
from pathlib import Path
from typing import Dict, List
from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState

NOTEBOOKS_DIR = Path("notebooks")

def ensure_notebooks_dir():
    NOTEBOOKS_DIR.mkdir(exist_ok=True)

def save_notebook(notebook: Notebook) -> None:
    ensure_notebooks_dir()

    data = {
        "id": notebook.id,
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
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def load_notebook(notebook_id: str) -> Notebook:
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"

    with open(file_path, 'r') as f:
        data = json.load(f)

    cells = [
        Cell(
            id=cell_data["id"],
            type=CellType(cell_data["type"]),
            code=cell_data["code"],
            status=CellStatus.IDLE,
            reads=set(cell_data.get("reads", [])),
            writes=set(cell_data.get("writes", []))
        )
        for cell_data in data["cells"]
    ]

    notebook = Notebook(
        id=data["id"],
        db_conn_string=data.get("db_conn_string"),
        cells=cells,
        revision=data.get("revision", 0)
    )

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook

def list_notebooks() -> List[str]:
    ensure_notebooks_dir()
    return [f.stem for f in NOTEBOOKS_DIR.glob("*.json")]
```

---

#### 3.2 Demo Notebook
**File**: `backend/demo_notebook.py` (NEW FILE)

```python
import uuid
from models import Notebook, Cell, CellType, CellStatus

def create_demo_notebook() -> Notebook:
    cells = [
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="x = 10  # Upstream variable",
            status=CellStatus.IDLE,
            reads=set(),
            writes={'x'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="y = x + 5  # Depends on x",
            status=CellStatus.IDLE,
            reads={'x'},
            writes={'y'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import matplotlib.pyplot as plt

# Matplotlib chart - rendered as PNG
plt.figure(figsize=(8, 5))
plt.plot([1, 2, 3], [x, y, 15], marker='o', linewidth=2)
plt.title(f"Matplotlib: Dependency Demo (x={x}, y={y})")
plt.xlabel("Step")
plt.ylabel("Value")
plt.grid(True, alpha=0.3)
plt.gcf()""",
            status=CellStatus.IDLE,
            reads={'x', 'y', 'plt'},
            writes={'plt'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import pandas as pd

# Create DataFrame
df = pd.DataFrame({
    "category": ["A", "B", "C", "D"],
    "value": [x, y, x+y, x*2],
    "label": ["X", "Y", "Sum", "Double"]
})
df""",
            status=CellStatus.IDLE,
            reads={'x', 'y', 'pd'},
            writes={'df', 'pd'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import plotly.express as px

# Plotly interactive chart - rendered as HTML
fig = px.bar(
    df,
    x="category",
    y="value",
    title=f"Plotly: Interactive Bar Chart (x={x})",
    labels={"value": "Amount", "category": "Category"},
    text="label",
    color="value",
    color_continuous_scale="viridis"
)
fig.update_traces(textposition='outside')
fig.update_layout(height=400)
fig""",
            status=CellStatus.IDLE,
            reads={'df', 'x', 'px'},
            writes={'fig', 'px'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import altair as alt

# Altair chart - rendered as Vega-Lite JSON
chart = alt.Chart(df).mark_bar().encode(
    x=alt.X('category:N', title='Category'),
    y=alt.Y('value:Q', title='Value'),
    color=alt.Color('value:Q', scale=alt.Scale(scheme='viridis')),
    tooltip=['category', 'value', 'label']
).properties(
    title='Altair: Declarative Visualization',
    width=400,
    height=300
)
chart""",
            status=CellStatus.IDLE,
            reads={'df', 'alt'},
            writes={'chart', 'alt'}
        )
    ]

    notebook = Notebook(id="demo", cells=cells, revision=0)

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook
```

---

#### 3.3 Auto-save Integration
**File**: `backend/routes.py`

```python
from storage import save_notebook, load_notebook, list_notebooks

# Add save_notebook() calls after:
# Line 52 (notebook creation)
# Line 88 (DB update)
# Line 116 (cell creation)
# Line 156 (cell update)
# Line 181 (cell deletion)
```

---

#### 3.4 Startup Loading
**File**: `backend/main.py`

```python
from storage import list_notebooks, load_notebook, save_notebook
from demo_notebook import create_demo_notebook

@app.on_event("startup")
async def startup_event():
    notebook_ids = list_notebooks()

    if notebook_ids:
        print(f"Loading {len(notebook_ids)} notebook(s)...")
        for notebook_id in notebook_ids:
            try:
                notebook = load_notebook(notebook_id)
                NOTEBOOKS[notebook_id] = notebook
                print(f"  ✓ Loaded: {notebook_id}")
            except Exception as e:
                print(f"  ✗ Failed: {notebook_id}: {e}")
    else:
        print("Creating demo notebook...")
        demo = create_demo_notebook()
        NOTEBOOKS[demo.id] = demo
        save_notebook(demo)
        print(f"  ✓ Created demo: {demo.id}")
```

---

### Success Criteria:

#### Automated Verification:
- [x] **COMPLETED** - Implementation complete (storage.py, demo_notebook.py, auto-save, startup loading)
- [ ] `ls notebooks/` shows JSON files (requires server restart)
- [ ] Server restart preserves notebooks
- [ ] `cat notebooks/demo.json` shows valid JSON

#### Manual Verification:
- [ ] Create notebook, restart, verify persists
- [ ] Demo notebook loads with 6 cells: x, y, matplotlib, pandas, plotly, altair
- [ ] All charts in demo render correctly (PNG, table, HTML, Vega-Lite)
- [ ] Edits to demo persist across restarts

---

## Phase 4: Double-Run Bug Fix

### Changes Required:

**File**: `frontend/src/components/Notebook.tsx`

Already fixed in Phase 1.9 - outputs cleared when status becomes 'running'

---

## Phase 5: Cell Number Traceback Mapping

### Changes Required:

Already implemented in Phase 1.4 - cell_index passed to compile()

---

## Testing Strategy

### Manual Integration Tests:

1. **Chart Rendering:**
   - Run matplotlib, plotly, altair cells
   - Verify charts display correctly
   - Check sizing and styling

2. **Persistence:**
   - Create notebook, restart, verify persists
   - Edit demo, restart, verify changes saved

3. **Reactive Charts:**
   - Cell 1: `x = 5`
   - Cell 2: matplotlib chart using x
   - Change x, verify chart updates

4. **Bug Fixes:**
   - Run cell twice, no duplicate output
   - Error shows Cell[N] not UUID

---

## Implementation Order

1. Phase 2 (Packages) - 30 min
2. Phase 4 (Bug fix) - Already in Phase 1
3. Phase 5 (Traceback) - Already in Phase 1
4. Phase 1 (MIME bundles) - 3-4 hours
5. Phase 3 (Persistence) - 2 hours

**Total: 6-8 hours**

---

## Implementation Status

### ✅ Completed (December 27, 2024)

**Phase 1: MIME Bundle Output System** - COMPLETE
- ✅ Backend models updated (Output, MimeType, Cell.outputs)
- ✅ MIME bundle conversion functions (matplotlib, plotly, altair, pandas)
- ✅ ExecutionResult refactored to use outputs
- ✅ execute_python_cell captures last expression values
- ✅ WebSocket broadcasting for outputs
- ✅ Scheduler updated to broadcast outputs
- ✅ Frontend types (Output, TableData)
- ✅ WebSocket message types updated
- ✅ Notebook.tsx message handling with double-run bug fix
- ✅ OutputRenderer component created with Vega-Lite support
- ✅ Cell.tsx updated to use OutputRenderer

**Phase 2: Standard Package Set** - COMPLETE
- ✅ Python packages installed (matplotlib, pandas, plotly, altair)
- ✅ Frontend Vega libraries installed (vega, vega-lite, vega-embed)
- ✅ All imports verified working

**Phase 3: Notebook Persistence** - COMPLETE
- ✅ storage.py created with save/load functions
- ✅ demo_notebook.py created with 6 example cells
- ✅ Auto-save integrated in routes.py (all CRUD operations)
- ✅ Startup loading in main.py

**Phase 4: Double-Run Bug Fix** - COMPLETE
- ✅ Fixed in Phase 1.9 (outputs cleared on 'running' status)

**Phase 5: Cell Number Traceback Mapping** - COMPLETE
- ✅ Fixed in Phase 1.4 (cell_index passed to compile())

### 🔧 Known Issues

1. **TypeScript Build Error** - Frontend has type error in Notebook.tsx line 26 related to status type casting
   - Issue: When clearing outputs on 'running' status, TypeScript doesn't properly infer the CellStatus type
   - Fix needed: Cast 'running' to CellStatus type or adjust the return type

### 📋 Remaining Tasks

1. Fix TypeScript build error
2. Restart backend server to activate all changes
3. Manual testing of chart rendering
4. Verify persistence across server restarts

### 🚀 How to Access the Demo Notebook

The demo notebook has been created at `backend/notebooks/demo.json`. To access it:

1. **Backend** (should auto-reload, but if not):
   ```bash
   cd backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open in browser**: Navigate to `http://localhost:5173` (or the port shown by Vite)

4. **Load demo notebook**: The frontend should automatically connect to the "demo" notebook ID

The demo notebook contains 6 cells demonstrating:
- Cell 0: Define variable `x = 10`
- Cell 1: Define variable `y = x + 5` (reactive dependency)
- Cell 2: Matplotlib line chart using x and y
- Cell 3: Pandas DataFrame creation
- Cell 4: Plotly interactive bar chart
- Cell 5: Altair/Vega-Lite declarative chart

All cells will re-execute automatically when dependencies change!
