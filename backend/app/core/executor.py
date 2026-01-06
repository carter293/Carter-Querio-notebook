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
        """Convert Python objects to Output format (stub implementation)."""
        # For now, just convert to text
        # Future: Handle pandas DataFrames, matplotlib figures, etc.
        return Output(
            mime_type='text/plain',
            data=str(obj)
        )

    def reset(self):
        """Clear the execution namespace."""
        self.globals_dict.clear()


class SQLExecutor:
    """Executes SQL queries (stub implementation)."""

    def execute(self, sql: str, variables: Dict[str, Any]) -> ExecutionResult:
        """
        Execute SQL query with variable substitution.

        For now, this is a stub that returns fake data.
        Future: Connect to actual database.
        """
        try:
            # Substitute {variable} templates
            substituted_sql = self._substitute_variables(sql, variables)

            # Stub: Return fake table data
            return ExecutionResult(
                status='success',
                stdout=f'Executed: {substituted_sql}\n',
                outputs=[Output(
                    mime_type='application/json',
                    data={
                        'type': 'table',
                        'columns': ['id', 'name'],
                        'rows': [[1, 'Alice'], [2, 'Bob']]
                    }
                )]
            )
        except Exception as e:
            return ExecutionResult(
                status='error',
                error=str(e)
            )

    def _substitute_variables(self, sql: str, variables: Dict[str, Any]) -> str:
        """Replace {variable} templates with actual values."""
        import re

        def replace_var(match):
            var_name = match.group(1)
            if var_name not in variables:
                raise ValueError(f"Variable '{var_name}' not found in namespace")
            return str(variables[var_name])

        return re.sub(r'\{(\w+)\}', replace_var, sql)
