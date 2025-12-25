import sys
import traceback
from io import StringIO
from contextlib import redirect_stdout
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Cell, CellStatus
else:
    Cell = 'Cell'
    CellStatus = 'CellStatus'

class ExecutionResult:
    def __init__(self, status, stdout: str = "",
                 result: Any = None, error: Optional[str] = None):
        self.status = status
        self.stdout = stdout
        self.result = result
        self.error = error

async def execute_python_cell(cell, globals_dict: Dict[str, Any]) -> ExecutionResult:
    """
    Execute Python code in cell, capturing stdout and errors.
    Updates globals_dict in place.
    """
    from models import CellStatus

    stdout_capture = StringIO()

    try:
        # Compile code
        compiled = compile(cell.code, f"<cell-{cell.id}>", "exec")

        # Execute with stdout capture
        with redirect_stdout(stdout_capture):
            exec(compiled, globals_dict)

        # Success
        stdout_text = stdout_capture.getvalue()
        return ExecutionResult(
            status=CellStatus.SUCCESS,
            stdout=stdout_text,
            result=None  # Could extract last expression value if needed
        )

    except SyntaxError as e:
        # Format with line number and context
        error_msg = f"SyntaxError on line {e.lineno}: {e.msg}"
        if e.text:
            error_msg += f"\n{e.text.rstrip()}"
            if e.offset:
                error_msg += f"\n{' ' * (e.offset - 1)}^"
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=error_msg
        )

    except Exception as e:
        # Capture full traceback
        error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=error_msg
        )

async def execute_sql_cell(cell, conn_string: str, globals_dict: Dict[str, Any]) -> ExecutionResult:
    """
    Execute SQL query against PostgreSQL database.
    Returns result as table (columns + rows).
    """
    from models import CellStatus
    from ast_parser import substitute_sql_variables

    if not conn_string:
        return ExecutionResult(
            status=CellStatus.ERROR,
            error="Database connection string not configured"
        )

    try:
        import asyncpg

        # Substitute variables
        substituted_sql = substitute_sql_variables(cell.code, globals_dict)

        # Connect and execute
        conn = await asyncpg.connect(conn_string)
        try:
            result = await conn.fetch(substituted_sql)

            # Convert to dict format
            if result:
                columns = list(result[0].keys())
                rows = [list(record.values()) for record in result]

                # Limit rows to prevent UI overload
                MAX_ROWS = 1000
                truncated_msg = ""
                if len(rows) > MAX_ROWS:
                    rows = rows[:MAX_ROWS]
                    truncated_msg = f"(Showing first {MAX_ROWS} of {len(result)} rows)"

                result_data = {
                    "type": "table",
                    "columns": columns,
                    "rows": rows,
                    "truncated": truncated_msg
                }
            else:
                result_data = {"type": "empty", "message": "Query returned no rows"}

            return ExecutionResult(
                status=CellStatus.SUCCESS,
                result=result_data
            )
        finally:
            await conn.close()

    except NameError as e:
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=f"Variable error: {str(e)}"
        )
    except ImportError:
        return ExecutionResult(
            status=CellStatus.ERROR,
            error="asyncpg not installed. Install with: pip install asyncpg"
        )
    except Exception as e:
        # Handle asyncpg.PostgresError and other exceptions
        error_type = type(e).__name__
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=f"{error_type}: {str(e)}"
        )
