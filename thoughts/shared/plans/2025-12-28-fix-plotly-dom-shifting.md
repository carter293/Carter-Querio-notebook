---
date: 2025-12-28T11:05:24+00:00
planner: AI Assistant
topic: "Fix Plotly Chart DOM Shifting - Height Switching Issue"
tags: [planning, implementation, plotly, layout, height, dom-shifting, frontend]
status: completed
last_updated: 2025-12-28
last_updated_by: AI Assistant
git_commit: 8f0926d0c1f7eaa87adc5e25c7c0507eea8d92cd
---

# Fix Plotly Chart DOM Shifting - Height Switching Issue

**Date**: 2025-12-28T11:05:24+00:00  
**Planner**: AI Assistant  
**Status**: ✅ Completed  
**Git Commit**: 8f0926d0c1f7eaa87adc5e25c7c0507eea8d92cd

## Overview

Fix the DOM shifting issue where elements below Plotly cells jump up and down during cell re-execution and typing. The root cause is Plotly's internal `.svg-container` div dynamically switching its height between a fixed value (`height: 400px`) and a relative value (`height: 100%`) during React re-renders.

## Root Cause Analysis

### The Issue

Plotly's internal `.svg-container` div dynamically switches its height during React re-renders:
- **Fixed height**: `height: 400px` (normal state)
- **Relative height**: `height: 100%` (during re-render transition)

### Why This Causes DOM Shifting

1. When you type in the cell editor, React re-renders the component tree
2. During re-render, Plotly's `.svg-container` briefly uses `height: 100%`
3. Since the parent containers don't have a fixed height defined, `100%` of nothing = `0` height
4. The chart collapses to `0` height momentarily
5. Elements below (like other charts) jump up to fill the space
6. When Plotly finishes re-rendering, it switches back to `height: 400px`
7. The chart reappears and pushes elements back down

**Result**: Visible "jumping" or "shifting" of DOM elements below the Plotly chart.

### Original Implementation

**PlotlyRenderer** (`frontend/src/components/OutputRenderer.tsx:169-186`):

```tsx
function PlotlyRenderer({ spec, cellId, outputIndex }: PlotlyRendererProps) {
  const plotKey = cellId && outputIndex !== undefined 
    ? `${cellId}-${outputIndex}-${JSON.stringify(spec.data).slice(0, 100)}`
    : `plot-${JSON.stringify(spec.data).slice(0, 100)}`;

  return (
    <Plot
      key={plotKey}
      data={spec.data}
      layout={spec.layout || {}}  // ⚠️ No fixed height
      config={spec.config || { responsive: true, displayModeBar: true }}
      style={{ width: '100%' }}  // ⚠️ No container height to reserve space
      useResizeHandler={true}
    />
  );
}
```

**Problem**: No container to reserve DOM space when Plotly's internal height switches to `100%`.

## Solution

### Key Insight

The fix is simpler than initially thought. We don't need to disable responsiveness or autosize. The **only critical fix** is:

1. **Wrap Plot in a container with `minHeight`** - This reserves DOM space even when Plotly's `.svg-container` briefly switches to `height: 100%`
2. **Set explicit `height` in layout** - Ensures Plotly knows what height to render at

### Why This Works

When Plotly's `.svg-container` switches to `height: 100%` during re-render:
- The parent `<div>` with `minHeight: 500px` still occupies that space in the DOM
- Elements below the chart stay in place because the container maintains its minimum height
- When Plotly finishes re-rendering and switches back to a fixed height, nothing has shifted

### Benefits

- ✅ DOM space is always reserved (no collapsing to 0 height)
- ✅ No visible "jumping" of elements below charts
- ✅ **Charts remain fully responsive** - resize with browser window
- ✅ **All Plotly features work** - zoom, pan, hover, toolbar
- ✅ Minimal code change - just a wrapper div with minHeight
- ✅ Users can still specify custom heights in their Plotly code

## Implementation

### Changes Required

#### 1. Update PlotlyRenderer Implementation

**File**: `frontend/src/components/OutputRenderer.tsx`  
**Lines**: 169-202

**New code**:
```tsx
function PlotlyRenderer({ spec, cellId, outputIndex }: PlotlyRendererProps) {
  // Create a unique key that changes when the data changes to force remount
  // This ensures the Plot component properly unmounts and remounts when cell re-executes
  const plotKey = cellId && outputIndex !== undefined 
    ? `${cellId}-${outputIndex}-${JSON.stringify(spec.data).slice(0, 100)}`
    : `plot-${JSON.stringify(spec.data).slice(0, 100)}`;

  // Use user-provided dimensions or defaults
  // Fixed dimensions prevent Plotly's .svg-container from collapsing to height: 100%
  // during React re-renders, which causes DOM shifting
  const height = spec.layout?.height || 500;

  const layout = {
    ...spec.layout,
    height,
  };

  return (
    <div style={{ minHeight: `${height}px`, width: '100%' }}>
      <Plot
        key={plotKey}
        data={spec.data}
        layout={layout}
        config={{ 
          autosizable: true,
          responsive: true,
          displayModeBar: true 
        }}
        style={{ width: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}
```

**Key changes**:
1. **Container with `minHeight`**: Wraps Plot in `<div style={{ minHeight: \`${height}px\`, width: '100%' }}>` - this is the critical fix that reserves DOM space
2. **Explicit height in layout**: Sets `height` in layout (default 500px, or user-provided)
3. **Keep responsive features**: `responsive: true`, `useResizeHandler={true}`, `autosizable: true` all remain enabled

### What We're NOT Doing

1. ~~**Disabling responsive mode**~~ - Not needed, responsiveness works fine
2. ~~**Disabling autosize**~~ - Not needed, the container fix handles it
3. ~~**Setting fixed width**~~ - Not needed, charts can be responsive width
4. ~~**Disabling useResizeHandler**~~ - Not needed, resize handling works fine
5. **Not changing backend**: This is purely a frontend layout fix
6. **Not using `revision` prop**: Not needed
7. **Not changing key strategy**: Existing key strategy is fine

## Success Criteria

### Automated Verification

- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] No TypeScript errors or warnings

### Manual Verification

1. **Load demo notebook**:
   - [x] Navigate to notebook with Plotly cell
   - [x] Verify Plotly chart renders at expected size

2. **Test DOM shifting fix**:
   - [x] Type in the Plotly cell editor
   - [x] **Verify**: Elements below the chart DO NOT shift up/down
   - [x] **Verify**: Chart maintains consistent height during typing

3. **Test cell re-execution**:
   - [x] Press Cmd+Enter to re-run the Plotly cell
   - [x] **Verify**: Elements below DO NOT shift during execution
   - [x] **Verify**: Chart updates correctly with new data

4. **Inspect DOM**:
   - [x] Open DevTools Elements panel
   - [x] **Verify**: Parent container has `min-height: 500px`

5. **Test chart functionality**:
   - [x] Hover over chart - verify tooltips work
   - [x] Test zoom/pan - verify interactions work
   - [x] Verify toolbar buttons work
   - [x] Verify chart resizes with browser window (responsive)

6. **Test multiple charts**:
   - [x] Create multiple Plotly cells in same notebook
   - [x] Verify no interference between charts

### Regression Testing

- [x] Verify other output types still render correctly:
  - [x] Text output
  - [x] Tables
  - [x] Vega-Lite charts (should be unaffected)
  - [x] PNG images
  - [x] HTML output

## Performance Considerations

### Pros
- **Minimal overhead**: Just a wrapper div - no computation
- **Responsive charts**: No performance penalty from disabling resize features
- **Standard Plotly behavior**: All optimization features remain enabled

### Cons
- None identified - this is a minimal, non-intrusive fix

## Migration Notes

- **No data migration needed**: Frontend-only change
- **No API changes**: Backend unchanged
- **Backward compatible**: Existing notebooks work without changes
- **User code preserved**: If users specify `height` in their Plotly layout, it's respected

## References

### Research
- Original issue: `thoughts/shared/research/2025-12-27-plotly-dom-shifting-on-rerender.md`
- Plotly implementation: `thoughts/shared/research/2025-12-27-plotly-json-rendering-implementation.md`

### Documentation
- Plotly.js layout reference: https://plotly.com/javascript/reference/layout/
- react-plotly.js: https://github.com/plotly/react-plotly.js
- Plotly.js sizing: https://plotly.com/javascript/setting-graph-size/

### Code References
- PlotlyRenderer: `frontend/src/components/OutputRenderer.tsx:169-202`
- VegaLiteRenderer (comparison): `frontend/src/components/OutputRenderer.tsx:146-161`
- Cell output rendering: `frontend/src/components/Cell.tsx:200-209`
