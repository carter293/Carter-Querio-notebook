import sys
import traceback
import base64
from io import StringIO, BytesIO
from contextlib import redirect_stdout
from typing import Optional, Dict, Any, Union, List, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Cell, CellStatus, Output
else:
    Cell = 'Cell'
    CellStatus = 'CellStatus'
    Output = 'Output'

def to_mime_bundle(obj: object) -> Optional['Output']:
    """Convert Python object to MIME bundle output"""
    from models import Output, MimeType

    # Matplotlib figure
    try:
        import matplotlib.pyplot as plt
        if isinstance(obj, plt.Figure):
            buf = BytesIO()
            obj.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            return Output(mime_type=MimeType.PNG, data=img_base64)
    except ImportError:
        pass

    # Plotly figure
    try:
        import plotly.graph_objects as go
        if isinstance(obj, go.Figure):
            # Use to_json() for frontend rendering with Plotly.js
            import json
            spec = json.loads(obj.to_json())
            return Output(mime_type=MimeType.PLOTLY_JSON, data=spec)
    except ImportError:
        pass

    # Altair chart
    try:
        import altair as alt
        if isinstance(obj, alt.Chart):
            vega_json = obj.to_dict()
            return Output(mime_type=MimeType.VEGA_LITE, data=vega_json)
    except ImportError:
        pass

    # Pandas DataFrame
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            table_data = {
                "type": "table",
                "columns": obj.columns.tolist(),
                "rows": obj.values.tolist()
            }
            return Output(mime_type=MimeType.JSON, data=table_data)
    except ImportError:
        pass

    # Fallback: convert to string
    return Output(mime_type=MimeType.PLAIN, data=str(obj))

class ExecutionResult:
    def __init__(
        self,
        status: 'CellStatus',
        stdout: str = "",
        error: Optional[str] = None,
        outputs: Optional[List['Output']] = None
    ):
        self.status: 'CellStatus' = status
        self.stdout: str = stdout
        self.error: Optional[str] = error
        self.outputs: List['Output'] = outputs or []

async def execute_python_cell(
    cell: 'Cell',
    globals_dict: Dict[str, Any],
    cell_index: int = 0
) -> ExecutionResult:
    """
    Execute Python code in cell, capturing stdout and last expression value.
    
    Note: This runs synchronously in the main thread because libraries like matplotlib
    use thread-local storage and GUI backends that don't work in thread pools.
    The caller should use `await asyncio.sleep(0)` before calling to yield to the
    event loop and flush pending WebSocket messages.
    """
    from models import CellStatus
    import ast

    stdout_capture = StringIO()
    outputs: List['Output'] = []

    try:
        # Try to parse as expression first
        try:
            compiled = compile(cell.code, f"Cell[{cell_index}]", "eval")
            with redirect_stdout(stdout_capture):
                result_value = eval(compiled, globals_dict)

            # Convert result to MIME bundle
            if result_value is not None:
                output = to_mime_bundle(result_value)
                if output:
                    outputs.append(output)

        except SyntaxError:
            # Not a simple expression, compile as statements
            tree = ast.parse(cell.code)

            if tree.body and isinstance(tree.body[-1], ast.Expr):
                # Last statement is an expression
                exec_code = compile(ast.Module(body=tree.body[:-1], type_ignores=[]),
                                   f"Cell[{cell_index}]", "exec")
                eval_code = compile(ast.Expression(body=tree.body[-1].value),
                                   f"Cell[{cell_index}]", "eval")

                with redirect_stdout(stdout_capture):
                    exec(exec_code, globals_dict)
                    result_value = eval(eval_code, globals_dict)

                if result_value is not None:
                    output = to_mime_bundle(result_value)
                    if output:
                        outputs.append(output)
            else:
                # No trailing expression
                compiled = compile(cell.code, f"Cell[{cell_index}]", "exec")
                with redirect_stdout(stdout_capture):
                    exec(compiled, globals_dict)

        stdout_text = stdout_capture.getvalue()
        return ExecutionResult(
            status=CellStatus.SUCCESS,
            stdout=stdout_text,
            outputs=outputs
        )

    except SyntaxError as e:
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
        error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        return ExecutionResult(
            status=CellStatus.ERROR,
            error=error_msg
        )

async def execute_sql_cell(cell, conn_string: str, globals_dict: Dict[str, Any]) -> ExecutionResult:
    """
    Execute SQL query against PostgreSQL database.
    Returns result as table (columns + rows) in outputs.
    """
    from models import CellStatus, Output, MimeType
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

            outputs: List['Output'] = []
            # Convert to dict format
            if result:
                columns = list(result[0].keys())
                
                # Convert rows, handling non-JSON-serializable types (dates, decimals, etc.)
                rows = []
                for record in result:
                    row = []
                    for value in record.values():
                        # Convert dates/datetimes to ISO format strings
                        if hasattr(value, 'isoformat'):
                            row.append(value.isoformat())
                        # Convert decimals to float
                        elif hasattr(value, '__float__') and type(value).__name__ == 'Decimal':
                            row.append(float(value))
                        else:
                            row.append(value)
                    rows.append(row)

                # Limit rows to prevent UI overload
                MAX_ROWS = 1000
                truncated_msg = ""
                if len(rows) > MAX_ROWS:
                    rows = rows[:MAX_ROWS]
                    truncated_msg = f"(Showing first {MAX_ROWS} of {len(result)} rows)"

                table_data = {
                    "type": "table",
                    "columns": columns,
                    "rows": rows,
                    "truncated": truncated_msg
                }
                outputs.append(Output(mime_type=MimeType.JSON, data=table_data))
            else:
                # Empty result - just show via plain text in stdout or skip
                pass

            return ExecutionResult(
                status=CellStatus.SUCCESS,
                outputs=outputs,
                stdout="Query returned no rows" if not result else ""
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
