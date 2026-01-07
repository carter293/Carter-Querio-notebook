# Rich Output MIME Conversion Implementation Plan

**Date:** 2026-01-07
**Research Document:** [2026-01-07-rich-output-mime-conversion.md](../research/2026-01-07-rich-output-mime-conversion.md)

---

## Overview

This plan implements rich output support for visualization libraries (matplotlib, plotly, altair) and enhanced pandas DataFrame rendering in the reactive notebook system. The implementation requires changes to only the **Executor layer** (`backend/app/core/executor.py`), as all downstream layers are already generic transport/presentation layers.

---

## Current State Analysis

### What Exists Now
- ✅ **Frontend**: Fully implemented rendering for 6 MIME types ([OutputRenderer.tsx:44-131](../../../frontend/src/components/OutputRenderer.tsx))
  - `image/png`, `text/html`, `application/vnd.vegalite.v6+json`, `application/vnd.plotly.v1+json`, `application/json`, `text/plain`
- ✅ **Kernel/Orchestration/WebSocket**: Generic transport layers that preserve any MIME type
- ❌ **Executor**: Only supports `text/plain` output ([executor.py:86-93](../../../backend/app/core/executor.py))
- ❌ **Dependencies**: Missing optional visualization libraries in pyproject.toml

### Key Constraints Discovered
1. **Architecture**: 3-layer separation (Interface → Orchestration → Kernel) must be maintained
2. **Executor location**: MIME conversion must happen in executor because it has access to Python runtime
3. **Type safety**: All changes must maintain Pydantic model validation
4. **Optional libraries**: Visualization libraries should be optional dependencies (not everyone needs plots)
5. **Error handling**: Must gracefully handle missing libraries with ImportError

---

## System Context Analysis

The executor is part of the **Kernel layer** in the reactive notebook architecture. This layer is responsible for:
- Executing Python code in an isolated namespace
- Converting Python objects to serializable output formats
- Capturing stdout/stderr during execution

**Root Cause vs Symptom:** This is implementing a **missing core feature**, not fixing a symptom. The current implementation has a TODO comment acknowledging this gap ([executor.py:87](../../../backend/app/core/executor.py)).

**Architectural Pattern:** The implementation follows the **IPython display protocol** pattern used by Jupyter, where objects can provide rich MIME bundle representations of themselves. Our implementation will inspect object types and convert them to appropriate MIME formats.

---

## Desired End State

### Verification Criteria
After this implementation is complete:

1. **Matplotlib figures** render as PNG images in the frontend
2. **Plotly charts** render as interactive visualizations
3. **Altair charts** render using Vega-Lite
4. **Pandas DataFrames** render as formatted tables (not just text)
5. **Reactive cascades** work with visualizations (changing upstream cell updates downstream plots)
6. **Missing libraries** fail gracefully with helpful error messages

---

## What We're NOT Doing

To prevent scope creep, explicitly **out of scope**:

- ❌ Large output truncation (e.g., limiting 10,000-row DataFrames to first 1,000)
- ❌ Output caching or memoization
- ❌ Support for additional libraries (seaborn, bokeh, etc.) - can be added later
- ❌ Custom `_repr_html_()` or `_repr_mimebundle_()` protocol support
- ❌ Output metadata handling beyond basic MIME conversion
- ❌ Performance optimizations for large images

---

## Implementation Approach

### High-Level Strategy

**Single-file enhancement pattern:**
1. Replace stub `_to_output()` method with duck-typed MIME detection
2. Use try/except ImportError pattern for optional libraries
3. Check most-specific types first (matplotlib, plotly, altair, pandas), fallback to text/plain
4. Add optional dependencies to pyproject.toml
5. Write comprehensive unit tests with `pytest.importorskip()`

**Why this works:**
- Executor already has the correct architecture hook (`_to_output()` method)
- All downstream layers are generic - they work with any MIME type
- Duck typing with ImportError handling makes libraries truly optional
- Pattern matches IPython/Jupyter's display system

---

## Phase 1: Update Executor MIME Conversion

### Overview
Replace the stub `_to_output()` method with full MIME bundle conversion logic.

### Changes Required

#### 1. Core Executor Logic
**File**: [backend/app/core/executor.py](../../../backend/app/core/executor.py)

**Replace lines 86-93** with enhanced MIME conversion:

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
            plt.close(obj)  # Free memory

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

**Rationale:**
- **Try/except pattern**: Allows graceful degradation when libraries aren't installed
- **Duck typing**: Uses `isinstance()` checks after confirming imports
- **Order matters**: Most specific types checked first, generic fallback last
- **Memory management**: `plt.close(obj)` prevents figure accumulation
- **Type consistency**: Returns same `Output` model used by SQLExecutor

### Success Criteria

#### Automated Verification:
- [x] Code type-checks: `cd backend && uv run mypy app/core/executor.py --strict`
- [x] Unit tests pass: `cd backend && uv run pytest tests/test_executor.py -v`
- [x] No linting errors: `cd backend && uv run ruff check app/core/executor.py`

#### Manual Verification:
- [x] Read the modified file and verify the logic is correct
- [x] Verify matplotlib figures get `plt.close()` called to free memory
- [x] Verify pandas DataFrames use the same table format as SQLExecutor

---

## Phase 2: Add Optional Dependencies

### Overview
Add visualization libraries as optional dependencies so users can install them as needed.

### Changes Required

#### 1. Add Optional Dependencies Section
**File**: [backend/pyproject.toml](../../../backend/pyproject.toml)

**Add after line 14** (after main dependencies):

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

**Rationale:**
- **Separation**: `viz` for plotting libraries, `data` for data analysis
- **Optional**: Users can install only what they need
- **Version pins**: Use stable versions with good compatibility
- **Precedent**: Matches Jupyter's tiered installation (minimal → scipy → datascience)

### Success Criteria

#### Automated Verification:
- [x] Dependencies sync correctly: `cd backend && uv sync --extra viz --extra data`
- [x] Basic install still works: `cd backend && uv sync` (without extras)
- [x] pyproject.toml validates: `cd backend && uv run python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"`

#### Manual Verification:
- [x] Verify version numbers are reasonable (not too old, not too cutting-edge)
- [x] Confirm package names are correct (no typos)

---

## Phase 3: Unit Tests

### Overview
Add comprehensive unit tests for each MIME type conversion, using `pytest.importorskip()` to handle optional dependencies.

### Changes Required

#### 1. Rich Output Unit Tests
**File**: [backend/tests/test_executor.py](../../../backend/tests/test_executor.py)

**Add after existing tests** (after line 96):

```python
# Rich Output Tests

def test_matplotlib_figure_output():
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


def test_plotly_figure_output():
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


def test_pandas_dataframe_output():
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


def test_altair_chart_output():
    """Test altair chart converts to Vega-Lite spec."""
    pytest.importorskip('altair')
    pytest.importorskip('pandas')  # altair requires pandas

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
    # Vega-Lite specs have either 'mark' or '$schema' at top level
    assert 'mark' in result.outputs[0].data or '$schema' in result.outputs[0].data


def test_fallback_to_text_plain():
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


def test_missing_visualization_library():
    """Test that missing library errors are captured properly."""
    executor = PythonExecutor()

    # Try to import a library that doesn't exist
    code = """
import nonexistent_plotting_library
"""

    result = executor.execute(code)

    assert result.status == 'error'
    assert 'ModuleNotFoundError' in result.error or 'ImportError' in result.error
```

**Rationale:**
- **pytest.importorskip()**: Automatically skips tests if library not installed
- **Real code execution**: Tests the full path through AST parsing and exec()
- **Assertion coverage**: Checks status, output count, MIME type, and data structure
- **Fallback testing**: Verifies text/plain fallback for unknown types
- **Error handling**: Tests that missing libraries fail with helpful errors

### Success Criteria

#### Automated Verification:
- [x] All tests pass with viz libraries: `cd backend && uv sync --extra viz --extra data && uv run pytest tests/test_executor.py::test_matplotlib_figure_output -v`
- [x] All tests pass with viz libraries: `cd backend && uv run pytest tests/test_executor.py::test_plotly_figure_output -v`
- [x] All tests pass with data libraries: `cd backend && uv run pytest tests/test_executor.py::test_pandas_dataframe_output -v`
- [x] All tests pass with data libraries: `cd backend && uv run pytest tests/test_executor.py::test_altair_chart_output -v`
- [x] Fallback test passes: `cd backend && uv run pytest tests/test_executor.py::test_fallback_to_text_plain -v`
- [x] All executor tests pass: `cd backend && uv run pytest tests/test_executor.py -v`

#### Manual Verification:
- [x] Verify tests are skipped (not failed) when libraries aren't installed
- [x] Run a test without the library and confirm it's skipped: `uv sync && uv run pytest tests/test_executor.py::test_matplotlib_figure_output -v`

---

## Phase 4: Integration Tests

### Overview
Add end-to-end integration tests that verify rich outputs flow through the full stack (executor → kernel → orchestration → WebSocket).

### Changes Required

#### 1. Rich Output Integration Tests
**File**: `backend/tests/test_rich_output_integration.py` *(create new file)*

```python
"""Integration tests for rich outputs through kernel and orchestration."""
import pytest
from app.core.graph import DependencyGraph
from app.models import Cell


@pytest.mark.asyncio
async def test_matplotlib_reactive_cascade():
    """Test matplotlib output updates through reactive cascade."""
    pytest.importorskip('matplotlib')
    pytest.importorskip('numpy')

    graph = DependencyGraph()

    # Cell 1: Define variable
    cell1 = Cell(id='c1', type='python', code='n = 5')
    graph.add_cell(cell1)

    # Cell 2: Create plot using variable
    cell2 = Cell(id='c2', type='python', code="""
import matplotlib.pyplot as plt
import numpy as np

x = np.arange(n)
y = np.random.rand(n)

fig, ax = plt.subplots()
ax.plot(x, y)
ax.set_title(f'Data points: {n}')
fig
""")
    graph.add_cell(cell2)

    # Execute both cells
    await graph.execute_cell(cell1.id)
    await graph.execute_cell(cell2.id)

    # Verify cell2 has matplotlib output
    result2 = graph.get_cell_result(cell2.id)
    assert result2.status == 'success'
    assert len(result2.outputs) == 1
    assert result2.outputs[0].mime_type == 'image/png'

    # Update cell1 variable
    cell1.code = 'n = 10'

    # Execute cell1 - should trigger reactive cascade
    cascade = await graph.execute_cell(cell1.id)

    # Verify cell2 was re-executed with new value
    assert cell2.id in cascade
    result2_updated = graph.get_cell_result(cell2.id)
    assert result2_updated.status == 'success'
    assert result2_updated.outputs[0].mime_type == 'image/png'
    # New plot should be different (different data)
    assert result2_updated.outputs[0].data != result2.outputs[0].data


@pytest.mark.asyncio
async def test_pandas_dataframe_reactive_cascade():
    """Test pandas DataFrame output updates through reactive cascade."""
    pytest.importorskip('pandas')

    graph = DependencyGraph()

    # Cell 1: Define data size
    cell1 = Cell(id='c1', type='python', code='rows = 3')
    graph.add_cell(cell1)

    # Cell 2: Create DataFrame
    cell2 = Cell(id='c2', type='python', code="""
import pandas as pd

df = pd.DataFrame({
    'id': list(range(rows)),
    'value': [i * 10 for i in range(rows)]
})
df
""")
    graph.add_cell(cell2)

    # Execute both cells
    await graph.execute_cell(cell1.id)
    await graph.execute_cell(cell2.id)

    # Verify DataFrame output
    result2 = graph.get_cell_result(cell2.id)
    assert result2.status == 'success'
    assert len(result2.outputs) == 1
    assert result2.outputs[0].mime_type == 'application/json'
    assert result2.outputs[0].data['type'] == 'table'
    assert len(result2.outputs[0].data['rows']) == 3

    # Update row count
    cell1.code = 'rows = 5'

    # Execute and verify cascade
    cascade = await graph.execute_cell(cell1.id)
    assert cell2.id in cascade

    result2_updated = graph.get_cell_result(cell2.id)
    assert len(result2_updated.outputs[0].data['rows']) == 5


@pytest.mark.asyncio
async def test_plotly_chart_output():
    """Test plotly chart renders correctly."""
    pytest.importorskip('plotly')

    graph = DependencyGraph()

    cell = Cell(id='c1', type='python', code="""
import plotly.graph_objects as go

fig = go.Figure(data=[
    go.Bar(x=['A', 'B', 'C'], y=[3, 7, 2])
])
fig.update_layout(title='Bar Chart')
fig
""")
    graph.add_cell(cell)

    await graph.execute_cell(cell.id)

    result = graph.get_cell_result(cell.id)
    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'application/vnd.plotly.v1+json'
    assert 'data' in result.outputs[0].data
    assert 'layout' in result.outputs[0].data
```

**Rationale:**
- **Full stack testing**: Tests executor changes through the dependency graph
- **Reactive cascade verification**: Ensures visualizations update when upstream cells change
- **Real-world scenarios**: Tests actual user workflows (variable → data → plot)

### Success Criteria

#### Automated Verification:
- [x] Integration tests pass: `cd backend && uv run pytest tests/test_rich_output_integration.py -v`
- [x] All backend tests pass: `cd backend && uv run pytest tests/ -v`

#### Manual Verification:
- [x] Verify tests correctly simulate the full reactive execution path
- [x] Confirm cascade tests properly verify that downstream cells re-execute

---

## Phase 5: Manual End-to-End Testing

### Overview
Start the full application and manually test each visualization type in the frontend to ensure the complete pipeline works.

### Testing Steps

#### 1. Install Dependencies and Start Backend
```bash
cd backend
uv sync --extra viz --extra data
uv run uvicorn app.main:app --reload
```

#### 2. Start Frontend
```bash
cd frontend
npm run dev
```

#### 3. Test Matplotlib
Create a new Python cell:
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

**Expected:** PNG image of sine wave appears in cell output

#### 4. Test Plotly
Create a new Python cell:
```python
import plotly.graph_objects as go

fig = go.Figure(data=[
    go.Bar(x=['A', 'B', 'C'], y=[3, 7, 2])
])
fig.update_layout(title='Bar Chart')
fig
```

**Expected:** Interactive bar chart appears (can hover, zoom, pan)

#### 5. Test Altair
Create a new Python cell:
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

**Expected:** Vega-Lite line chart appears

#### 6. Test Pandas DataFrame
Create a new Python cell:
```python
import pandas as pd

df = pd.DataFrame({
    'Name': ['Alice', 'Bob', 'Charlie'],
    'Age': [25, 30, 35],
    'Score': [92.5, 87.3, 95.1]
})
df
```

**Expected:** Formatted HTML table (not plain text representation)

#### 7. Test Reactive Cascade with Visualization
Create three cells:

**Cell 1:**
```python
n = 10
```

**Cell 2:**
```python
import pandas as pd
import numpy as np

df = pd.DataFrame({
    'x': np.arange(n),
    'y': np.random.rand(n)
})
df
```

**Cell 3:**
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(df['x'], df['y'])
ax.set_title(f'Random Data (n={n})')
fig
```

**Test:** Change Cell 1 to `n = 20` and re-run

**Expected:** Cells 2 and 3 automatically re-execute, showing 20 data points in table and plot

#### 8. Test Missing Library Error
Create a new Python cell:
```python
import matplotlib.pyplot as plt
fig = plt.figure()
fig
```

Then in terminal:
```bash
cd backend
uv pip uninstall matplotlib
```

Re-run cell

**Expected:** Clear error message: "ModuleNotFoundError: No module named 'matplotlib'"

### Success Criteria

#### Manual Verification:
- [ ] Matplotlib plots render as PNG images in frontend
- [ ] Plotly charts are interactive (hover, zoom, pan work)
- [ ] Altair charts render correctly using Vega-Lite
- [ ] Pandas DataFrames render as tables (not `<pandas.DataFrame>` text)
- [ ] Reactive cascades update visualizations when upstream cells change
- [ ] Plot in Cell 3 updates when Cell 1 variable changes
- [ ] Missing library errors display helpful messages in cell output
- [ ] No console errors in browser dev tools
- [ ] No Python tracebacks in backend logs (except expected ImportError)

---

## Testing Strategy

### Unit Tests
**Goal:** Test each MIME conversion function in isolation

**Approach:**
- Use `pytest.importorskip()` to handle optional dependencies
- Test each library independently (matplotlib, plotly, altair, pandas)
- Verify fallback to text/plain for unknown types
- Test error handling for missing libraries

**Coverage:** Lines 86-93 replacement in executor.py (the `_to_output()` method)

### Integration Tests
**Goal:** Verify rich outputs flow through full system

**Approach:**
- Test executor → kernel → orchestration → WebSocket pipeline
- Verify reactive cascades work with visualizations
- Test real-world workflows (variable → DataFrame → plot)

**Coverage:** Full stack from executor through dependency graph

### Manual Testing
**Goal:** Verify frontend rendering and user experience

**Approach:**
- Test each visualization type in running application
- Verify interactive features (Plotly hover/zoom)
- Test reactive cascades with UI
- Verify error messages display correctly

**Coverage:** Complete user-facing functionality

---

## Performance Considerations

### Memory Management
- **Matplotlib figures**: Call `plt.close(obj)` after converting to PNG to free memory
- **Large DataFrames**: Current implementation sends all rows (no truncation)
  - Future enhancement: Limit to 1,000 rows with truncation message
  - Out of scope for this plan

### Network Transfer
- **PNG images**: Base64 encoding increases size by ~33%
  - Typical matplotlib figure: 50-200KB
  - Acceptable for WebSocket transfer
- **Plotly/Altair JSON**: Usually smaller than PNG (5-50KB)
- **Large DataFrames**: Could be >1MB for thousands of rows
  - Out of scope: Add size limits or pagination

### Rendering Performance
- **Frontend already optimized**: Uses React keys for Plotly to prevent unnecessary re-renders
- **No changes needed**: Current implementation is sufficient

---

## Migration Notes

### Backward Compatibility
- ✅ **Existing notebooks**: Will continue to work (all output was text/plain before)
- ✅ **No database migrations**: No schema changes required
- ✅ **No API changes**: WebSocket messages have same structure

### Gradual Rollout
Users can opt-in to visualization support by:
1. Installing optional dependencies: `uv sync --extra viz --extra data`
2. Using visualization libraries in cells (automatic MIME conversion)

Users without optional dependencies:
- Get helpful ImportError messages if they try to import missing libraries
- Can continue using notebooks with text/plain output

---

## References

### Research Documents
- [2026-01-07-rich-output-mime-conversion.md](../research/2026-01-07-rich-output-mime-conversion.md) - Complete architecture analysis

### Architecture Documents
- [2026-01-06-fresh-start-architecture.md](../research/2026-01-06-fresh-start-architecture.md) - Original 3-layer design

### Implementation Files
- [backend/app/core/executor.py:86-93](../../../backend/app/core/executor.py) - **Primary change location**
- [backend/pyproject.toml](../../../backend/pyproject.toml) - Dependencies
- [backend/tests/test_executor.py](../../../backend/tests/test_executor.py) - Unit tests
- [frontend/src/components/OutputRenderer.tsx:44-131](../../../frontend/src/components/OutputRenderer.tsx) - Frontend rendering (no changes)

### External References
- Jupyter MIME protocol: https://jupyter-client.readthedocs.io/en/stable/messaging.html#display-data
- IPython display system: https://ipython.readthedocs.io/en/stable/config/integrating.html
- Matplotlib backends: https://matplotlib.org/stable/users/explain/figure/backends.html
- Plotly JSON format: https://plotly.com/javascript/plotlyjs-function-reference/
- Vega-Lite spec: https://vega.github.io/vega-lite/docs/spec.html

---

## Conclusion

This implementation adds rich output support through a **single-file enhancement** to the executor layer, plus optional dependencies and comprehensive testing. The existing architecture is perfectly designed for this feature:

- ✅ Executor is the correct location (has access to Python runtime)
- ✅ All downstream layers are generic (no changes needed)
- ✅ Frontend is already implemented (supports all MIME types)
- ✅ Type safety maintained (Pydantic models)
- ✅ Low-risk, high-value change

**Implementation effort:** ~2-3 hours
**Risk level:** Low (isolated to executor, backward compatible)
**Value:** High (enables data science workflows with visualizations)
