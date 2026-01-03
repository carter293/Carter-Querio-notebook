import pytest
from app.models import Cell, CellType, CellStatus
from app.execution import execute_python_cell, ExecutionResult
from tests.test_utils import create_test_cell

@pytest.mark.asyncio
async def test_execute_simple_assignment():
    cell = Cell(id="test", type=CellType.PYTHON, code="x = 5")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.SUCCESS
    assert globals_dict['x'] == 5

@pytest.mark.asyncio
async def test_execute_with_stdout():
    cell = Cell(id="test", type=CellType.PYTHON, code="print('hello world')")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.SUCCESS
    assert result.stdout == "hello world\n"

@pytest.mark.asyncio
async def test_execute_with_dependency():
    globals_dict = {"__builtins__": __builtins__, "x": 10}
    cell = Cell(id="test", type=CellType.PYTHON, code="y = x * 2")

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.SUCCESS
    assert globals_dict['y'] == 20

@pytest.mark.asyncio
async def test_execute_syntax_error():
    cell = Cell(id="test", type=CellType.PYTHON, code="x = (")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.ERROR
    assert "SyntaxError" in result.error

@pytest.mark.asyncio
async def test_execute_runtime_error():
    cell = Cell(id="test", type=CellType.PYTHON, code="x = 1 / 0")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.ERROR
    assert "ZeroDivisionError" in result.error

@pytest.mark.asyncio
async def test_execute_name_error():
    cell = Cell(id="test", type=CellType.PYTHON, code="y = undefined_var")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.ERROR
    assert "NameError" in result.error

@pytest.mark.asyncio
async def test_execute_multiple_statements():
    cell = Cell(id="test", type=CellType.PYTHON, code="x = 5\ny = x * 2\nprint(y)")
    globals_dict = {"__builtins__": __builtins__}

    result = await execute_python_cell(cell, globals_dict)

    assert result.status == CellStatus.SUCCESS
    assert globals_dict['x'] == 5
    assert globals_dict['y'] == 10
    assert result.stdout == "10\n"
