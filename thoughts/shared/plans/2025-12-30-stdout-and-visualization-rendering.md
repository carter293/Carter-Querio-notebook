---
date: 2025-12-30T15:53:07Z
planner: AI Assistant
topic: "Print statements and fig.show() output rendering"
tags: [planning, implementation, stdout, plotly, websocket, output-rendering]
status: draft
last_updated: 2025-12-30
last_updated_by: AI Assistant
---

# Print Statements and fig.show() Output Rendering Implementation Plan

**Date**: 2025-12-30 15:53:07 GMT  
**Planner**: AI Assistant

## Overview

This plan addresses two bugs that prevent notebook output from rendering correctly:

1. **`print()` statements produce no visible output** - The backend captures stdout and broadcasts it via WebSocket, but the frontend `handleWebSocketMessage` has no handler for `cell_stdout` messages.

2. **`fig.show()` opens browser tabs** - The executor only captures the last expression's value. When `fig.show()` is the last statement, it returns `None` while triggering Plotly's default renderer (which opens a browser).

## Current State Analysis

### Backend (Working Correctly for stdout)
- `executor.py:103,123,134` - Uses `redirect_stdout(stdout_capture)` to capture print output
- `executor.py:137-142` - Returns `stdout_text` in `ExecutionResult`
- `scheduler.py:147` - Sets `cell.stdout = result.stdout`
- `scheduler.py:154-155` - Broadcasts stdout if non-empty via `broadcast_cell_stdout`
- `websocket.py:49-54` - Sends `{type: "cell_stdout", cellId, data}` message

### Frontend (Bug Location)
- `useNotebookWebSocket.ts:13` - Defines `cell_stdout` message type correctly
- `NotebookApp.tsx:113-175` - Handles `cell_updated`, `cell_created`, `cell_deleted`, `cell_status`, `cell_output`, `cell_error` but **NO `cell_stdout` handler**
- `NotebookCell.tsx:135-140` - Only renders `outputs` array, never renders `stdout` field

### Visualization Libraries
- `executor.py:32-38` - `to_mime_bundle()` correctly detects Plotly figures when they're the last expression
- However, `fig.show()` returns `None`, so nothing is captured
- No mechanism to intercept `.show()` calls from matplotlib, Plotly, or Altair

## System Context Analysis

This plan addresses **both the symptom AND the root cause**:

1. **Symptom**: Missing frontend handler for `cell_stdout` - simple fix
2. **Root Cause (stdout)**: Stdout should stream line-by-line, not accumulate (architectural improvement)  
3. **Root Cause (visualization)**: Need library-specific overrides to capture `.show()` calls instead of relying on last-expression capture

The visualization fix follows the same pattern Jupyter uses - overriding each library's display mechanism rather than AST/regex detection of `.show()` calls.

## Desired End State

After implementation:

1. **Print statements display in cells** - Any `print()` output appears in a dedicated stdout area
2. **stdout streams in real-time** - Long-running cells show output as it's produced
3. **`fig.show()` renders inline** - Plotly, Matplotlib, and Altair `.show()` methods capture figures instead of opening browsers
4. **Multiple outputs per cell** - A cell can produce multiple charts plus stdout

### Key Discoveries

- `CellResponse.stdout` field already exists in types (`types.gen.ts:20`)
- WebSocket message type `cell_stdout` already defined (`useNotebookWebSocket.ts:13`)
- Backend already broadcasts stdout (`scheduler.py:154-155`)
- Only frontend handler + rendering is missing

## What We're NOT Doing

1. **Stderr capture** - Out of scope; could be added later using same pattern
2. **Rich text/ANSI color support in stdout** - Plain text only for now
3. **Streaming during execution** - Phase 1 sends stdout after execution completes; Phase 2 adds true streaming
4. **Seaborn/Bokeh/other visualization libraries** - Only Matplotlib, Plotly, Altair initially

## Implementation Approach

Three phases:
1. **Phase 1**: Frontend fixes - Add `cell_stdout` handler and render stdout
2. **Phase 2**: Backend streaming - Stream stdout line-by-line during execution  
3. **Phase 3**: Visualization capture - Override `.show()` for supported libraries

---

## Phase 1: Frontend stdout Handling

### Overview
Add the missing `cell_stdout` WebSocket handler and render stdout in cells.

### Changes Required

#### 1. Add `cell_stdout` Handler
**File**: `frontend/src/components/NotebookApp.tsx`
**Changes**: Add case for `cell_stdout` in `handleWebSocketMessage` switch statement

```typescript
case "cell_stdout":
  setCells((prev) =>
    prev.map((c) =>
      c.id === msg.cellId
        ? {
            ...c,
            stdout: (c.stdout || "") + msg.data,  // Append streamed data
          }
        : c
    )
  );
  break;
```

#### 2. Clear stdout on Cell Run
**File**: `frontend/src/components/NotebookApp.tsx`
**Changes**: Modify `cell_status` case to clear stdout when status is 'running'

```typescript
case "cell_status":
  setCells((prev) =>
    prev.map((c) => {
      if (c.id !== msg.cellId) return c;
      if (msg.status === 'running') {
        // Clear outputs AND stdout when execution starts
        return { ...c, status: msg.status, outputs: [], stdout: "", error: undefined };
      }
      return { ...c, status: msg.status };
    })
  );
  break;
```

#### 3. Render stdout in Cell
**File**: `frontend/src/components/NotebookCell.tsx`
**Changes**: Add stdout rendering area above rich outputs

```tsx
{/* stdout Area - separate from rich outputs */}
{cell.stdout && (
  <div className="bg-zinc-900/50 border-b border-border p-4 font-mono text-sm text-zinc-300">
    <pre className="whitespace-pre-wrap overflow-x-auto">{cell.stdout}</pre>
  </div>
)}

{/* Rich Outputs Area */}
{cell.outputs && cell.outputs.length > 0 && (
  <div className="bg-muted/30 p-4 space-y-2">
    {cell.outputs.map((output, idx) => (
      <OutputRenderer key={idx} output={output} cellId={cell.id} outputIndex={idx} />
    ))}
  </div>
)}
```

### Success Criteria

#### Automated Verification:
- [ ] TypeScript compiles: `cd frontend && npm run build`
- [ ] ESLint passes: `cd frontend && npm run lint`

#### Manual Verification:
- [ ] Create a cell with `print("Hello, World!")` and run it - output appears
- [ ] Create a cell with multiple print statements - all appear in order
- [ ] Run cell twice - previous stdout is cleared, new stdout appears
- [ ] stdout appears in its own styled area, separate from rich outputs

---

## Phase 2: Backend stdout Streaming

### Overview
Modify the executor to stream stdout line-by-line during execution instead of accumulating and sending at the end.

### Changes Required

#### 1. Create Streaming stdout Wrapper
**File**: `backend/executor.py`
**Changes**: Add `StreamingStdout` class and helper

```python
class StreamingStdout:
    """Stdout wrapper that streams lines via callback."""
    
    def __init__(self, callback):
        """
        Args:
            callback: Callable that receives line strings to stream
        """
        self._callback = callback
        self._buffer = ""
    
    def write(self, data: str):
        self._buffer += data
        # Flush complete lines
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self._callback(line + '\n')
    
    def flush(self):
        if self._buffer:
            self._callback(self._buffer)
            self._buffer = ""


def create_stdout_streamer(broadcaster, notebook_id: str, cell_id: str):
    """Create a streaming stdout that broadcasts via WebSocket."""
    import asyncio
    
    def stream_line(line: str):
        # Schedule the async broadcast in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                broadcaster.broadcast_cell_stdout(notebook_id, cell_id, line)
            )
        except RuntimeError:
            # No running loop - fall back to synchronous accumulation
            pass
    
    return StreamingStdout(stream_line)
```

#### 2. Update Executor to Use Streaming stdout
**File**: `backend/executor.py`
**Changes**: Modify `execute_python_cell` to accept optional streaming callback

```python
async def execute_python_cell(
    cell: 'Cell',
    globals_dict: Dict[str, Any],
    cell_index: int = 0,
    stdout_stream: Optional[Any] = None  # StreamingStdout instance
) -> ExecutionResult:
    """Execute Python code, optionally streaming stdout."""
    from models import CellStatus
    import ast
    
    # Use provided stream or fall back to StringIO for accumulated capture
    stdout_capture = stdout_stream or StringIO()
    outputs: List['Output'] = []
    
    try:
        # ... existing execution code with redirect_stdout(stdout_capture) ...
        
        # If using StringIO (non-streaming), get accumulated text
        if isinstance(stdout_capture, StringIO):
            stdout_text = stdout_capture.getvalue()
        else:
            # Streaming mode - flush any remaining buffer
            stdout_capture.flush()
            stdout_text = ""  # Already streamed
        
        return ExecutionResult(
            status=CellStatus.SUCCESS,
            stdout=stdout_text,
            outputs=outputs
        )
```

#### 3. Update Scheduler to Create Streaming stdout
**File**: `backend/scheduler.py`
**Changes**: Create streaming stdout in `_execute_cell` before execution

```python
async def _execute_cell(self, notebook_id: str, cell, notebook, broadcaster):
    """Execute a single cell and broadcast results"""
    from executor import execute_python_cell, execute_sql_cell, create_stdout_streamer
    from models import CellStatus, CellType

    # ... existing status broadcast code ...
    
    # Create streaming stdout for this cell
    stdout_stream = create_stdout_streamer(broadcaster, notebook_id, cell.id)
    
    # Execute based on type
    if cell.type == CellType.PYTHON:
        result = await execute_python_cell(
            cell, 
            notebook.kernel.globals_dict, 
            cell_index,
            stdout_stream=stdout_stream  # Pass streaming stdout
        )
    # ... rest of method ...
```

### Success Criteria

#### Automated Verification:
- [ ] Backend tests pass: `cd backend && python -m pytest`
- [ ] No Python syntax errors: `python -m py_compile backend/executor.py backend/scheduler.py`

#### Manual Verification:
- [ ] Create cell with `import time; [print(i) or time.sleep(0.5) for i in range(5)]`
- [ ] Each number should appear one at a time as it prints (not all at once at end)
- [ ] Long-running cells show streaming output

---

## Phase 3: Visualization Capture

### Overview
Override `.show()` methods for Matplotlib, Plotly, and Altair to capture figures instead of opening browsers.

### Changes Required

#### 1. Create Visualization Capture Module
**File**: `backend/visualization_capture.py` (new file)
**Changes**: Implement unified visualization capture setup

```python
"""
Visualization capture for notebook execution.

Overrides .show() methods for supported libraries to capture output
instead of opening browsers/windows.
"""

from typing import List, Dict, Any
import base64
from io import BytesIO


def setup_visualization_capture(output_collector: List[Dict[str, Any]]):
    """
    Configure supported visualization libraries to capture .show() calls.
    
    Call at the start of each cell execution, passing the output collector
    that will accumulate outputs during execution.
    
    Args:
        output_collector: List to append captured outputs to
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # MATPLOTLIB - Override plt.show()
    # ═══════════════════════════════════════════════════════════════════
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        
        def _capture_plt_show(*args, **kwargs):
            """Capture all open figures when plt.show() is called."""
            figs = [plt.figure(num) for num in plt.get_fignums()]
            for fig in figs:
                buf = BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
                buf.seek(0)
                output_collector.append({
                    "mime_type": "image/png",
                    "data": base64.b64encode(buf.read()).decode('utf-8')
                })
            plt.close('all')  # Clean up after capture
        
        plt.show = _capture_plt_show
    except ImportError:
        pass
    
    # ═══════════════════════════════════════════════════════════════════
    # PLOTLY - Custom renderer for fig.show()
    # ═══════════════════════════════════════════════════════════════════
    try:
        import plotly.io as pio
        
        class NotebookPlotlyRenderer:
            """Custom Plotly renderer that captures to output collector."""
            
            def __call__(self, fig_dict, **kwargs):
                output_collector.append({
                    "mime_type": "application/vnd.plotly.v1+json",
                    "data": fig_dict
                })
        
        pio.renderers["notebook_capture"] = NotebookPlotlyRenderer()
        pio.renderers.default = "notebook_capture"
    except ImportError:
        pass
    
    # ═══════════════════════════════════════════════════════════════════
    # ALTAIR - Override .display() method
    # ═══════════════════════════════════════════════════════════════════
    try:
        import altair as alt
        
        def _capture_altair_display(self, *args, **kwargs):
            """Capture Altair chart when .display() is called."""
            output_collector.append({
                "mime_type": "application/vnd.vegalite.v6+json",
                "data": self.to_dict()
            })
        
        # Override for all chart types
        for chart_class in [alt.Chart, alt.LayerChart, alt.HConcatChart, 
                           alt.VConcatChart, alt.FacetChart]:
            if hasattr(chart_class, 'display'):
                chart_class.display = _capture_altair_display
    except ImportError:
        pass
```

#### 2. Integrate with Executor
**File**: `backend/executor.py`
**Changes**: Call `setup_visualization_capture` before executing user code

```python
async def execute_python_cell(
    cell: 'Cell',
    globals_dict: Dict[str, Any],
    cell_index: int = 0,
    stdout_stream: Optional[Any] = None
) -> ExecutionResult:
    """Execute Python code, capturing stdout and visualizations."""
    from models import CellStatus
    from visualization_capture import setup_visualization_capture
    import ast

    stdout_capture = stdout_stream or StringIO()
    outputs: List['Output'] = []
    
    # Collector for .show() calls during execution
    show_outputs = []
    setup_visualization_capture(show_outputs)
    
    try:
        # ... existing execution code ...
        
        # After execution, add .show() outputs BEFORE last-expression output
        for output_dict in show_outputs:
            from models import Output, MimeType
            mime_type = MimeType(output_dict["mime_type"])
            outputs.append(Output(mime_type=mime_type, data=output_dict["data"]))
        
        # Then add last-expression result (existing code)
        if result_value is not None:
            output = to_mime_bundle(result_value)
            if output:
                outputs.append(output)
        
        return ExecutionResult(
            status=CellStatus.SUCCESS,
            stdout=stdout_text,
            outputs=outputs
        )
```

#### 3. Update MimeType Enum (if needed)
**File**: `backend/models.py`
**Changes**: Ensure PNG mime type is defined for matplotlib output

```python
class MimeType(str, Enum):
    PLAIN = "text/plain"
    HTML = "text/html"
    PNG = "image/png"
    JSON = "application/json"
    PLOTLY_JSON = "application/vnd.plotly.v1+json"
    VEGA_LITE = "application/vnd.vegalite.v6+json"
```

### Success Criteria

#### Automated Verification:
- [ ] Backend tests pass: `cd backend && python -m pytest`
- [ ] New module imports correctly: `python -c "from visualization_capture import setup_visualization_capture"`

#### Manual Verification:
- [ ] Plotly cell ending with `fig.show()` - renders inline, no browser tab
- [ ] Plotly cell ending with `fig` - still works (last-expression capture)
- [ ] Matplotlib cell with `plt.show()` - renders inline PNG
- [ ] Cell with multiple `.show()` calls - all figures render in order
- [ ] Cell with `print()` AND `fig.show()` - both stdout and chart render

---

## Testing Strategy

### Unit Tests

**File**: `backend/tests/test_visualization_capture.py` (new)

```python
def test_plotly_show_captured():
    """fig.show() should capture figure instead of opening browser."""
    from visualization_capture import setup_visualization_capture
    import plotly.graph_objects as go
    
    outputs = []
    setup_visualization_capture(outputs)
    
    fig = go.Figure(data=go.Scatter(x=[1,2,3], y=[1,2,3]))
    fig.show()
    
    assert len(outputs) == 1
    assert outputs[0]["mime_type"] == "application/vnd.plotly.v1+json"

def test_matplotlib_show_captured():
    """plt.show() should capture all figures as PNG."""
    from visualization_capture import setup_visualization_capture
    import matplotlib.pyplot as plt
    
    outputs = []
    setup_visualization_capture(outputs)
    
    plt.figure()
    plt.plot([1,2,3], [1,2,3])
    plt.show()
    
    assert len(outputs) == 1
    assert outputs[0]["mime_type"] == "image/png"

def test_multiple_shows():
    """Multiple .show() calls should produce multiple outputs."""
    from visualization_capture import setup_visualization_capture
    import plotly.graph_objects as go
    
    outputs = []
    setup_visualization_capture(outputs)
    
    go.Figure().show()
    go.Figure().show()
    go.Figure().show()
    
    assert len(outputs) == 3
```

### Integration Tests

Test via the notebook UI:
1. Create cell with print + chart, verify both render
2. Create cell with multiple charts, verify all render in order
3. Verify streaming stdout works with long-running cells

### Manual Testing Steps

1. Start backend: `cd backend && uvicorn main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open notebook in browser
4. Test each scenario from Success Criteria

## Performance Considerations

1. **Streaming stdout adds WebSocket messages** - Each line is a separate message. For cells that print thousands of lines, consider batching or throttling.

2. **Large figures** - PNG images for matplotlib are base64 encoded, increasing size ~33%. Consider adding compression or size limits.

3. **Memory for captured outputs** - The `output_collector` list holds all outputs in memory during execution. For cells that produce many large charts, this could be significant.

## Migration Notes

No database migrations required. Changes are backward-compatible:
- Frontend will simply start displaying stdout that was always being sent
- Visualization capture adds new capability without breaking existing behavior
- Cells that end with `fig` (not `fig.show()`) continue to work via last-expression capture

## References

- Original research: `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md`
- WebSocket message types: `frontend/src/useNotebookWebSocket.ts:8-15`
- Cell type definition: `frontend/src/client/types.gen.ts:6-37`
- Executor implementation: `backend/executor.py:80-161`
- Scheduler broadcast: `backend/scheduler.py:151-166`

