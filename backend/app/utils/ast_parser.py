import ast
import re
from typing import Set, Tuple, Dict, Any


class VariableVisitor(ast.NodeVisitor):
    """Extract reads/writes from Python AST"""

    def __init__(self):
        self.reads: Set[str] = set()
        self.writes: Set[str] = set()
        self.local_scope: Set[str] = set()  # Variables defined in this cell

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            # Only track as read if not locally defined
            if node.id not in self.local_scope:
                self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.writes.add(node.id)
            self.local_scope.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.writes.add(node.name)
        # Don't descend into function body (module-level semantics)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.writes.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.writes.add(node.name)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split('.')[0]
            self.writes.add(name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            if name != '*':  # Ignore star imports
                self.writes.add(name)


def extract_dependencies(code: str) -> Tuple[Set[str], Set[str]]:
    """
    Extract read and write dependencies from Python code.
    Returns: (reads, writes)
    """
    try:
        tree = ast.parse(code)
        visitor = VariableVisitor()
        visitor.visit(tree)

        # Filter out builtins
        builtins = set(dir(__builtins__))
        reads = visitor.reads - builtins

        return reads, visitor.writes
    except SyntaxError:
        # If code has syntax error, return empty sets
        return set(), set()


def extract_sql_dependencies(sql: str) -> Set[str]:
    """
    Extract {variable} references from SQL template.
    Returns set of variable names.
    """
    # Find all {variable} patterns
    pattern = r'\{(\w+)\}'
    matches = re.findall(pattern, sql)
    return set(matches)


def substitute_sql_variables(sql: str, globals_dict: Dict[str, Any]) -> str:
    """
    Replace {variable} with actual values from globals_dict.
    Properly escapes SQL to prevent injection.
    """
    def replacer(match):
        var_name = match.group(1)

        if var_name not in globals_dict:
            raise NameError(f"Variable '{var_name}' not defined")

        value = globals_dict[var_name]

        # Simple SQL escaping (in production, use parameterized queries)
        if isinstance(value, str):
            # Escape single quotes
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, (int, float)):
            return str(value)
        elif value is None:
            return "NULL"
        else:
            # For complex types, stringify
            return f"'{str(value)}'"

    return re.sub(r'\{(\w+)\}', replacer, sql)

