---
date: 2025-12-27T19:59:03+00:00
researcher: AI Assistant
topic: "Plotly HTML Chart Not Rendering - Script Execution Issue"
tags: [research, codebase, plotly, html, script-execution, frontend, output-renderer]
status: complete
last_updated: 2025-12-27
last_updated_by: AI Assistant
---

# Research: Plotly HTML Chart Not Rendering - Script Execution Issue

**Date**: 2025-12-27T19:59:03+00:00
**Researcher**: AI Assistant

## Research Question

Why does the Plotly chart cell in the demo notebook not display visible output, even though the websocket message contains valid HTML output with Plotly code?

## Summary

The Plotly HTML output is being generated correctly on the backend and transmitted via WebSocket, but **scripts embedded in the HTML are not executing** when inserted via React's `dangerouslySetInnerHTML`. This is due to a browser security feature where scripts inserted via `innerHTML` (or React's `dangerouslySetInnerHTML`) are parsed but not executed. The Plotly chart requires JavaScript execution to render, so the chart div appears empty.

**Root Cause**: Scripts in HTML inserted via `dangerouslySetInnerHTML` do not execute automatically. Scripts must be extracted and executed programmatically using the DOM API.

## Detailed Findings

### Backend: Plotly HTML Generation (`backend/executor.py`)

The backend correctly generates Plotly HTML output:

```python:31:36:backend/executor.py
# Plotly figure
try:
    import plotly.graph_objects as go
    if isinstance(obj, go.Figure):
        html = obj.to_html(include_plotlyjs='cdn', div_id=None)
        return Output(mime_type=MimeType.HTML, data=html)
```

**Key Points**:
- Uses `plotly.graph_objects.Figure.to_html()` with `include_plotlyjs='cdn'` to generate HTML
- The HTML includes:
  - Plotly CDN script tags (`<script src="https://cdn.plot.ly/plotly-3.3.0.min.js">`)
  - A div container with a unique ID
  - JavaScript code that calls `Plotly.newPlot()` to render the chart
- The HTML is valid and complete (verified from websocket message)

### Frontend: HTML Rendering (`frontend/src/components/OutputRenderer.tsx`)

The frontend renders HTML outputs using `dangerouslySetInnerHTML`:

```tsx:36:45:frontend/src/components/OutputRenderer.tsx
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
```

**The Problem**: When HTML containing `<script>` tags is inserted via `dangerouslySetInnerHTML`:
1. The browser parses the HTML and inserts elements into the DOM
2. **Script tags are inserted but NOT executed** (browser security feature)
3. The Plotly div exists but remains empty because `Plotly.newPlot()` never runs

### WebSocket Message Flow

The websocket message structure is correct:

```json
{
  "type": "cell_output",
  "cellId": "3b2bd02b-d14e-4163-94ed-f50944ac59e0",
  "output": {
    "mime_type": "text/html",
    "data": "<html>...<script>Plotly.newPlot(...)</script>...</html>"
  }
}
```

The message is received and stored correctly in `Notebook.tsx`:

```tsx:85:93:frontend/src/components/Notebook.tsx
case 'cell_output':
  return {
    ...prev,
    cells: prev.cells.map(cell => {
      if (cell.id !== msg.cellId) return cell;
      const outputs = cell.outputs || [];
      return { ...cell, outputs: [...outputs, msg.output] };
    })
  };
```

### Browser Behavior: Script Execution with innerHTML

**Critical Finding**: Browsers have a security restriction where:
- Scripts present in the original HTML when the page loads **execute**
- Scripts added via `innerHTML` or `dangerouslySetInnerHTML` **do NOT execute**
- Scripts must be added programmatically using `document.createElement('script')` and `appendChild()` to execute

This is documented browser behavior, not a React-specific issue.

### Architecture Context

The application uses a **MIME bundle architecture** for output transport:
- Backend converts Python objects (matplotlib figures, Plotly figures, DataFrames) to MIME bundles
- MIME bundles are transmitted via WebSocket as `cell_output` messages
- Frontend renders outputs based on `mime_type`:
  - `image/png` → `<img>` tag
  - `text/html` → `dangerouslySetInnerHTML`
  - `application/vnd.vegalite.v5+json` → Vega-Lite renderer (uses DOM API)
  - `application/json` → Table or JSON display

**Notable**: Vega-Lite charts work correctly because they use the `vega-embed` library which programmatically creates and executes scripts via the DOM API, not via `dangerouslySetInnerHTML`.

## Code References

- `backend/executor.py:31-36` - Plotly HTML generation
- `frontend/src/components/OutputRenderer.tsx:36-45` - HTML output rendering
- `frontend/src/components/Notebook.tsx:85-93` - WebSocket message handling for outputs
- `frontend/src/components/Cell.tsx:200-209` - Output display in cells
- `backend/websocket.py:70-82` - Output broadcasting

## Architecture Insights

### Current Pattern: Direct HTML Injection
- **Works for**: Static HTML, CSS-styled content, HTML tables
- **Fails for**: HTML requiring script execution (Plotly, D3, etc.)

### Alternative Pattern: Programmatic Script Execution
- **Used by**: Vega-Lite renderer (`OutputRenderer.tsx:119-134`)
- **Approach**: Extract scripts from HTML, create script elements via DOM API, append to DOM
- **Security**: Requires careful handling to avoid XSS vulnerabilities

### Recommended Solution Approaches

1. **Extract and Execute Scripts** (Recommended):
   - Parse HTML to extract `<script>` tags
   - Create script elements programmatically: `document.createElement('script')`
   - Set `src` or `textContent` and append to DOM
   - Execute inline scripts and load external scripts

2. **Use iframe with srcdoc**:
   - Create an iframe element
   - Set `srcdoc` attribute to the HTML
   - Scripts execute in isolated iframe context
   - More secure but may have styling/layout challenges

3. **Use Plotly.js Directly**:
   - Instead of HTML, send Plotly JSON spec
   - Use Plotly.js library in frontend to render
   - Similar to Vega-Lite approach
   - Requires adding Plotly.js as frontend dependency

## Historical Context (from thoughts/)

The implementation plan (`thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md`) documents the Plotly integration but does not address script execution:

- Line 703: Manual verification checklist includes "Run `import plotly.express as px; px.bar(...)` - Interactive chart displays"
- Line 541: Shows `dangerouslySetInnerHTML` usage for HTML outputs
- Line 1187: Demo notebook includes Plotly cell

**Note**: The implementation plan was completed but the script execution issue was not identified during implementation.

## Related Research

- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Output state management issues
- `thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md` - Original Plotly implementation plan

## Open Questions

1. **Security Considerations**: What XSS protections should be in place when executing scripts from notebook outputs?
2. **Performance**: Should scripts be executed synchronously or asynchronously?
3. **Error Handling**: How should script execution errors be displayed to users?
4. **Alternative Libraries**: Should we consider using Plotly.js directly instead of HTML output?

## Recommended Next Steps

1. **Immediate Fix**: Implement script extraction and execution in `OutputRenderer.tsx` for `text/html` outputs
2. **Testing**: Verify Plotly charts render correctly after fix
3. **Security Review**: Ensure script execution doesn't introduce XSS vulnerabilities
4. **Documentation**: Update implementation plan with script execution requirements

