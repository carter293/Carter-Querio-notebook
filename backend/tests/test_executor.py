"""Tests for code executor."""
import pytest
from app.core.executor import PythonExecutor, SQLExecutor


def test_simple_execution():
    """Test basic code execution."""
    executor = PythonExecutor()
    result = executor.execute("x = 10")

    assert result.status == 'success'
    assert executor.globals_dict['x'] == 10


def test_stdout_capture():
    """Test that print statements are captured."""
    executor = PythonExecutor()
    result = executor.execute("print('Hello, world!')")

    assert result.status == 'success'
    assert result.stdout == 'Hello, world!\n'


def test_expression_result():
    """Test that final expression results are captured."""
    executor = PythonExecutor()
    result = executor.execute("2 + 2")

    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'text/plain'
    assert result.outputs[0].data == '4'


def test_stateful_execution():
    """Test that variables persist across executions."""
    executor = PythonExecutor()

    # First cell
    result1 = executor.execute("x = 10")
    assert result1.status == 'success'

    # Second cell uses variable from first
    result2 = executor.execute("y = x * 2")
    assert result2.status == 'success'
    assert executor.globals_dict['y'] == 20


def test_syntax_error():
    """Test that syntax errors are captured."""
    executor = PythonExecutor()
    result = executor.execute("x = (")

    assert result.status == 'error'
    assert result.error is not None
    assert 'SyntaxError' in result.error


def test_runtime_error():
    """Test that runtime errors are captured."""
    executor = PythonExecutor()
    result = executor.execute("1 / 0")

    assert result.status == 'error'
    assert result.error is not None
    assert 'ZeroDivisionError' in result.error


@pytest.mark.asyncio
async def test_sql_no_connection_string():
    """Test SQL executor without connection string."""
    executor = SQLExecutor()
    result = await executor.execute(
        "SELECT * FROM users WHERE id = {user_id}",
        variables={'user_id': 42}
    )

    assert result.status == 'error'
    assert 'not configured' in result.error.lower()


@pytest.mark.asyncio
async def test_sql_missing_variable():
    """Test SQL with missing variable."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://localhost/testdb")
    
    result = await executor.execute(
        "SELECT * FROM users WHERE id = {user_id}",
        variables={}
    )

    assert result.status == 'error'
    assert 'user_id' in result.error.lower()
    assert 'not found' in result.error.lower()


# Rich Output Tests

def test_matplotlib_figure_output():
    """Test matplotlib figure converts to PNG."""
    pytest.importorskip('matplotlib')  # Skip if not installed

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
