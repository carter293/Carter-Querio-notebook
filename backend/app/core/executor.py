"""Code execution engine."""
import ast
import traceback
from io import StringIO
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Output(BaseModel):
    """Represents a cell output."""
    mime_type: str
    data: str | dict | list
    metadata: Optional[dict[str, Any]] = None


class ExecutionResult(BaseModel):
    """Result of executing a cell."""
    status: str  # 'success' or 'error'
    stdout: str = ''
    outputs: List[Output] = []
    error: Optional[str] = None


class PythonExecutor:
    """Executes Python code and captures outputs."""

    def __init__(self):
        self.globals_dict: Dict[str, Any] = {}

    def execute(self, code: str) -> ExecutionResult:
        """
        Execute Python code and capture outputs.

        Strategy:
        1. Parse code into AST
        2. If last statement is an expression, eval it and capture the result
        3. Execute all other statements with exec()
        4. Capture stdout during execution
        5. Convert final expression result to output (if not None)
        """
        stdout_buffer = StringIO()
        outputs: List[Output] = []

        try:
            tree = ast.parse(code)

            # Check if last statement is an expression
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                # Split into statements + final expression
                statements = ast.Module(body=tree.body[:-1], type_ignores=[])
                expression = ast.Expression(body=tree.body[-1].value)

                with redirect_stdout(stdout_buffer):
                    # Execute statements
                    if statements.body:
                        exec(compile(statements, '<cell>', 'exec'), self.globals_dict)

                    # Evaluate expression
                    result = eval(compile(expression, '<cell>', 'eval'), self.globals_dict)

                # Convert result to output
                if result is not None:
                    output = self._to_output(result)
                    if output:
                        outputs.append(output)
            else:
                # Pure statements, no expression
                with redirect_stdout(stdout_buffer):
                    exec(compile(tree, '<cell>', 'exec'), self.globals_dict)

            return ExecutionResult(
                status='success',
                stdout=stdout_buffer.getvalue(),
                outputs=outputs
            )

        except Exception as e:
            # Capture full traceback
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            return ExecutionResult(
                status='error',
                error=''.join(tb)
            )

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

    def reset(self):
        """Clear the execution namespace."""
        self.globals_dict.clear()


class SQLExecutor:
    """Executes SQL queries against PostgreSQL database."""

    def __init__(self):
        """Initialize SQL executor with no connection."""
        self.connection_string: str | None = None

    def set_connection_string(self, conn_str: str) -> None:
        """
        Configure database connection string.

        Args:
            conn_str: PostgreSQL connection string (e.g., "postgresql://localhost/testdb")
        """
        self.connection_string = conn_str

    def _prepare_parameterized_query(
        self, sql: str, variables: Dict[str, Any]
    ) -> tuple[str, list[str]]:
        """
        Convert {variable} templates to $1, $2, ... parameter syntax.

        Args:
            sql: SQL query with {variable_name} templates
            variables: Dictionary mapping variable names to values

        Returns:
            Tuple of (parameterized_sql, parameter_values as strings)

        Raises:
            ValueError: If a template variable is not found in variables dict

        Example:
            sql = "SELECT {user_id} as id, {min_age} as min_age"
            variables = {'user_id': 42, 'min_age': 18}

            Returns:
                ("SELECT $1 as id, $2 as min_age", ['42', '18'])
                
        Note:
            All parameters are converted to strings. PostgreSQL will automatically
            convert them to the appropriate type based on the SQL context (e.g.,
            in comparisons, function arguments, etc.). This avoids type inference
            issues with queries like "SELECT $1" where PostgreSQL has no context
            to determine the parameter type.
        """
        import re

        params: list[str] = []
        param_counter = 1

        def replace_var(match: re.Match) -> str:
            nonlocal param_counter
            var_name = match.group(1)

            if var_name not in variables:
                raise ValueError(f"Variable '{var_name}' not found in namespace")

            value = variables[var_name]
            # Convert to string, handle None as NULL
            params.append(str(value) if value is not None else None)
            
            placeholder = f"${param_counter}"
            param_counter += 1
            return placeholder

        safe_sql = re.sub(r'\{(\w+)\}', replace_var, sql)
        return safe_sql, params

    async def execute(self, sql: str, variables: Dict[str, Any]) -> ExecutionResult:
        """
        Execute SQL query with safe parameter binding.

        Args:
            sql: SQL query with {variable_name} templates
            variables: Python namespace for variable substitution

        Returns:
            ExecutionResult with table data or error
        """
        import asyncpg
        from io import StringIO

        stdout_buffer = StringIO()

        # Check connection configured
        if not self.connection_string:
            return ExecutionResult(
                status='error',
                error='Database connection not configured. Use PUT /notebooks/{id}/db to set connection string.'
            )

        try:
            # Convert templates to parameterized query
            safe_sql, params = self._prepare_parameterized_query(sql, variables)

            # Log the executed query
            stdout_buffer.write(f"Executing: {safe_sql}\n")
            stdout_buffer.write(f"Parameters: {params}\n")

            # Connect and execute
            conn = await asyncpg.connect(self.connection_string)
            try:
                # Parameters are already converted to strings in _prepare_parameterized_query
                records = await conn.fetch(safe_sql, *params)

                if records:
                    # Convert asyncpg Records to table format
                    from datetime import datetime, date, time

                    def serialize_value(val):
                        """Convert non-JSON-serializable types to strings."""
                        if isinstance(val, (datetime, date, time)):
                            return val.isoformat()
                        return val

                    columns = list(records[0].keys())
                    rows = [[serialize_value(val) for val in record.values()] for record in records]

                    stdout_buffer.write(f"Returned {len(rows)} row(s)\n")

                    return ExecutionResult(
                        status='success',
                        stdout=stdout_buffer.getvalue(),
                        outputs=[
                            Output(
                                mime_type='application/json',
                                data={
                                    'type': 'table',
                                    'columns': columns,
                                    'rows': rows
                                }
                            )
                        ]
                    )
                else:
                    # No results
                    return ExecutionResult(
                        status='success',
                        stdout=stdout_buffer.getvalue() + "Query returned 0 rows\n"
                    )

            finally:
                await conn.close()

        except ValueError as e:
            # Missing variable in template
            return ExecutionResult(
                status='error',
                error=f"Template variable error: {str(e)}"
            )

        except asyncpg.PostgresError as e:
            # Database error (syntax, permissions, etc)
            return ExecutionResult(
                status='error',
                error=f"Database error: {str(e)}"
            )

        except Exception as e:
            # Unexpected error
            return ExecutionResult(
                status='error',
                error=f"Execution failed: {str(e)}"
            )
