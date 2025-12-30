---
date: 2025-12-30T15:37:45Z
researcher: AI Assistant
topic: "Print statements and fig.show() not rendering in notebook UI"
tags: [research, codebase, stdout, plotly, websocket, output-rendering]
status: complete
last_updated: 2025-12-30
last_updated_by: AI Assistant
last_updated_note: "Added design decisions for dual stdout/output rendering and Plotly renderer override approach"
---

# Research: Print statements and fig.show() not rendering in notebook UI

**Date**: 2025-12-30T15:37:45 GMT  
**Researcher**: AI Assistant

## Research Question
Why do `print()` statements produce no output in the notebook UI? Why does `fig.show()` open a browser tab instead of rendering inline?

## Summary

**Two distinct bugs were identified:**

1. **`stdout` from `print()` is never rendered** - The backend captures stdout and broadcasts it via WebSocket (`cell_stdout` message), but the frontend `handleWebSocketMessage` has **no handler** for `cell_stdout` messages. The message is received but silently ignored.

2. **`fig.show()` opens browser** - This is by design. The executor only captures the *last expression* in a cell. When you call `fig.show()` as the last statement, it returns `None` (not the figure), so no Plotly output is captured. Meanwhile, `fig.show()` itself triggers Plotly's default renderer which opens a browser tab since it's not running in a Jupyter environment.

## Detailed Findings

### Issue 1: `print()` / `stdout` Not Displayed

#### Backend Flow (Working Correctly)
1. **Capture**: `executor.py:103,123,134` uses `redirect_stdout(stdout_capture)` to capture all print output
2. **Return**: `executor.py:137-142` returns `stdout_text` in `ExecutionResult`
3. **Update cell**: `scheduler.py:147` sets `cell.stdout = result.stdout`  
4. **Broadcast**: `scheduler.py:154-155` broadcasts stdout if non-empty:
   ```python
   if result.stdout:
       await broadcaster.broadcast_cell_stdout(notebook_id, cell.id, result.stdout)
   ```
5. **WebSocket message**: `websocket.py:49-54` sends:
   ```python
   {"type": "cell_stdout", "cellId": cell_id, "data": data}
   ```

#### Frontend Bug (Missing Handler)
The `handleWebSocketMessage` in `NotebookApp.tsx:113-174` handles these message types:
- ✅ `cell_updated`
- ✅ `cell_created`
- ✅ `cell_deleted`
- ✅ `cell_status`
- ✅ `cell_output`
- ✅ `cell_error`
- ❌ **`cell_stdout` - NO HANDLER**

The `cell_stdout` message is defined in `useNotebookWebSocket.ts:13`:
```typescript
| { type: 'cell_stdout'; cellId: string; data: string }
```

But `NotebookApp.tsx` never processes it. The stdout data arrives via WebSocket but is dropped.

#### Output Rendering
`NotebookCell.tsx:135-140` only renders the `outputs` array:
```tsx
{cell.outputs && cell.outputs.length > 0 && (
  <div className="bg-muted/30 p-4 space-y-2">
    {cell.outputs.map((output, idx) => (
      <OutputRenderer key={idx} output={output} ... />
    ))}
  </div>
)}
```

The `stdout` field exists on cells (`models.py:39`, `types.gen.ts:20`) but is **never rendered**.

### Issue 2: `fig.show()` Opens Browser Tab

#### How Figure Rendering Works
The executor captures the *last expression* of a cell and converts it via `to_mime_bundle()`:

```python
# executor.py:32-38
try:
    import plotly.graph_objects as go
    if isinstance(obj, go.Figure):
        spec = json.loads(obj.to_json())
        return Output(mime_type=MimeType.PLOTLY_JSON, data=spec)
except ImportError:
    pass
```

This works when the last line is `fig` (the figure object).

#### Why `fig.show()` Fails
`fig.show()` does two things:
1. Calls Plotly's renderer to display the figure (in non-Jupyter environments, this opens a browser)
2. Returns `None`

So when your cell ends with `fig.show()`:
- The executor captures `None` as the last expression value
- `None` produces no output
- Meanwhile, Plotly opens a browser tab

#### Correct Usage
```python
# This works - returns the figure object
fig

# This does NOT work - returns None and opens browser
fig.show()
```

## Code References
- `backend/executor.py:103,123,134` - stdout capture with `redirect_stdout`
- `backend/executor.py:137-142` - stdout returned in ExecutionResult
- `backend/scheduler.py:147,154-155` - stdout set on cell and broadcast
- `backend/websocket.py:49-54` - `broadcast_cell_stdout` implementation
- `frontend/src/useNotebookWebSocket.ts:13` - `cell_stdout` message type defined
- `frontend/src/components/NotebookApp.tsx:113-174` - message handler missing `cell_stdout` case
- `frontend/src/components/NotebookCell.tsx:135-140` - only renders `outputs` array
- `backend/executor.py:32-38` - Plotly figure detection in `to_mime_bundle`

## Architecture Insights

The notebook uses a **MIME bundle output model** similar to Jupyter:
- Outputs are structured data with `mime_type` and `data`
- The frontend `OutputRenderer` switches on mime_type to render appropriately
- This is the correct architecture - the bug is just missing integration

The **stdout** handling was designed to be separate from rich outputs, allowing streaming of print statements. However, the frontend integration was never completed.

## Recommended Fixes

### Fix 1: Frontend - Add `cell_stdout` Handler + Separate stdout UI

**a) Add handler in `NotebookApp.tsx`:**

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

**b) Add stdout rendering in `NotebookCell.tsx`:**

```tsx
{/* stdout Area - separate from rich outputs */}
{cell.stdout && (
  <div className="bg-muted/50 p-4 font-mono text-sm border-b border-border">
    <pre className="whitespace-pre-wrap">{cell.stdout}</pre>
  </div>
)}

{/* Rich Outputs Area */}
{cell.outputs && cell.outputs.length > 0 && (
  <div className="bg-muted/30 p-4 space-y-2">
    {cell.outputs.map((output, idx) => (
      <OutputRenderer key={idx} output={output} ... />
    ))}
  </div>
)}
```

**c) Clear stdout on cell run (in `cell_status` handler when status='running'):**

```typescript
case "cell_status":
  setCells((prev) =>
    prev.map((c) => {
      if (c.id !== msg.cellId) return c;
      if (msg.status === 'running') {
        return { ...c, status: msg.status, outputs: [], stdout: "", error: undefined };
      }
      return { ...c, status: msg.status };
    })
  );
  break;
```

### Fix 2: Backend - Stream stdout Line-by-Line

Modify `executor.py` to use a custom stdout wrapper that streams to WebSocket:

```python
class StreamingStdout:
    """Stdout wrapper that streams lines to WebSocket."""
    
    def __init__(self, broadcaster, notebook_id, cell_id):
        self._broadcaster = broadcaster
        self._notebook_id = notebook_id
        self._cell_id = cell_id
        self._buffer = ""
    
    def write(self, data):
        self._buffer += data
        # Flush complete lines
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            asyncio.create_task(
                self._broadcaster.broadcast_cell_stdout(
                    self._notebook_id, self._cell_id, line + '\n'
                )
            )
    
    def flush(self):
        if self._buffer:
            asyncio.create_task(
                self._broadcaster.broadcast_cell_stdout(
                    self._notebook_id, self._cell_id, self._buffer
                )
            )
            self._buffer = ""
```

### Fix 3: Backend - Override All Visualization Library Renderers

Set up custom renderers/overrides for all supported visualization libraries. See **Design Decisions § 3** above for the full `setup_visualization_capture()` implementation covering:

- **Matplotlib**: Override `plt.show()` to capture all open figures as PNG
- **Plotly**: Register custom renderer via `pio.renderers` to capture JSON
- **Altair**: Override `.display()` method to capture Vega-Lite spec
- **Pandas**: No override needed (uses last-expression capture via `to_mime_bundle`)

**Integration with executor:**

```python
# In execute_python_cell(), before running user code:
output_collector = []
setup_visualization_capture(output_collector)

# ... run user code ...

# After execution, output_collector contains .show() outputs
# Combine with last-expression output for final outputs list
```

**Key architectural point:** The `output_collector` accumulates outputs from `.show()` calls during execution, while `to_mime_bundle()` handles the last expression. Both contribute to the final `outputs` list, enabling cells that produce multiple visualizations.

## Design Decisions

Based on feedback, the following design decisions have been made:

### 1. Dual Output Areas: stdout AND Rich Outputs

Cells should render **both** stdout and rich outputs (graphs, tables, etc.) when applicable. This means:
- A cell with `print()` statements AND a Plotly figure should show both
- stdout appears in its own dedicated area
- Rich outputs (graphs, tables, images) appear in a separate area
- Both areas render if content exists for each

**UI Layout per cell:**
```
┌─────────────────────────────────┐
│ Code Editor                     │
├─────────────────────────────────┤
│ stdout (if any)                 │  ← Streaming text output
│ > line 1                        │
│ > line 2                        │
├─────────────────────────────────┤
│ Rich Outputs (if any)           │  ← Graphs, tables, images
│ [Plotly chart]                  │
└─────────────────────────────────┘
```

### 2. Streaming stdout Line-by-Line

stdout should stream line-by-line to the frontend rather than accumulating and sending at end. This provides:
- Real-time feedback during long-running cells
- Better UX for debugging/logging
- Matches Jupyter's behavior

**Implementation approach:**
- Backend streams stdout chunks via WebSocket as they're produced
- Frontend appends to a dedicated stdout buffer/display area
- May require modifying `redirect_stdout` to use a custom stream that flushes to WebSocket

### 3. Handle `.show()` via Library-Specific Overrides (NOT Regex)

**Do NOT** use regex/AST to detect `.show()` calls. Instead, leverage each library's built-in extension points to intercept display calls.

**Why this approach:**
- Clean, library-supported mechanisms
- Works for any way `.show()` is called (direct, via variable, in loops, etc.)
- No brittle string matching
- Same pattern Jupyter uses

#### Supported Libraries (from `executor.py:to_mime_bundle`)

| Library | Type | MIME Type | Has `.show()`? |
|---------|------|-----------|----------------|
| **Matplotlib** | `plt.Figure` | `image/png` | Yes - `plt.show()` |
| **Plotly** | `go.Figure` | `application/vnd.plotly.v1+json` | Yes - `fig.show()` |
| **Altair** | `alt.Chart` | `application/vnd.vegalite.v6+json` | Yes - `chart.display()` |
| **Pandas** | `pd.DataFrame` | `application/json` (table) | No |

#### Implementation: Unified Visualization Capture

```python
def setup_visualization_capture(output_collector: list):
    """
    Configure all supported visualization libraries to capture .show() calls
    instead of opening external windows/browsers.
    
    Call once per kernel initialization, passing the output collector list
    that will accumulate outputs during cell execution.
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # MATPLOTLIB - Override plt.show()
    # ═══════════════════════════════════════════════════════════════════
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend (no GUI)
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        
        _original_show = plt.show
        
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
        import json
        
        class NotebookPlotlyRenderer:
            """Custom Plotly renderer that captures to output collector."""
            
            def __call__(self, fig_dict, **kwargs):
                # fig_dict is already the JSON-serializable dict
                output_collector.append({
                    "mime_type": "application/vnd.plotly.v1+json",
                    "data": fig_dict
                })
        
        pio.renderers["notebook"] = NotebookPlotlyRenderer()
        pio.renderers.default = "notebook"
    except ImportError:
        pass
    
    # ═══════════════════════════════════════════════════════════════════
    # ALTAIR - Override display() method
    # ═══════════════════════════════════════════════════════════════════
    try:
        import altair as alt
        
        _original_display = alt.Chart.display
        
        def _capture_altair_display(self, *args, **kwargs):
            """Capture Altair chart when .display() is called."""
            output_collector.append({
                "mime_type": "application/vnd.vegalite.v6+json",
                "data": self.to_dict()
            })
        
        alt.Chart.display = _capture_altair_display
        
        # Also handle alt.LayerChart, alt.HConcatChart, alt.VConcatChart
        for chart_class in [alt.LayerChart, alt.HConcatChart, alt.VConcatChart, alt.FacetChart]:
            if hasattr(chart_class, 'display'):
                chart_class.display = _capture_altair_display
    except ImportError:
        pass
    
    # ═══════════════════════════════════════════════════════════════════
    # PANDAS - No .show() method, relies on last-expression capture
    # (No override needed - to_mime_bundle handles DataFrames)
    # ═══════════════════════════════════════════════════════════════════
```

#### How Output Collection Works

The `output_collector` list is:
1. Created fresh at start of cell execution
2. Passed to visualization setup (for `.show()` captures)
3. Also receives the last-expression result via `to_mime_bundle()`
4. All items broadcast as `cell_output` messages after execution

This means a cell can produce multiple outputs:
```python
# Cell code:
plt.figure()
plt.plot([1,2,3])
plt.show()           # Captured output #1 (matplotlib PNG)

fig = go.Figure()
fig.add_trace(...)
fig.show()           # Captured output #2 (plotly JSON)

df                   # Captured output #3 (pandas table) - last expression
```

All three outputs render in the cell's output area.

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Should stdout be streamed line-by-line or accumulated? | **Stream line-by-line** for real-time feedback |
| Should stdout be separate from rich outputs? | **Yes**, separate UI areas for each |
| Should we auto-detect `.show()` calls? | **No regex** - use each library's built-in extension points (Plotly renderers, matplotlib backend, Altair display override) |
| Which visualization libraries need overrides? | All supported: **Matplotlib** (`plt.show`), **Plotly** (`fig.show`), **Altair** (`.display`). Pandas has no show method. |

## Remaining Open Questions

1. What order should stdout vs rich outputs appear? (stdout first, then outputs? Or interleaved by time?)
2. Should there be a max height/scrollable area for stdout to prevent huge logs from overwhelming the UI?
3. Should we also capture `stderr` separately (e.g., warnings, logging)?


