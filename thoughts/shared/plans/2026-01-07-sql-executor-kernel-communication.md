# SQLExecutor Implementation with Database Connection Protocol

**Date:** 2026-01-07
**Purpose:** Complete SQLExecutor implementation with asyncpg and kernel message protocol for database connection configuration

---

## Overview

This plan implements a working SQLExecutor that can execute PostgreSQL queries with safe parameter binding, along with the kernel communication protocol needed to configure database connections from the API layer. The implementation bridges the orchestration-kernel boundary with a new message type for runtime configuration.

## Current State Analysis

### What Exists Now

1. **SQL Dependency Extraction**: ✅ Fully implemented
   - [backend/app/core/ast_parser.py:105-116](backend/app/core/ast_parser.py) - Regex-based `{variable}` template extraction
   - Returns `Set[str]` of variable names referenced in SQL

2. **SQLExecutor Stub**: ⚠️ Returns fake data with unsafe substitution
   - [backend/app/core/executor.py:100-144](backend/app/core/executor.py) - Current implementation
   - Uses string interpolation (SQL injection vulnerable)
   - Returns hardcoded mock data: `[{'id': 1, 'name': 'Alice'}, ...]`

3. **Connection String Storage**: ✅ Persisted in notebook metadata
   - [backend/app/models.py:50](backend/app/models.py) - `NotebookResponse.db_conn_string` field
   - [backend/app/api/notebooks.py:47-56](backend/app/api/notebooks.py) - `PUT /notebooks/{id}/db` endpoint
   - [backend/app/file_storage.py:25-32](backend/app/file_storage.py) - Stored as `# DB:` comment in `.py` files

4. **Kernel Process**: ✅ Event loop with message routing
   - [backend/app/kernel/process.py:11-152](backend/app/kernel/process.py) - Main event loop
   - [backend/app/kernel/types.py](backend/app/kernel/types.py) - Message type definitions
   - Current message types: `RegisterCellRequest`, `ExecuteRequest`, `ShutdownRequest`

5. **SQL Execution Flow**: ⚠️ Passes Python namespace but no DB connection
   - [backend/app/kernel/process.py:120](backend/app/kernel/process.py) - Calls `sql_executor.execute(cell_code, python_executor.globals_dict)`
   - Python variables available for template substitution
   - No database connection configured

### Key Discoveries

- **Critical Gap**: Connection string stored in notebook metadata never reaches the kernel process
- **Architecture Pattern**: Kernel uses queue-based IPC with Pydantic message models ([backend/app/kernel/process.py:27](backend/app/kernel/process.py))
- **Type Discrimination**: Messages routed by `type` field, `ExecuteRequest` has no type field ([backend/app/kernel/process.py:29-84](backend/app/kernel/process.py))
- **SQL is Read-Only**: SQL cells only have reads (from templates), never writes ([backend/app/kernel/process.py:121-122](backend/app/kernel/process.py))
- **Test Coverage**: Stub tests exist ([backend/tests/test_executor.py:69-90](backend/tests/test_executor.py))

### Missing Pieces

1. ❌ No `asyncpg` dependency in [backend/pyproject.toml:7-12](backend/pyproject.toml)
2. ❌ No message type to send connection string to kernel
3. ❌ No mechanism for orchestrator to send connection string on notebook load
4. ❌ SQLExecutor has no connection state or async execution capability

## System Context Analysis

This implementation operates within the 3-layer architecture defined in [thoughts/shared/research/2026-01-06-fresh-start-architecture.md](thoughts/shared/research/2026-01-06-fresh-start-architecture.md):

```
Interface Layer (FastAPI API/WebSocket)
         ↓
Orchestration Layer (NotebookCoordinator)
         ↓ (Queue-based IPC)
Kernel Layer (Separate Process)
```

**Current Flow (Broken)**:
1. API receives `PUT /notebooks/{id}/db` with connection string
2. Connection string saved to file storage
3. ❌ Kernel never receives connection string
4. SQL cells execute with stub data

**Target Flow (Fixed)**:
1. API receives `PUT /notebooks/{id}/db`
2. Connection string saved to file storage
3. ✅ Orchestrator sends `SetDatabaseConfigRequest` to kernel via queue
4. ✅ Kernel configures SQLExecutor with connection string
5. ✅ SQL cells execute real queries via asyncpg

This plan addresses a **root cause** (missing kernel communication protocol) not just a symptom (stub SQLExecutor). The proper solution requires both components: the executor implementation AND the configuration protocol.

## Desired End State

After this plan is complete:

1. **Functional SQL Execution**:
   - SQL cells execute real PostgreSQL queries via asyncpg
   - Template variables `{var}` safely substituted using parameterized queries
   - Results returned as table data (`application/json` with columns/rows)

2. **Database Configuration Protocol**:
   - New `SetDatabaseConfigRequest` message type in kernel protocol
   - Orchestrator sends connection string to kernel on notebook load
   - API endpoint updates trigger kernel reconfiguration

3. **Type Safety**:
   - All code passes `mypy --strict`
   - Pydantic models for all message types
   - Proper async/await with asyncpg

### Verification Steps

**Automated Verification**:
- [ ] Tests pass: `uv run pytest backend/tests/test_executor.py -k sql`
- [ ] Tests pass: `uv run pytest backend/tests/test_kernel_integration.py -k database_config`
- [ ] Type checking passes: `uv run mypy backend/app/core/executor.py backend/app/kernel/`

**Manual Verification**:
- [ ] Create notebook, set `db_conn_string` via `PUT /notebooks/{id}/db`
- [ ] Create Python cell: `user_id = 42`
- [ ] Create SQL cell: `SELECT * FROM users WHERE id = {user_id}`
- [ ] Run SQL cell, verify real database query executes
- [ ] Change Python cell to `user_id = 99`, verify SQL cell re-executes with new value
- [ ] Test error cases: invalid SQL, missing variable, connection failure

## What We're NOT Doing

To prevent scope creep:

- ❌ Connection pooling (use simple connection per query)
- ❌ Query result limits (return all rows)
- ❌ Multiple database support (PostgreSQL only)
- ❌ Query timeout configuration (use asyncpg defaults)
- ❌ SQL syntax highlighting in frontend
- ❌ Query performance monitoring
- ❌ Connection string validation/testing endpoint
- ❌ Database schema introspection
- ❌ Prepared statement caching

## Implementation Approach

### High-Level Strategy

1. **Add asyncpg dependency** - Minimal change to pyproject.toml
2. **Implement safe parameter binding** - Convert `{var}` → `$1, $2, ...` for asyncpg
3. **Add async execution** - SQLExecutor methods become async
4. **Define message protocol** - New Pydantic models for database configuration
5. **Wire up kernel handler** - Route `SetDatabaseConfigRequest` to SQLExecutor
6. **Orchestrator integration** - Send connection string on notebook load and API updates
7. **Update tests** - Real database tests + protocol tests

### Why This Order

- Dependencies first (can't import asyncpg without installing it)
- Executor implementation second (core business logic, testable in isolation)
- Protocol third (enables integration between layers)
- Integration last (depends on all components working)

---

## Phase 1: Dependencies and Executor Core

### Overview
Install asyncpg and implement safe SQL execution with parameterized queries. This phase focuses purely on the executor logic without kernel integration.

### Changes Required

#### 1. Add asyncpg Dependency
**File**: [backend/pyproject.toml](backend/pyproject.toml)
**Changes**: Add asyncpg to dependencies list

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "python-multipart>=0.0.20",
    "asyncpg>=0.29.0",  # Add this line
]
```

**Install**: Run `uv sync` after making this change

#### 2. Implement Safe Parameter Binding
**File**: [backend/app/core/executor.py](backend/app/core/executor.py)
**Changes**: Replace unsafe string substitution with parameterized query preparation

Add new helper method to convert `{variable}` templates to PostgreSQL `$N` placeholders:

```python
def _prepare_parameterized_query(
    self, sql: str, variables: Dict[str, Any]
) -> tuple[str, list[Any]]:
    """
    Convert {variable} templates to $1, $2, ... parameter syntax.

    Args:
        sql: SQL query with {variable_name} templates
        variables: Dictionary mapping variable names to values

    Returns:
        Tuple of (parameterized_sql, parameter_values)

    Raises:
        ValueError: If a template variable is not found in variables dict

    Example:
        sql = "SELECT * FROM users WHERE id = {user_id} AND age > {min_age}"
        variables = {'user_id': 42, 'min_age': 18}

        Returns:
            ("SELECT * FROM users WHERE id = $1 AND age > $2", [42, 18])
    """
    import re

    params: list[Any] = []
    param_counter = 1

    def replace_var(match: re.Match) -> str:
        nonlocal param_counter
        var_name = match.group(1)

        if var_name not in variables:
            raise ValueError(f"Variable '{var_name}' not found in namespace")

        params.append(variables[var_name])
        placeholder = f"${param_counter}"
        param_counter += 1
        return placeholder

    safe_sql = re.sub(r'\{(\w+)\}', replace_var, sql)
    return safe_sql, params
```

#### 3. Add Connection State to SQLExecutor
**File**: [backend/app/core/executor.py](backend/app/core/executor.py)
**Changes**: Add `__init__` method and connection string attribute

Replace the class definition starting at line 100:

```python
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
```

#### 4. Implement Async SQL Execution
**File**: [backend/app/core/executor.py](backend/app/core/executor.py)
**Changes**: Replace stub `execute()` method with real asyncpg implementation

Replace the entire `execute()` method (currently lines 103-144):

```python
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
            records = await conn.fetch(safe_sql, *params)

            if records:
                # Convert asyncpg Records to table format
                columns = list(records[0].keys())
                rows = [list(record.values()) for record in records]

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
```

#### 5. Remove Old Stub Method
**File**: [backend/app/core/executor.py](backend/app/core/executor.py)
**Changes**: Delete `_substitute_variables()` method (lines 133-143)

This method is replaced by `_prepare_parameterized_query()` which is safer.

### Success Criteria

#### Automated Verification
- [ ] Install dependencies: `uv sync`
- [ ] Type checking passes: `uv run mypy backend/app/core/executor.py`
- [ ] Unit test for parameterization: `uv run pytest backend/tests/test_executor.py::test_sql_parameterization -v`

#### Manual Verification
- [ ] SQLExecutor can be instantiated without errors
- [ ] `set_connection_string()` stores connection string
- [ ] `_prepare_parameterized_query()` converts `{user_id}` to `$1` correctly
- [ ] Missing variable raises `ValueError` with clear message

---

## Phase 2: Kernel Message Protocol

### Overview
Define new Pydantic message types for database configuration and add kernel event loop handler. This enables the orchestrator to communicate connection strings to the kernel at runtime.

### Changes Required

#### 1. Define Message Types
**File**: [backend/app/kernel/types.py](backend/app/kernel/types.py)
**Changes**: Add new request/result models after `ShutdownRequest` (after line 55)

```python
class SetDatabaseConfigRequest(BaseModel):
    """Request to configure database connection in kernel."""
    type: Literal["set_database_config"] = "set_database_config"
    connection_string: str


class SetDatabaseConfigResult(BaseModel):
    """Result of database configuration."""
    type: Literal["config_result"] = "config_result"
    status: Literal["success", "error"]
    error: str | None = None
```

**Rationale**: Follows existing pattern of Request/Result pairs with `type` discriminator field

#### 2. Add Kernel Event Loop Handler
**File**: [backend/app/kernel/process.py](backend/app/kernel/process.py)
**Changes**: Add handler for `set_database_config` message type

Insert after the `register_cell` handler (after line 77, before line 79):

```python
    # Handle database configuration
    if request_data.get('type') == 'set_database_config':
        try:
            from .types import SetDatabaseConfigRequest, SetDatabaseConfigResult

            config_req = SetDatabaseConfigRequest(**request_data)

            # Configure SQL executor
            sql_executor.set_connection_string(config_req.connection_string)

            print(f"[Kernel] Database configured: {config_req.connection_string}")

            # Send success result
            result = SetDatabaseConfigResult(status='success')
            output_queue.put(result.model_dump())

        except Exception as e:
            # Send error result
            result = SetDatabaseConfigResult(
                status='error',
                error=str(e)
            )
            output_queue.put(result.model_dump())

        continue
```

**Rationale**: Matches existing handler pattern, returns result to orchestrator for error handling

#### 3. Make SQL Execution Async-Compatible
**File**: [backend/app/kernel/process.py](backend/app/kernel/process.py)
**Changes**: Update SQL execution to handle async executor (line 120)

Replace line 120:

```python
# OLD (line 120):
exec_result = sql_executor.execute(cell_code, python_executor.globals_dict)

# NEW:
import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
exec_result = loop.run_until_complete(
    sql_executor.execute(cell_code, python_executor.globals_dict)
)
loop.close()
```

**Rationale**: Kernel process is synchronous but SQLExecutor.execute() is now async (uses asyncpg)

### Success Criteria

#### Automated Verification
- [ ] Type checking passes: `uv run mypy backend/app/kernel/`
- [ ] Message types serialize correctly: `uv run pytest backend/tests/test_kernel_types.py -v`

#### Manual Verification
- [ ] `SetDatabaseConfigRequest` can be serialized with `.model_dump()`
- [ ] Kernel handler receives and processes message without errors
- [ ] `sql_executor.connection_string` is set after receiving message

---

## Phase 3: Orchestrator Integration

### Overview
Wire up the orchestrator to send database configuration to the kernel when notebooks are loaded or connection strings are updated via the API.

### Changes Required

#### 1. Send Configuration on Notebook Load
**File**: [backend/app/orchestration/coordinator.py](backend/app/orchestration/coordinator.py)
**Changes**: Add database configuration after cell registration in `load_notebook()` method

Add after line 41 (after registering all cells):

```python
        # Configure database if connection string exists
        if self.notebook.db_conn_string:
            await self._configure_database(self.notebook.db_conn_string)
```

#### 2. Implement Database Configuration Helper
**File**: [backend/app/orchestration/coordinator.py](backend/app/orchestration/coordinator.py)
**Changes**: Add new private method for sending config to kernel

Add new method to the `NotebookCoordinator` class:

```python
    async def _configure_database(self, connection_string: str) -> None:
        """
        Send database connection string to kernel.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            RuntimeError: If kernel returns error status
        """
        from ..kernel.types import SetDatabaseConfigRequest, SetDatabaseConfigResult
        import asyncio

        # Send configuration request
        request = SetDatabaseConfigRequest(connection_string=connection_string)
        self.kernel.input_queue.put(request.model_dump())

        # Wait for result
        loop = asyncio.get_event_loop()
        result_data = await loop.run_in_executor(None, self.kernel.output_queue.get)
        result = SetDatabaseConfigResult(**result_data)

        if result.status == 'error':
            raise RuntimeError(f"Failed to configure database: {result.error}")

        print(f"[Coordinator] Database configured successfully")
```

#### 3. Trigger Configuration on API Update
**File**: [backend/app/api/notebooks.py](backend/app/api/notebooks.py)
**Changes**: Notify coordinator when connection string updated via `PUT /db` endpoint

Modify the `update_db_connection` function (lines 47-56):

```python
@router.put("/{notebook_id}/db")
async def update_db_connection(notebook_id: str, request: UpdateDbConnectionRequest):
    """Update database connection string."""
    notebook = NotebookFileStorage.parse_notebook(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Update and persist
    notebook.db_conn_string = request.connection_string
    NotebookFileStorage.serialize_notebook(notebook)

    # ADDED: Notify coordinator to update kernel
    from ..orchestration.coordinator import coordinator_instance
    if coordinator_instance.notebook.id == notebook_id:
        await coordinator_instance._configure_database(request.connection_string)

    return {"status": "ok"}
```

**Note**: This assumes a singleton coordinator pattern. If coordinators are per-websocket, we'll need to broadcast config updates differently (addressed in testing notes).

### Success Criteria

#### Automated Verification
- [ ] Integration test passes: `uv run pytest backend/tests/test_coordinator_kernel_integration.py::test_database_config -v`
- [ ] Type checking passes: `uv run mypy backend/app/orchestration/ backend/app/api/`

#### Manual Verification
- [ ] Create notebook, open WebSocket connection
- [ ] Call `PUT /notebooks/{id}/db` with valid connection string
- [ ] Verify SQL cells can now execute queries
- [ ] Check kernel logs show "[Kernel] Database configured: ..."
- [ ] Verify coordinator logs show "[Coordinator] Database configured successfully"

---

## Phase 4: Testing and Error Handling

### Overview
Add comprehensive tests for SQL execution, parameter binding, and error cases. Ensure graceful handling of connection failures, missing variables, and invalid SQL.

### Changes Required

#### 1. Add SQL Execution Tests
**File**: Create [backend/tests/test_sql_executor_integration.py](backend/tests/test_sql_executor_integration.py)
**Changes**: New test file for SQL executor with real database

```python
"""Integration tests for SQLExecutor with PostgreSQL."""

import pytest
import asyncio
from backend.app.core.executor import SQLExecutor


@pytest.mark.asyncio
async def test_sql_basic_query():
    """Test basic SQL query execution."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://localhost/testdb")

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
    executor.set_connection_string("postgresql://localhost/testdb")

    variables = {'user_id': 42, 'status': 'active'}

    result = await executor.execute(
        "SELECT {user_id} as id, '{status}' as status",
        variables
    )

    assert result.status == 'success'
    data = result.outputs[0].data
    assert data['rows'] == [[42, 'active']]


@pytest.mark.asyncio
async def test_sql_missing_variable():
    """Test error handling for missing template variable."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://localhost/testdb")

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
    executor.set_connection_string("postgresql://localhost/testdb")

    result = await executor.execute("INVALID SQL SYNTAX", {})

    assert result.status == 'error'
    assert 'syntax' in result.error.lower() or 'error' in result.error.lower()


@pytest.mark.asyncio
async def test_sql_connection_failure():
    """Test error handling for connection failures."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://invalid-host:9999/baddb")

    result = await executor.execute("SELECT 1", {})

    assert result.status == 'error'
```

**Note**: These tests require a local PostgreSQL instance running. Add setup instructions in test docstrings.

#### 2. Add Kernel Protocol Tests
**File**: Create [backend/tests/test_kernel_database_protocol.py](backend/tests/test_kernel_database_protocol.py)
**Changes**: New test file for kernel message protocol

```python
"""Tests for database configuration kernel protocol."""

import pytest
from multiprocessing import Queue
from backend.app.kernel.types import SetDatabaseConfigRequest, SetDatabaseConfigResult


def test_database_config_message_serialization():
    """Test SetDatabaseConfigRequest serializes correctly."""
    request = SetDatabaseConfigRequest(
        connection_string="postgresql://localhost/testdb"
    )

    data = request.model_dump()

    assert data['type'] == 'set_database_config'
    assert data['connection_string'] == 'postgresql://localhost/testdb'


def test_database_config_result_serialization():
    """Test SetDatabaseConfigResult serializes correctly."""
    result = SetDatabaseConfigResult(status='success')

    data = result.model_dump()

    assert data['type'] == 'config_result'
    assert data['status'] == 'success'
    assert data['error'] is None


def test_database_config_error_result():
    """Test error result serialization."""
    result = SetDatabaseConfigResult(
        status='error',
        error='Connection failed'
    )

    data = result.model_dump()

    assert data['status'] == 'error'
    assert data['error'] == 'Connection failed'
```

#### 3. Update Existing Tests
**File**: [backend/tests/test_executor.py](backend/tests/test_executor.py)
**Changes**: Update existing SQL tests to use async/await

Modify `test_sql_template_substitution` (line 69):

```python
@pytest.mark.asyncio
async def test_sql_template_substitution():
    """Test SQL template variable substitution."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://localhost/testdb")

    variables = {'user_id': 42}
    result = await executor.execute(
        "SELECT {user_id} as id",
        variables
    )

    assert result.status == 'success'
    assert 'user_id' not in result.stdout  # Template was substituted
    assert '$1' not in result.stdout  # Parameters used internally
```

Modify `test_sql_missing_variable` (line 81):

```python
@pytest.mark.asyncio
async def test_sql_missing_variable():
    """Test error when template variable not found."""
    executor = SQLExecutor()
    executor.set_connection_string("postgresql://localhost/testdb")

    result = await executor.execute(
        "SELECT {unknown_var}",
        {}
    )

    assert result.status == 'error'
    assert 'unknown_var' in result.error
```

#### 4. Add Test Documentation
**File**: Create [backend/tests/README.md](backend/tests/README.md)
**Changes**: Document test requirements and setup

```markdown
# Backend Tests

## Prerequisites

### PostgreSQL Setup
SQL executor tests require a local PostgreSQL instance:

1. Install PostgreSQL (if not installed):
   ```bash
   # macOS
   brew install postgresql@14
   brew services start postgresql@14

   # Ubuntu
   sudo apt install postgresql-14
   sudo systemctl start postgresql
   ```

2. Create test database:
   ```bash
   createdb testdb
   ```

3. Set connection string (optional, tests use default):
   ```bash
   export TEST_DATABASE_URL="postgresql://localhost/testdb"
   ```

## Running Tests

All tests:
```bash
uv run pytest
```

SQL executor tests only:
```bash
uv run pytest backend/tests/test_sql_executor_integration.py -v
```

Skip SQL tests (no database required):
```bash
uv run pytest -m "not integration"
```
```

### Success Criteria

#### Automated Verification
- [ ] All tests pass: `uv run pytest backend/tests/ -v`
- [ ] SQL executor tests pass with real database: `uv run pytest backend/tests/test_sql_executor_integration.py -v`
- [ ] Type checking passes: `uv run mypy backend/`

#### Manual Verification
- [ ] Error messages are clear and actionable
- [ ] Missing variables show which variable is missing
- [ ] Connection errors show connection string (without password)
- [ ] SQL syntax errors show PostgreSQL error message

---

## Testing Strategy

### Unit Tests

**Parameter Binding** ([backend/tests/test_executor.py](backend/tests/test_executor.py)):
- Convert `{var}` to `$1` correctly
- Handle multiple variables in order
- Error on missing variable
- Error on no connection string

**Message Protocol** ([backend/tests/test_kernel_database_protocol.py](backend/tests/test_kernel_database_protocol.py)):
- Request serializes correctly
- Result deserializes correctly
- Error results include error message

### Integration Tests

**SQL Execution** ([backend/tests/test_sql_executor_integration.py](backend/tests/test_sql_executor_integration.py)):
- Basic queries return correct data
- Template substitution works end-to-end
- Connection errors handled gracefully
- Syntax errors reported clearly

**Kernel Communication** ([backend/tests/test_coordinator_kernel_integration.py](backend/tests/test_coordinator_kernel_integration.py)):
- Coordinator can send config to kernel
- Kernel receives and applies config
- SQL executor uses configured connection
- Errors propagate back to coordinator

### Manual Testing Steps

1. **Setup Test Database**:
   ```bash
   createdb testdb
   psql testdb -c "CREATE TABLE users (id INT, name TEXT)"
   psql testdb -c "INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')"
   ```

2. **Start Backend**:
   ```bash
   uv run uvicorn backend.main:app --reload
   ```

3. **Test via API**:
   ```bash
   # Create notebook
   NOTEBOOK_ID=$(curl -X POST http://localhost:8000/api/v1/notebooks/ | jq -r '.notebook_id')

   # Set connection string
   curl -X PUT "http://localhost:8000/api/v1/notebooks/$NOTEBOOK_ID/db" \
     -H "Content-Type: application/json" \
     -d '{"connection_string": "postgresql://localhost/testdb"}'

   # Create Python cell
   CELL1=$(curl -X POST "http://localhost:8000/api/v1/notebooks/$NOTEBOOK_ID/cells" | jq -r '.cell_id')
   curl -X PUT "http://localhost:8000/api/v1/notebooks/$NOTEBOOK_ID/cells/$CELL1" \
     -H "Content-Type: application/json" \
     -d '{"code": "user_id = 1"}'

   # Create SQL cell
   CELL2=$(curl -X POST "http://localhost:8000/api/v1/notebooks/$NOTEBOOK_ID/cells" \
     -H "Content-Type: application/json" \
     -d '{"type": "sql"}' | jq -r '.cell_id')
   curl -X PUT "http://localhost:8000/api/v1/notebooks/$NOTEBOOK_ID/cells/$CELL2" \
     -H "Content-Type: application/json" \
     -d '{"code": "SELECT * FROM users WHERE id = {user_id}"}'
   ```

4. **Test via WebSocket**:
   - Connect to `ws://localhost:8000/api/v1/ws/notebook`
   - Send: `{"type": "authenticate"}`
   - Send: `{"type": "run_cell", "cellId": "<cell2_id>"}`
   - Verify: Receive `cell_output` with `{"type": "table", "columns": ["id", "name"], "rows": [[1, "Alice"]]}`

5. **Test Reactive Update**:
   - Update Cell 1: `user_id = 2`
   - Run Cell 1 via WebSocket
   - Verify: Cell 2 auto-executes and shows `[[2, "Bob"]]`

## Performance Considerations

### Connection Overhead
- Each SQL query creates a new connection (no pooling in v1)
- Typical overhead: 10-50ms per query for local PostgreSQL
- Acceptable for interactive notebook use case
- Future: Add connection pooling if performance becomes an issue

### Query Execution
- No query timeout configured (uses asyncpg default: 60s)
- No result set limits (returns all rows)
- For production: Consider adding `LIMIT` clause or row count warnings

### Memory Usage
- asyncpg Records converted to Python lists (copies data)
- Large result sets (>10k rows) may cause frontend lag
- Out of scope for this plan, but noted for future optimization

## Migration Notes

### Backwards Compatibility
- Existing notebooks without `db_conn_string` continue to work
- SQL cells show clear error: "Database connection not configured"
- No breaking changes to existing API contracts

### Upgrading Notebooks
1. Existing notebooks load normally
2. SQL cells show "not configured" error
3. User sets connection string via `PUT /db` endpoint
4. SQL cells immediately work (kernel reconfigured)

### Rollback Plan
If issues arise after deployment:
1. Revert to stub SQLExecutor (restore old `execute()` method)
2. Remove asyncpg dependency (optional, doesn't break anything)
3. Database configuration messages ignored by kernel (no-op)

## References

- Architecture document: [thoughts/shared/research/2026-01-06-fresh-start-architecture.md](thoughts/shared/research/2026-01-06-fresh-start-architecture.md)
- Task requirements: [the_task.md](the_task.md)
- asyncpg documentation: https://magicstack.github.io/asyncpg/current/
- PostgreSQL parameter binding: https://www.postgresql.org/docs/current/sql-prepare.html
- Similar implementation: Jupyter SQL magic (reference only, not directly applicable)

---

## Implementation Checklist

### Phase 1: Dependencies and Executor Core
- [x] Add asyncpg to pyproject.toml
- [ ] Run `uv sync`
- [x] Add `_prepare_parameterized_query()` method
- [x] Add `__init__` and `set_connection_string()` methods
- [x] Replace `execute()` with async asyncpg implementation
- [x] Remove old `_substitute_variables()` method
- [x] Verify type checking passes
- [ ] Run unit tests

### Phase 2: Kernel Message Protocol
- [x] Add `SetDatabaseConfigRequest` to types.py
- [x] Add `SetDatabaseConfigResult` to types.py
- [x] Add kernel handler in process.py
- [x] Update SQL execution to handle async
- [x] Verify message serialization works
- [ ] Run kernel protocol tests

### Phase 3: Orchestrator Integration
- [x] Add database config call in `load_notebook()`
- [x] Implement `_configure_database()` helper method
- [x] Update API endpoint to notify coordinator
- [ ] Verify integration with logs
- [ ] Run integration tests

### Phase 4: Testing and Error Handling
- [x] Create SQL executor integration tests
- [x] Create kernel protocol tests
- [x] Update existing executor tests
- [x] Add test README with setup instructions
- [ ] Run full test suite
- [ ] Perform manual end-to-end testing
