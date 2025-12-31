---
date: 2025-12-31T10:36:09Z
researcher: AI Assistant
topic: "LLM Chat Prompt: Supported Visualization Libraries and Mime Bundling"
tags: [research, codebase, llm, chat, visualization, plotly, matplotlib, altair, mime-types]
status: complete
last_updated: 2025-12-31
last_updated_by: AI Assistant
---

# Research: LLM Chat Prompt: Supported Visualization Libraries and Mime Bundling

**Date**: 2025-12-31T10:36:09 GMT  
**Researcher**: AI Assistant

## Research Question

How should the LLM chat system prompt in `chat.py` be improved to accurately reflect the supported visualization libraries for mime bundling, and why will `fig.show()` break?

## Summary

The current system prompt in `chat.py:71-96` instructs the LLM to "use pandas for data manipulation and plotly for visualization" but lacks critical information about:

1. **All supported visualization libraries**: The executor supports matplotlib, plotly, and altair (not just plotly)
2. **Critical usage constraint**: Users must return the figure object as the last expression (e.g., `fig`) rather than calling `.show()` methods
3. **Why `.show()` breaks**: These methods attempt to open browser windows or GUI displays, which fail in the headless server environment

The mime bundling system (`executor.py:to_mime_bundle`) converts only specific library types to frontend-renderable formats. The LLM should be aware of these constraints to generate correct code.

## Detailed Findings

### Architecture: Mime Bundle System

The notebook uses a **Jupyter-style MIME bundle architecture** where Python objects are converted to structured outputs with specific MIME types for frontend rendering.

#### Supported Libraries and MIME Types

From `backend/executor.py:15-65` and `backend/models.py:17-24`:

| Library | Object Type | MIME Type | Conversion Method | Frontend Renderer |
|---------|-------------|-----------|-------------------|-------------------|
| **Matplotlib** | `plt.Figure` | `image/png` | `savefig()` → base64 PNG | `<img>` tag |
| **Plotly** | `go.Figure` | `application/vnd.plotly.v1+json` | `to_json()` → JSON spec | `react-plotly.js` |
| **Altair** | `alt.Chart` | `application/vnd.vegalite.v6+json` | `to_dict()` → Vega-Lite spec | `vega-embed` |
| **Pandas** | `pd.DataFrame` | `application/json` | Columns + rows as lists | Custom table renderer |

#### How It Works

```19:65:backend/executor.py
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
        # Use to_json() for frontend rendering with Plotly.js
        import json
        spec = json.loads(obj.to_json())
        return Output(mime_type=MimeType.PLOTLY_JSON, data=spec)
except ImportError:
    pass

# Altair chart
try:
    import altair as alt
    if isinstance(obj, alt.Chart):
        vega_json = alt.to_dict()
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
```

The `to_mime_bundle()` function is called on the **last expression value** of a cell (`executor.py:108, 128`).

### Why `fig.show()` Breaks

#### The Problem

When users write code ending with `.show()`:

```python
import plotly.graph_objects as go
fig = go.Figure(data=go.Scatter(x=[1,2,3], y=[4,5,6]))
fig.show()  # ❌ BREAKS
```

This causes two issues:

1. **Returns `None`**: `.show()` methods return `None`, not the figure object
2. **Attempts GUI display**: Plotly/matplotlib try to open browser windows or spawn GUI processes

From `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md:95-112`:

> `fig.show()` does two things:
> 1. Calls Plotly's renderer to display the figure (in non-Jupyter environments, this opens a browser)
> 2. Returns `None`
>
> So when your cell ends with `fig.show()`:
> - The executor captures `None` as the last expression value
> - `None` produces no output
> - Meanwhile, Plotly opens a browser tab

#### The Solution

Return the figure object as the last expression:

```python
import plotly.graph_objects as go
fig = go.Figure(data=go.Scatter(x=[1,2,3], y=[4,5,6]))
fig  # ✅ CORRECT - returns the figure object
```

The executor captures `fig`, detects it's a `go.Figure`, and converts it via `to_mime_bundle()`.

### Frontend Rendering Pipeline

From `frontend/src/components/OutputRenderer.tsx:43-131`:

The frontend switches on `mime_type` to render outputs:

- `image/png` → Base64 `<img>` tag
- `application/vnd.plotly.v1+json` → `<Plot>` component from `react-plotly.js`
- `application/vnd.vegalite.v6+json` → `vega-embed` renderer
- `application/json` (with `type: "table"`) → Custom HTML table
- `text/plain` → `<pre>` tag

### Current System Prompt (Lines 71-96)

```71:96:backend/chat.py
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
```

#### Issues with Current Prompt

1. **Incomplete library list**: Only mentions plotly, not matplotlib or altair
2. **Missing critical constraint**: Doesn't explain the `.show()` issue
3. **No guidance on correct usage**: Doesn't tell LLM to return figure objects

## Code References

### Backend Files
- `backend/chat.py:71-96` - System prompt needing improvement
- `backend/executor.py:15-65` - `to_mime_bundle()` conversion logic
- `backend/executor.py:80-161` - Python cell execution with last-expression capture
- `backend/models.py:17-24` - MIME type enum definitions
- `backend/demo_notebook.py:25-98` - Demo examples showing correct usage

### Frontend Files
- `frontend/src/components/OutputRenderer.tsx:43-131` - MIME type rendering switch
- `frontend/src/components/OutputRenderer.tsx:161-194` - Plotly renderer component
- `frontend/src/components/OutputRenderer.tsx:138-153` - Vega-Lite renderer component

## Architecture Insights

### Design Pattern: Last Expression Capture

The notebook follows **IPython/Jupyter semantics** where the last expression in a cell is automatically displayed:

```python
# These all work:
df                    # DataFrame displayed as table
fig                   # Plotly chart displayed
plt.gcf()            # Matplotlib figure displayed
chart                 # Altair chart displayed

# These do NOT work:
fig.show()           # Returns None, triggers browser
plt.show()           # Returns None, triggers GUI
```

This is implemented in `executor.py:116-130` where the AST is parsed to detect if the last statement is an expression, which is then evaluated separately and passed to `to_mime_bundle()`.

### Future Enhancement: `.show()` Capture

There's a documented plan to override `.show()` methods for all supported libraries to capture their output instead of failing. See:
- `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md:287-397`
- `thoughts/shared/plans/2025-12-30-stdout-and-visualization-rendering.md:296-469`

This would use library-specific extension points:
- **Matplotlib**: Override `plt.show()` after `matplotlib.use('Agg')`
- **Plotly**: Register custom renderer via `plotly.io.renderers`
- **Altair**: Override `Chart.display()` method

However, this is **not yet implemented**, so the system prompt must instruct the LLM to avoid `.show()` calls.

## Improved System Prompt

### Recommended Changes

Replace lines 84-85 in `backend/chat.py` with:

```python
Important:
- Always use get_notebook_state first to understand the current state
- When creating data analysis code, use pandas for data manipulation
- For visualizations, use matplotlib (static charts), plotly (interactive charts), or altair (declarative charts)
- CRITICAL: Return the figure/chart object as the last line (e.g., `fig` not `fig.show()`)
- Do NOT call .show() methods - they will fail in this server environment
- For matplotlib, use `plt.gcf()` as the last expression to display the current figure
- For SQL cells, use {{variable}} syntax to reference Python variables
- Be concise and helpful
- If a cell fails, read the error and suggest fixes
```

### Full Updated System Prompt

```python
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
- When creating data analysis code, use pandas for data manipulation
- For visualizations, use matplotlib (static charts), plotly (interactive charts), or altair (declarative charts)
- CRITICAL: Return the figure/chart object as the last line (e.g., `fig` not `fig.show()`)
- Do NOT call .show() methods - they will fail in this server environment
- For matplotlib, use `plt.gcf()` as the last expression to display the current figure
- For SQL cells, use {{variable}} syntax to reference Python variables
- Be concise and helpful
- If a cell fails, read the error and suggest fixes

Supported output types:
- Matplotlib figures (rendered as PNG images)
- Plotly figures (rendered as interactive charts)
- Altair charts (rendered as Vega-Lite visualizations)
- Pandas DataFrames (rendered as tables)
- Plain text and print() statements

Cell statuses:
- idle: Not executed yet
- running: Currently executing
- success: Executed successfully
- error: Execution failed
- blocked: Waiting for dependencies
"""
```

### Key Improvements

1. **Explicit library list**: Mentions all three supported viz libraries with use cases
2. **Critical constraint highlighted**: Uses "CRITICAL:" prefix for the `.show()` warning
3. **Positive guidance**: Tells LLM what to do (return object) not just what not to do
4. **Matplotlib-specific note**: `plt.gcf()` pattern for current figure
5. **Output types section**: New section documenting what can be rendered

## Historical Context (from thoughts/)

### Related Research Documents

- `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md` - Comprehensive analysis of why `.show()` fails and architecture of the mime bundle system
- `thoughts/shared/research/2025-12-27-plotly-json-rendering-implementation.md` - Implementation notes for Plotly JSON mime type
- `thoughts/shared/research/2025-12-28-llm-assistant-integration-architecture.md` - LLM chat integration architecture including output previews

### Related Plans

- `thoughts/shared/plans/2025-12-30-stdout-and-visualization-rendering.md` - Future plan to support `.show()` capture via library overrides
- `thoughts/shared/plans/2025-12-27-plotly-json-rendering.md` - Original Plotly JSON rendering implementation plan
- `thoughts/shared/plans/2025-12-29-llm-assistant-integration.md` - LLM chat feature implementation plan

## Testing Strategy

After updating the system prompt, verify:

1. **LLM generates correct matplotlib code**:
   - Ask: "Create a line chart with matplotlib"
   - Verify: Code ends with `plt.gcf()` not `plt.show()`

2. **LLM generates correct plotly code**:
   - Ask: "Create an interactive bar chart"
   - Verify: Code ends with `fig` not `fig.show()`

3. **LLM generates correct altair code**:
   - Ask: "Create a scatter plot with altair"
   - Verify: Code ends with `chart` object return

4. **LLM chooses appropriate library**:
   - Ask: "Create an interactive visualization" → Should suggest plotly
   - Ask: "Create a simple static chart" → Could suggest matplotlib
   - Ask: "Create a declarative visualization" → Could suggest altair

## Open Questions

1. Should we add examples of correct usage directly in the system prompt?
2. Should we include performance guidance (e.g., matplotlib for simple, plotly for interactive)?
3. Should we warn about large DataFrame rendering limits (currently 1000 rows for SQL results)?
4. When `.show()` capture is implemented, how should the prompt be updated?

## Related Research

- MIME bundle architecture documented in `thoughts/shared/research/2025-12-27-plotly-html-not-rendering.md`
- Output rendering pipeline analyzed in `thoughts/shared/research/2025-12-30-design-inspo-frontend-analysis.md`
- LLM tool execution flow in `thoughts/shared/research/2025-12-29-agentic-loop-implementation-analysis.md`

---

## Implementation Checklist

- [ ] Update `backend/chat.py:84-95` with improved prompt text
- [ ] Test with various visualization requests to verify LLM generates correct code
- [ ] Monitor LLM actions log for any `.show()` calls being generated
- [ ] Update this research doc if prompt needs further refinement
- [ ] Consider adding examples to prompt if LLM still generates `.show()` calls

