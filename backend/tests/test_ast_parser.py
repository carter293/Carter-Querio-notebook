"""Tests for AST dependency extraction."""
import pytest
from app.core.ast_parser import extract_python_dependencies, extract_sql_dependencies


def test_simple_assignment():
    code = "x = 10"
    reads, writes = extract_python_dependencies(code)
    assert reads == set()
    assert writes == {'x'}


def test_read_and_write():
    code = "y = x * 2"
    reads, writes = extract_python_dependencies(code)
    assert reads == {'x'}
    assert writes == {'y'}


def test_multiple_variables():
    code = """
a = x + 1
b = y + 2
c = a + b
"""
    reads, writes = extract_python_dependencies(code)
    assert reads == {'x', 'y'}  # a, b are defined in this cell, not external deps
    assert writes == {'a', 'b', 'c'}


def test_function_definition():
    code = """
def foo(x):
    local_var = x * 2
    return local_var
"""
    reads, writes = extract_python_dependencies(code)
    assert reads == set()
    assert writes == {'foo'}  # Only the function name


def test_import_statements():
    code = """
import pandas as pd
from matplotlib import pyplot as plt
"""
    reads, writes = extract_python_dependencies(code)
    assert reads == set()
    assert writes == {'pd', 'plt'}


def test_class_definition():
    code = """
class MyClass:
    def __init__(self):
        self.value = 10
"""
    reads, writes = extract_python_dependencies(code)
    assert reads == set()
    assert writes == {'MyClass'}


def test_syntax_error():
    code = "x = ("  # Invalid syntax
    reads, writes = extract_python_dependencies(code)
    assert reads == set()
    assert writes == set()


def test_sql_template_extraction():
    sql = "SELECT * FROM users WHERE id = {user_id} AND status = {status}"
    deps = extract_sql_dependencies(sql)
    assert deps == {'user_id', 'status'}


def test_sql_no_templates():
    sql = "SELECT * FROM users LIMIT 10"
    deps = extract_sql_dependencies(sql)
    assert deps == set()
