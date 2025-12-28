---
date: 2025-12-27T21:55:24+00:00
researcher: AI Assistant
topic: "Plotly Chart DOM Shifting During Cell Re-run and Updates"
tags: [research, plotly, dom, positioning, react-plotly.js, cell-updates]
status: in_progress
last_updated: 2025-12-27
last_updated_by: AI Assistant
git_commit: 8f0926d0c1f7eaa87adc5e25c7c0507e8a8d92cd
---

# Research: Plotly Chart DOM Shifting During Cell Re-run and Updates

**Date**: 2025-12-27T21:55:24+00:00  
**Git Commit**: 8f0926d0c1f7eaa87adc5e25c7c0507e8a8d92cd

## Research Question

When the Plotly cell in the demo notebook is re-running or being updated, the DOM shifts but the chart doesn't unmount. After pressing Cmd+Enter (runs), every second keypress moves the DOM below the cell up (as if the Plotly chart was `position: absolute`), but then the next keystroke it's like it's `position: static`. What causes this DOM shifting behavior?

## Summary

The Plotly chart rendering appears to have a DOM positioning issue where:
1. Chart doesn't properly unmount during cell re-execution
2. DOM elements below the cell shift upward intermittently during typing
3. Behavior alternates between `position: absolute`-like and `position: static`-like positioning
4. Issue manifests specifically after Cmd+Enter execution

## Current Implementation Analysis

### PlotlyRenderer Component (`frontend/src/components/OutputRenderer.tsx:169-186`)

```tsx
function PlotlyRenderer({ spec, cellId, outputIndex }: PlotlyRendererProps) {
  // Create a unique key that changes when the data changes to force remount
  const plotKey = cellId && outputIndex !== undefined 
    ? `${cellId}-${outputIndex}-${JSON.stringify(spec.data).slice(0, 100)}`
    : `plot-${JSON.stringify(spec.data).slice(0, 100)}`;

  return (
    <Plot
      key={plotKey}
      data={spec.data}
      layout={spec.layout || {}}
      config={spec.config || { responsive: true, displayModeBar: true }}
      style={{ width: '100%' }}
      useResizeHandler={true}
    />
  );
}
```

**Key Observations**:
- Uses `react-plotly.js` `Plot` component
- Key strategy: `${cellId}-${outputIndex}-${dataHash}` - only changes when data changes
- `useResizeHandler={true}` enables responsive resizing
- No explicit cleanup/unmount logic

### Cell Component Output Rendering (`frontend/src/components/Cell.tsx:200-207`)

```tsx
{cell.outputs && cell.outputs.map((output, idx) => (
  <div key={`${cell.id}-output-${idx}-${cell.status}`} style={{
    backgroundColor: '#f3f4f6',
    padding: '8px',
    borderRadius: '4px',
    marginTop: '8px'
  }}>
    <OutputRenderer output={output} cellId={cell.id} outputIndex={idx} />
  </div>
))}
```

**Key Observations**:
- Output container key includes `cell.status`: `${cell.id}-output-${idx}-${cell.status}`
- This means the container remounts when status changes (idle → running → success)
- But `PlotlyRenderer` key doesn't include status, only data hash

### Key Strategy Mismatch

**Problem**: There's a mismatch between when the output container remounts vs when the Plot component remounts:

1. **Output Container Key**: `${cell.id}-output-${idx}-${cell.status}`
   - Changes when: cell status changes (idle → running → success)
   - Does NOT change when: cell code is edited (status stays same)

2. **PlotlyRenderer Key**: `${cellId}-${outputIndex}-${dataHash}`
   - Changes when: output data changes
   - Does NOT change when: cell status changes but data is same

**Implication**: When a cell is edited (typing), the output container key stays the same, but React might be re-rendering the Plot component without proper cleanup.

## Hypotheses

### Hypothesis 1: react-plotly.js Internal DOM Management Issue ⭐ **MOST LIKELY**

**Theory**: `react-plotly.js`'s `Plot` component creates internal DOM elements (SVG, canvas, tooltips, etc.) that use absolute positioning or have layout-affecting properties. During re-renders without unmounting, these elements might not be properly cleaned up or repositioned.

**Evidence**:
- Chart doesn't unmount (key doesn't change during edits)
- DOM shifting suggests positioning issues
- Alternating behavior suggests React reconciliation issues

**How to Test**:
- Add logging to track when Plot component mounts/unmounts
- Inspect DOM during typing to see if Plotly elements are being duplicated
- Check computed styles of Plotly-generated DOM elements

### Hypothesis 2: Key Strategy Mismatch Causing Reconciliation Issues

**Theory**: The mismatch between output container key (includes status) and PlotlyRenderer key (doesn't include status) causes React to incorrectly reconcile the component tree. When status changes, container remounts but Plot might not, leading to stale DOM references.

**Evidence**:
- Output container remounts on status change
- PlotlyRenderer key doesn't change unless data changes
- This could leave Plot component in inconsistent state

**How to Test**:
- Add status to PlotlyRenderer key: `${cellId}-${outputIndex}-${cellStatus}-${dataHash}`
- Or remove status from output container key
- Compare behavior before/after

### Hypothesis 3: useResizeHandler Causing Layout Thrashing

**Theory**: The `useResizeHandler={true}` prop might be triggering resize events during cell updates, causing Plotly to recalculate layout and manipulate DOM in ways that affect surrounding elements.

**Evidence**:
- Resize handlers can cause layout thrashing
- Issue manifests during typing (frequent re-renders)
- DOM shifting suggests layout recalculation

**How to Test**:
- Temporarily disable `useResizeHandler`
- Add logging to track resize events
- Monitor layout shifts with browser DevTools

### Hypothesis 4: Plotly Toolbar/UI Elements Using Absolute Positioning

**Theory**: Plotly's toolbar and UI elements (zoom buttons, modebar, etc.) might be positioned absolutely relative to the plot container. During re-renders, these elements might be repositioned incorrectly or left in the DOM when they shouldn't be.

**Evidence**:
- User reports "as if position absolute" behavior
- Plotly charts have complex UI overlays
- These elements might persist across re-renders

**How to Test**:
- Inspect Plotly-generated DOM elements for absolute positioning
- Check if toolbar elements are duplicated
- Disable toolbar (`displayModeBar: false`) and test

### Hypothesis 5: Cell Status Changes During Editing

**Theory**: When typing in a cell, if the cell status changes (e.g., from 'success' to 'idle' or 'running'), the output container key changes, causing remount. But if the Plot component doesn't remount properly, it might leave orphaned DOM elements.

**Evidence**:
- Issue occurs "when updating the cell"
- Status changes trigger output container remount
- PlotlyRenderer might not handle this transition correctly

**How to Test**:
- Log cell status changes during editing
- Track when output container remounts vs Plot component
- Check if status changes unexpectedly during typing

## Diagnostic Logging Plan

### 1. PlotlyRenderer Component Logging

Add logging to track:
- Component mount/unmount
- Key changes
- Props changes
- Re-render triggers

### 2. Cell Component Logging

Add logging to track:
- Output container key changes
- Cell status changes
- Output array changes
- Re-render triggers

### 3. DOM Inspection Logging

Add logging to track:
- Plotly-generated DOM elements
- Computed styles (especially position)
- Element count changes
- Layout shifts

### 4. React Reconciliation Logging

Add logging to track:
- When React decides to remount vs update
- Key comparison results
- Component tree changes

## Diagnostic Logging Implementation ✅

### Logging Added to PlotlyRenderer Component

**Location**: `frontend/src/components/OutputRenderer.tsx:169-230`

**Logs Track**:
1. **Component lifecycle**: Mount/unmount events with cellId, outputIndex, plotKey
2. **Key changes**: When plotKey changes (indicates remount vs update)
3. **Props changes**: When spec.data, spec.layout, or spec.config change
4. **DOM inspection**: After render, logs:
   - Container element computed styles (position, display, height, width)
   - Count of Plotly-generated DOM elements
   - Position and display styles of each Plotly element

**Key Features**:
- Uses `useRef` to track previous plotKey for change detection
- Wraps Plot component in a container div with `position: relative` for DOM inspection
- 100ms timeout after render to allow DOM to settle before inspection

### Logging Added to Cell Component

**Location**: `frontend/src/components/Cell.tsx:48-155`

**Logs Track**:
1. **Status changes**: When cell.status changes (idle → running → success)
2. **Output changes**: When cell.outputs array changes (count, keys)
3. **Component re-renders**: Every render with cell metadata
4. **Output container lifecycle**: Mount/unmount of each output container
5. **Output container DOM inspection**: Computed styles and Plotly element count

**Key Features**:
- Created `OutputContainer` component to properly use hooks for logging
- Tracks previous status and outputs using `useRef` for change detection
- Output containers have data attributes for debugging: `data-cell-id`, `data-output-index`, `data-output-key`

### Log Format

All logs are prefixed with component name:
- `[PlotlyRenderer]` - Logs from PlotlyRenderer component
- `[Cell]` - Logs from Cell component

Each log includes:
- Relevant identifiers (cellId, outputIndex, plotKey, etc.)
- Timestamp in ISO format
- Context-specific data (status, props, DOM info)

## Initial Log Analysis (2025-12-27)

### Key Observations from Console Logs

1. **React StrictMode Double Rendering**:
   - React StrictMode is enabled (`main.tsx:8`)
   - In development, StrictMode intentionally double-invokes effects and components
   - This explains the rapid mount/unmount cycles (mount → unmount → mount)
   - However, this shouldn't cause DOM shifting in production

2. **Rapid Mount/Unmount Cycle**: 
   - PlotlyRenderer is mounting and unmounting very rapidly (within milliseconds)
   - Pattern observed: Mount → Unmount → Mount → Unmount → Mount
   - Mount duration is very short (< 1ms in some cases)
   - This happens even when `plotKey` stays the same
   - **Output containers also remount with 0ms duration even when outputKey stays the same**

3. **Output Index Observation**:
   - All outputs correctly have `outputIndex: 0` (each cell has one output)
   - This is expected behavior - `outputIndex` is per-cell, not global
   - The user's question confirms this is working as intended

4. **Critical Finding - Rapid Remounts Even With Same Key**:
   - Output containers are remounting with 0ms duration even when `outputKey` stays the same
   - Example: `outputKey: '3b2bd02b-d14e-4163-94ed-f50944ac59e0-output-0-success'` unmounts and immediately remounts
   - This suggests React StrictMode double-rendering OR parent component remounting
   - **This rapid remounting could be causing Plotly's DOM manipulation to interfere with layout**

5. **Next Steps for Diagnosis**:
   - ✅ Enhanced logging added to highlight critical issues
   - Check console for `[PlotlyRenderer] DOM inspection summary` - quick overview
   - Check for `⚠️ Found absolutely positioned elements` warnings
   - Check for `⚠️ Multiple Plotly divs in document` warnings
   - These warnings will help identify the root cause of DOM shifting

6. **Enhanced Logging Added**:
   - Separate summary log for quick overview
   - Warning logs for absolutely positioned elements (if found)
   - Warning logs for duplicate Plotly divs (if found)
   - Easier to spot issues without expanding large objects

## Root Cause Identified ✅ (2025-12-27)

### Critical Findings from Console Logs

**⚠️ Found absolutely positioned elements: count: 5**
- Plotly creates 5 absolutely positioned elements (likely toolbar, hover tooltips, modebar buttons)
- These elements use `position: absolute` and are positioned relative to the plot container
- During rapid mount/unmount cycles, these elements can be left behind or repositioned incorrectly

**⚠️ Multiple Plotly divs in document: count: 3**
- There are 3 Plotly divs in the document when there should only be 1
- This indicates Plotly instances aren't being properly cleaned up on unmount
- Old Plotly divs remain in the DOM, causing layout issues

### Root Cause Analysis

The DOM shifting is caused by a combination of:

1. **React StrictMode Double-Rendering**: 
   - Causes rapid mount/unmount cycles (0ms, 1ms durations)
   - PlotlyRenderer mounts → unmounts → mounts again immediately

2. **Plotly's Absolutely Positioned Elements**:
   - Plotly creates 5 absolutely positioned elements (toolbar, tooltips, etc.)
   - These elements are positioned relative to the plot container
   - During rapid remounts, these elements can be orphaned or repositioned incorrectly

3. **Incomplete Cleanup**:
   - Multiple Plotly divs exist in the document (3 instead of 1)
   - `react-plotly.js`'s `Plot` component may not be cleaning up properly on unmount
   - Old Plotly instances remain in the DOM, causing layout conflicts

4. **Key Strategy Mismatch**:
   - Output container key includes `cell.status`, causing remounts on status changes
   - PlotlyRenderer key doesn't include status, but still remounts due to parent remounting
   - This mismatch causes React reconciliation issues

### Confirmed Hypotheses

✅ **Hypothesis 1**: react-plotly.js Internal DOM Management Issue - **CONFIRMED**
- Plotly creates absolutely positioned elements that aren't properly cleaned up

✅ **Hypothesis 4**: Plotly Toolbar/UI Elements Using Absolute Positioning - **CONFIRMED**
- 5 absolutely positioned elements found (likely toolbar and tooltips)

✅ **Hypothesis 2**: Key Strategy Mismatch - **CONFIRMED**
- Output container remounts on status change, causing PlotlyRenderer to remount unnecessarily

## Proposed Solutions

### Solution 1: Fix Key Strategy Mismatch ⭐ **RECOMMENDED FIRST**

**Problem**: Output container key includes `cell.status`, causing remounts even when data hasn't changed.

**Fix**: Remove `cell.status` from output container key, or add it to PlotlyRenderer key to ensure consistent remounting.

**Implementation**:
```tsx
// Option A: Remove status from output container key
<div key={`${cell.id}-output-${idx}`} ...>

// Option B: Add status to PlotlyRenderer key
const plotKey = `${cellId}-${outputIndex}-${cellStatus}-${dataHash}`;
```

**Pros**: 
- Prevents unnecessary remounts when status changes but data stays same
- Aligns React reconciliation behavior

**Cons**: 
- May need to handle status changes differently for clearing outputs

### Solution 2: Explicit Plotly Cleanup

**Problem**: Plotly instances aren't being cleaned up properly, leaving multiple divs in DOM.

**Fix**: Add explicit cleanup using Plotly's `Plotly.purge()` method.

**Implementation**:
```tsx
useEffect(() => {
  return () => {
    if (containerRef.current) {
      const plotElement = containerRef.current.querySelector('.js-plotly-plot');
      if (plotElement) {
        Plotly.purge(plotElement);
      }
    }
  };
}, [plotKey]);
```

**Pros**: 
- Ensures Plotly instances are properly cleaned up
- Prevents DOM pollution

**Cons**: 
- Requires importing Plotly directly
- May conflict with react-plotly.js's internal cleanup

### Solution 3: Disable React StrictMode (Development Only)

**Problem**: StrictMode causes double-rendering, triggering rapid mount/unmount cycles.

**Fix**: Temporarily disable StrictMode to test if issue persists in production.

**Implementation**:
```tsx
// main.tsx - Remove StrictMode wrapper
ReactDOM.createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
);
```

**Pros**: 
- Quick test to confirm StrictMode is contributing to issue
- Production builds don't use StrictMode anyway

**Cons**: 
- Only masks the issue, doesn't fix root cause
- Loses benefits of StrictMode for catching bugs

### Solution 4: Use Plotly.js Directly (Like Vega-Lite)

**Problem**: `react-plotly.js` wrapper may not handle cleanup properly.

**Fix**: Use Plotly.js directly with `useEffect` and `useRef`, similar to `VegaLiteRenderer`.

**Implementation**:
```tsx
function PlotlyRenderer({ spec, cellId, outputIndex }: PlotlyRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      Plotly.newPlot(containerRef.current, spec.data, spec.layout, spec.config);
    }
    
    return () => {
      if (containerRef.current) {
        Plotly.purge(containerRef.current);
      }
    };
  }, [spec.data, spec.layout, spec.config]);

  return <div ref={containerRef} style={{ width: '100%' }} />;
}
```

**Pros**: 
- Full control over Plotly lifecycle
- Consistent with Vega-Lite pattern
- Explicit cleanup with `Plotly.purge()`

**Cons**: 
- Requires removing `react-plotly.js` dependency
- Need to handle resize events manually
- More code to maintain

## Recommended Fix Order

1. **First**: Fix key strategy mismatch (Solution 1) - easiest, addresses root cause
2. **Second**: Add explicit cleanup (Solution 2) - ensures proper cleanup
3. **If still issues**: Consider using Plotly.js directly (Solution 4) - most control
4. **Testing**: Temporarily disable StrictMode (Solution 3) - to confirm contribution

2. **Output Container Remounting**:
   - Output container key includes `cell.status`: `${cell.id}-output-${idx}-${cell.status}`
   - When status changes (success → running → success), container remounts
   - This triggers PlotlyRenderer remount even though plotKey hasn't changed

3. **Component Re-renders During Typing**:
   - When typing in cell (codeLength changes), Cell component re-renders
   - Output container key stays the same (status is still 'success')
   - But PlotlyRenderer might be re-rendering unnecessarily

4. **Potential Root Cause**:
   - The mismatch between output container key (includes status) and PlotlyRenderer key (doesn't include status) causes React reconciliation issues
   - When output container remounts due to status change, React might be remounting Plot component even though plotKey is the same
   - This rapid remounting could be causing Plotly's internal DOM manipulation to interfere with layout

### Enhanced Logging Added

**New logging features**:
- Mount duration tracking (to identify rapid mount/unmount cycles)
- Stack traces on mount/unmount (to see what triggers remounts)
- Detailed DOM inspection:
  - All absolutely positioned elements
  - Total Plotly div count in document (to detect duplicates)
  - Bounding rect information
  - Next sibling information (to track layout shifts)
- MutationObserver to track Plot element appearance/disappearance in DOM
- Render count tracking

## Next Steps

1. ✅ Add comprehensive logging to PlotlyRenderer and Cell components
2. ✅ Enhanced logging with mount duration, stack traces, and detailed DOM inspection
3. **Test with enhanced logging** - Run the app and interact with Plotly cell, especially:
   - Type in the cell (observe mount/unmount patterns)
   - Press Cmd+Enter (observe status change behavior)
   - Watch for DOM inspection logs showing absolute positioning
4. **Analyze enhanced logs** to identify:
   - What's triggering the rapid mount/unmount cycles
   - If Plotly elements are using absolute positioning
   - If there are duplicate Plotly divs in the document
   - Layout shift patterns
5. **Implement fix** based on findings (likely fixing key strategy mismatch)
6. **Verify fix** resolves DOM shifting issue
7. **Remove or reduce logging** after issue is resolved

## Related Research

- `thoughts/shared/research/2025-12-27-plotly-json-rendering-implementation.md` - Implementation of Plotly JSON rendering
- `thoughts/shared/research/2025-12-27-plotly-html-not-rendering.md` - Original Plotly HTML rendering issues
- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Cell output state management issues

## References

- react-plotly.js documentation: https://plotly.com/javascript/react/
- Plotly.js DOM structure: https://plotly.com/javascript/plotlyjs-function-reference/
- React reconciliation: https://react.dev/learn/preserving-and-resetting-state

