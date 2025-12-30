---
date: 2025-12-30T09:34:04+00:00
researcher: AI Assistant
topic: "Database Architecture for Notebooks: AWS RDS, Migrations, and Type Safety"
tags: [research, database, aws, rds, postgres, sqlalchemy, pydantic, alembic, migrations, type-safety]
status: complete
last_updated: 2025-12-30
last_updated_by: AI Assistant
---

# Research: Database Architecture for Notebooks: AWS RDS, Migrations, and Type Safety

**Date**: 2025-12-30T09:34:04+00:00
**Researcher**: AI Assistant

## Research Question

How should we implement a database for notebooks and users in the reactive notebook application? What are the modern best practices (Dec 2025) for:
1. AWS RDS PostgreSQL deployment and management
2. Database migration strategies and tooling
3. Type safety across Python backend (SQLAlchemy 2.0, Pydantic v2)
4. RDS vs DynamoDB decision factors

## Summary

For a take-home project demonstrating full-stack competency, **AWS RDS PostgreSQL** is the superior choice over DynamoDB, paired with **SQLModel** (which combines SQLAlchemy 2.0 + Pydantic v2) for type safety and **Alembic** for migrations.

### Recommended Stack

**Database**: AWS RDS PostgreSQL
- Demonstrates relational database expertise
- Native SQL support (already have SQL cells in notebook)
- ACID compliance for notebook state
- Better for complex queries and relationships
- Existing docker postgres setup translates directly

**ORM + Type Safety**: SQLModel
- Combines SQLAlchemy 2.0 ORM with Pydantic v2 validation
- Single model definition for both database and API schemas
- Full type hints and editor autocomplete
- Runtime validation with Pydantic
- Officially endorsed by FastAPI creator (Sebastián Ramírez)

**Migrations**: Alembic
- Industry standard for SQLAlchemy migrations
- Auto-generates migrations from model changes
- Version control for database schema
- Safe rollback capabilities
- Integrates seamlessly with SQLModel

**Why This Demonstrates Competency**:
1. **Relational Design**: Shows understanding of foreign keys, relationships, constraints
2. **Type Safety**: Modern Python patterns (Pydantic v2, SQLAlchemy 2.0)
3. **Migration Management**: Production-ready schema evolution
4. **AWS Integration**: RDS setup, security groups, parameter groups
5. **Full Stack**: Database → ORM → API → Frontend type safety

### Why Not DynamoDB?

While DynamoDB is "easier", it doesn't showcase:
- Relational modeling skills
- SQL expertise
- Schema design
- Complex query optimization
- Traditional database management

For a take-home, demonstrating depth > ease.

## Current Architecture Analysis

### Storage Implementation

**Current System** (`backend/storage.py`):
```python
# File-based JSON persistence
NOTEBOOKS_DIR = Path("notebooks")

def save_notebook(notebook: Notebook) -> None:
    # Atomic write using tempfile + os.replace
    data = {
        "id": notebook.id,
        "user_id": notebook.user_id,
        "name": notebook.name,
        "db_conn_string": notebook.db_conn_string,
        "revision": notebook.revision,
        "cells": [...] 
    }
    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"
    # ... write to temp file, then atomic rename
```

**Current Models** (`backend/models.py`):
- Using Python `dataclasses`
- In-memory state with file persistence
- No database integration yet
- Already has `user_id` field (prepared for multi-user)

**Current Postgres Usage** (`postgres/docker-compose.yml`):
- Only for SQL cell execution
- Not used for application data storage
- Sample Iris dataset for testing

### Key Findings from Codebase

**Data Flow**: API Routes → Notebook Operations → In-Memory Dict → File Storage

**Persistence Points**:
1. `locked_update_cell()` - calls `save_notebook()` after changes
2. `locked_create_cell()` - calls `save_notebook()` after creation
3. `locked_delete_cell()` - calls `save_notebook()` after deletion

**Concurrency Control**:
- Each notebook has `asyncio.Lock`
- Optimistic locking with revision numbers
- Thread-safe operations in `notebook_operations.py`

**Integration Points for Database**:
- Replace `storage.save_notebook()` with database insert/update
- Replace `storage.load_notebook()` with database query
- Keep in-memory caching for performance
- Maintain existing lock-based concurrency

## AWS RDS Best Practices (December 2025)

### Instance Configuration

**Recommended Setup for MVP**:
- **Instance Class**: `db.t4g.micro` or `db.t4g.small` (ARM-based, cost-effective)
- **Storage**: 20GB General Purpose SSD (gp3)
- **Engine Version**: PostgreSQL 16 (latest stable)
- **Region**: `eu-north-1` (London) - matches existing infrastructure

**Security Configuration**:
```terraform
resource "aws_db_instance" "notebooks" {
  identifier           = "querio-notebook-db"
  engine              = "postgres"
  engine_version      = "16.1"
  instance_class      = "db.t4g.micro"
  allocated_storage   = 20
  storage_type        = "gp3"
  
  db_name             = "notebooks"
  username            = "admin"
  password            = var.db_password  # From AWS Secrets Manager
  
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.private.name
  
  # Best practices
  publicly_accessible    = false  # Private subnets only
  multi_az              = false   # Enable for production
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"
  
  # Performance
  auto_minor_version_upgrade = true
  performance_insights_enabled = true
  
  # Monitoring
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  
  # Deletion protection
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "querio-notebook-final-snapshot"
  
  tags = {
    Name        = "Querio Notebook Database"
    Environment = "production"
  }
}
```

**Parameter Groups** (Best Practices Dec 2025):
```terraform
resource "aws_db_parameter_group" "postgres16" {
  name   = "querio-postgres16-params"
  family = "postgres16"

  # Connection settings
  parameter {
    name  = "max_connections"
    value = "100"
  }

  # Performance tuning
  parameter {
    name  = "shared_buffers"
    value = "{DBInstanceClassMemory/4096}"  # 25% of RAM
  }

  parameter {
    name  = "effective_cache_size"
    value = "{DBInstanceClassMemory/2048}"  # 75% of RAM
  }

  # Logging for debugging
  parameter {
    name  = "log_statement"
    value = "all"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries > 1s
  }
}
```

### Security Best Practices

**VPC and Subnet Configuration**:
- RDS in **private subnets** only
- ECS tasks access via security group rules
- No public internet access
- Use AWS Secrets Manager for credentials

**Security Group Rules**:
```terraform
resource "aws_security_group" "rds" {
  name        = "querio-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  # Allow PostgreSQL from ECS tasks only
  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  # No outbound rules needed for RDS
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

**Connection String Management**:
```python
# backend/database.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Get from environment (set via ECS task definition)
DATABASE_URL = os.getenv("DATABASE_URL")
# Example: postgresql+asyncpg://admin:password@rds-endpoint.region.rds.amazonaws.com:5432/notebooks

engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Log all SQL in development
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
```

### Backup and Recovery

**Automated Backups**:
- Retention: 7-30 days (7 for MVP, 30 for production)
- Backup window: During low-traffic hours (3-4 AM)
- Point-in-time recovery enabled
- Cross-region backups for disaster recovery (production)

**Manual Snapshots**:
- Before major migrations
- Before schema changes
- Before production deployments

### Monitoring and Alerts

**CloudWatch Metrics to Monitor**:
- `CPUUtilization` - Alert if > 80%
- `FreeableMemory` - Alert if < 256MB
- `DatabaseConnections` - Alert if near max_connections
- `ReadLatency` / `WriteLatency` - Alert if > 100ms
- `FreeStorageSpace` - Alert if < 2GB

**Performance Insights**:
- Enable for free (7 days retention)
- Identify slow queries
- Monitor connection usage
- Track wait events

## Database Migration Strategy

### Why Alembic?

**Industry Standard**:
- 10+ years of production use
- Battle-tested with SQLAlchemy
- Supported by FastAPI ecosystem
- Extensive documentation

**Key Features**:
- Auto-generate migrations from model changes
- Version control for schema
- Safe rollback capabilities
- Branching and merging
- Dependency resolution

### Alembic Setup

**Installation**:
```bash
pip install alembic asyncpg sqlalchemy[asyncio]
```

**Initialize** (`backend/`):
```bash
cd backend
alembic init alembic
```

**Configure** (`alembic.ini`):
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://localhost:5432/notebooks

# Logging
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic
```

**Update** `alembic/env.py` for async:
```python
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio

# Import your models
from models import Base  # SQLModel creates this

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

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
    """Run migrations in 'online' mode with async."""
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

### Migration Workflow

**1. Create Initial Migration**:
```bash
# Auto-generate from models
alembic revision --autogenerate -m "Initial tables"

# Review generated file in alembic/versions/
# Edit if needed

# Apply migration
alembic upgrade head
```

**2. Make Schema Changes**:
```bash
# Modify models in models.py
# Generate migration
alembic revision --autogenerate -m "Add notebook tags"

# Review the generated migration
cat alembic/versions/xxxx_add_notebook_tags.py

# Apply to database
alembic upgrade head
```

**3. Rollback if Needed**:
```bash
# Rollback one version
alembic downgrade -1

# Rollback to specific version
alembic downgrade abc123

# Rollback all
alembic downgrade base
```

**4. Production Migration Strategy**:
```bash
# 1. Test migration on staging database
alembic upgrade head --sql > migration.sql
# Review SQL before running

# 2. Backup production database
aws rds create-db-snapshot \
  --db-instance-identifier querio-notebook-db \
  --db-snapshot-identifier pre-migration-$(date +%Y%m%d)

# 3. Apply migration during maintenance window
alembic upgrade head

# 4. Verify with health check
curl https://api.example.com/health
```

### Alternative: db-migration-manager

**Modern Alternative** (2025):
```bash
pip install db-migration-manager
```

**Features**:
- FastAPI-first design
- Pydantic model support
- Auto-diff capability
- Transaction safety
- Rollback support

**Example Setup**:
```python
from db_migration_manager import MigrationManager

manager = MigrationManager(
    database_url="postgresql+asyncpg://...",
    migrations_dir="migrations/",
    pydantic_models=[NotebookModel, UserModel]
)

# Auto-generate from Pydantic models
await manager.create_migration("add_notebooks_table")

# Apply migrations
await manager.upgrade()
```

## Type Safety: SQLModel (SQLAlchemy 2.0 + Pydantic v2)

### Why SQLModel?

**Created by FastAPI Author**: Sebastián Ramírez (tiangolo)
- Designed specifically for FastAPI applications
- Combines best of SQLAlchemy + Pydantic
- Single source of truth for models

**Benefits**:
1. **One Model Definition**: Use same class for database and API
2. **Full Type Hints**: Editor autocomplete + type checking
3. **Runtime Validation**: Pydantic v2 validation
4. **Relationship Support**: SQLAlchemy relationships
5. **Async Support**: Native async/await with asyncpg

### SQLModel Implementation

**Installation**:
```bash
pip install sqlmodel asyncpg
```

**Base Setup** (`backend/models.py`):
```python
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from datetime import datetime
from uuid import UUID, uuid4

# User Model
class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship
    notebooks: List["Notebook"] = Relationship(back_populates="owner")

# Notebook Model
class Notebook(SQLModel, table=True):
    __tablename__ = "notebooks"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: Optional[str] = Field(default=None, max_length=255)
    db_conn_string: Optional[str] = Field(default=None, max_length=512)
    revision: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key
    user_id: UUID = Field(foreign_key="users.id")
    owner: User = Relationship(back_populates="notebooks")
    
    # Relationship
    cells: List["Cell"] = Relationship(back_populates="notebook", cascade_delete=True)

# Cell Model
class Cell(SQLModel, table=True):
    __tablename__ = "cells"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: str = Field(max_length=50)  # "python" or "sql"
    code: str = Field(default="")
    position: int = Field(default=0)  # For ordering
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Foreign key
    notebook_id: UUID = Field(foreign_key="notebooks.id")
    notebook: Notebook = Relationship(back_populates="cells")

# Create tables
from sqlmodel import create_engine

engine = create_engine("postgresql+asyncpg://...")
SQLModel.metadata.create_all(engine)  # Development only
# Use Alembic for production migrations
```

**API Schemas** (Separate from DB models):
```python
# Request/Response models that inherit from base
class NotebookCreate(SQLModel):
    name: Optional[str] = None
    db_conn_string: Optional[str] = None

class NotebookRead(SQLModel):
    id: UUID
    name: Optional[str]
    user_id: UUID
    created_at: datetime
    cells: List["CellRead"] = []

class NotebookUpdate(SQLModel):
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
```

**Database Session** (`backend/database.py`):
```python
from sqlmodel import create_engine, Session, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**CRUD Operations** (`backend/routes.py`):
```python
from fastapi import Depends, HTTPException
from sqlmodel import select
from typing import List

@router.post("/notebooks", response_model=NotebookRead)
async def create_notebook(
    notebook: NotebookCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    db_notebook = Notebook(
        **notebook.dict(),
        user_id=user.id
    )
    session.add(db_notebook)
    await session.commit()
    await session.refresh(db_notebook)
    return db_notebook

@router.get("/notebooks", response_model=List[NotebookRead])
async def list_notebooks(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    statement = select(Notebook).where(Notebook.user_id == user.id)
    result = await session.execute(statement)
    notebooks = result.scalars().all()
    return notebooks

@router.get("/notebooks/{notebook_id}", response_model=NotebookRead)
async def get_notebook(
    notebook_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    statement = select(Notebook).where(
        Notebook.id == notebook_id,
        Notebook.user_id == user.id
    )
    result = await session.execute(statement)
    notebook = result.scalar_one_or_none()
    
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    return notebook
```

### Type Safety Benefits

**Editor Support**:
```python
# Full autocomplete
notebook = Notebook(name="My Notebook")
notebook.  # IDE shows: id, name, user_id, cells, created_at, etc.

# Type checking catches errors
notebook.name = 123  # Error: Expected str, got int
```

**Pydantic Validation**:
```python
# Runtime validation
try:
    notebook = Notebook(
        name="Test",
        email="not-an-email"  # Pydantic validates email format
    )
except ValidationError as e:
    print(e.json())
```

**Database Constraints**:
```python
# SQLAlchemy ensures constraints
class User(SQLModel, table=True):
    email: str = Field(unique=True, index=True)
    # Generates: CREATE UNIQUE INDEX ON users(email)
```

### Alternative: Pure SQLAlchemy 2.0 + Pydantic v2

If not using SQLModel, separate the layers:

**SQLAlchemy Models** (`backend/db_models.py`):
```python
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(UUID, primary_key=True)
    email = Column(String(255), unique=True, index=True)
    notebooks = relationship("Notebook", back_populates="owner")
```

**Pydantic Schemas** (`backend/schemas.py`):
```python
from pydantic import BaseModel, EmailStr, UUID4

class UserSchema(BaseModel):
    id: UUID4
    email: EmailStr
    
    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode)
```

**Conversion**:
```python
# DB to Pydantic
db_user = session.query(User).first()
pydantic_user = UserSchema.from_orm(db_user)

# Pydantic to DB
user_data = UserCreate(email="test@example.com")
db_user = User(**user_data.dict())
```

## Schema Design for Notebooks

### Recommended Tables

**users**
- `id` (UUID, PK)
- `email` (VARCHAR(255), UNIQUE)
- `hashed_password` (VARCHAR(255))
- `is_active` (BOOLEAN)
- `created_at` (TIMESTAMP)

**notebooks**
- `id` (UUID, PK)
- `user_id` (UUID, FK → users.id)
- `name` (VARCHAR(255), NULLABLE)
- `db_conn_string` (VARCHAR(512), NULLABLE)
- `revision` (INTEGER, DEFAULT 0)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

**cells**
- `id` (UUID, PK)
- `notebook_id` (UUID, FK → notebooks.id, CASCADE DELETE)
- `type` (VARCHAR(50)) - "python" or "sql"
- `code` (TEXT)
- `position` (INTEGER) - For ordering within notebook
- `created_at` (TIMESTAMP)

**cell_outputs** (optional, for caching)
- `id` (UUID, PK)
- `cell_id` (UUID, FK → cells.id, CASCADE DELETE)
- `mime_type` (VARCHAR(100))
- `data` (JSONB) - Store output data
- `created_at` (TIMESTAMP)

### Indexes

```sql
-- User lookups
CREATE UNIQUE INDEX idx_users_email ON users(email);

-- Notebook queries
CREATE INDEX idx_notebooks_user_id ON notebooks(user_id);
CREATE INDEX idx_notebooks_created_at ON notebooks(created_at DESC);

-- Cell queries
CREATE INDEX idx_cells_notebook_id ON cells(notebook_id);
CREATE INDEX idx_cells_position ON cells(notebook_id, position);

-- Output queries (if using cell_outputs table)
CREATE INDEX idx_cell_outputs_cell_id ON cell_outputs(cell_id);
```

### Relationships

```
users (1) ──< (many) notebooks
notebooks (1) ──< (many) cells
cells (1) ──< (many) cell_outputs [optional]
```

### Migration Strategy for Existing Data

**Current State**: JSON files in `backend/notebooks/`

**Migration Steps**:

1. **Create tables** via Alembic
2. **Migrate existing notebooks**:
```python
# backend/migrate_to_db.py
import json
from pathlib import Path
from database import get_session
from models import User, Notebook, Cell
import asyncio

async def migrate_notebooks():
    async with async_session() as session:
        # Create default user for existing notebooks
        default_user = User(
            email="admin@example.com",
            hashed_password="<generate>",
            is_active=True
        )
        session.add(default_user)
        await session.flush()
        
        # Migrate each notebook file
        for json_file in Path("notebooks").glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
            
            # Extract user_id or use default
            user_id = data.get("user_id", default_user.id)
            
            # Create notebook
            notebook = Notebook(
                id=data["id"],
                user_id=user_id,
                name=data.get("name"),
                db_conn_string=data.get("db_conn_string"),
                revision=data.get("revision", 0)
            )
            session.add(notebook)
            
            # Create cells
            for i, cell_data in enumerate(data["cells"]):
                cell = Cell(
                    id=cell_data["id"],
                    notebook_id=notebook.id,
                    type=cell_data["type"],
                    code=cell_data["code"],
                    position=i
                )
                session.add(cell)
        
        await session.commit()
        print("Migration complete!")

asyncio.run(migrate_notebooks())
```

3. **Update application code** to use database
4. **Keep JSON files as backup** initially
5. **Remove file-based storage** after validation

## Integration with Existing Codebase

### Changes Required

**1. Update `backend/storage.py`**:
```python
# Replace file-based with database operations
from sqlmodel import select
from database import get_session

async def save_notebook(notebook: Notebook, session: AsyncSession) -> None:
    """Save notebook to database."""
    notebook.updated_at = datetime.utcnow()
    notebook.revision += 1
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)

async def load_notebook(notebook_id: UUID, user_id: UUID, session: AsyncSession) -> Notebook:
    """Load notebook from database."""
    statement = select(Notebook).where(
        Notebook.id == notebook_id,
        Notebook.user_id == user_id
    )
    result = await session.execute(statement)
    notebook = result.scalar_one_or_none()
    if not notebook:
        raise ValueError(f"Notebook {notebook_id} not found")
    return notebook

async def list_notebooks(user_id: UUID, session: AsyncSession) -> List[Notebook]:
    """List user's notebooks."""
    statement = select(Notebook).where(Notebook.user_id == user_id)
    result = await session.execute(statement)
    return result.scalars().all()
```

**2. Update `backend/notebook_operations.py`**:
```python
# Add session parameter to all functions
async def locked_update_cell(
    notebook: Notebook,
    cell_id: UUID,
    code: str,
    session: AsyncSession,  # NEW
    expected_revision: Optional[int] = None
) -> Cell:
    async with notebook._lock:
        # ... existing logic ...
        
        # Save to database instead of file
        await save_notebook(notebook, session)
        
        return cell
```

**3. Update `backend/routes.py`**:
```python
from fastapi import Depends
from database import get_session

@router.post("/notebooks")
async def create_notebook(
    notebook_data: NotebookCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    notebook = Notebook(**notebook_data.dict(), user_id=user.id)
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    
    # Add to in-memory cache
    NOTEBOOKS[notebook.id] = notebook
    
    return notebook
```

**4. Add `backend/database.py`**:
```python
from sqlmodel import create_engine, Session
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost:5432/notebooks")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**5. Update `backend/requirements.txt`**:
```txt
# Existing dependencies
fastapi==0.104.1
uvicorn==0.24.0
asyncpg==0.29.0
pydantic==2.12.5

# Add for database
sqlmodel==0.0.14  # Latest as of Dec 2025
alembic==1.13.1
psycopg2-binary==2.9.9  # For migrations
```

### Hybrid Approach: In-Memory + Database

For optimal performance, maintain hybrid architecture:

**In-Memory Cache**:
- Fast access for active notebooks
- Maintain existing lock-based concurrency
- Keep execution state in memory

**Database Persistence**:
- Durable storage
- User authentication and authorization
- Notebook listing and search
- Audit logging

**Implementation**:
```python
# In-memory cache (existing)
NOTEBOOKS: Dict[UUID, Notebook] = {}

async def get_notebook(notebook_id: UUID, user_id: UUID, session: AsyncSession) -> Notebook:
    """Get notebook from cache or database."""
    # Try cache first
    if notebook_id in NOTEBOOKS:
        notebook = NOTEBOOKS[notebook_id]
        # Verify ownership
        if notebook.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        return notebook
    
    # Load from database
    notebook = await load_notebook(notebook_id, user_id, session)
    
    # Cache it
    NOTEBOOKS[notebook_id] = notebook
    
    return notebook
```

## RDS vs DynamoDB Decision Matrix

### When to Use RDS (PostgreSQL)

✅ **Use RDS if**:
- Complex queries and joins needed
- ACID compliance required
- Relational data model
- SQL expertise on team
- Existing PostgreSQL knowledge
- Need transactions
- Foreign key constraints important
- Rich querying (filtering, sorting, aggregation)

**For This Project**: ✅ RDS is ideal
- Notebooks have relational structure (user → notebook → cells)
- SQL cells need PostgreSQL anyway
- Complex queries for notebook search/filtering
- Demonstrates full-stack SQL expertise
- Existing docker postgres setup

### When to Use DynamoDB

✅ **Use DynamoDB if**:
- Simple key-value or document storage
- Need massive scale (millions of TPS)
- Serverless/pay-per-request model
- Global replication required
- Single-table design pattern
- No complex queries needed
- Simple access patterns (get by ID, list by user)

**For This Project**: ❌ Not ideal
- Doesn't showcase SQL skills
- Notebooks are inherently relational
- Would need complex index management
- Harder to query/filter notebooks
- Less impressive for take-home

### Cost Comparison

**RDS** (`db.t4g.micro`, London):
- Instance: $13-15/month
- Storage: $2-5/month (20GB)
- Backups: Included in storage cost
- **Total**: ~$20/month for development

**DynamoDB** (on-demand):
- Write: $1.25 per million requests
- Read: $0.25 per million requests
- Storage: $0.25/GB
- **Total**: $5-50/month depending on usage

**Verdict**: For development/MVP, costs are similar. RDS shows more competency.

### Performance Comparison

**RDS**:
- Latency: 1-5ms (within VPC)
- Throughput: ~1000 queries/sec (single instance)
- Scaling: Vertical (larger instance) or read replicas

**DynamoDB**:
- Latency: 1-2ms (single-digit ms)
- Throughput: Virtually unlimited with on-demand
- Scaling: Automatic and horizontal

**Verdict**: For notebook use case (< 100 concurrent users), RDS is sufficient.

## Terraform Configuration for RDS

### Complete RDS Module

**`terraform/modules/database/main.tf`**:
```terraform
resource "aws_db_subnet_group" "private" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.project_name} DB Subnet Group"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

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
    value = "1000"
  }

  tags = {
    Name = "${var.project_name} PostgreSQL Parameters"
  }
}

resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "db_password" {
  name = "${var.project_name}-db-password"

  tags = {
    Name = "${var.project_name} DB Password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

resource "aws_db_instance" "main" {
  identifier           = "${var.project_name}-db"
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

resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project_name}/database_url"
  type  = "SecureString"
  value = "postgresql+asyncpg://${var.database_username}:${random_password.db_password.result}@${aws_db_instance.main.endpoint}/${var.database_name}"

  tags = {
    Name = "${var.project_name} Database URL"
  }
}
```

**`terraform/modules/database/variables.tf`**:
```terraform
variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecs_security_group_id" {
  type = string
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "database_name" {
  type    = string
  default = "notebooks"
}

variable "database_username" {
  type    = string
  default = "admin"
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = true
}
```

**`terraform/modules/database/outputs.tf`**:
```terraform
output "endpoint" {
  value = aws_db_instance.main.endpoint
}

output "database_name" {
  value = aws_db_instance.main.db_name
}

output "database_url_ssm_parameter" {
  value = aws_ssm_parameter.database_url.name
}

output "security_group_id" {
  value = aws_security_group.rds.id
}
```

### Use in Main Terraform

**`terraform/main.tf`**:
```terraform
module "database" {
  source = "./modules/database"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = module.networking.vpc_id
  private_subnet_ids     = module.networking.private_subnet_ids
  ecs_security_group_id  = module.compute.ecs_security_group_id

  instance_class       = "db.t4g.micro"
  allocated_storage    = 20
  multi_az            = false  # Enable for production
  deletion_protection = true
}

# Update ECS task definition to include DATABASE_URL
resource "aws_ecs_task_definition" "backend" {
  # ... existing config ...

  container_definitions = jsonencode([
    {
      # ... existing config ...
      
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = module.database.database_url_ssm_parameter
        }
      ]
    }
  ])
}
```

## Historical Context

### Existing Infrastructure Research

From `thoughts/shared/research/2025-12-28-aws-terraform-deployment-strategy.md`:

**Current Limitations**:
- In-memory state (notebooks in Python dict)
- Single ECS task due to lack of persistence
- Data lost on pod restart
- Can't scale horizontally

**Planned Enhancements**:
> "Future enhancements could include:
> - Implement S3 storage for notebooks
> - Or use RDS PostgreSQL
> - Update backend code to use persistent storage"

This research provides the foundation for RDS implementation.

### Authentication Research

From `thoughts/shared/research/2025-12-28-username-password-authentication-implementation.md`:

**User Management Requirements**:
- FastAPI Users library selected
- SQLAlchemy integration needed
- User table required
- JWT authentication

**Database Integration**:
```python
# Planned: Create database.py with SQLAlchemy setup
# Planned: User table definition
# Planned: Database initialization
```

This research confirms need for relational database.

## Implementation Roadmap

### Phase 1: Database Setup (1-2 hours)

- [x] Research AWS RDS best practices ✓
- [x] Research migration tools (Alembic) ✓
- [x] Research type safety (SQLModel) ✓
- [ ] Install dependencies (SQLModel, Alembic)
- [ ] Create `database.py` with async engine
- [ ] Create SQLModel models (User, Notebook, Cell)
- [ ] Initialize Alembic
- [ ] Generate initial migration
- [ ] Test locally with docker postgres

### Phase 2: CRUD Migration (2-3 hours)

- [ ] Update `storage.py` to use database
- [ ] Update `notebook_operations.py` with session params
- [ ] Update `routes.py` with dependency injection
- [ ] Migrate existing JSON files to database
- [ ] Test all CRUD operations
- [ ] Verify WebSocket still works

### Phase 3: AWS RDS Deployment (2-3 hours)

- [ ] Create Terraform RDS module
- [ ] Configure security groups
- [ ] Deploy RDS instance
- [ ] Update ECS task with DATABASE_URL
- [ ] Run Alembic migrations on RDS
- [ ] Test production database access
- [ ] Configure backups and monitoring

### Phase 4: Production Hardening (1-2 hours)

- [ ] Add connection pooling
- [ ] Add retry logic
- [ ] Add health checks for database
- [ ] Set up CloudWatch alarms
- [ ] Document database operations
- [ ] Create migration playbook

**Total Time Estimate**: 6-10 hours

### Testing Checklist

**Local Testing**:
- [ ] Create notebook (persists to DB)
- [ ] Update cell (revision increments)
- [ ] Delete notebook (cascade deletes cells)
- [ ] Restart server (data persists)
- [ ] Multiple users (isolation works)

**Migration Testing**:
- [ ] Run migration on empty database
- [ ] Run migration twice (idempotent)
- [ ] Rollback migration
- [ ] Migrate existing JSON data

**AWS RDS Testing**:
- [ ] Connect from ECS task
- [ ] Create/read/update/delete operations
- [ ] Performance (< 10ms queries within VPC)
- [ ] Backup and restore
- [ ] Failover (if Multi-AZ)

## Open Questions

1. **Schema Versioning**: Should we store schema version in database for migration validation?
   - **Recommendation**: Yes, Alembic tracks this in `alembic_version` table

2. **Soft Deletes**: Should notebooks be soft-deleted (is_deleted flag) or hard-deleted?
   - **Recommendation**: Start with hard deletes, add soft deletes if audit requirements emerge

3. **Cell Dependencies**: Should we store cell reads/writes in database?
   - **Recommendation**: No, keep dependency graph in-memory for performance (rebuild on load)

4. **Output Caching**: Should we cache cell outputs in database?
   - **Recommendation**: Not initially, add if needed for performance

5. **Multi-Region**: Should we plan for cross-region replication?
   - **Recommendation**: Not for MVP, but RDS read replicas support this

## Related Research

- `thoughts/shared/research/2025-12-28-aws-terraform-deployment-strategy.md` - AWS infrastructure
- `thoughts/shared/research/2025-12-28-username-password-authentication-implementation.md` - User management
- `thoughts/shared/research/2025-12-28-kernel-orchestration-architecture.md` - DynamoDB comparison

## External Resources

### Official Documentation

- **SQLModel**: https://sqlmodel.tiangolo.com/
- **Alembic**: https://alembic.sqlalchemy.org/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/
- **Pydantic v2**: https://docs.pydantic.dev/2.0/
- **AWS RDS**: https://docs.aws.amazon.com/rds/
- **FastAPI Database Guide**: https://fastapi.tiangolo.com/tutorial/sql-databases/

### Dev Blogs (December 2025)

- **AWS RDS Best Practices**: https://aws.amazon.com/blogs/database/best-practices-for-amazon-rds-for-postgresql-cross-region-read-replicas/
- **RDS Security**: https://www.datavail.com/blog/10-best-practices-to-secure-postgresql-aws-rds-aurora/
- **PostgreSQL on RDS Maintenance**: https://docs.aws.amazon.com/prescriptive-guidance/latest/postgresql-maintenance-rds-aurora/introduction.html
- **Alembic Async Patterns**: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- **SQLModel with FastAPI**: https://sqlmodel.tiangolo.com/tutorial/fastapi/

### Migration Tools

- **Migropy**: https://pypi.org/project/migropy/
- **DB Migration Manager**: https://pypi.org/project/db-migration-manager/
- **RDS Migration Toolkit**: https://pypi.org/project/rds-migration-toolkit/

### Code Examples

- **FastAPI + SQLModel**: https://github.com/tiangolo/sqlmodel/tree/main/docs_src
- **Async SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Alembic Async**: https://github.com/sqlalchemy/alembic/tree/main/examples/asyncio

## Conclusion

For the Querio take-home project, implementing **AWS RDS PostgreSQL** with **SQLModel** and **Alembic** migrations is the optimal choice to demonstrate:

1. **Full-Stack Competency**: Relational database design, SQL expertise, ORM patterns
2. **Modern Python**: Type safety with Pydantic v2, async/await, SQLAlchemy 2.0
3. **Production Readiness**: Migrations, backups, monitoring, security best practices
4. **AWS Expertise**: RDS configuration, VPC security, Terraform IaC

**Key Advantages Over DynamoDB**:
- Showcases SQL and relational modeling skills
- Natural fit for notebook → cell relationship
- Demonstrates migration management expertise
- More impressive for engineering evaluation
- Existing PostgreSQL setup (docker) translates directly

**Implementation Priority**:
1. Local SQLModel setup with docker postgres (1-2 hours)
2. Migrate CRUD operations to database (2-3 hours)
3. Deploy AWS RDS via Terraform (2-3 hours)
4. Production hardening and monitoring (1-2 hours)

**Total Effort**: 6-10 hours to fully implement database persistence with AWS RDS, demonstrating comprehensive full-stack and infrastructure competency.

