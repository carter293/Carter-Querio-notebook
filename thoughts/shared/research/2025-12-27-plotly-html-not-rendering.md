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

#### Option 1: Extract and Execute Scripts (Jupyter-like approach)
**How it works**:
- Parse HTML to extract `<script>` tags (both inline and external)
- Create script elements programmatically: `document.createElement('script')`
- Set `src` for external scripts or `textContent` for inline scripts
- Append to DOM using `appendChild()` to trigger execution
- Handle script loading order and dependencies

**Pros**:
- Works with existing HTML output from Plotly
- No backend changes needed
- Similar to how Jupyter handles script execution

**Cons**:
- Requires careful parsing and script extraction
- Security considerations (XSS risk)
- Need to handle script loading order

#### Option 2: Use Plotly.js Directly (marimo-like approach) ⭐ **RECOMMENDED**
**How it works**:
- Change backend to send Plotly JSON spec instead of HTML
- Use `fig.to_json()` instead of `fig.to_html()`
- Add Plotly.js as frontend dependency (`npm install plotly.js`)
- Create React component that uses Plotly.js directly
- Similar to how our Vega-Lite renderer works

**Pros**:
- ✅ Matches marimo's proven approach
- ✅ No script execution needed (library handles it)
- ✅ Better React integration
- ✅ More secure (no arbitrary script execution)
- ✅ Consistent with Vega-Lite pattern already in codebase

**Cons**:
- Requires backend change (use `to_json()` instead of `to_html()`)
- Requires frontend dependency (`plotly.js`)
- Slightly more code changes

**Implementation**:
```python
# Backend change (executor.py)
html = obj.to_json()  # Instead of to_html()
return Output(mime_type=MimeType.PLOTLY_JSON, data=html)
```

```tsx
// Frontend component (similar to VegaLiteRenderer)
import Plotly from 'plotly.js';
import { useEffect, useRef } from 'react';

function PlotlyRenderer({ spec }: { spec: any }) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (containerRef.current) {
      Plotly.newPlot(containerRef.current, spec.data, spec.layout);
    }
  }, [spec]);
  
  return <div ref={containerRef} style={{ width: '100%' }} />;
}
```

#### Option 3: Use iframe with srcdoc
**How it works**:
- Create an iframe element
- Set `srcdoc` attribute to the HTML
- Scripts execute in isolated iframe context

**Pros**:
- Scripts execute automatically in iframe
- Isolated execution context (more secure)

**Cons**:
- Styling/layout challenges (iframe sizing, scrolling)
- Communication between iframe and parent can be complex
- May not match notebook UI styling

**Recommendation**: **Option 2 (Plotly.js Directly)** - This matches marimo's approach and is consistent with our existing Vega-Lite implementation pattern.

## How marimo and Jupyter Handle Plotly Rendering

### marimo's Approach

**Key Insight**: marimo does NOT use raw HTML injection for Plotly charts. Instead, it uses a React component wrapper:

- **`mo.ui.plotly(fig)`**: A specialized React component that wraps Plotly figures
- **No HTML injection**: The component handles rendering internally, avoiding the script execution problem
- **Reactive integration**: Supports reactive selections for scatter plots, treemaps, and sunburst charts
- **Architecture**: Uses Plotly.js directly in the frontend, not HTML output from Python

**Why This Works**:
- marimo's `mo.ui.plotly` component uses Plotly.js library directly in React
- No need to execute scripts from HTML because the component manages script loading
- Similar to how our Vega-Lite renderer works (uses `vega-embed` library directly)

**Relevance to Our Codebase**:
- Our implementation plan (`thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md`) mentions following marimo's MIME bundle architecture
- However, marimo uses React components for interactive charts, not raw HTML output
- We're using HTML output from Plotly's `to_html()` method, which creates a different challenge

### Jupyter Notebook's Approach

**Key Insight**: Jupyter uses native DOM manipulation, not React's `dangerouslySetInnerHTML`:

- **Output Area**: Jupyter's output area is not a React component - it uses native DOM APIs
- **Script Execution**: When HTML is inserted into Jupyter's output area, scripts execute because:
  - Jupyter uses `appendChild()` and native DOM methods, not `innerHTML`
  - The output area is designed to execute arbitrary JavaScript for rich outputs
  - Scripts are added programmatically or executed via Jupyter's output rendering pipeline

**How Jupyter Works**:
1. Plotly's `notebook` renderer generates HTML with embedded scripts
2. Jupyter's output area receives the HTML
3. Scripts are extracted and executed via Jupyter's output rendering system
4. The output area is designed to handle script execution safely

**Why This Doesn't Apply to Us**:
- We're using React, which has security restrictions on script execution
- `dangerouslySetInnerHTML` doesn't execute scripts (by design)
- We need a React-compatible solution

### Comparison Table

| Approach | marimo | Jupyter | Our Current Implementation |
|----------|--------|---------|----------------------------|
| **Framework** | React | Native DOM | React |
| **Plotly Rendering** | `mo.ui.plotly()` React component | HTML with script execution | HTML via `dangerouslySetInnerHTML` |
| **Script Execution** | Handled by component (Plotly.js library) | Native DOM execution | ❌ Scripts don't execute |
| **Architecture** | React components for interactive charts | HTML injection with script support | MIME bundle → HTML injection |
| **Solution Pattern** | Use Plotly.js directly in frontend | Native DOM manipulation | Need script extraction/execution |

### Key Takeaways

1. **marimo avoids the problem**: Uses React components instead of raw HTML, so no script execution needed
2. **Jupyter uses native DOM**: Not constrained by React's security model
3. **Our approach needs adaptation**: We're using HTML output but need to execute scripts in React
4. **Best solution**: Either extract/execute scripts OR use Plotly.js directly (like marimo)

## Historical Context (from thoughts/)

The implementation plan (`thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md`) documents the Plotly integration but does not address script execution:

- Line 703: Manual verification checklist includes "Run `import plotly.express as px; px.bar(...)` - Interactive chart displays"
- Line 541: Shows `dangerouslySetInnerHTML` usage for HTML outputs
- Line 1187: Demo notebook includes Plotly cell
- Line 5: Mentions following marimo's MIME bundle architecture, but marimo uses React components for Plotly, not HTML

**Note**: The implementation plan was completed but the script execution issue was not identified during implementation. The plan references marimo's architecture but doesn't account for the difference in how marimo handles interactive charts (React components vs. HTML output).

## Related Research

- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Output state management issues
- `thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md` - Original Plotly implementation plan

## Open Questions

1. **Solution Choice**: Should we use Plotly.js directly (marimo approach) or script extraction (Jupyter approach)?
   - **Answer**: Plotly.js directly is recommended - matches marimo, more secure, consistent with Vega-Lite pattern
2. **Backend Changes**: If using Plotly.js directly, should we add a new MIME type (`application/vnd.plotly+json`) or reuse existing?
   - **Suggestion**: Add `PLOTLY_JSON = "application/vnd.plotly+json"` to MimeType enum
3. **Error Handling**: How should Plotly rendering errors be displayed to users?
   - **Suggestion**: Similar to Vega-Lite error handling - console.error + user-friendly message
4. **Backward Compatibility**: Should we support both HTML and JSON outputs, or migrate fully to JSON?
   - **Suggestion**: Migrate fully to JSON (cleaner, more consistent with marimo pattern)

## Recommended Next Steps

### Recommended Approach: Use Plotly.js Directly (marimo pattern)

1. **Backend Changes** (`backend/executor.py`):
   - Change Plotly output from HTML to JSON: `obj.to_json()` instead of `obj.to_html()`
   - Add new MIME type: `MimeType.PLOTLY_JSON = "application/vnd.plotly+json"`
   - Return JSON spec instead of HTML string

2. **Frontend Changes** (`frontend/src/components/OutputRenderer.tsx`):
   - Add `plotly.js` dependency: `npm install plotly.js`
   - Create `PlotlyRenderer` component (similar to `VegaLiteRenderer`)
   - Handle `application/vnd.plotly+json` MIME type
   - Use `Plotly.newPlot()` to render charts

3. **Testing**:
   - Verify Plotly charts render correctly
   - Test with demo notebook Plotly cell
   - Verify interactive features (zoom, pan, hover) work

4. **Documentation**:
   - Update implementation plan with Plotly.js approach
   - Document the pattern for future chart libraries

### Alternative Approach: Script Extraction (if keeping HTML output)

If HTML output must be preserved:
1. Implement script extraction utility in `OutputRenderer.tsx`
2. Parse HTML to extract `<script>` tags
3. Create and execute script elements programmatically
4. Handle script loading order and dependencies
5. Add security review for XSS prevention

