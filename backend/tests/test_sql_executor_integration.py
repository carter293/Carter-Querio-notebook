"""Integration tests for SQLExecutor with PostgreSQL.

These tests require a local PostgreSQL instance running.
See ../postgres/README.md for setup instructions:
    cd postgres && docker compose up -d

Connection string: postgresql://querio_user:querio_password@localhost:5432/querio_db
"""

import pytest
import asyncio
import asyncpg
from app.core.executor import SQLExecutor

# Connection string from postgres/README.md
DB_CONNECTION_STRING = "postgresql://querio_user:querio_password@localhost:5432/querio_db"


# Check if PostgreSQL is available
async def check_postgres_available():
    """Check if PostgreSQL is running with querio_db database."""
    try:
        conn = await asyncpg.connect(DB_CONNECTION_STRING, timeout=2)
        await conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not asyncio.run(check_postgres_available()),
    reason="PostgreSQL not available. Start with: cd postgres && docker compose up -d"
)


@pytest.mark.asyncio
async def test_sql_basic_query():
    """Test basic SQL query execution."""
    executor = SQLExecutor()
    executor.set_connection_string(DB_CONNECTION_STRING)

    result = await executor.execute(
        "SELECT 1 as num, 'hello' as text",
        {}
    )

    assert result.status == 'success'
    assert len(result.outputs) == 1
    assert result.outputs[0].mime_type == 'application/json'

    data = result.outputs[0].data
    assert data['type'] == 'table'
    assert data['columns'] == ['num', 'text']
    assert data['rows'] == [[1, 'hello']]


@pytest.mark.asyncio
async def test_sql_template_substitution():
    """Test {variable} template substitution with parameterized queries."""
    executor = SQLExecutor()
    executor.set_connection_string(DB_CONNECTION_STRING)

    variables = {'user_id': 42, 'min_age': 18}

    result = await executor.execute(
        "SELECT {user_id} as id, {min_age} as min_age",
        variables
    )

    assert result.status == 'success'
    data = result.outputs[0].data
    # Parameters are converted to strings for PostgreSQL type compatibility
    assert data['rows'] == [['42', '18']]


@pytest.mark.asyncio
async def test_sql_missing_variable():
    """Test error handling for missing template variable."""
    executor = SQLExecutor()
    executor.set_connection_string(DB_CONNECTION_STRING)

    result = await executor.execute(
        "SELECT {missing_var}",
        {}
    )

    assert result.status == 'error'
    assert 'missing_var' in result.error.lower()
    assert 'not found' in result.error.lower()


@pytest.mark.asyncio
async def test_sql_no_connection_string():
    """Test error when connection string not configured."""
    executor = SQLExecutor()

    result = await executor.execute("SELECT 1", {})

    assert result.status == 'error'
    assert 'not configured' in result.error.lower()


@pytest.mark.asyncio
async def test_sql_syntax_error():
    """Test error handling for invalid SQL syntax."""
    executor = SQLExecutor()
    executor.set_connection_string(DB_CONNECTION_STRING)

    result = await executor.execute("INVALID SQL SYNTAX", {})

    assert result.status == 'error'
    assert 'syntax' in result.error.lower() or 'database error' in result.error.lower()


@pytest.mark.asyncio
async def test_sql_connection_failure():
    """Test error handling for connection failures."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://invalid-host:9999/baddb")

    result = await executor.execute("SELECT 1", {})

    assert result.status == 'error'

