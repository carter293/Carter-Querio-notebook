---
date: 2025-12-31T11:00:00Z
author: AI Assistant
topic: "Implementation: Improve LLM Chat System Prompt for Visualization Libraries"
tags: [implementation, llm, chat, visualization, system-prompt]
status: complete
related_research: thoughts/shared/research/2025-12-31-llm-chat-prompt-visualization-libraries.md
---

# Implementation: Improve LLM Chat System Prompt for Visualization Libraries

**Date**: 2025-12-31T11:00:00 GMT  
**Implementer**: AI Assistant  
**Related Research**: `thoughts/shared/research/2025-12-31-llm-chat-prompt-visualization-libraries.md`

## Objective

Update the LLM chat system prompt in `backend/chat.py` to accurately document all supported visualization libraries (matplotlib, plotly, altair) and explain the critical constraint that users must return figure objects as the last expression rather than calling `.show()` methods.

## Problem Statement

The original system prompt (lines 71-96 in `chat.py`) had several issues:

1. **Incomplete library documentation**: Only mentioned plotly, omitting matplotlib and altair
2. **Missing critical constraint**: Didn't explain why `.show()` methods fail
3. **No positive guidance**: Didn't tell the LLM what to do (return figure objects)
4. **No output types documentation**: Didn't list what can be rendered

This led to potential issues where the LLM might generate code ending with `.show()` calls, which return `None` and attempt to open browser windows/GUI displays that fail in the headless server environment.

## Implementation

### Changes Made

#### File: `backend/chat.py`

**Lines 71-96**: Updated system prompt with comprehensive visualization guidance

**Before**:
```python
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
```

**After**:
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
```

### Key Improvements

1. **Explicit library list**: Documents all three supported visualization libraries with use cases:
   - Matplotlib for static charts
   - Plotly for interactive charts
   - Altair for declarative charts

2. **Critical constraint highlighted**: Uses "CRITICAL:" prefix to emphasize the `.show()` warning

3. **Positive guidance**: Tells the LLM what to do (return figure object) not just what not to do

4. **Matplotlib-specific pattern**: Documents the `plt.gcf()` pattern for returning the current figure

5. **New "Supported output types" section**: Lists all renderable output types with descriptions

## Architecture Context

### MIME Bundle System

The notebook uses a Jupyter-style MIME bundle architecture where Python objects are converted to structured outputs:

| Library | Object Type | MIME Type | Frontend Renderer |
|---------|-------------|-----------|-------------------|
| Matplotlib | `plt.Figure` | `image/png` | `<img>` tag |
| Plotly | `go.Figure` | `application/vnd.plotly.v1+json` | `react-plotly.js` |
| Altair | `alt.Chart` | `application/vnd.vegalite.v6+json` | `vega-embed` |
| Pandas | `pd.DataFrame` | `application/json` | Custom table renderer |

### Why `.show()` Breaks

When code ends with `.show()`:

1. **Returns `None`**: `.show()` methods return `None`, not the figure object
2. **Attempts GUI display**: Libraries try to open browser windows or spawn GUI processes
3. **No output captured**: The executor receives `None` and produces no output

### Correct Pattern

The executor captures the last expression value and passes it to `to_mime_bundle()` (in `executor.py:15-65`), which detects the object type and converts it to the appropriate MIME bundle.

**Correct usage**:
```python
# Matplotlib
plt.plot([1, 2, 3], [4, 5, 6])
plt.gcf()  # Returns the current figure

# Plotly
fig = go.Figure(data=go.Scatter(x=[1,2,3], y=[4,5,6]))
fig  # Returns the figure object

# Altair
chart = alt.Chart(data).mark_bar().encode(x='x', y='y')
chart  # Returns the chart object
```

## Testing

### Test Results

Ran the LLM tools test suite to verify the chat system still works correctly:

```bash
cd backend && python -m pytest tests/test_llm_tools.py -v
```

**Result**: ✅ All 5 tests passed

Tests verified:
- `test_get_notebook_state` - Notebook state retrieval
- `test_create_cell` - Cell creation
- `test_update_cell` - Cell updates
- `test_delete_cell` - Cell deletion
- `test_create_output_preview` - Output preview generation (including plotly and image outputs)

### Manual Verification

The updated prompt should be tested with actual LLM interactions:

1. **Matplotlib test**: Ask "Create a line chart with matplotlib"
   - Verify: Code ends with `plt.gcf()` not `plt.show()`

2. **Plotly test**: Ask "Create an interactive bar chart"
   - Verify: Code ends with `fig` not `fig.show()`

3. **Altair test**: Ask "Create a scatter plot with altair"
   - Verify: Code ends with `chart` object return

4. **Library selection test**: Ask "Create an interactive visualization"
   - Verify: LLM suggests plotly (appropriate for interactive charts)

## Code References

### Files Modified
- `backend/chat.py:71-96` - System prompt updated

### Related Files (Not Modified)
- `backend/executor.py:15-65` - MIME bundle conversion logic
- `backend/models.py:17-24` - MIME type definitions
- `frontend/src/components/OutputRenderer.tsx:43-131` - Frontend rendering

## Future Enhancements

From the research document, there's a documented plan to override `.show()` methods for all supported libraries to capture their output instead of failing. This would involve:

- **Matplotlib**: Override `plt.show()` after `matplotlib.use('Agg')`
- **Plotly**: Register custom renderer via `plotly.io.renderers`
- **Altair**: Override `Chart.display()` method

When this is implemented, the system prompt should be updated to remove the `.show()` warning.

See:
- `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md:287-397`
- `thoughts/shared/plans/2025-12-30-stdout-and-visualization-rendering.md:296-469`

## Success Criteria

- [x] System prompt updated with all three visualization libraries
- [x] Critical `.show()` constraint documented with "CRITICAL:" prefix
- [x] Positive guidance provided (return figure objects)
- [x] Matplotlib-specific `plt.gcf()` pattern documented
- [x] New "Supported output types" section added
- [x] All existing tests pass
- [x] No linter errors introduced
- [x] Code compiles successfully

## Deployment Notes

This change only affects the system prompt string in `chat.py`. No database migrations, frontend changes, or infrastructure updates are required.

The change will take effect immediately when the backend is restarted, as the system prompt is constructed dynamically on each chat request.

## Monitoring

After deployment, monitor the LLM actions log (`backend/logs/audit/llm_actions.log`) for:
- Any `.show()` calls being generated by the LLM
- Error patterns related to visualization rendering
- User feedback about visualization code quality

If the LLM still generates `.show()` calls, consider:
1. Adding concrete examples directly in the system prompt
2. Increasing the emphasis on the constraint (e.g., repeating it)
3. Adding a post-processing step to detect and warn about `.show()` calls

## Related Documentation

### Research Documents
- `thoughts/shared/research/2025-12-31-llm-chat-prompt-visualization-libraries.md` - Original research
- `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md` - Why `.show()` fails
- `thoughts/shared/research/2025-12-27-plotly-json-rendering-implementation.md` - Plotly implementation

### Related Plans
- `thoughts/shared/plans/2025-12-30-stdout-and-visualization-rendering.md` - Future `.show()` capture plan
- `thoughts/shared/plans/2025-12-27-plotly-json-rendering.md` - Plotly rendering implementation
- `thoughts/shared/plans/2025-12-29-llm-assistant-integration.md` - LLM chat feature

---

## Implementation Summary

**Status**: ✅ Complete  
**Date Completed**: 2025-12-31  
**Files Changed**: 1 (`backend/chat.py`)  
**Lines Changed**: ~25 lines (system prompt string)  
**Tests Passed**: 5/5  
**Breaking Changes**: None  
**Deployment Risk**: Low (string-only change)

The LLM chat system now provides comprehensive guidance on visualization libraries and the critical constraint about returning figure objects instead of calling `.show()` methods. This should significantly improve the quality of visualization code generated by the LLM assistant.

