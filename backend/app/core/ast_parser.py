"""AST-based dependency extraction for Python cells."""
import ast
from typing import Set, Tuple


class DependencyExtractor(ast.NodeVisitor):
    """Extract variable reads and writes from Python code."""

    def __init__(self):
        self.reads: Set[str] = set()
        self.writes: Set[str] = set()
        self.scope_stack: list[Set[str]] = [set()]  # Track local scopes

    def visit_Name(self, node: ast.Name):
        """Visit variable name nodes."""
        if isinstance(node.ctx, ast.Load):
            # Reading a variable
            # Only add to reads if it's not in the current module scope
            # (i.e., it's an external dependency)
            if not self._is_local(node.id) and node.id not in self.scope_stack[0]:
                self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            # Writing a variable (module-level only)
            if len(self.scope_stack) == 1:  # Top-level scope
                self.writes.add(node.id)
                self.scope_stack[0].add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions."""
        # Functions define a name at module level
        if len(self.scope_stack) == 1:
            self.writes.add(node.name)
        # Don't descend into function body (local variables are not tracked)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit async function definitions."""
        if len(self.scope_stack) == 1:
            self.writes.add(node.name)
        # Don't descend into function body

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions."""
        if len(self.scope_stack) == 1:
            self.writes.add(node.name)
        # Don't descend into class body

    def visit_Import(self, node: ast.Import):
        """Visit import statements."""
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.writes.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Visit 'from X import Y' statements."""
        for alias in node.names:
            if alias.name == '*':
                # Can't track wildcard imports
                continue
            name = alias.asname or alias.name
            self.writes.add(name)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        """Visit augmented assignments (x += 1)."""
        # This both reads and writes the variable
        if isinstance(node.target, ast.Name):
            if len(self.scope_stack) == 1:
                self.reads.add(node.target.id)
                self.writes.add(node.target.id)
                self.scope_stack[0].add(node.target.id)
        self.generic_visit(node)

    def _is_local(self, name: str) -> bool:
        """Check if a variable name is in a local scope."""
        # If we're in a nested scope, check if it's defined there
        if len(self.scope_stack) > 1:
            for scope in self.scope_stack[1:]:
                if name in scope:
                    return True
        return False


def extract_python_dependencies(code: str) -> Tuple[Set[str], Set[str]]:
    """
    Extract variable dependencies from Python code.

    Returns:
        (reads, writes) - Sets of variable names that are read and written
    """
    try:
        tree = ast.parse(code)
        extractor = DependencyExtractor()
        extractor.visit(tree)

        # Return raw reads and writes
        # A variable can be both read and written (e.g., x += 1)
        return extractor.reads, extractor.writes
    except SyntaxError:
        # If code has syntax errors, return empty sets
        return set(), set()


def extract_sql_dependencies(sql: str) -> Set[str]:
    """
    Extract template variable references from SQL code.

    SQL cells use {variable_name} syntax for substitution.
    Example: SELECT * FROM users WHERE id = {user_id}

    Returns:
        Set of variable names referenced in the SQL
    """
    import re
    return set(re.findall(r'\{(\w+)\}', sql))
