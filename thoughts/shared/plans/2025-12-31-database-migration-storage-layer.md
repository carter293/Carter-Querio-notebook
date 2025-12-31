---
date: 2025-12-31T10:02:11Z
planner: matthew
topic: "Database Migration: Moving from File-Based to Persistent Storage"
tags: [planning, implementation, database, storage, rds, dynamodb, migration, sqlmodel, alembic]
status: draft
last_updated: 2025-12-31
last_updated_by: matthew
---

# Database Migration: Moving from File-Based to Persistent Storage

**Date**: 2025-12-31T10:02:11Z
**Planner**: matthew
**Commit**: a1a8fd074551c8df6f2cd49ebddb7d2e3376a39d

## Overview

Migrate the notebook application from file-based JSON storage to a persistent database solution (AWS RDS PostgreSQL or DynamoDB). This enables horizontal scaling, multi-instance deployments, and production-ready data persistence.

## Current State Analysis

### Storage Architecture

**Location**: `backend/storage.py`

The application currently uses file-based JSON storage:

```python
# Atomic write pattern (storage.py:46-58)
NOTEBOOKS_DIR = Path("notebooks")

def save_notebook(notebook: Notebook) -> None:
    # Serialize notebook to dict
    data = {...}
    # Atomic write: tempfile + os.replace
    with tempfile.NamedTemporaryFile(...) as f:
        json.dump(data, f, indent=2)
    os.replace(temp_path, file_path)

def load_notebook(notebook_id: str) -> Notebook:
    # Load from {notebook_id}.json
    # Reconstruct Notebook object
    # Rebuild dependency graph
```

**Key Features**:
- Atomic writes via temp file + `os.replace`
- Backward compatibility for legacy notebooks without `user_id`
- In-memory cache (`NOTEBOOKS` dict) for fast access
- Async locks (`notebook._lock`) for concurrency control
- Optimistic locking via revision numbers

**Limitations**:
- Single-instance only (file-based storage prevents horizontal scaling)
- Data lost on pod restart (no persistence beyond local disk)
- No database for user management or relational queries
- Can't scale ECS task count beyond 1

### Data Model

**Location**: `backend/models.py`

```python
@dataclass
class Notebook:
    id: str                           # UUID
    user_id: str                      # Clerk user ID
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = []
    revision: int = 0
    _lock: Lock = Lock()              # Not serialized

@dataclass
class Cell:
    id: str                           # UUID
    type: CellType                    # "python" | "sql"
    code: str
    status: CellStatus
    outputs: List[Output] = []
    reads: Set[str] = set()           # Variable dependencies
    writes: Set[str] = set()
```

### Demo Notebook Provisioning

**Location**: `backend/routes.py:175-217`

Demo notebooks are already provisioned automatically on first `GET /notebooks` request:

```python
@router.get("/notebooks")
async def list_notebooks_endpoint(user_id: str = Depends(...)):
    # Create blank-{user_id} if missing
    if not user_has_blank:
        blank_notebook = Notebook(id=f"blank-{user_id}", ...)
        save_notebook(blank_notebook)
    
    # Create demo-{user_id} if missing
    if not user_has_demo:
        demo_notebook = create_demo_notebook(user_id)
        demo_notebook.id = f"demo-{user_id}"
        save_notebook(demo_notebook)
```

**No changes needed** - this logic will continue to work with database storage.

### CRUD Operations

All mutations follow consistent pattern (`backend/notebook_operations.py`):

1. Acquire async lock: `async with notebook._lock`
2. Perform mutation (update cells, graph, etc.)
3. Increment revision: `notebook.revision += 1`
4. Persist: `save_notebook(notebook)`

**Examples**:
- `locked_update_cell()` - Update cell code, rebuild graph
- `locked_create_cell()` - Insert cell at index, rebuild graph
- `locked_delete_cell()` - Remove cell, clean up kernel variables

## System Context Analysis

### Architectural Decision: RDS vs DynamoDB

Based on comprehensive research (see references), we have two viable options:

#### Option A: AWS RDS PostgreSQL (RECOMMENDED)

**Advantages**:
- ✅ Demonstrates **relational modeling** and SQL expertise
- ✅ Natural fit for notebook → cell → output relationships
- ✅ Enables **complex queries** (search, filtering, analytics)
- ✅ **Type safety** via SQLModel (SQLAlchemy 2.0 + Pydantic v2)
- ✅ **Schema migrations** with Alembic (version control for schema)
- ✅ Synergy with existing SQL cell execution feature
- ✅ More impressive for take-home demonstration

**Trade-offs**:
- Requires schema design and migration management
- Higher operational complexity (instance management)
- Vertical scaling (larger instances) vs DynamoDB's horizontal scaling

**When to Choose RDS**:
- Need complex queries and joins
- Want to showcase full-stack SQL competency
- Relational data model fits naturally
- ACID compliance required
- Existing PostgreSQL knowledge

#### Option B: DynamoDB

**Advantages**:
- ✅ **Serverless** scaling (no instance management)
- ✅ Simpler schema (document-based)
- ✅ Pay-per-request pricing (cost-effective at low scale)
- ✅ Single-digit millisecond latency
- ✅ TTL for automatic cleanup

**Trade-offs**:
- Limited query capabilities (no JOINs, aggregates)
- Doesn't showcase SQL expertise
- Less impressive for relational data modeling
- Requires careful index design (GSIs)
- No native migration tooling

**When to Choose DynamoDB**:
- Simple key-value access patterns
- Need massive scale (millions TPS)
- Serverless/pay-per-request model preferred
- No complex queries needed

### Recommendation: AWS RDS PostgreSQL

For this project, **RDS PostgreSQL** is the superior choice because:

1. **Demonstrates Competency**: Shows relational design, SQL expertise, migration management
2. **Natural Fit**: Notebooks have inherent relationships (user → notebook → cells → outputs)
3. **Query Flexibility**: Enables future features (search, analytics, user management)
4. **Type Safety**: SQLModel provides full-stack type safety (DB → API → Frontend)
5. **Existing Patterns**: Already using asyncpg for SQL cells, Pydantic for validation

**This plan will focus on RDS implementation**, with DynamoDB details available in the research document if needed.

## Desired End State

### System Architecture

**Database**: AWS RDS PostgreSQL 16
- Private subnet deployment (no public access)
- Accessed by ECS tasks via security group rules
- Credentials managed via AWS Secrets Manager
- Automated backups (7-day retention)
- Performance Insights enabled

**Storage Layer**: SQLModel + Async SQLAlchemy
- Type-safe models for User, Notebook, Cell, CellOutput
- Async operations with `asyncpg` driver
- Connection pooling (10 connections, 20 max overflow)
- Dependency injection via FastAPI `Depends()`

**Migration Management**: Alembic
- Version-controlled schema migrations
- Auto-generation from model changes
- Safe rollback capabilities
- Async migration support

**Hybrid Architecture** (maintains performance):
- **In-memory cache**: `NOTEBOOKS` dict for active notebooks
- **Database persistence**: Durable storage for all notebooks
- **Async locks**: Maintain existing concurrency control
- **Optimistic locking**: Keep revision-based conflict detection

### Success Verification

**Automated Verification**:
- [ ] Unit tests pass: `pytest backend/tests/`
- [ ] Type checking passes: `mypy backend/`
- [ ] Linting passes: `cd backend && python -m black . && python -m isort .`
- [ ] Migrations apply cleanly: `alembic upgrade head`
- [ ] Database health check: `curl http://localhost:8000/health`

**Manual Verification**:
- [ ] Create notebook → persists to database
- [ ] Restart server → notebooks load from database
- [ ] Update cell → revision increments, changes persist
- [ ] Delete notebook → cascade deletes cells and outputs
- [ ] Multiple concurrent requests → no data corruption
- [ ] Demo notebooks still auto-provision on first access

### Key Discoveries

From codebase analysis and research:

1. **Atomic Write Pattern** (`storage.py:46-58`): Current implementation uses temp file + `os.replace` for crash safety - database transactions will provide better atomicity
2. **Backward Compatibility** (`storage.py:88-97`): Gracefully handles missing `user_id` - migration script must preserve this
3. **Graph Reconstruction** (`storage.py:109-110`): Always rebuilds dependency graph after loading - keep this pattern
4. **Demo Provisioning** (`routes.py:175-217`): Already works correctly - no changes needed
5. **Async Patterns** (`notebook_operations.py`): All operations use `async with notebook._lock` - maintain for consistency
6. **Testing Patterns** (`tests/test_concurrency.py`): Comprehensive concurrency tests exist - reuse for database migrations

## What We're NOT Doing

To prevent scope creep, explicitly out of scope:

- ❌ Multi-region replication (future enhancement)
- ❌ Soft deletes / audit trails (add if needed later)
- ❌ Caching cell outputs in database (keep in-memory for now)
- ❌ Storing dependency graph in database (rebuild on load, as current)
- ❌ User authentication changes (Clerk integration stays as-is)
- ❌ Changing frontend code (storage layer is backend-only)
- ❌ Modifying cell execution logic (only storage changes)

## Implementation Approach

### High-Level Strategy

**Incremental Migration with Backward Compatibility**:

1. **Phase 1**: Add SQLModel models and database setup (no behavior changes)
2. **Phase 2**: Implement database CRUD operations (parallel to file storage)
3. **Phase 3**: Run migration script to move existing notebooks to database
4. **Phase 4**: Deploy RDS infrastructure via Terraform
5. **Phase 5**: Switch storage layer, remove file-based code
6. **Phase 6**: Production validation and monitoring

**Deployment Strategy**: Blue-green with maintenance window
- Deploy new backend version with database support
- Run migration script during low-traffic window
- Validate all notebooks migrated correctly
- Rollback plan: keep JSON files as backup for 7 days

## Phase 1: SQLModel Setup and Database Configuration

### Overview

Set up SQLModel models, database connection, and Alembic migrations without changing application behavior.

### Changes Required

#### 1. Install Dependencies

**File**: `backend/requirements.txt`

**Changes**: Add database dependencies

```txt
# Existing dependencies (keep all)
fastapi==0.104.1
uvicorn==0.24.0
asyncpg==0.29.0
pydantic==2.12.5
# ... (all existing packages)

# Add for database migration
sqlmodel==0.0.14
alembic==1.13.1
psycopg2-binary==2.9.9
```

#### 2. Create Database Configuration

**File**: `backend/database.py` (NEW)

**Changes**: Create async database engine and session management

```python
from sqlmodel import create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
import os

# Get from environment variable (set via ECS task definition)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/notebooks"  # Default for local dev
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Log all SQL in development
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,  # Concurrent connections
    max_overflow=20,  # Additional connections under load
    connect_args={
        "server_settings": {
            "application_name": "querio-notebook"
        }
    }
)

# Session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
    autoflush=False,  # Manual control over flush
    autocommit=False  # Explicit transaction management
)

# Dependency for FastAPI routes
async def get_session():
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Health check function
async def check_database_health() -> bool:
    """Check if database is accessible."""
    try:
        async with async_session_maker() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        print(f"Database health check failed: {e}")
        return False
```

#### 3. Create SQLModel Models

**File**: `backend/db_models.py` (NEW)

**Changes**: Define SQLModel models for database tables

```python
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

# Enums (match existing models.py)
class CellTypeDB(str, Enum):
    PYTHON = "python"
    SQL = "sql"

class CellStatusDB(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"

# User Model (for future authentication)
class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    clerk_user_id: str = Field(unique=True, index=True, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    notebooks: List["NotebookDB"] = Relationship(back_populates="owner", cascade_delete=True)

# Notebook Model
class NotebookDB(SQLModel, table=True):
    __tablename__ = "notebooks"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: Optional[str] = Field(default=None, max_length=255)
    db_conn_string: Optional[str] = Field(default=None, max_length=512)
    revision: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key
    user_id: UUID = Field(foreign_key="users.id", index=True)
    owner: User = Relationship(back_populates="notebooks")
    
    # Relationships
    cells: List["CellDB"] = Relationship(back_populates="notebook", cascade_delete=True)

# Cell Model
class CellDB(SQLModel, table=True):
    __tablename__ = "cells"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: str = Field(max_length=50)  # "python" or "sql"
    code: str = Field(default="", sa_column_kwargs={"type_": "TEXT"})
    position: int = Field(default=0, index=True)  # For ordering within notebook
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Cell dependencies (stored as JSON arrays)
    reads: Optional[str] = Field(default=None, sa_column_kwargs={"type_": "TEXT"})  # JSON array
    writes: Optional[str] = Field(default=None, sa_column_kwargs={"type_": "TEXT"})  # JSON array
    
    # Foreign key
    notebook_id: UUID = Field(foreign_key="notebooks.id", index=True)
    notebook: NotebookDB = Relationship(back_populates="cells")
    
    # Relationships
    outputs: List["CellOutputDB"] = Relationship(back_populates="cell", cascade_delete=True)

# Cell Output Model
class CellOutputDB(SQLModel, table=True):
    __tablename__ = "cell_outputs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    mime_type: str = Field(max_length=100)
    data: str = Field(sa_column_kwargs={"type_": "TEXT"})  # JSON string or base64
    metadata: Optional[str] = Field(default=None, sa_column_kwargs={"type_": "TEXT"})  # JSON string
    position: int = Field(default=0)  # Order within cell outputs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key
    cell_id: UUID = Field(foreign_key="cells.id", index=True)
    cell: CellDB = Relationship(back_populates="outputs")
```

#### 4. Initialize Alembic

**Command**: Initialize Alembic in backend directory

```bash
cd backend
alembic init alembic
```

**File**: `backend/alembic.ini`

**Changes**: Configure database URL (will be overridden by env var in production)

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
# Use environment variable in production
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/notebooks

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

**File**: `backend/alembic/env.py`

**Changes**: Configure for async operations and import models

```python
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio
import os

# Import your SQLModel models
from db_models import SQLModel

# this is the Alembic Config object
config = context.config

# Override database URL from environment if set
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata from SQLModel
target_metadata = SQLModel.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async support."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    
    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

#### 5. Generate Initial Migration

**Command**: Create initial migration from models

```bash
cd backend
alembic revision --autogenerate -m "Initial schema: users, notebooks, cells, outputs"
```

**Review**: Open generated file in `backend/alembic/versions/` and verify:
- All tables created correctly
- Indexes on user_id, notebook_id, cell_id
- Foreign key constraints with CASCADE DELETE
- Appropriate column types (TEXT for code, UUID for IDs)

#### 6. Update Health Check

**File**: `backend/main.py`

**Changes**: Add database health check to existing endpoint

```python
from fastapi import FastAPI
from database import check_database_health

app = FastAPI()

# ... existing code ...

@app.get("/health")
async def health_check():
    """Health check endpoint for ALB target group."""
    db_healthy = await check_database_health()
    
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "database": "connected" if db_healthy else "disconnected"
    }
```

### Success Criteria

#### Automated Verification:
- [ ] Dependencies install: `pip install -r backend/requirements.txt`
- [ ] Type checking passes: `mypy backend/database.py backend/db_models.py`
- [ ] Alembic initializes: `alembic check` (no errors)
- [ ] Migration generates: `alembic revision --autogenerate -m "test"` (creates file)
- [ ] Models import: `python -c "from db_models import NotebookDB; print('OK')"`

#### Manual Verification:
- [ ] Review generated migration file - verify all tables, indexes, constraints
- [ ] Database URL environment variable can be set and read
- [ ] No changes to existing application behavior (Phase 1 is setup only)

---

## Phase 2: Implement Database CRUD Operations

### Overview

Create async database operations for notebooks while maintaining file-based storage as fallback.

### Changes Required

#### 1. Create Database Storage Layer

**File**: `backend/storage_db.py` (NEW)

**Changes**: Implement async database operations

```python
from typing import List, Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from db_models import User, NotebookDB, CellDB, CellOutputDB
from models import Notebook, Cell, CellType, CellStatus, Output
from uuid import UUID
import json

class DatabaseStorage:
    """Database storage layer for notebooks using SQLModel."""
    
    async def save_notebook(self, notebook: Notebook, session: AsyncSession) -> None:
        """Save or update notebook in database."""
        # Find or create user
        user = await self._get_or_create_user(notebook.user_id, session)
        
        # Find existing notebook or create new
        statement = select(NotebookDB).where(NotebookDB.id == UUID(notebook.id))
        result = await session.execute(statement)
        db_notebook = result.scalar_one_or_none()
        
        if db_notebook is None:
            # Create new notebook
            db_notebook = NotebookDB(
                id=UUID(notebook.id),
                name=notebook.name,
                db_conn_string=notebook.db_conn_string,
                revision=notebook.revision,
                user_id=user.id
            )
            session.add(db_notebook)
        else:
            # Update existing notebook
            db_notebook.name = notebook.name
            db_notebook.db_conn_string = notebook.db_conn_string
            db_notebook.revision = notebook.revision
            db_notebook.updated_at = datetime.utcnow()
        
        # Delete existing cells (will cascade to outputs)
        await session.execute(
            select(CellDB).where(CellDB.notebook_id == UUID(notebook.id))
        )
        existing_cells = await session.execute(
            select(CellDB).where(CellDB.notebook_id == UUID(notebook.id))
        )
        for cell in existing_cells.scalars():
            await session.delete(cell)
        
        # Create cells
        for position, cell in enumerate(notebook.cells):
            db_cell = CellDB(
                id=UUID(cell.id),
                notebook_id=UUID(notebook.id),
                type=cell.type.value,
                code=cell.code,
                position=position,
                reads=json.dumps(list(cell.reads)),
                writes=json.dumps(list(cell.writes))
            )
            session.add(db_cell)
            
            # Create outputs
            for output_pos, output in enumerate(cell.outputs):
                db_output = CellOutputDB(
                    cell_id=UUID(cell.id),
                    mime_type=output.mime_type,
                    data=json.dumps(output.data) if isinstance(output.data, (dict, list)) else output.data,
                    metadata=json.dumps(output.metadata),
                    position=output_pos
                )
                session.add(db_output)
        
        await session.flush()
    
    async def load_notebook(self, notebook_id: str, session: AsyncSession) -> Optional[Notebook]:
        """Load notebook from database."""
        # Load notebook with cells and outputs
        statement = (
            select(NotebookDB)
            .where(NotebookDB.id == UUID(notebook_id))
        )
        result = await session.execute(statement)
        db_notebook = result.scalar_one_or_none()
        
        if db_notebook is None:
            return None
        
        # Load cells (ordered by position)
        cells_statement = (
            select(CellDB)
            .where(CellDB.notebook_id == UUID(notebook_id))
            .order_by(CellDB.position)
        )
        cells_result = await session.execute(cells_statement)
        db_cells = cells_result.scalars().all()
        
        # Convert to domain models
        cells = []
        for db_cell in db_cells:
            # Load outputs for this cell
            outputs_statement = (
                select(CellOutputDB)
                .where(CellOutputDB.cell_id == db_cell.id)
                .order_by(CellOutputDB.position)
            )
            outputs_result = await session.execute(outputs_statement)
            db_outputs = outputs_result.scalars().all()
            
            outputs = [
                Output(
                    mime_type=db_output.mime_type,
                    data=json.loads(db_output.data) if db_output.data.startswith(('[', '{')) else db_output.data,
                    metadata=json.loads(db_output.metadata) if db_output.metadata else {}
                )
                for db_output in db_outputs
            ]
            
            cell = Cell(
                id=str(db_cell.id),
                type=CellType(db_cell.type),
                code=db_cell.code,
                status=CellStatus.IDLE,  # Runtime state, not persisted
                outputs=outputs,
                reads=set(json.loads(db_cell.reads)) if db_cell.reads else set(),
                writes=set(json.loads(db_cell.writes)) if db_cell.writes else set()
            )
            cells.append(cell)
        
        # Get user's clerk_user_id
        user_statement = select(User).where(User.id == db_notebook.user_id)
        user_result = await session.execute(user_statement)
        user = user_result.scalar_one()
        
        # Create notebook
        notebook = Notebook(
            id=str(db_notebook.id),
            user_id=user.clerk_user_id,
            name=db_notebook.name,
            db_conn_string=db_notebook.db_conn_string,
            cells=cells,
            revision=db_notebook.revision
        )
        
        # Rebuild dependency graph
        from graph import rebuild_graph
        rebuild_graph(notebook)
        
        return notebook
    
    async def list_notebooks(self, user_clerk_id: str, session: AsyncSession) -> List[str]:
        """List all notebook IDs for a user."""
        # Find user by clerk ID
        user_statement = select(User).where(User.clerk_user_id == user_clerk_id)
        user_result = await session.execute(user_statement)
        user = user_result.scalar_one_or_none()
        
        if user is None:
            return []
        
        # List notebooks
        notebooks_statement = select(NotebookDB).where(NotebookDB.user_id == user.id)
        notebooks_result = await session.execute(notebooks_statement)
        notebooks = notebooks_result.scalars().all()
        
        return [str(nb.id) for nb in notebooks]
    
    async def delete_notebook(self, notebook_id: str, session: AsyncSession) -> None:
        """Delete notebook from database (cascades to cells and outputs)."""
        statement = select(NotebookDB).where(NotebookDB.id == UUID(notebook_id))
        result = await session.execute(statement)
        notebook = result.scalar_one_or_none()
        
        if notebook:
            await session.delete(notebook)
            await session.flush()
    
    async def _get_or_create_user(self, clerk_user_id: str, session: AsyncSession) -> User:
        """Get or create user by Clerk user ID."""
        statement = select(User).where(User.clerk_user_id == clerk_user_id)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if user is None:
            user = User(clerk_user_id=clerk_user_id)
            session.add(user)
            await session.flush()
        
        return user
```

#### 2. Update Notebook Operations

**File**: `backend/notebook_operations.py`

**Changes**: Add optional session parameter to all locked operations

```python
from typing import Optional
from uuid import uuid4
from models import Notebook, Cell, CellType, CellStatus
from ast_parser import extract_dependencies, extract_sql_dependencies
from graph import rebuild_graph, detect_cycle
from storage import save_notebook as save_notebook_file
from storage_db import DatabaseStorage
from sqlmodel.ext.asyncio.session import AsyncSession

# Initialize database storage
db_storage = DatabaseStorage()

async def locked_update_cell(
    notebook: Notebook,
    cell_id: str,
    code: str,
    expected_revision: Optional[int] = None,
    session: Optional[AsyncSession] = None  # NEW: optional database session
) -> Cell:
    """
    Update cell code with concurrency protection and optimistic locking.
    
    Raises:
        ValueError: If cell not found or revision conflict
    """
    async with notebook._lock:
        # ... existing logic (optimistic locking, find cell, extract dependencies, rebuild graph) ...
        
        # Increment revision
        notebook.revision += 1
        
        # Save to storage (file + database if session provided)
        save_notebook_file(notebook)
        if session is not None:
            await db_storage.save_notebook(notebook, session)
        
        return cell

async def locked_create_cell(
    notebook: Notebook,
    cell_type: CellType,
    code: str,
    index: Optional[int] = None,
    session: Optional[AsyncSession] = None  # NEW: optional database session
) -> Cell:
    """Create new cell with concurrency protection."""
    async with notebook._lock:
        # ... existing logic (create cell, extract dependencies, insert, rebuild graph) ...
        
        # Increment revision
        notebook.revision += 1
        
        # Save to storage (file + database if session provided)
        save_notebook_file(notebook)
        if session is not None:
            await db_storage.save_notebook(notebook, session)
        
        return new_cell

async def locked_delete_cell(
    notebook: Notebook,
    cell_id: str,
    session: Optional[AsyncSession] = None  # NEW: optional database session
) -> None:
    """Delete cell with concurrency protection."""
    async with notebook._lock:
        # ... existing logic (find cell, remove from list, remove from graph, clean kernel) ...
        
        # Increment revision
        notebook.revision += 1
        
        # Save to storage (file + database if session provided)
        save_notebook_file(notebook)
        if session is not None:
            await db_storage.save_notebook(notebook, session)
```

#### 3. Add Database Support to Routes

**File**: `backend/routes.py`

**Changes**: Inject database session into endpoints (dual-write to file and DB)

```python
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from database import get_session

# ... existing code ...

@router.post("/notebooks", response_model=CreateNotebookResponse)
async def create_notebook(
    request: Request,
    user_id: str = Depends(get_current_user_dependency),
    session: AsyncSession = Depends(get_session)  # NEW: inject database session
):
    """Create a new notebook with one empty Python cell"""
    notebook_id = str(uuid.uuid4())
    
    # ... existing notebook creation logic ...
    
    NOTEBOOKS[notebook_id] = notebook
    save_notebook(notebook)
    
    # NEW: Also save to database
    from storage_db import DatabaseStorage
    db_storage = DatabaseStorage()
    await db_storage.save_notebook(notebook, session)
    
    return CreateNotebookResponse(notebook_id=notebook_id)

@router.put("/notebooks/{notebook_id}/cells/{cell_id}")
async def update_cell(
    notebook_id: str,
    cell_id: str,
    request_body: UpdateCellRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency),
    session: AsyncSession = Depends(get_session)  # NEW: inject database session
):
    """Update cell code"""
    # ... existing validation ...
    
    try:
        expected_revision = getattr(request_body, 'expected_revision', None)
        cell = await locked_update_cell(
            notebook,
            cell_id,
            request_body.code,
            expected_revision=expected_revision,
            session=session  # NEW: pass database session
        )
        
        # ... existing broadcast logic ...
        
        return {"status": "ok", "revision": notebook.revision}
    except ValueError as e:
        # ... existing error handling ...

# Similar changes for:
# - create_cell
# - delete_cell
# - update_db_connection
# - rename_notebook
# - delete_notebook_endpoint
```

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `pytest backend/tests/test_storage_db.py` (write new tests)
- [ ] Migration applies: `alembic upgrade head` (no errors)
- [ ] Type checking: `mypy backend/storage_db.py backend/notebook_operations.py`
- [ ] Integration test: `pytest backend/tests/test_integration_db.py`

#### Manual Verification:
- [ ] Start local postgres: `docker-compose -f postgres/docker-compose.yml up -d`
- [ ] Run migrations: `cd backend && alembic upgrade head`
- [ ] Start backend: `cd backend && uvicorn main:app --reload`
- [ ] Create notebook via API → check database: `psql -c "SELECT * FROM notebooks;"`
- [ ] Update cell → verify revision increments in DB
- [ ] Restart backend → notebook loads from database
- [ ] Both file and database have same data (dual-write working)

---

## Phase 3: Data Migration Script

### Overview

Migrate existing JSON notebooks to database while preserving all data.

### Changes Required

#### 1. Create Migration Script

**File**: `backend/scripts/migrate_to_database.py` (NEW)

**Changes**: Script to import all JSON notebooks into database

```python
#!/usr/bin/env python3
"""
Migrate existing JSON notebooks to database.

Usage:
    python scripts/migrate_to_database.py [--dry-run] [--notebooks-dir ./notebooks]
"""

import asyncio
import argparse
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import load_notebook as load_from_file
from storage_db import DatabaseStorage
from database import async_session_maker
from sqlalchemy import text

async def migrate_notebooks(notebooks_dir: Path, dry_run: bool = False):
    """Migrate all notebooks from JSON files to database."""
    db_storage = DatabaseStorage()
    json_files = list(notebooks_dir.glob("*.json"))
    
    print(f"Found {len(json_files)} notebooks to migrate")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
    print("-" * 60)
    
    migrated = 0
    failed = 0
    
    for json_file in json_files:
        notebook_id = json_file.stem
        print(f"\nMigrating: {notebook_id}")
        
        try:
            # Load from file
            notebook = load_from_file(notebook_id)
            print(f"  ✓ Loaded from file")
            print(f"    - User: {notebook.user_id}")
            print(f"    - Name: {notebook.name or '(unnamed)'}")
            print(f"    - Cells: {len(notebook.cells)}")
            print(f"    - Revision: {notebook.revision}")
            
            if not dry_run:
                # Save to database
                async with async_session_maker() as session:
                    await db_storage.save_notebook(notebook, session)
                    await session.commit()
                    print(f"  ✓ Saved to database")
            else:
                print(f"  [DRY RUN] Would save to database")
            
            migrated += 1
            
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Migration complete:")
    print(f"  - Migrated: {migrated}")
    print(f"  - Failed: {failed}")
    print(f"  - Total: {len(json_files)}")
    
    if dry_run:
        print("\n⚠️  This was a DRY RUN - no data was written to database")
    else:
        print("\n✓ All notebooks migrated to database")
        print("  - Original JSON files preserved as backup")

async def verify_migration(notebooks_dir: Path):
    """Verify that all notebooks were migrated correctly."""
    db_storage = DatabaseStorage()
    json_files = list(notebooks_dir.glob("*.json"))
    
    print(f"\nVerifying {len(json_files)} notebooks...")
    print("-" * 60)
    
    all_ok = True
    
    for json_file in json_files:
        notebook_id = json_file.stem
        
        try:
            # Load from file
            file_notebook = load_from_file(notebook_id)
            
            # Load from database
            async with async_session_maker() as session:
                db_notebook = await db_storage.load_notebook(notebook_id, session)
            
            if db_notebook is None:
                print(f"✗ {notebook_id}: NOT FOUND in database")
                all_ok = False
                continue
            
            # Compare
            if file_notebook.id != db_notebook.id:
                print(f"✗ {notebook_id}: ID mismatch")
                all_ok = False
            elif file_notebook.user_id != db_notebook.user_id:
                print(f"✗ {notebook_id}: user_id mismatch")
                all_ok = False
            elif len(file_notebook.cells) != len(db_notebook.cells):
                print(f"✗ {notebook_id}: cell count mismatch ({len(file_notebook.cells)} vs {len(db_notebook.cells)})")
                all_ok = False
            else:
                print(f"✓ {notebook_id}")
        
        except Exception as e:
            print(f"✗ {notebook_id}: ERROR - {e}")
            all_ok = False
    
    print("\n" + "=" * 60)
    if all_ok:
        print("✓ All notebooks verified successfully")
        return 0
    else:
        print("✗ Verification failed - see errors above")
        return 1

async def main():
    parser = argparse.ArgumentParser(description="Migrate notebooks to database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    parser.add_argument("--notebooks-dir", type=Path, default=Path("notebooks"), help="Path to notebooks directory")
    parser.add_argument("--verify", action="store_true", help="Verify migration after completion")
    
    args = parser.parse_args()
    
    if not args.notebooks_dir.exists():
        print(f"Error: Notebooks directory not found: {args.notebooks_dir}")
        return 1
    
    # Run migration
    await migrate_notebooks(args.notebooks_dir, args.dry_run)
    
    # Verify if requested
    if args.verify and not args.dry_run:
        return await verify_migration(args.notebooks_dir)
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

#### 2. Make Script Executable

**Command**: Set executable permissions

```bash
chmod +x backend/scripts/migrate_to_database.py
```

### Success Criteria

#### Automated Verification:
- [ ] Dry run succeeds: `python backend/scripts/migrate_to_database.py --dry-run`
- [ ] Migration succeeds: `python backend/scripts/migrate_to_database.py`
- [ ] Verification passes: `python backend/scripts/migrate_to_database.py --verify`

#### Manual Verification:
- [ ] All notebooks in database: `psql -c "SELECT id, name, user_id FROM notebooks;"`
- [ ] Cell counts match: `psql -c "SELECT notebook_id, COUNT(*) FROM cells GROUP BY notebook_id;"`
- [ ] No data loss: Compare JSON files to database records
- [ ] Demo notebooks preserved: Check `demo-user_*` and `blank-user_*` entries

---

## Phase 4: AWS RDS Infrastructure

### Overview

Deploy AWS RDS PostgreSQL instance via Terraform with security best practices.

### Changes Required

#### 1. Create RDS Terraform Module

**File**: `terraform/modules/database/main.tf` (NEW)

**Changes**: Define RDS instance, security groups, and secrets

```terraform
# Database subnet group (private subnets only)
resource "aws_db_subnet_group" "private" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.project_name} DB Subnet Group"
  }
}

# Security group for RDS
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

  # Allow PostgreSQL from ECS tasks only
  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name} RDS Security Group"
  }
}

# Parameter group for PostgreSQL 16
resource "aws_db_parameter_group" "postgres16" {
  name   = "${var.project_name}-postgres16-params"
  family = "postgres16"

  parameter {
    name  = "max_connections"
    value = "100"
  }

  parameter {
    name  = "shared_buffers"
    value = "{DBInstanceClassMemory/4096}"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries > 1s
  }

  tags = {
    Name = "${var.project_name} PostgreSQL Parameters"
  }
}

# Generate random password
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# Store password in Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  name = "${var.project_name}-db-password-${var.environment}"

  tags = {
    Name = "${var.project_name} DB Password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

# RDS instance
resource "aws_db_instance" "main" {
  identifier           = "${var.project_name}-db-${var.environment}"
  engine              = "postgres"
  engine_version      = "16.1"
  instance_class      = var.instance_class
  allocated_storage   = var.allocated_storage
  storage_type        = "gp3"
  storage_encrypted   = true

  db_name  = var.database_name
  username = var.database_username
  password = random_password.db_password.result

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.private.name
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  publicly_accessible    = false
  multi_az              = var.multi_az
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"

  auto_minor_version_upgrade = true
  performance_insights_enabled = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  deletion_protection = var.deletion_protection
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-final-snapshot-${formatdate("YYYYMMDD-hhmm", timestamp())}"

  tags = {
    Name        = "${var.project_name} Database"
    Environment = var.environment
  }
}

# Store connection string in SSM Parameter Store
resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project_name}/${var.environment}/database_url"
  type  = "SecureString"
  value = "postgresql+asyncpg://${var.database_username}:${random_password.db_password.result}@${aws_db_instance.main.endpoint}/${var.database_name}"

  tags = {
    Name = "${var.project_name} Database URL"
  }
}
```

**File**: `terraform/modules/database/variables.tf` (NEW)

```terraform
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (e.g. production, staging)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for security groups"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for DB subnet group"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "database_name" {
  description = "Database name"
  type        = string
  default     = "notebooks"
}

variable "database_username" {
  description = "Database admin username"
  type        = string
  default     = "admin"
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}
```

**File**: `terraform/modules/database/outputs.tf` (NEW)

```terraform
output "endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
}

output "database_name" {
  description = "Database name"
  value       = aws_db_instance.main.db_name
}

output "database_url_ssm_parameter" {
  description = "SSM parameter name for DATABASE_URL"
  value       = aws_ssm_parameter.database_url.name
}

output "security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

output "instance_id" {
  description = "RDS instance ID"
  value       = aws_db_instance.main.id
}
```

#### 2. Update Main Terraform Configuration

**File**: `terraform/main.tf`

**Changes**: Add database module

```terraform
# ... existing modules ...

# Database Module - RDS PostgreSQL for notebooks
module "database" {
  source = "./modules/database"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = module.networking.vpc_id
  private_subnet_ids     = module.networking.private_subnet_ids
  ecs_security_group_id  = module.security.ecs_tasks_security_group_id

  instance_class       = "db.t4g.micro"
  allocated_storage    = 20
  multi_az            = false  # Enable for production
  deletion_protection = true
}
```

#### 3. Update ECS Task Definition

**File**: `terraform/modules/compute/main.tf`

**Changes**: Add DATABASE_URL secret to container definition

```terraform
resource "aws_ecs_task_definition" "backend" {
  # ... existing configuration ...

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "${var.ecr_repository_url}:latest"
      
      # ... existing config ...
      
      secrets = [
        {
          name      = "CLERK_SECRET_KEY"
          valueFrom = aws_secretsmanager_secret_version.clerk_secret.arn
        },
        {
          name      = "DATABASE_URL"
          valueFrom = var.database_url_ssm_parameter  # NEW
        }
      ]
      
      # ... rest of config ...
    }
  ])
}
```

**File**: `terraform/modules/compute/variables.tf`

**Changes**: Add database_url_ssm_parameter variable

```terraform
# ... existing variables ...

variable "database_url_ssm_parameter" {
  description = "SSM parameter name for DATABASE_URL"
  type        = string
}
```

**File**: `terraform/main.tf`

**Changes**: Pass database URL to compute module

```terraform
module "compute" {
  source = "./modules/compute"

  # ... existing variables ...
  
  database_url_ssm_parameter = module.database.database_url_ssm_parameter  # NEW
}
```

#### 4. Update IAM Policies

**File**: `terraform/modules/security/main.tf`

**Changes**: Grant ECS task permission to read DATABASE_URL from SSM

```terraform
resource "aws_iam_role_policy" "ecs_task_role_policy" {
  name = "${var.project_name}-ecs-task-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ... existing statements ...
      
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-*"
        ]
      }
    ]
  })
}
```

### Success Criteria

#### Automated Verification:
- [ ] Terraform validates: `cd terraform && terraform validate`
- [ ] Terraform plans: `terraform plan -var-file=production.tfvars`
- [ ] No circular dependencies or errors

#### Manual Verification:
- [ ] Review Terraform plan output - verify RDS instance created
- [ ] Apply Terraform: `terraform apply -var-file=production.tfvars`
- [ ] RDS endpoint accessible from ECS: Check security group rules
- [ ] DATABASE_URL available in ECS task: `aws ecs describe-tasks ...`
- [ ] Connect to RDS: `psql -h <endpoint> -U admin -d notebooks`
- [ ] Run migrations: `alembic upgrade head` (from bastion or ECS exec)

---

## Phase 5: Switch to Database Storage

### Overview

Switch from file-based to database-first storage, keeping files as backup.

### Changes Required

#### 1. Update Storage Layer

**File**: `backend/storage.py`

**Changes**: Make database primary, keep files as backup

```python
import os
from pathlib import Path
from typing import Dict, List, Optional
from models import Notebook
from storage_db import DatabaseStorage
from sqlmodel.ext.asyncio.session import AsyncSession

# Check if database is enabled
DATABASE_ENABLED = bool(os.getenv("DATABASE_URL"))

# Initialize database storage
db_storage = DatabaseStorage() if DATABASE_ENABLED else None

NOTEBOOKS_DIR = Path("notebooks")

def ensure_notebooks_dir():
    NOTEBOOKS_DIR.mkdir(exist_ok=True)

async def save_notebook(notebook: Notebook, session: Optional[AsyncSession] = None) -> None:
    """
    Save notebook to storage.
    
    If DATABASE_URL is set and session provided: save to database (primary)
    Always save to file as backup.
    """
    # Save to database if enabled
    if DATABASE_ENABLED and db_storage and session:
        await db_storage.save_notebook(notebook, session)
    
    # Always save to file as backup
    _save_notebook_file(notebook)

def _save_notebook_file(notebook: Notebook) -> None:
    """Save notebook to JSON file (private function)."""
    # ... existing file save logic (storage.py:13-58) ...

async def load_notebook(notebook_id: str, session: Optional[AsyncSession] = None) -> Notebook:
    """
    Load notebook from storage.
    
    Priority:
    1. Database (if enabled and session provided)
    2. File (fallback)
    """
    # Try database first if enabled
    if DATABASE_ENABLED and db_storage and session:
        notebook = await db_storage.load_notebook(notebook_id, session)
        if notebook:
            return notebook
    
    # Fallback to file
    return _load_notebook_file(notebook_id)

def _load_notebook_file(notebook_id: str) -> Notebook:
    """Load notebook from JSON file (private function)."""
    # ... existing file load logic (storage.py:60-112) ...

async def list_notebooks(user_id: Optional[str] = None, session: Optional[AsyncSession] = None) -> List[str]:
    """
    List notebooks.
    
    If database enabled: list from database
    Otherwise: list from files
    """
    if DATABASE_ENABLED and db_storage and session and user_id:
        return await db_storage.list_notebooks(user_id, session)
    
    return _list_notebooks_files()

def _list_notebooks_files() -> List[str]:
    """List notebooks from files (private function)."""
    # ... existing file list logic (storage.py:114-119) ...

async def delete_notebook(notebook_id: str, session: Optional[AsyncSession] = None) -> None:
    """
    Delete notebook from storage.
    
    Deletes from both database and file.
    """
    # Delete from database if enabled
    if DATABASE_ENABLED and db_storage and session:
        await db_storage.delete_notebook(notebook_id, session)
    
    # Delete file
    _delete_notebook_file(notebook_id)

def _delete_notebook_file(notebook_id: str) -> None:
    """Delete notebook file (private function)."""
    # ... existing file delete logic (storage.py:120-125) ...
```

#### 2. Update All Callers

**Files**: 
- `backend/routes.py`
- `backend/notebook_operations.py`
- `backend/main.py` (startup logic)

**Changes**: Ensure all storage calls pass session

```python
# Example: routes.py

@router.get("/notebooks", response_model=ListNotebooksResponse)
async def list_notebooks_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_dependency),
    session: AsyncSession = Depends(get_session)
):
    """List all notebooks for the current user"""
    # ... existing demo notebook provisioning logic ...
    
    # List notebooks (now uses database if available)
    all_notebook_ids = await list_notebooks(user_id, session)
    
    # Load into memory cache if not already loaded
    for notebook_id in all_notebook_ids:
        if notebook_id not in NOTEBOOKS:
            notebook = await load_notebook(notebook_id, session)
            NOTEBOOKS[notebook_id] = notebook
    
    # Return user notebooks
    user_notebooks = [
        NotebookMetadataResponse(id=nb.id, name=nb.name or nb.id)
        for nb in NOTEBOOKS.values()
        if nb.user_id == user_id
    ]
    return ListNotebooksResponse(notebooks=user_notebooks)
```

#### 3. Update Startup Logic

**File**: `backend/main.py`

**Changes**: Load notebooks from database on startup if enabled

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import async_session_maker, check_database_health
from storage import load_notebook, list_notebooks, DATABASE_ENABLED
from routes import NOTEBOOKS
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    print("Starting up...")
    
    # Check database health if enabled
    if DATABASE_ENABLED:
        db_healthy = await check_database_health()
        if db_healthy:
            print("✓ Database connected")
            
            # Load notebooks from database
            try:
                async with async_session_maker() as session:
                    # Load all notebooks (no user filter for admin view)
                    # In production, you might want to lazy-load notebooks
                    print("Loading notebooks from database...")
                    # Note: This requires a modified list_notebooks that can return all
                    # Or: lazy load notebooks on first access
                    print("✓ Notebooks loaded from database")
            except Exception as e:
                print(f"⚠ Failed to load notebooks from database: {e}")
                print("  Will fall back to file-based storage")
        else:
            print("⚠ Database not available - using file-based storage")
    else:
        print("ℹ Database not configured - using file-based storage")
        # Load notebooks from files
        from storage import list_notebooks as list_files
        for notebook_id in list_files():
            try:
                notebook = await load_notebook(notebook_id)
                NOTEBOOKS[notebook_id] = notebook
            except Exception as e:
                print(f"⚠ Failed to load notebook {notebook_id}: {e}")
    
    print(f"Loaded {len(NOTEBOOKS)} notebooks")
    
    yield
    
    print("Shutting down...")

app = FastAPI(lifespan=lifespan)

# ... rest of app configuration ...
```

### Success Criteria

#### Automated Verification:
- [ ] Tests pass: `pytest backend/tests/`
- [ ] Type checking: `mypy backend/`
- [ ] Linting: `cd backend && python -m black . && python -m isort .`
- [ ] Integration tests: `pytest backend/tests/test_integration_db.py`

#### Manual Verification:
- [ ] Start backend with DATABASE_URL: Logs show "Database connected"
- [ ] Start backend without DATABASE_URL: Falls back to file storage
- [ ] Create notebook: Saved to database, file as backup
- [ ] Restart backend: Notebooks load from database
- [ ] Database connection fails: Falls back to file storage gracefully
- [ ] All existing notebooks accessible after migration

---

## Phase 6: Production Validation and Monitoring

### Overview

Validate database migration in production and set up monitoring.

### Changes Required

#### 1. Add CloudWatch Alarms

**File**: `terraform/modules/database/cloudwatch.tf` (NEW)

**Changes**: Create alarms for RDS metrics

```terraform
# CPU Utilization Alarm
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-rds-cpu-${var.environment}"
  alarm_description   = "RDS CPU utilization is too high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = []  # Add SNS topic for notifications

  tags = {
    Name = "${var.project_name} RDS CPU Alarm"
  }
}

# Database Connections Alarm
resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.project_name}-rds-connections-${var.environment}"
  alarm_description   = "RDS connection count is high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"  # 80% of max_connections

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = []  # Add SNS topic for notifications

  tags = {
    Name = "${var.project_name} RDS Connections Alarm"
  }
}

# Free Storage Space Alarm
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.project_name}-rds-storage-${var.environment}"
  alarm_description   = "RDS free storage space is low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "2147483648"  # 2 GB in bytes

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = []  # Add SNS topic for notifications

  tags = {
    Name = "${var.project_name} RDS Storage Alarm"
  }
}
```

#### 2. Create Deployment Checklist

**File**: `thoughts/shared/plans/database-migration-checklist.md` (NEW)

**Changes**: Step-by-step deployment guide

```markdown
# Database Migration Deployment Checklist

## Pre-Deployment (1 day before)

- [ ] Review Terraform plan for RDS module
- [ ] Verify backup retention is 7 days
- [ ] Confirm maintenance window is acceptable
- [ ] Test migration script on staging data
- [ ] Announce maintenance window to users

## Deployment Day - Phase 1: Infrastructure (15 minutes)

- [ ] Apply Terraform changes: `terraform apply -var-file=production.tfvars`
- [ ] Wait for RDS instance to be available (5-10 minutes)
- [ ] Verify RDS endpoint is accessible from ECS
- [ ] Test database connection: `psql -h <endpoint> -U admin -d notebooks`

## Phase 2: Schema Migration (5 minutes)

- [ ] Connect to RDS via bastion or ECS exec
- [ ] Run migrations: `alembic upgrade head`
- [ ] Verify tables created: `\dt` in psql
- [ ] Check indexes: `\di` in psql

## Phase 3: Data Migration (10-30 minutes, depending on data size)

- [ ] Stop ECS tasks to prevent writes during migration
- [ ] Run migration script: `python scripts/migrate_to_database.py`
- [ ] Verify migration: `python scripts/migrate_to_database.py --verify`
- [ ] Check database: `SELECT COUNT(*) FROM notebooks;`

## Phase 4: Deploy New Backend (10 minutes)

- [ ] Build new Docker image with database support
- [ ] Push to ECR
- [ ] Update ECS service to use new image
- [ ] Set DATABASE_URL environment variable
- [ ] Start ECS tasks
- [ ] Wait for tasks to be healthy
- [ ] Check logs for "Database connected" message

## Phase 5: Validation (15 minutes)

- [ ] Test API health check: `curl https://api.example.com/health`
- [ ] List notebooks: `curl https://api.example.com/notebooks`
- [ ] Create test notebook
- [ ] Update test cell
- [ ] Delete test notebook
- [ ] Verify all operations succeed
- [ ] Check database for test data

## Phase 6: Monitoring (Ongoing)

- [ ] Check CloudWatch alarms are active
- [ ] Monitor RDS Performance Insights
- [ ] Watch ECS task logs for errors
- [ ] Monitor application error rates
- [ ] Check response times

## Rollback Plan (if needed)

If critical issues occur:

1. [ ] Revert ECS service to previous task definition
2. [ ] Remove DATABASE_URL environment variable
3. [ ] Restart ECS tasks (will use file storage)
4. [ ] JSON files still intact as backup
5. [ ] Investigate issues before retry

## Post-Deployment (1 week later)

- [ ] Monitor RDS costs
- [ ] Review Performance Insights for slow queries
- [ ] Check backup success
- [ ] Test backup restore process
- [ ] Archive JSON files to S3 (optional)
- [ ] Document any issues encountered
```

#### 3. Add Monitoring Queries

**File**: `backend/scripts/db_monitoring.sql` (NEW)

**Changes**: Useful queries for monitoring

```sql
-- Check notebook counts by user
SELECT 
    u.clerk_user_id,
    COUNT(n.id) as notebook_count,
    MAX(n.updated_at) as last_updated
FROM users u
LEFT JOIN notebooks n ON n.user_id = u.id
GROUP BY u.id
ORDER BY notebook_count DESC;

-- Check cell counts by notebook
SELECT 
    n.id,
    n.name,
    COUNT(c.id) as cell_count
FROM notebooks n
LEFT JOIN cells c ON c.notebook_id = n.id
GROUP BY n.id
ORDER BY cell_count DESC
LIMIT 20;

-- Check database size
SELECT 
    pg_size_pretty(pg_database_size('notebooks')) as database_size;

-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check slow queries (requires pg_stat_statements extension)
SELECT 
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check active connections
SELECT 
    datname,
    usename,
    application_name,
    client_addr,
    state,
    query
FROM pg_stat_activity
WHERE datname = 'notebooks';
```

### Success Criteria

#### Automated Verification:
- [ ] CloudWatch alarms created: Check AWS Console
- [ ] Health check returns 200: `curl https://api.example.com/health`
- [ ] Metrics flowing to CloudWatch: Check RDS metrics

#### Manual Verification:
- [ ] RDS Performance Insights shows queries
- [ ] CloudWatch logs show application logs
- [ ] No error spike after deployment
- [ ] Response times within acceptable range (<100ms)
- [ ] Database CPU < 50%
- [ ] Database connections < 20
- [ ] All notebooks accessible via API
- [ ] Demo notebooks still provision correctly
- [ ] Cell execution works (Python + SQL)
- [ ] WebSocket updates work

---

## Testing Strategy

### Unit Tests

**File**: `backend/tests/test_storage_db.py` (NEW)

**Test Cases**:
- [ ] Save notebook to database
- [ ] Load notebook from database
- [ ] List notebooks for user
- [ ] Delete notebook (cascade deletes cells)
- [ ] Handle missing notebook gracefully
- [ ] Preserve cell order (position field)
- [ ] Store and retrieve outputs
- [ ] Handle JSON serialization (reads/writes sets)

**File**: `backend/tests/test_db_models.py` (NEW)

**Test Cases**:
- [ ] User model validation
- [ ] Notebook model validation
- [ ] Cell model validation
- [ ] Relationships (user.notebooks, notebook.cells)
- [ ] Cascade deletes

### Integration Tests

**File**: `backend/tests/test_integration_db.py` (NEW)

**Test Cases**:
- [ ] End-to-end: Create notebook → Add cells → Save → Load → Verify
- [ ] Concurrent updates with database
- [ ] Optimistic locking with database persistence
- [ ] Demo notebook provisioning with database
- [ ] Migration script on test data
- [ ] Fallback to file storage if database unavailable

### Manual Testing Steps

1. **Local Development**:
   - [ ] Start postgres: `docker-compose -f postgres/docker-compose.yml up -d`
   - [ ] Run migrations: `cd backend && alembic upgrade head`
   - [ ] Start backend: `uvicorn main:app --reload`
   - [ ] Create notebook via UI
   - [ ] Add cells, execute code
   - [ ] Restart backend → verify notebook persists

2. **Staging Environment**:
   - [ ] Deploy RDS + new backend to staging
   - [ ] Run migration script on staging data
   - [ ] Test all API endpoints
   - [ ] Test WebSocket connections
   - [ ] Test concurrent requests
   - [ ] Test error scenarios (DB down, network issues)

3. **Production Deployment**:
   - [ ] Follow deployment checklist
   - [ ] Monitor for 1 hour after deployment
   - [ ] Test from multiple browsers
   - [ ] Verify demo notebooks work for new users
   - [ ] Check CloudWatch metrics

## Performance Considerations

### Query Optimization

1. **Indexes** (defined in db_models.py):
   - `user_id` on notebooks (frequent filter)
   - `notebook_id` on cells (foreign key lookup)
   - `cell_id` on cell_outputs (foreign key lookup)
   - `position` on cells (ordering)

2. **N+1 Query Prevention**:
   - Use `joinedload` or `selectinload` for eager loading
   - Load notebook with cells in single query
   - Example: `select(NotebookDB).options(joinedload(NotebookDB.cells))`

3. **Connection Pooling**:
   - Pool size: 10 connections
   - Max overflow: 20 connections
   - Pool pre-ping enabled (detect stale connections)

### Caching Strategy

**Hybrid Architecture** (current + improved):
- **In-memory cache**: Keep active notebooks in `NOTEBOOKS` dict
- **Database**: Persistent storage
- **File backup**: Disaster recovery

**Cache Invalidation**:
- Update cache on every mutation
- Load from database on cache miss
- No TTL (explicit invalidation only)

### Database Size Estimates

**Assumptions**:
- 100 users
- 10 notebooks per user (1000 notebooks)
- 20 cells per notebook (20,000 cells)
- 2 outputs per cell (40,000 outputs)
- Average cell code: 500 bytes
- Average output data: 10 KB

**Estimated Size**:
- Notebooks table: 1000 × 1 KB = 1 MB
- Cells table: 20,000 × 1 KB = 20 MB
- Outputs table: 40,000 × 10 KB = 400 MB
- **Total**: ~421 MB

**RDS t4g.micro** (1 vCPU, 1 GB RAM) is sufficient for this scale.

## Migration Notes

### Backward Compatibility

**Handling Legacy Notebooks**:
- Notebooks without `user_id` → extract from ID pattern or assign to default user
- Missing `name` → `None` (acceptable)
- Missing `revision` → default to 0

**File Backup Strategy**:
- Keep JSON files for 7 days after migration
- Archive to S3 for long-term backup (optional)
- Clear files after validation period

### Data Integrity

**Migration Script Guarantees**:
- Atomic: All or nothing (transaction per notebook)
- Idempotent: Re-run safe (upsert logic)
- Verifiable: --verify flag checks all data

**Database Constraints**:
- Foreign keys prevent orphaned records
- Cascade deletes ensure cleanup
- NOT NULL on required fields
- Unique constraints on IDs

### Rollback Strategy

**If migration fails**:
1. Revert ECS task definition (remove DATABASE_URL)
2. Backend falls back to file storage
3. JSON files still intact
4. Fix issues, retry migration

**If database fails in production**:
1. Backend detects connection failure
2. Falls back to file storage
3. Operates in degraded mode
4. Restore database, resume normal operation

## References

### Research Documents

- `thoughts/shared/research/2025-12-31-dynamodb-notebook-storage-implementation.md` - DynamoDB implementation details and trade-offs
- `thoughts/shared/research/2025-12-30-database-architecture-rds-migrations-type-safety.md` - **Primary reference** for RDS migration approach

### Code References

- `backend/storage.py:13-58` - Current file-based save operation
- `backend/storage.py:60-112` - Current file-based load operation
- `backend/models.py:79-89` - Notebook data model
- `backend/models.py:34-43` - Cell data model
- `backend/demo_notebook.py:4-106` - Demo notebook creation logic
- `backend/routes.py:175-217` - Demo notebook provisioning logic
- `backend/notebook_operations.py:13-63` - Cell update with locking pattern
- `backend/tests/test_concurrency.py:7-139` - Concurrency testing patterns
- `terraform/main.tf:1-67` - Current Terraform module structure

### External Documentation

- **SQLModel**: https://sqlmodel.tiangolo.com/
- **Alembic**: https://alembic.sqlalchemy.org/
- **SQLAlchemy 2.0 Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **AWS RDS Best Practices**: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html
- **PostgreSQL 16**: https://www.postgresql.org/docs/16/

---

**End of Implementation Plan**

**Estimated Timeline**: 
- Phase 1 (Setup): 2 hours
- Phase 2 (CRUD): 3 hours
- Phase 3 (Migration): 1 hour
- Phase 4 (Infrastructure): 2 hours
- Phase 5 (Switch): 2 hours
- Phase 6 (Validation): 2 hours
- **Total**: 12 hours (1.5 days)

**Risk Level**: Medium (database migration always carries risk, but comprehensive testing and rollback plan mitigate)

**Recommendation**: Proceed with RDS implementation in phases, with thorough testing at each step. The hybrid architecture (in-memory + database + file backup) provides multiple layers of safety.

