---
date: 2025-12-31T12:20:06Z
planner: AI Planning Agent
topic: "Backend Folder Structure Reorganization"
tags: [planning, implementation, backend, fastapi, refactoring, architecture]
status: draft
last_updated: 2025-12-31
last_updated_by: AI Planning Agent
---

# Backend Folder Structure Reorganization Implementation Plan

**Date**: 2025-12-31 12:20:06 GMT
**Planner**: AI Planning Agent
**Repository**: Carter-Querio-notebook (7c4d6a252b45f2e6b26f9f70a57ecfb3656c9cc9)

## Overview

This plan reorganizes the FastAPI backend from a flat module structure (15+ files at root) to a layered, domain-driven architecture following industry best practices. The reorganization will improve maintainability, scalability, and code clarity while maintaining all existing functionality.

## Current State Analysis

**Current Structure**: Flat module structure with all Python files in `backend/` root
- 15+ Python modules at root level
- Mixed concerns (routes, models, storage, execution, utilities)
- Data directories (`notebooks/`, `logs/`) in source tree
- No API versioning
- Large route file (`routes.py` - 651 lines)

**See**: `thoughts/shared/research/2025-12-31-backend-folder-structure-analysis.md` for detailed analysis

## System Context Analysis

The backend is a **modular FastAPI application** for a reactive notebook system. It follows async patterns with strong concurrency control, dependency injection for authentication, and clean storage abstraction. The current flat structure works but doesn't scale well as the application grows.

**Root Cause**: The flat structure is a symptom of rapid prototyping. As features were added (chat, LLM tools, DynamoDB storage), the number of root-level modules grew without a clear organizational strategy.

**Justification for Refactoring**: This is the right time to reorganize because:
1. The application has reached a stable feature set
2. Team may grow, requiring clearer structure
3. API versioning will be needed for production
4. Current structure makes onboarding new developers harder
5. Best practices are clear and well-established

## Desired End State

**New Structure**: Layered architecture with clear separation of concerns

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/                    # API layer
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── notebooks.py
│   │           ├── cells.py
│   │           ├── chat.py
│   │           └── websocket.py
│   ├── core/                   # Configuration
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── security.py
│   ├── models/                 # Domain models
│   │   ├── __init__.py
│   │   ├── notebook.py
│   │   ├── cell.py
│   │   └── graph.py
│   ├── schemas/                # API contracts
│   │   ├── __init__.py
│   │   ├── notebook.py
│   │   ├── cell.py
│   │   └── chat.py
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   ├── notebook_service.py
│   │   └── execution_service.py
│   ├── storage/                # Data persistence
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── file_storage.py
│   │   └── dynamodb_storage.py
│   ├── execution/              # Execution engine
│   │   ├── __init__.py
│   │   ├── executor.py
│   │   ├── scheduler.py
│   │   └── dependencies.py
│   ├── websocket/              # Real-time
│   │   ├── __init__.py
│   │   └── broadcaster.py
│   └── utils/                  # Utilities
│       ├── __init__.py
│       ├── ast_parser.py
│       └── llm_tools.py
├── tests/                      # Tests (mirrors app structure)
│   ├── __init__.py
│   ├── conftest.py
│   └── unit/
│       ├── test_executor.py
│       ├── test_graph.py
│       └── ...
├── scripts/                    # Deployment scripts
├── data/                       # Runtime data (dev only)
│   └── notebooks/
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── README.md
```

### Verification Criteria

**Success means**:
1. All tests pass without modification
2. Application starts and runs correctly
3. All API endpoints work as before
4. WebSocket connections function properly
5. Both file and DynamoDB storage work
6. No import errors or circular dependencies
7. Code is more maintainable and navigable

## What We're NOT Doing

1. **Not changing functionality** - This is purely structural refactoring
2. **Not modifying tests** (except imports) - Tests should pass with minimal changes
3. **Not changing the API** - All endpoints remain the same
4. **Not refactoring logic** - Business logic stays identical
5. **Not changing dependencies** - `requirements.txt` stays the same
6. **Not migrating databases** - Storage format remains unchanged
7. **Not adding new features** - Pure code organization

## Implementation Approach

**Strategy**: Incremental, file-by-file migration with continuous verification

**Principles**:
1. Create new structure first
2. Move files one layer at a time
3. Update imports as we go
4. Run tests after each major change
5. Keep both structures temporarily if needed
6. Use git to track every step

**Risk Mitigation**:
- Create branch for reorganization
- Commit after each phase
- Run full test suite after each phase
- Keep backup of working state

## Phase 1: Preparation & New Directory Structure

### Overview
Create the new directory structure and prepare for migration without touching existing files.

### Changes Required

#### 1. Create Branch and Directory Structure
**Changes**: Create git branch and all new directories

```bash
# Create feature branch
git checkout -b refactor/backend-folder-structure

# Create new app directory structure
mkdir -p backend/app/api/v1/endpoints
mkdir -p backend/app/core
mkdir -p backend/app/models
mkdir -p backend/app/schemas
mkdir -p backend/app/services
mkdir -p backend/app/storage
mkdir -p backend/app/execution
mkdir -p backend/app/websocket
mkdir -p backend/app/utils
mkdir -p backend/data/notebooks
```

#### 2. Create __init__.py Files
**Changes**: Create all `__init__.py` files for Python packages

```bash
# Create all __init__.py files
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/api/v1/__init__.py
touch backend/app/api/v1/endpoints/__init__.py
touch backend/app/core/__init__.py
touch backend/app/models/__init__.py
touch backend/app/schemas/__init__.py
touch backend/app/services/__init__.py
touch backend/app/storage/__init__.py
touch backend/app/execution/__init__.py
touch backend/app/websocket/__init__.py
touch backend/app/utils/__init__.py
```

#### 3. Move Data Directories
**Changes**: Move `notebooks/` and `logs/` to `data/`

```bash
# Move data directories out of source tree
mv backend/notebooks/ backend/data/notebooks/
mkdir -p backend/data/logs/audit
mv backend/logs/audit/llm_actions.log backend/data/logs/audit/ 2>/dev/null || true
```

### Success Criteria

#### Automated Verification:
- [ ] Branch created: `git branch --list | grep refactor/backend-folder-structure`
- [ ] All directories exist: `test -d backend/app/api/v1/endpoints && test -d backend/app/core && test -d backend/app/models && test -d backend/app/schemas && test -d backend/app/services && test -d backend/app/storage && test -d backend/app/execution && test -d backend/app/websocket && test -d backend/app/utils`
- [ ] All __init__.py files exist: `find backend/app -name "__init__.py" | wc -l` (should be 13)
- [ ] Data directories moved: `test -d backend/data/notebooks`

#### Manual Verification:
- [ ] Directory structure matches the plan
- [ ] All new directories are empty except for __init__.py files
- [ ] Old structure is still intact and functional

---

## Phase 2: Move Core Configuration & Security

### Overview
Extract configuration and authentication logic into `app/core/` module.

### Changes Required

#### 1. Create Configuration Module
**File**: `backend/app/core/config.py`
**Changes**: Extract settings from `main.py` into Pydantic BaseSettings

```python
from pydantic import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # Clerk Authentication
    CLERK_FRONTEND_API: str
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # DynamoDB
    DYNAMODB_ENABLED: bool = False
    DYNAMODB_TABLE_NAME: str | None = None
    AWS_REGION: str = "us-east-1"
    
    # Storage
    NOTEBOOK_STORAGE_DIR: str = "backend/data/notebooks"
    
    # Application
    APP_TITLE: str = "Reactive Notebook"
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    @property
    def jwks_url(self) -> str:
        return f"https://{self.CLERK_FRONTEND_API}/.well-known/jwks.json"

settings = Settings()
```

#### 2. Create Security Module
**File**: `backend/app/core/security.py`
**Changes**: Extract authentication logic from `main.py`

```python
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request
from typing import Optional
from .config import settings

# Initialize PyJWKClient for JWT verification
jwks_client = PyJWKClient(
    uri=settings.jwks_url,
    cache_keys=True,
    max_cached_keys=16,
    cache_jwk_set=True,
    lifespan=300,
)

async def get_current_user(request: Request) -> str:
    """
    Verify Clerk JWT token and return user ID.
    Uses PyJWT with Clerk's JWKS endpoint for verification.
    Raises HTTPException(401) if token is invalid or missing.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Extract token from "Bearer <token>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = parts[1]
        
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify JWT token
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
                "verify_iss": False,
                "verify_iat": True,
            },
            leeway=0,
        )
        
        # Extract user_id from 'sub' claim
        user_id = decoded_token.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user ID (sub claim)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_id
    
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        raise HTTPException(
            status_code=401,
            detail=f"Authentication error ({error_type}): {error_msg}",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def verify_clerk_token(token: str) -> Optional[str]:
    """
    Verify Clerk JWT token and extract user_id.
    Used for WebSocket authentication.
    
    Args:
        token: JWT token string (without "Bearer " prefix)
        
    Returns:
        user_id if token is valid, None otherwise
    """
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_exp": True,
                "verify_aud": False,
                "verify_iss": False,
                "verify_iat": True,
            },
            leeway=0,
        )
        
        return decoded_token.get("sub")
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return None
```

#### 3. Update core/__init__.py
**File**: `backend/app/core/__init__.py`
**Changes**: Export core modules

```python
from .config import settings
from .security import get_current_user, verify_clerk_token, jwks_client

__all__ = ["settings", "get_current_user", "verify_clerk_token", "jwks_client"]
```

### Success Criteria

#### Automated Verification:
- [ ] Files created: `test -f backend/app/core/config.py && test -f backend/app/core/security.py`
- [ ] No syntax errors: `python -m py_compile backend/app/core/config.py backend/app/core/security.py`
- [ ] Imports work: `cd backend && python -c "from app.core import settings, get_current_user"`

#### Manual Verification:
- [ ] Settings object can be instantiated
- [ ] Security functions are properly typed
- [ ] No circular import errors

---

## Phase 3: Move Models & Create Schemas

### Overview
Split domain models from API schemas, moving models to `app/models/` and creating new schemas in `app/schemas/`.

### Changes Required

#### 1. Move Domain Models
**Files**: Split `backend/models.py` into multiple files in `app/models/`

**File**: `backend/app/models/cell.py`
```python
from dataclasses import dataclass, field
from typing import Optional, Set, List
from enum import Enum

class CellType(str, Enum):
    PYTHON = "python"
    SQL = "sql"

class CellStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"

class MimeType(str, Enum):
    """Known MIME types for output rendering"""
    PNG = "image/png"
    HTML = "text/html"
    PLAIN = "text/plain"
    VEGA_LITE = "application/vnd.vegalite.v6+json"
    JSON = "application/json"
    PLOTLY_JSON = "application/vnd.plotly.v1+json"

@dataclass
class Output:
    """Single output with MIME type metadata"""
    mime_type: str
    data: str | dict | list
    metadata: dict[str, str | int | float] = field(default_factory=dict)

@dataclass
class Cell:
    id: str
    type: CellType
    code: str
    status: CellStatus = CellStatus.IDLE
    stdout: str = ""
    outputs: List[Output] = field(default_factory=list)
    error: Optional[str] = None
    reads: Set[str] = field(default_factory=set)
    writes: Set[str] = field(default_factory=set)
```

**File**: `backend/app/models/graph.py`
```python
from dataclasses import dataclass, field

@dataclass
class Graph:
    edges: dict[str, set[str]] = field(default_factory=dict)
    reverse_edges: dict[str, set[str]] = field(default_factory=dict)

    def add_edge(self, from_cell: str, to_cell: str):
        """Add dependency: from_cell writes vars that to_cell reads"""
        if from_cell not in self.edges:
            self.edges[from_cell] = set()
        self.edges[from_cell].add(to_cell)

        if to_cell not in self.reverse_edges:
            self.reverse_edges[to_cell] = set()
        self.reverse_edges[to_cell].add(from_cell)

    def remove_cell(self, cell_id: str):
        """Remove all edges involving this cell"""
        if cell_id in self.edges:
            for dependent in self.edges[cell_id]:
                self.reverse_edges[dependent].discard(cell_id)
            del self.edges[cell_id]

        if cell_id in self.reverse_edges:
            for dependency in self.reverse_edges[cell_id]:
                self.edges[dependency].discard(cell_id)
            del self.reverse_edges[cell_id]
```

**File**: `backend/app/models/notebook.py`
```python
from dataclasses import dataclass, field
from asyncio import Lock
from typing import Optional, List
from .cell import Cell
from .graph import Graph

@dataclass
class KernelState:
    globals_dict: dict[str, object] = field(default_factory=lambda: {"__builtins__": __builtins__})

@dataclass
class Notebook:
    id: str
    user_id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)
```

**File**: `backend/app/models/__init__.py`
```python
from .cell import Cell, CellType, CellStatus, MimeType, Output
from .graph import Graph
from .notebook import Notebook, KernelState

__all__ = [
    "Cell", "CellType", "CellStatus", "MimeType", "Output",
    "Graph",
    "Notebook", "KernelState"
]
```

#### 2. Create API Schemas
**Files**: Create Pydantic models for API requests/responses in `app/schemas/`

**File**: `backend/app/schemas/notebook.py`
```python
from pydantic import BaseModel
from typing import Optional, List

class CreateNotebookRequest(BaseModel):
    pass

class CreateNotebookResponse(BaseModel):
    notebook_id: str

class UpdateDbConnectionRequest(BaseModel):
    connection_string: str

class RenameNotebookRequest(BaseModel):
    name: str

class NotebookMetadataResponse(BaseModel):
    id: str
    name: str

class ListNotebooksResponse(BaseModel):
    notebooks: List[NotebookMetadataResponse]
```

**File**: `backend/app/schemas/cell.py`
```python
from pydantic import BaseModel
from typing import Optional, List, Union, Literal
from app.models import CellType, CellStatus

class CreateCellRequest(BaseModel):
    type: CellType
    after_cell_id: Optional[str] = None

class UpdateCellRequest(BaseModel):
    code: str

class CreateCellResponse(BaseModel):
    cell_id: str

class TableData(BaseModel):
    """Table data structure for pandas DataFrames and SQL results"""
    type: Literal["table"]
    columns: List[str]
    rows: List[List[Union[str, int, float, bool, None]]]
    truncated: Optional[str] = None

class OutputResponse(BaseModel):
    mime_type: str
    data: Union[str, TableData, dict, list]
    metadata: Optional[dict[str, Union[str, int, float]]] = None

class CellResponse(BaseModel):
    id: str
    type: CellType
    code: str
    status: CellStatus
    stdout: Optional[str] = None
    outputs: List[OutputResponse]
    error: Optional[str] = None
    reads: List[str]
    writes: List[str]

class NotebookResponse(BaseModel):
    id: str
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[CellResponse]
```

**File**: `backend/app/schemas/chat.py`
```python
from pydantic import BaseModel
from typing import Optional

class ChatMessageRequest(BaseModel):
    message: str
    notebook_id: Optional[str] = None
```

**File**: `backend/app/schemas/__init__.py`
```python
from .notebook import (
    CreateNotebookRequest, CreateNotebookResponse,
    UpdateDbConnectionRequest, RenameNotebookRequest,
    NotebookMetadataResponse, ListNotebooksResponse
)
from .cell import (
    CreateCellRequest, UpdateCellRequest, CreateCellResponse,
    TableData, OutputResponse, CellResponse, NotebookResponse
)
from .chat import ChatMessageRequest

__all__ = [
    "CreateNotebookRequest", "CreateNotebookResponse",
    "UpdateDbConnectionRequest", "RenameNotebookRequest",
    "NotebookMetadataResponse", "ListNotebooksResponse",
    "CreateCellRequest", "UpdateCellRequest", "CreateCellResponse",
    "TableData", "OutputResponse", "CellResponse", "NotebookResponse",
    "ChatMessageRequest"
]
```

### Success Criteria

#### Automated Verification:
- [ ] All model files exist: `test -f backend/app/models/cell.py && test -f backend/app/models/graph.py && test -f backend/app/models/notebook.py`
- [ ] All schema files exist: `test -f backend/app/schemas/notebook.py && test -f backend/app/schemas/cell.py && test -f backend/app/schemas/chat.py`
- [ ] No syntax errors: `python -m py_compile backend/app/models/*.py backend/app/schemas/*.py`
- [ ] Imports work: `cd backend && python -c "from app.models import Notebook, Cell; from app.schemas import NotebookResponse"`

#### Manual Verification:
- [ ] Models can be instantiated
- [ ] Schemas validate correctly
- [ ] No circular dependencies

---

## Phase 4: Move Storage Layer

### Overview
Reorganize storage modules into `app/storage/` with clear abstraction.

### Changes Required

#### 1. Create Storage Base
**File**: `backend/app/storage/base.py`
**Changes**: Extract storage interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from app.models import Notebook

class StorageBackend(ABC):
    """Abstract base class for notebook storage backends"""
    
    @abstractmethod
    async def save_notebook(self, notebook: Notebook) -> None:
        """Save a notebook to storage"""
        pass
    
    @abstractmethod
    async def load_notebook(self, user_id: str, notebook_id: str) -> Optional[Notebook]:
        """Load a notebook from storage"""
        pass
    
    @abstractmethod
    async def list_notebooks(self, user_id: Optional[str] = None) -> List[str]:
        """List all notebook IDs, optionally filtered by user"""
        pass
    
    @abstractmethod
    async def delete_notebook(self, notebook_id: str, user_id: str) -> None:
        """Delete a notebook from storage"""
        pass
```

#### 2. Move File Storage
**File**: `backend/app/storage/file_storage.py`
**Changes**: Move from `storage.py`, adapt to use new paths and base class

```python
import os
import json
import tempfile
from typing import List, Optional
from app.models import Notebook, Cell, CellType, CellStatus, Output, Graph
from app.core import settings
from .base import StorageBackend

class FileStorage(StorageBackend):
    """File-based storage backend for local development"""
    
    def __init__(self, notebook_dir: str = None):
        self.notebook_dir = notebook_dir or settings.NOTEBOOK_STORAGE_DIR
        os.makedirs(self.notebook_dir, exist_ok=True)
    
    # ... (rest of implementation from storage.py)
```

#### 3. Move DynamoDB Storage
**File**: `backend/app/storage/dynamodb_storage.py`
**Changes**: Move from `storage_dynamodb.py`, adapt to use new imports

```python
from typing import Optional, List
import aioboto3
from app.models import Notebook, Cell, CellType, CellStatus, Output, Graph
from app.core import settings
from .base import StorageBackend

class DynamoDBStorage(StorageBackend):
    """DynamoDB storage backend for production"""
    
    def __init__(
        self,
        table_name: str = None,
        region: str = None
    ):
        self.table_name = table_name or settings.DYNAMODB_TABLE_NAME
        self.region = region or settings.AWS_REGION
        self.session = aioboto3.Session()
    
    # ... (rest of implementation from storage_dynamodb.py)
```

#### 4. Create Storage Factory
**File**: `backend/app/storage/__init__.py`
**Changes**: Factory pattern for storage backend selection

```python
from typing import Optional
from .base import StorageBackend
from .file_storage import FileStorage
from .dynamodb_storage import DynamoDBStorage
from app.core import settings

_storage_backend: Optional[StorageBackend] = None

def get_storage() -> StorageBackend:
    """Get the configured storage backend (singleton)"""
    global _storage_backend
    
    if _storage_backend is None:
        if settings.DYNAMODB_ENABLED:
            _storage_backend = DynamoDBStorage()
        else:
            _storage_backend = FileStorage()
    
    return _storage_backend

# Convenience functions for backward compatibility
async def save_notebook(notebook, subdirectory=None):
    return await get_storage().save_notebook(notebook)

async def load_notebook(notebook_id, user_id=None):
    storage = get_storage()
    if hasattr(storage, 'load_notebook'):
        return await storage.load_notebook(user_id or "", notebook_id)
    return None

async def list_notebooks(user_id=None):
    return await get_storage().list_notebooks(user_id)

async def delete_notebook(notebook_id, user_id):
    return await get_storage().delete_notebook(notebook_id, user_id)

__all__ = [
    "StorageBackend", "FileStorage", "DynamoDBStorage",
    "get_storage", "save_notebook", "load_notebook",
    "list_notebooks", "delete_notebook"
]
```

### Success Criteria

#### Automated Verification:
- [ ] All storage files exist: `test -f backend/app/storage/base.py && test -f backend/app/storage/file_storage.py && test -f backend/app/storage/dynamodb_storage.py`
- [ ] No syntax errors: `python -m py_compile backend/app/storage/*.py`
- [ ] Imports work: `cd backend && python -c "from app.storage import get_storage, save_notebook"`

#### Manual Verification:
- [ ] Storage factory returns correct backend based on config
- [ ] File storage can save/load notebooks
- [ ] DynamoDB storage can save/load notebooks (if configured)

---

## Phase 5: Move Execution Engine & Utilities

### Overview
Reorganize execution-related modules and utilities into proper directories.

### Changes Required

#### 1. Move Execution Modules
**Files**: Move `executor.py`, `scheduler.py`, `ast_parser.py` to appropriate locations

**File**: `backend/app/execution/executor.py`
**Changes**: Move from `backend/executor.py`, update imports

```python
# Update imports at top of file
from app.models import Cell, CellStatus, Output, MimeType
# ... rest remains the same
```

**File**: `backend/app/execution/scheduler.py`
**Changes**: Move from `backend/scheduler.py`, update imports

```python
# Update imports
from app.models import Notebook, Cell, CellStatus
from app.storage import save_notebook
from .executor import execute_python_cell, execute_sql_cell
from .dependencies import rebuild_graph, topological_sort
# ... rest remains the same
```

**File**: `backend/app/execution/dependencies.py`
**Changes**: Move dependency extraction and graph logic here

```python
# Combine ast_parser.py and graph.py functionality
from app.models import Notebook, Cell, Graph
# ... implementation
```

**File**: `backend/app/execution/__init__.py`
```python
from .executor import execute_python_cell, execute_sql_cell
from .scheduler import scheduler
from .dependencies import extract_dependencies, rebuild_graph

__all__ = [
    "execute_python_cell", "execute_sql_cell",
    "scheduler",
    "extract_dependencies", "rebuild_graph"
]
```

#### 2. Move Utilities
**Files**: Move utility modules to `app/utils/`

**File**: `backend/app/utils/ast_parser.py`
**Changes**: Move AST parsing utilities (if keeping separate from dependencies)

**File**: `backend/app/utils/llm_tools.py`
**Changes**: Move from `backend/llm_tools.py`

**File**: `backend/app/utils/__init__.py`
```python
from .ast_parser import extract_dependencies, extract_sql_dependencies
from .llm_tools import get_tool_schema, execute_tool

__all__ = [
    "extract_dependencies", "extract_sql_dependencies",
    "get_tool_schema", "execute_tool"
]
```

#### 3. Move Notebook Operations
**File**: `backend/app/services/notebook_service.py`
**Changes**: Move from `notebook_operations.py`, this is business logic

```python
from app.models import Notebook, Cell, CellType, CellStatus
from app.storage import save_notebook
from app.execution import extract_dependencies, rebuild_graph
# ... rest of locked operations
```

**File**: `backend/app/services/__init__.py`
```python
from .notebook_service import (
    locked_create_cell,
    locked_update_cell,
    locked_delete_cell
)

__all__ = [
    "locked_create_cell",
    "locked_update_cell",
    "locked_delete_cell"
]
```

### Success Criteria

#### Automated Verification:
- [ ] All execution files moved: `test -f backend/app/execution/executor.py && test -f backend/app/execution/scheduler.py`
- [ ] All utility files moved: `test -f backend/app/utils/llm_tools.py`
- [ ] Service files created: `test -f backend/app/services/notebook_service.py`
- [ ] No syntax errors: `python -m py_compile backend/app/execution/*.py backend/app/utils/*.py backend/app/services/*.py`

#### Manual Verification:
- [ ] Imports resolve correctly
- [ ] No circular dependencies
- [ ] Functions are accessible from new locations

---

## Phase 6: Move WebSocket & API Routes

### Overview
Reorganize WebSocket broadcaster and split API routes into versioned endpoints.

### Changes Required

#### 1. Move WebSocket Broadcaster
**File**: `backend/app/websocket/broadcaster.py`
**Changes**: Move from `backend/websocket.py`, update imports

```python
from fastapi import WebSocket
from typing import Dict, Set
from app.models import CellStatus

# ... rest of implementation remains the same

# Global broadcaster instance
broadcaster = WebSocketBroadcaster()
```

**File**: `backend/app/websocket/__init__.py`
```python
from .broadcaster import broadcaster, WebSocketBroadcaster

__all__ = ["broadcaster", "WebSocketBroadcaster"]
```

#### 2. Create API Dependencies
**File**: `backend/app/api/deps.py`
**Changes**: Centralize API dependencies

```python
from fastapi import Request
from app.core import get_current_user

# Re-export for convenience
async def get_current_user_dependency(request: Request) -> str:
    """Dependency for getting current authenticated user"""
    return await get_current_user(request)

__all__ = ["get_current_user_dependency"]
```

#### 3. Split Routes into Endpoints
**File**: `backend/app/api/v1/endpoints/notebooks.py`
**Changes**: Extract notebook CRUD endpoints from `routes.py`

```python
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict
from app.models import Notebook, Cell, CellType, CellStatus
from app.schemas import (
    CreateNotebookRequest, CreateNotebookResponse,
    UpdateDbConnectionRequest, RenameNotebookRequest,
    NotebookResponse, ListNotebooksResponse, NotebookMetadataResponse,
    CellResponse, OutputResponse
)
from app.storage import save_notebook, list_notebooks, delete_notebook
from app.api.deps import get_current_user_dependency
import uuid

router = APIRouter()

# In-memory storage (shared state)
NOTEBOOKS: Dict[str, Notebook] = {}

@router.post("/", response_model=CreateNotebookResponse)
async def create_notebook(
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.get("/", response_model=ListNotebooksResponse)
async def list_notebooks_endpoint(
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.put("/{notebook_id}/db")
async def update_db_connection(
    notebook_id: str,
    request_body: UpdateDbConnectionRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.put("/{notebook_id}/name")
async def rename_notebook(
    notebook_id: str,
    request_body: RenameNotebookRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.delete("/{notebook_id}")
async def delete_notebook_endpoint(
    notebook_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py
```

**File**: `backend/app/api/v1/endpoints/cells.py`
**Changes**: Extract cell CRUD endpoints from `routes.py`

```python
from fastapi import APIRouter, HTTPException, Depends, Request
from app.models import Notebook
from app.schemas import (
    CreateCellRequest, UpdateCellRequest, CreateCellResponse
)
from app.services import locked_create_cell, locked_update_cell, locked_delete_cell
from app.websocket import broadcaster
from app.api.deps import get_current_user_dependency
from .notebooks import NOTEBOOKS  # Shared state

router = APIRouter()

@router.post("/{notebook_id}/cells", response_model=CreateCellResponse)
async def create_cell(
    notebook_id: str,
    request_body: CreateCellRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.put("/{notebook_id}/cells/{cell_id}")
async def update_cell(
    notebook_id: str,
    cell_id: str,
    request_body: UpdateCellRequest,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py

@router.delete("/{notebook_id}/cells/{cell_id}")
async def delete_cell(
    notebook_id: str,
    cell_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from routes.py
```

**File**: `backend/app/api/v1/endpoints/websocket.py`
**Changes**: Extract WebSocket endpoint from `routes.py`

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket import broadcaster
from app.core import verify_clerk_token, jwks_client
from app.execution import scheduler
from .notebooks import NOTEBOOKS  # Shared state
import asyncio

router = APIRouter()

@router.websocket("/ws/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    # ... implementation from routes.py
```

**File**: `backend/app/api/v1/endpoints/chat.py`
**Changes**: Move chat endpoint from `backend/chat.py`

```python
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from app.schemas import ChatMessageRequest
from app.api.deps import get_current_user_dependency
# ... rest of chat implementation

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(
    request: Request,
    chat_request: ChatMessageRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    # ... implementation from chat.py
```

**File**: `backend/app/api/v1/endpoints/__init__.py`
```python
from .notebooks import router as notebooks_router, NOTEBOOKS
from .cells import router as cells_router
from .websocket import router as websocket_router
from .chat import router as chat_router

__all__ = [
    "notebooks_router", "cells_router",
    "websocket_router", "chat_router",
    "NOTEBOOKS"
]
```

#### 4. Aggregate Routers
**File**: `backend/app/api/v1/api.py`
**Changes**: Aggregate all v1 endpoints

```python
from fastapi import APIRouter
from .endpoints import (
    notebooks_router,
    cells_router,
    websocket_router,
    chat_router
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(notebooks_router, prefix="/notebooks", tags=["notebooks"])
api_router.include_router(cells_router, tags=["cells"])  # Already includes /notebooks prefix
api_router.include_router(websocket_router, tags=["websocket"])
api_router.include_router(chat_router, tags=["chat"])
```

**File**: `backend/app/api/v1/__init__.py`
```python
from .api import api_router

__all__ = ["api_router"]
```

**File**: `backend/app/api/__init__.py`
```python
from .v1 import api_router

__all__ = ["api_router"]
```

### Success Criteria

#### Automated Verification:
- [ ] WebSocket moved: `test -f backend/app/websocket/broadcaster.py`
- [ ] All endpoint files exist: `test -f backend/app/api/v1/endpoints/notebooks.py && test -f backend/app/api/v1/endpoints/cells.py && test -f backend/app/api/v1/endpoints/websocket.py && test -f backend/app/api/v1/endpoints/chat.py`
- [ ] API aggregation exists: `test -f backend/app/api/v1/api.py`
- [ ] No syntax errors: `python -m py_compile backend/app/api/v1/endpoints/*.py backend/app/api/v1/api.py`

#### Manual Verification:
- [ ] All routes are properly registered
- [ ] WebSocket endpoint is accessible
- [ ] Shared NOTEBOOKS state is accessible across endpoints

---

## Phase 7: Update Main Application & Entrypoint

### Overview
Update `main.py` to use the new structure and serve as a clean entrypoint.

### Changes Required

#### 1. Update Main Application
**File**: `backend/app/main.py`
**Changes**: Simplify entrypoint, use new imports

```python
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core import settings
from .api import api_router
from .storage import load_notebook, list_notebooks
from .api.v1.endpoints import NOTEBOOKS

load_dotenv(override=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    print(f"Starting {settings.APP_TITLE}...")
    
    if settings.DYNAMODB_ENABLED:
        print(f"✓ DynamoDB enabled: {settings.DYNAMODB_TABLE_NAME}")
        print("  - Sub-10ms latency for all operations")
        print("  - Serverless auto-scaling enabled")
        print("  - Notebooks will be lazy-loaded on first access")
    else:
        print("Using file-based storage (local dev)")
        notebook_ids = await list_notebooks()
        if notebook_ids:
            print(f"Loading {len(notebook_ids)} notebook(s)...")
            for notebook_id in notebook_ids:
                try:
                    notebook = await load_notebook(notebook_id)
                    if notebook:
                        NOTEBOOKS[notebook_id] = notebook
                        print(f"  ✓ Loaded: {notebook_id}")
                except Exception as e:
                    print(f"  ✗ Failed: {notebook_id}: {e}")
        else:
            print("No notebooks found. Users will create their own.")
    
    yield
    print("👋 Shutting down...")

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_TITLE,
        lifespan=lifespan,
        debug=settings.DEBUG
    )
    
    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API router with /api prefix
    app.include_router(api_router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 2. Create Root __init__.py
**File**: `backend/app/__init__.py`
```python
from .main import app, create_app

__version__ = "1.0.0"

__all__ = ["app", "create_app"]
```

#### 3. Update demo_notebook
**File**: `backend/app/utils/demo_notebook.py`
**Changes**: Move from `backend/demo_notebook.py`, update imports

```python
from app.models import Notebook, Cell, CellType, CellStatus
import uuid

def create_demo_notebook(user_id: str) -> Notebook:
    # ... implementation remains the same
```

### Success Criteria

#### Automated Verification:
- [ ] New main.py exists: `test -f backend/app/main.py`
- [ ] No syntax errors: `python -m py_compile backend/app/main.py`
- [ ] App can be imported: `cd backend && python -c "from app import app"`
- [ ] App can be created: `cd backend && python -c "from app import create_app; app = create_app()"`

#### Manual Verification:
- [ ] Application starts without errors: `cd backend && python -m app.main`
- [ ] Health endpoint responds: `curl http://localhost:8000/health`
- [ ] API routes are accessible: `curl http://localhost:8000/api/v1/notebooks` (should require auth)

---

## Phase 8: Update Tests & Scripts

### Overview
Update test imports and deployment scripts to use new structure.

### Changes Required

#### 1. Update Test Imports
**Files**: Update all test files in `backend/tests/`

**Example**: `backend/tests/test_executor.py`
```python
# Old imports:
# from executor import execute_python_cell
# from models import Cell, CellType, CellStatus

# New imports:
from app.execution import execute_python_cell
from app.models import Cell, CellType, CellStatus
```

**Changes needed in**:
- `test_executor.py`
- `test_graph.py`
- `test_ast_parser.py`
- `test_llm_tools.py`
- `test_concurrency.py`
- `test_utils.py`
- `conftest.py`

#### 2. Update pytest Configuration
**File**: `backend/pytest.ini`
**Changes**: Update Python path for new structure

```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
env =
    DYNAMODB_ENABLED=false
    CLERK_FRONTEND_API=test.clerk.accounts.dev
```

#### 3. Update Docker Configuration
**File**: `backend/Dockerfile`
**Changes**: Update paths and entry point

```dockerfile
FROM python:3.12-slim

WORKDIR /code

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Create data directory
RUN mkdir -p /code/data/notebooks /code/data/logs/audit

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 4. Update Deployment Scripts
**File**: `backend/scripts/deploy.sh`
**Changes**: Update any paths referencing old structure

```bash
# Update references from backend/main.py to backend/app/main.py
# Update any import checks
# Update health check endpoints
```

### Success Criteria

#### Automated Verification:
- [ ] All tests pass: `cd backend && pytest tests/ -v`
- [ ] No import errors in tests: `cd backend && python -m pytest --collect-only`
- [ ] Docker builds successfully: `cd backend && docker build -t notebook-backend .`
- [ ] Linting passes: `cd backend && python -m py_compile app/**/*.py`

#### Manual Verification:
- [ ] All test files updated with correct imports
- [ ] Docker container runs and serves requests
- [ ] Deployment scripts work correctly
- [ ] No broken imports anywhere

---

## Phase 9: Clean Up & Documentation

### Overview
Remove old files, update documentation, and verify everything works.

### Changes Required

#### 1. Remove Old Files
**Changes**: Delete old root-level Python modules

```bash
cd backend

# Remove old module files (keep backups temporarily)
mkdir -p .backup
mv routes.py .backup/
mv chat.py .backup/
mv models.py .backup/
mv storage.py .backup/
mv storage_dynamodb.py .backup/
mv executor.py .backup/
mv scheduler.py .backup/
mv websocket.py .backup/
mv notebook_operations.py .backup/
mv ast_parser.py .backup/
mv graph.py .backup/
mv llm_tools.py .backup/
mv demo_notebook.py .backup/
mv main.py .backup/

# After verification, delete backups
# rm -rf .backup/
```

#### 2. Update .gitignore
**File**: `backend/.gitignore`
**Changes**: Add new patterns

```gitignore
# Virtual environment
venv/
__pycache__/
*.pyc
*.pyo
*.pyd

# IDE
.vscode/
.idea/
*.swp
*.swo

# Data directories
data/notebooks/*.json
!data/notebooks/test/
data/logs/

# Environment
.env
.env.local

# Testing
.pytest_cache/
htmlcov/
.coverage

# Build
*.egg-info/
dist/
build/

# Backups
.backup/
```

#### 3. Update README
**File**: `backend/README.md`
**Changes**: Document new structure

```markdown
# Reactive Notebook Backend

FastAPI backend for the Reactive Notebook application.

## Project Structure

```
backend/
├── app/                        # Main application package
│   ├── api/                    # API layer
│   │   └── v1/                 # API version 1
│   │       ├── endpoints/      # Route handlers
│   │       └── api.py          # Router aggregation
│   ├── core/                   # Configuration & security
│   ├── models/                 # Domain models
│   ├── schemas/                # API request/response models
│   ├── services/               # Business logic
│   ├── storage/                # Data persistence
│   ├── execution/              # Notebook execution engine
│   ├── websocket/              # Real-time communication
│   ├── utils/                  # Utilities
│   └── main.py                 # Application entrypoint
├── tests/                      # Test suite
├── scripts/                    # Deployment & utilities
├── data/                       # Runtime data (dev only)
└── requirements.txt            # Dependencies
```

## Getting Started

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:

```env
CLERK_FRONTEND_API=your-app.clerk.accounts.dev
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
DYNAMODB_ENABLED=false
```

### Running the Application

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Running Tests

```bash
pytest tests/ -v
```

### Docker

```bash
# Build
docker build -t notebook-backend .

# Run
docker run -p 8000:8000 --env-file .env notebook-backend
```

## Architecture

### Layers

- **API Layer** (`app/api/`): HTTP/WebSocket interface, request validation
- **Services** (`app/services/`): Business logic orchestration
- **Models** (`app/models/`): Domain models and business entities
- **Storage** (`app/storage/`): Data persistence abstraction
- **Execution** (`app/execution/`): Notebook execution engine
- **Core** (`app/core/`): Configuration and cross-cutting concerns

### Key Features

- **Authentication**: Clerk JWT-based authentication
- **Real-time Updates**: WebSocket support for collaborative editing
- **Storage Backends**: File storage (dev) and DynamoDB (production)
- **Execution Engine**: Python and SQL cell execution with dependency resolution
- **LLM Integration**: Chat interface with tool execution

## Development

### Adding a New Endpoint

1. Create handler in `app/api/v1/endpoints/`
2. Add router to `app/api/v1/api.py`
3. Define schemas in `app/schemas/`
4. Write tests in `tests/`

### Project Conventions

- Use async/await for all I/O operations
- Type hints everywhere
- Pydantic for validation
- Dependency injection for shared dependencies
- Lock-based concurrency control for notebook operations

## Deployment

See `scripts/deploy.sh` for deployment procedures.
```

#### 4. Create Migration Guide
**File**: `backend/MIGRATION_GUIDE.md`
**Changes**: Document changes for developers

```markdown
# Migration Guide: Backend Reorganization

This guide helps you update your code after the backend folder structure reorganization.

## Import Changes

### Models
```python
# Old
from models import Notebook, Cell, CellType, CellStatus

# New
from app.models import Notebook, Cell, CellType, CellStatus
```

### Storage
```python
# Old
from storage import save_notebook, load_notebook

# New
from app.storage import save_notebook, load_notebook
```

### Execution
```python
# Old
from executor import execute_python_cell
from scheduler import scheduler

# New
from app.execution import execute_python_cell, scheduler
```

### WebSocket
```python
# Old
from websocket import broadcaster

# New
from app.websocket import broadcaster
```

### Configuration
```python
# Old
# Configuration was in main.py

# New
from app.core import settings
```

### Security
```python
# Old
# Auth was in main.py

# New
from app.core import get_current_user
```

## Path Changes

### Data Directories
- `backend/notebooks/` → `backend/data/notebooks/`
- `backend/logs/` → `backend/data/logs/`

### Application Entry
- `python main.py` → `python -m app.main`
- `uvicorn main:app` → `uvicorn app.main:app`

## Testing Changes

### Test Imports
Update all test imports to use `app.` prefix:

```python
# Old
from models import Notebook

# New
from app.models import Notebook
```

### Running Tests
No change:
```bash
pytest tests/ -v
```

## Docker Changes

### Build & Run
No user-facing changes, but Dockerfile has been updated internally.

```bash
# Still works the same
docker build -t notebook-backend .
docker run -p 8000:8000 notebook-backend
```

## Breaking Changes

None - all existing functionality is preserved.

## Gradual Migration

If you have external tools or scripts:

1. Update Python path: `PYTHONPATH=backend`
2. Update imports to use `app.` prefix
3. Update file paths to use `data/` directory
4. Test thoroughly before deploying
```

### Success Criteria

#### Automated Verification:
- [ ] Old files removed or backed up: `! test -f backend/routes.py || test -f backend/.backup/routes.py`
- [ ] Documentation updated: `test -f backend/README.md && test -f backend/MIGRATION_GUIDE.md`
- [ ] All tests still pass: `cd backend && pytest tests/ -v`
- [ ] App still runs: `cd backend && python -c "from app import app; print('OK')"`

#### Manual Verification:
- [ ] README accurately describes new structure
- [ ] Migration guide is complete and accurate
- [ ] No old files remaining in root
- [ ] Documentation is helpful for new developers

---

## Phase 10: Final Verification & Deployment

### Overview
Comprehensive testing and deployment verification.

### Changes Required

#### 1. Run Full Test Suite
**Changes**: Execute all tests

```bash
cd backend

# Unit tests
pytest tests/ -v --cov=app

# Integration tests
pytest tests/integration/ -v

# Type checking
mypy app/

# Linting
flake8 app/
```

#### 2. Manual Testing Checklist
**Changes**: Test all major features

**Test Cases**:
1. **Authentication**
   - [ ] Can authenticate with valid token
   - [ ] Reject invalid token
   - [ ] Reject expired token

2. **Notebook CRUD**
   - [ ] Create notebook
   - [ ] List notebooks for user
   - [ ] Get notebook by ID
   - [ ] Update notebook name
   - [ ] Update DB connection
   - [ ] Delete notebook

3. **Cell CRUD**
   - [ ] Create Python cell
   - [ ] Create SQL cell
   - [ ] Update cell code
   - [ ] Delete cell
   - [ ] Cell execution

4. **WebSocket**
   - [ ] Connect to WebSocket
   - [ ] Authenticate via WebSocket
   - [ ] Receive real-time updates
   - [ ] Run cell via WebSocket

5. **Storage**
   - [ ] File storage works (dev)
   - [ ] DynamoDB storage works (production)

6. **Execution**
   - [ ] Python cells execute correctly
   - [ ] SQL cells execute correctly
   - [ ] Dependencies resolved correctly
   - [ ] Cycle detection works

#### 3. Performance Verification
**Changes**: Verify no performance regression

```bash
# Load testing
cd backend
python -m locust -f tests/load_test.py

# Memory profiling
python -m memory_profiler app/main.py
```

#### 4. Deployment
**Changes**: Deploy to staging/production

```bash
# Build Docker image
docker build -t notebook-backend:latest .

# Tag for deployment
docker tag notebook-backend:latest your-registry/notebook-backend:latest

# Push to registry
docker push your-registry/notebook-backend:latest

# Deploy (following your deployment process)
./scripts/deploy.sh
```

### Success Criteria

#### Automated Verification:
- [ ] All unit tests pass: `pytest tests/unit/ -v`
- [ ] All integration tests pass: `pytest tests/integration/ -v`
- [ ] Code coverage > 80%: `pytest --cov=app --cov-report=term-missing`
- [ ] No type errors: `mypy app/ --strict`
- [ ] No linting errors: `flake8 app/`
- [ ] Docker image builds: `docker build -t test .`
- [ ] Docker container runs: `docker run --rm test python -c "from app import app"`

#### Manual Verification:
- [ ] All API endpoints work as expected
- [ ] WebSocket connections stable
- [ ] Real-time updates received
- [ ] Cell execution works correctly
- [ ] Storage operations succeed
- [ ] Performance is acceptable
- [ ] No errors in logs
- [ ] Production deployment successful

---

## Testing Strategy

### Unit Tests

**What to test**:
- Individual functions and classes
- Edge cases and error handling
- Data validation (Pydantic models)
- Business logic

**Example**:
```python
# tests/unit/test_models.py
from app.models import Notebook, Cell, CellType

def test_notebook_creation():
    nb = Notebook(id="test", user_id="user123")
    assert nb.id == "test"
    assert len(nb.cells) == 0
```

### Integration Tests

**What to test**:
- API endpoints (request/response)
- WebSocket connections
- Storage operations
- End-to-end flows

**Example**:
```python
# tests/integration/test_api.py
from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### Manual Testing Steps

1. **Start Application**: `uvicorn app.main:app --reload`
2. **Test Authentication**: Send requests with valid/invalid tokens
3. **Create Notebook**: POST to `/api/v1/notebooks`
4. **Add Cells**: POST to `/api/v1/notebooks/{id}/cells`
5. **Execute Cell**: Connect WebSocket, send run message
6. **Verify Output**: Check cell output and status updates

## Performance Considerations

### Expected Performance

- **API Response Time**: < 100ms for CRUD operations
- **WebSocket Latency**: < 50ms for broadcasts
- **Cell Execution**: Depends on code complexity
- **Storage Operations**: 
  - File storage: < 10ms
  - DynamoDB: < 5ms (p99)

### Monitoring

- Response times for each endpoint
- WebSocket connection counts
- Cell execution times
- Storage operation latencies
- Error rates

## Migration Notes

### Data Migration

**Not required** - storage format remains unchanged. Existing notebooks will work without modification.

### Backward Compatibility

All APIs remain at same paths (now under `/api/v1` prefix). Frontend may need minor updates to API URLs.

## References

- Research Document: `thoughts/shared/research/2025-12-31-backend-folder-structure-analysis.md`
- FastAPI Best Practices: https://fastapi.tiangolo.com/
- Project Repository: Carter-Querio-notebook

## Rollback Plan

If issues arise:

1. **Immediate**: Keep old code in `.backup/` temporarily
2. **Revert**: `git revert` the reorganization commits
3. **Redeploy**: Deploy previous working version
4. **Investigate**: Debug issues in separate branch

## Next Steps

After successful reorganization:

1. **Monitor**: Watch for errors or performance issues
2. **Document**: Update any missing documentation
3. **Train**: Help team members understand new structure
4. **Iterate**: Make further improvements based on feedback
5. **Plan v2 API**: Now that versioning is in place, plan v2 changes

---

## Appendix: File Mapping

### Complete Mapping of File Moves

| Old Path | New Path | Notes |
|----------|----------|-------|
| `backend/main.py` | `backend/app/main.py` | Simplified entrypoint |
| `backend/routes.py` | Multiple files in `backend/app/api/v1/endpoints/` | Split by domain |
| `backend/chat.py` | `backend/app/api/v1/endpoints/chat.py` | Moved to endpoints |
| `backend/models.py` | `backend/app/models/*.py` | Split into multiple files |
| `backend/storage.py` | `backend/app/storage/file_storage.py` | Renamed and refactored |
| `backend/storage_dynamodb.py` | `backend/app/storage/dynamodb_storage.py` | Moved to storage/ |
| `backend/executor.py` | `backend/app/execution/executor.py` | Moved to execution/ |
| `backend/scheduler.py` | `backend/app/execution/scheduler.py` | Moved to execution/ |
| `backend/websocket.py` | `backend/app/websocket/broadcaster.py` | Moved to websocket/ |
| `backend/notebook_operations.py` | `backend/app/services/notebook_service.py` | Moved to services/ |
| `backend/ast_parser.py` | `backend/app/utils/ast_parser.py` | Moved to utils/ |
| `backend/graph.py` | `backend/app/execution/dependencies.py` | Merged with dependencies |
| `backend/llm_tools.py` | `backend/app/utils/llm_tools.py` | Moved to utils/ |
| `backend/demo_notebook.py` | `backend/app/utils/demo_notebook.py` | Moved to utils/ |
| `backend/notebooks/` | `backend/data/notebooks/` | Moved to data/ |
| `backend/logs/` | `backend/data/logs/` | Moved to data/ |

### New Files Created

| New Path | Purpose |
|----------|---------|
| `backend/app/core/config.py` | Configuration management |
| `backend/app/core/security.py` | Authentication & security |
| `backend/app/storage/base.py` | Storage abstraction interface |
| `backend/app/storage/__init__.py` | Storage factory |
| `backend/app/schemas/*.py` | API request/response schemas |
| `backend/app/api/deps.py` | API dependencies |
| `backend/app/api/v1/api.py` | Router aggregation |
| `backend/MIGRATION_GUIDE.md` | Developer migration guide |

---

**Plan Status**: Draft - Ready for Review
**Next Action**: Review and approve plan before implementation

