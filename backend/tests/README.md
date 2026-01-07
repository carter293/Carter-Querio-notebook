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

