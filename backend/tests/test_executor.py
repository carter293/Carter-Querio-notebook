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


def test_sql_template_substitution():
    """Test SQL variable substitution."""
    executor = SQLExecutor()
    result = executor.execute(
        "SELECT * FROM users WHERE id = {user_id}",
        variables={'user_id': 42}
    )

    assert result.status == 'success'
    assert 'id = 42' in result.stdout


def test_sql_missing_variable():
    """Test SQL with missing variable."""
    executor = SQLExecutor()
    result = executor.execute(
        "SELECT * FROM users WHERE id = {user_id}",
        variables={}
    )

    assert result.status == 'error'
    assert 'user_id' in result.error
