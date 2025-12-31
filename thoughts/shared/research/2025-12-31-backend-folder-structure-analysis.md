---
date: 2025-12-31T12:20:06Z
researcher: AI Research Agent
topic: "FastAPI Backend Folder Structure Analysis"
tags: [research, backend, fastapi, architecture, refactoring]
status: complete
last_updated: 2025-12-31
last_updated_by: AI Research Agent
---

# Research: FastAPI Backend Folder Structure Analysis

**Date**: 2025-12-31 12:20:06 GMT
**Researcher**: AI Research Agent
**Repository**: Carter-Querio-notebook (7c4d6a252b45f2e6b26f9f70a57ecfb3656c9cc9)

## Research Question

What is the current backend folder structure, how should a production-ready FastAPI backend be organized according to best practices, and what changes are needed to reorganize the Carter-Querio-notebook backend?

## Summary

The current backend is organized as a **flat module structure** where most Python modules live directly in the `backend/` directory. While this works for small projects, it lacks the separation of concerns and scalability needed as the application grows. Industry best practices recommend organizing FastAPI applications into layers (API routes, business logic, data models, storage, configuration, utilities) within subdirectories under an `app/` or similar root.

The backend currently has 15+ Python modules at the root level, mixed with data directories (`notebooks/`, `logs/`), scripts, tests, and a virtual environment. This makes it harder to:
- Quickly understand the application's structure
- Separate concerns (routes, models, business logic)
- Implement versioned APIs
- Scale the team and codebase
- Maintain clear boundaries between layers

**Key Finding**: The backend needs to be reorganized into a layered, domain-driven structure following FastAPI best practices.

## Current State Analysis

### Current Directory Structure

```
backend/
├── __init__.py
├── main.py                    # FastAPI app entrypoint
├── routes.py                  # API routes (notebooks, cells, WebSocket)
├── chat.py                    # Chat/LLM API routes
├── models.py                  # Data models (Notebook, Cell, etc.)
├── storage.py                 # Storage abstraction layer
├── storage_dynamodb.py        # DynamoDB storage implementation
├── executor.py                # Cell execution logic
├── scheduler.py               # Execution scheduling
├── websocket.py               # WebSocket broadcaster
├── notebook_operations.py     # Thread-safe notebook mutations
├── ast_parser.py              # Dependency extraction
├── graph.py                   # Dependency graph management
├── llm_tools.py               # LLM tool definitions
├── demo_notebook.py           # Demo notebook creation
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── notebooks/                 # Data directory (should not be in source)
│   ├── *.json
│   └── test/
├── logs/                      # Logs directory
│   └── audit/
├── scripts/                   # Deployment and utility scripts
│   ├── deploy.sh
│   ├── docker-test.sh
│   └── ...
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── conftest.py
│   └── test_*.py
└── venv/                      # Virtual environment (should be .gitignored)
```

### Current Component Responsibilities

Based on deep code analysis, the backend components are:

1. **Application Entrypoint** (`main.py:168 lines`)
   - FastAPI app initialization
   - CORS configuration
   - Clerk JWT authentication setup
   - Router inclusion
   - Lifecycle management (loading notebooks on startup)

2. **API Routes** (`routes.py:651 lines`, `chat.py`)
   - REST endpoints for notebooks and cells (CRUD)
   - WebSocket endpoint for real-time updates
   - Chat/LLM streaming endpoint (SSE)
   - Authentication dependency injection
   - In-memory notebook state management

3. **Data Models** (`models.py:90 lines`)
   - Core dataclasses: `Notebook`, `Cell`, `Output`, `Graph`, `KernelState`
   - Enums: `CellType`, `CellStatus`, `MimeType`
   - Concurrency control (locks)

4. **Storage Layer** (`storage.py`, `storage_dynamodb.py`)
   - Abstraction for file-based and DynamoDB storage
   - Notebook persistence (save, load, list, delete)
   - Atomic file writes
   - Async DynamoDB operations

5. **Execution Engine** (`executor.py:236 lines`)
   - Python and SQL cell execution
   - Output capture (stdout, images, tables, charts)
   - MIME bundle conversion (matplotlib, plotly, pandas, etc.)

6. **Scheduler** (`scheduler.py:178 lines`)
   - Concurrent cell execution management
   - Dependency resolution and topological sorting
   - Per-notebook execution queues

7. **WebSocket Broadcasting** (`websocket.py:110 lines`)
   - Real-time client communication
   - Per-notebook connection tracking
   - Event broadcasting (cell status, output, CRUD events)

8. **Notebook Operations** (`notebook_operations.py:166 lines`)
   - Thread-safe, lock-guarded mutations
   - Cell creation, update, deletion
   - Dependency extraction and graph rebuilding
   - Cycle detection

9. **Dependency Management** (`ast_parser.py`, `graph.py`)
   - Python/SQL code parsing for variable dependencies
   - Dependency graph building and management
   - Cycle detection

10. **LLM Tools** (`llm_tools.py`)
    - Tool definitions for LLM integration
    - Agentic workflow support

## FastAPI Best Practices Research

### Industry-Standard Structure (2024-2025)

Based on research from FastAPI documentation, community best practices, and production applications:

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entrypoint
│   │
│   ├── api/                    # API layer
│   │   ├── __init__.py
│   │   ├── deps.py             # Common dependencies
│   │   └── v1/                 # API versioning
│   │       ├── __init__.py
│   │       ├── api.py          # Router aggregation
│   │       └── endpoints/      # Route handlers by domain
│   │           ├── __init__.py
│   │           ├── notebooks.py
│   │           ├── cells.py
│   │           ├── chat.py
│   │           └── websocket.py
│   │
│   ├── core/                   # Configuration & utilities
│   │   ├── __init__.py
│   │   ├── config.py           # Settings (Pydantic BaseSettings)
│   │   ├── security.py         # Authentication/authorization
│   │   └── logging.py          # Logging configuration
│   │
│   ├── models/                 # Domain models (business logic)
│   │   ├── __init__.py
│   │   ├── notebook.py
│   │   ├── cell.py
│   │   └── graph.py
│   │
│   ├── schemas/                # Pydantic models (API contracts)
│   │   ├── __init__.py
│   │   ├── notebook.py         # Request/response models
│   │   ├── cell.py
│   │   └── chat.py
│   │
│   ├── services/               # Business logic layer
│   │   ├── __init__.py
│   │   ├── notebook_service.py
│   │   ├── execution_service.py
│   │   └── chat_service.py
│   │
│   ├── storage/                # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py             # Storage abstraction
│   │   ├── file_storage.py
│   │   └── dynamodb_storage.py
│   │
│   ├── execution/              # Execution engine
│   │   ├── __init__.py
│   │   ├── executor.py
│   │   ├── scheduler.py
│   │   └── dependencies.py
│   │
│   ├── websocket/              # Real-time communication
│   │   ├── __init__.py
│   │   └── broadcaster.py
│   │
│   └── utils/                  # Utility functions
│       ├── __init__.py
│       ├── ast_parser.py
│       └── llm_tools.py
│
├── tests/                      # Test suite (mirrors app structure)
│   ├── __init__.py
│   ├── conftest.py
│   └── unit/
│       └── ...
│
├── scripts/                    # Deployment & utility scripts
│   └── ...
│
├── data/                       # Data directory (dev only)
│   └── notebooks/
│
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── README.md
```

### Key Principles

1. **Separation of Concerns**: Each directory has a clear responsibility
   - `api/` - HTTP/WebSocket interface
   - `models/` - Business logic and domain models
   - `schemas/` - API contracts (request/response)
   - `services/` - Business logic orchestration
   - `storage/` - Data persistence
   - `core/` - Configuration and cross-cutting concerns

2. **API Versioning**: Support for v1, v2, etc. for backward compatibility

3. **Dependency Injection**: Clean separation of dependencies in `api/deps.py`

4. **Configuration Management**: Centralized in `core/config.py` using Pydantic

5. **Testability**: Structure mirrors the app for easy testing

6. **Scalability**: Easy to add new domains/features without cluttering

## Detailed Findings

### Authentication Pattern

**Current Implementation** (`main.py:76-153`)
- JWT verification using PyJWT and Clerk's JWKS endpoint
- Dependency function `get_current_user(request: Request)`
- Extracts user_id from JWT 'sub' claim
- Handles token expiration and validation errors

**Best Practice**: Move to `app/core/security.py` for centralization

### Storage Pattern

**Current Implementation** (`storage.py`, `storage_dynamodb.py`)
- Abstraction layer with environment-based switching
- File storage for dev, DynamoDB for production
- Atomic writes with tempfile
- Async DynamoDB operations

**Best Practice**: Already follows good patterns, just needs better organization in `app/storage/`

### WebSocket Pattern

**Current Implementation** (`websocket.py`, `routes.py:497-651`)
- Per-notebook connection tracking
- Broadcast to all clients
- Dead connection cleanup
- In-band WebSocket authentication

**Best Practice**: Move to `app/websocket/` module

### API Routes Pattern

**Current Implementation** (`routes.py:651 lines`)
- Single large file with all notebook/cell endpoints
- Dependency injection for auth
- Resource ownership checks
- WebSocket endpoint in same file

**Best Practice**: Split by domain into `app/api/v1/endpoints/` (notebooks.py, cells.py, websocket.py)

## Architecture Insights

### Current Strengths
1. **Clear async patterns** - Good use of async/await throughout
2. **Strong concurrency control** - Lock-based operations prevent race conditions
3. **Separation of storage** - Storage abstraction is well-designed
4. **Real-time updates** - WebSocket broadcasting is robust
5. **Dependency injection** - Authentication uses FastAPI's DI system
6. **Type hints** - Consistent use of Python type annotations

### Current Issues
1. **Flat structure** - Hard to navigate with 15+ modules at root
2. **Large route file** - `routes.py` has 651 lines with mixed concerns
3. **No API versioning** - Can't maintain backward compatibility easily
4. **Mixed responsibilities** - `main.py` handles too much (auth setup, notebook loading)
5. **Data in source tree** - `notebooks/` and `logs/` shouldn't be in source directory
6. **No schemas separation** - Pydantic models mixed with business logic

### Patterns to Maintain
- Async/await everywhere
- Lock-based concurrency control
- Dependency injection for authentication
- WebSocket per-notebook connection management
- Storage abstraction layer
- Atomic file writes

## Code References

- `backend/main.py:1-168` - Application entrypoint and auth setup
- `backend/routes.py:1-651` - All API routes (notebooks, cells, WebSocket)
- `backend/models.py:1-90` - Core data models
- `backend/storage.py:1-245` - Storage abstraction
- `backend/storage_dynamodb.py:1-239` - DynamoDB implementation
- `backend/executor.py:1-236` - Execution engine
- `backend/scheduler.py:1-178` - Scheduler
- `backend/websocket.py:1-110` - WebSocket broadcaster
- `backend/notebook_operations.py:1-166` - Lock-guarded operations
- `backend/ast_parser.py` - Dependency extraction
- `backend/graph.py` - Dependency graph
- `backend/llm_tools.py` - LLM tools
- `backend/chat.py` - Chat API

## References

- FastAPI Best Practices: https://www.compilenrun.com/docs/framework/fastapi/fastapi-best-practices/fastapi-project-structure/
- FastAPI Official Documentation: https://fastapi.tiangolo.com/
- Research conducted: 2025-12-31

## Recommendations

1. **Create layered structure** following best practices
2. **Split routes.py** into domain-specific endpoint modules
3. **Separate Pydantic schemas** from domain models
4. **Move authentication** to `core/security.py`
5. **Version the API** with `api/v1/` structure
6. **Relocate data directories** outside source tree
7. **Extract services layer** for business logic
8. **Maintain all existing patterns** (async, locks, DI, storage abstraction)

## Open Questions

None - research is complete and ready for implementation planning.

