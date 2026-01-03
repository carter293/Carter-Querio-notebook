import pytest
from app.utils.ast_parser import extract_dependencies, extract_sql_dependencies, substitute_sql_variables

def test_extract_simple_assignment():
    code = "x = 5"
    reads, writes = extract_dependencies(code)
    assert writes == {'x'}
    assert reads == set()

def test_extract_dependency():
    code = "y = x + 1"
    reads, writes = extract_dependencies(code)
    assert writes == {'y'}
    assert reads == {'x'}

def test_extract_function_def():
    code = "def foo(): pass"
    reads, writes = extract_dependencies(code)
    assert writes == {'foo'}

def test_extract_import():
    code = "import pandas as pd"
    reads, writes = extract_dependencies(code)
    assert writes == {'pd'}

def test_local_variable_not_read():
    code = "x = 5\ny = x + 1"
    reads, writes = extract_dependencies(code)
    assert reads == set()  # x is local
    assert writes == {'x', 'y'}

def test_multiple_reads():
    code = "z = x + y"
    reads, writes = extract_dependencies(code)
    assert reads == {'x', 'y'}
    assert writes == {'z'}

def test_from_import():
    code = "from pandas import DataFrame"
    reads, writes = extract_dependencies(code)
    assert writes == {'DataFrame'}

def test_from_import_as():
    code = "from pandas import DataFrame as DF"
    reads, writes = extract_dependencies(code)
    assert writes == {'DF'}

def test_class_def():
    code = "class MyClass: pass"
    reads, writes = extract_dependencies(code)
    assert writes == {'MyClass'}

def test_syntax_error():
    code = "x = ("
    reads, writes = extract_dependencies(code)
    assert reads == set()
    assert writes == set()

def test_sql_template_extraction():
    sql = "SELECT * FROM users WHERE id = {user_id} AND name = {user_name}"
    deps = extract_sql_dependencies(sql)
    assert deps == {'user_id', 'user_name'}

def test_sql_template_extraction_empty():
    sql = "SELECT * FROM users"
    deps = extract_sql_dependencies(sql)
    assert deps == set()

def test_sql_substitution_int():
    sql = "SELECT * FROM users WHERE id = {user_id}"
    result = substitute_sql_variables(sql, {'user_id': 42})
    assert result == "SELECT * FROM users WHERE id = 42"

def test_sql_substitution_string():
    sql = "SELECT * FROM users WHERE name = {name}"
    result = substitute_sql_variables(sql, {'name': "Alice"})
    assert result == "SELECT * FROM users WHERE name = 'Alice'"

def test_sql_substitution_string_with_quotes():
    sql = "SELECT * FROM users WHERE name = {name}"
    result = substitute_sql_variables(sql, {'name': "O'Brien"})
    assert result == "SELECT * FROM users WHERE name = 'O''Brien'"

def test_sql_substitution_none():
    sql = "SELECT * FROM users WHERE name = {name}"
    result = substitute_sql_variables(sql, {'name': None})
    assert result == "SELECT * FROM users WHERE name = NULL"

def test_sql_substitution_missing_variable():
    sql = "SELECT * FROM users WHERE id = {user_id}"
    with pytest.raises(NameError):
        substitute_sql_variables(sql, {})

def test_sql_substitution_multiple():
    sql = "SELECT * FROM users WHERE id = {uid} AND name = {uname}"
    result = substitute_sql_variables(sql, {'uid': 123, 'uname': 'Bob'})
    assert result == "SELECT * FROM users WHERE id = 123 AND name = 'Bob'"
