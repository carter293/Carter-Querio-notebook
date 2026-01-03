# Reactive Notebook Backend

FastAPI backend for the Reactive Notebook application.

## Project Structure

```
backend/
├── app/                        # Main application package
│   ├── api/                    # API layer
│   │   ├── deps.py            # API dependencies (auth)
│   │   └── v1/                # API version 1
│   │       ├── state.py       # Shared application state
│   │       ├── api.py         # Router aggregation
│   │       └── endpoints/     # Route handlers
│   │           ├── notebooks.py  # Notebook CRUD
│   │           ├── cells.py      # Cell CRUD
│   │           ├── websocket.py  # WebSocket real-time
│   │           └── chat.py       # LLM chat
│   ├── core/                  # Configuration & security
│   │   ├── config.py         # Settings (Pydantic)
│   │   └── security.py       # JWT authentication (Clerk)
│   ├── models/                # Domain models
│   │   ├── cell.py           # Cell, Output, CellType, CellStatus
│   │   ├── graph.py          # Dependency graph
│   │   └── notebook.py       # Notebook, KernelState
│   ├── schemas/               # API request/response models
│   │   ├── notebook.py       # Notebook schemas
│   │   ├── cell.py           # Cell schemas
│   │   └── chat.py           # Chat schemas
│   ├── services/              # Business logic
│   │   └── notebook_service.py  # Locked operations
│   ├── storage/               # Data persistence
│   │   ├── base.py           # Storage interface
│   │   ├── file_storage.py   # Local file storage
│   │   └── dynamodb_storage.py  # AWS DynamoDB
│   ├── execution/             # Notebook execution engine
│   │   ├── executor.py       # Python/SQL execution
│   │   ├── scheduler.py      # Concurrent execution queue
│   │   └── dependencies.py   # Graph & topological sort
│   ├── websocket/             # Real-time communication
│   │   └── broadcaster.py    # WebSocket broadcaster
│   ├── utils/                 # Utilities
│   │   ├── ast_parser.py     # Variable extraction
│   │   ├── llm_tools.py      # LLM tool interface
│   │   └── demo_notebook.py  # Demo notebook generator
│   └── main.py                # Application entrypoint
├── data/                      # Runtime data (local dev)
│   ├── notebooks/            # Notebook JSON files
│   └── logs/                 # Application logs
├── tests/                     # Test suite
├── scripts/                   # Deployment & utilities
├── Dockerfile                 # Container definition
├── requirements.txt           # Dependencies
└── pytest.ini                 # Test configuration
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
NOTEBOOK_STORAGE_DIR=backend/data/notebooks
```

### Running the Application

```bash
# Development mode (auto-reload)
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

### Layered Design

- **API Layer** (`app/api/`): HTTP/WebSocket interface, versioning (v1)
- **Services** (`app/services/`): Business logic with locking
- **Models** (`app/models/`): Domain models (dataclasses)
- **Schemas** (`app/schemas/`): API contracts (Pydantic)
- **Storage** (`app/storage/`): Data persistence abstraction
- **Execution** (`app/execution/`): Cell execution engine
- **Core** (`app/core/`): Configuration and authentication

### Key Features

- **Authentication**: Clerk JWT-based authentication
- **Real-time Updates**: WebSocket support for collaborative editing
- **Storage Backends**: File storage (dev) and DynamoDB (production)
- **Execution Engine**: Python and SQL cell execution with dependency resolution
- **LLM Integration**: Chat interface with tool execution
- **Type Safety**: Pydantic for validation, type hints throughout

## API Endpoints

All endpoints are prefixed with `/api/v1`

### Notebooks
- `POST /notebooks` - Create notebook
- `GET /notebooks` - List notebooks
- `GET /notebooks/{id}` - Get notebook
- `PUT /notebooks/{id}/name` - Rename notebook
- `PUT /notebooks/{id}/db` - Update DB connection
- `DELETE /notebooks/{id}` - Delete notebook

### Cells
- `POST /notebooks/{id}/cells` - Create cell
- `PUT /notebooks/{id}/cells/{cell_id}` - Update cell
- `DELETE /notebooks/{id}/cells/{cell_id}` - Delete cell

### WebSocket
- `WS /ws/notebooks/{id}` - Real-time notebook updates

### Chat
- `POST /chat/{id}` - LLM chat with notebook context

### Health
- `GET /health` - Health check

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
- Dependency injection for authentication
- Lock-based concurrency control for notebook operations
- Store data in domain models, validate with schemas

### Import Paths

```python
# Models (internal data structures)
from app.models import Notebook, Cell, CellType, CellStatus

# Schemas (API contracts)
from app.schemas import NotebookResponse, CreateCellRequest

# Services (business logic)
from app.services import locked_update_cell

# Storage
from app.storage import save_notebook, load_notebook

# Execution
from app.execution import execute_python_cell, scheduler

# Config & Auth
from app.core import settings, get_current_user
```

## Deployment

### Environment Variables

Required:
- `CLERK_FRONTEND_API` - Clerk API URL

Optional:
- `ALLOWED_ORIGINS` - CORS origins (default: localhost)
- `DYNAMODB_ENABLED` - Use DynamoDB (default: false)
- `DYNAMODB_TABLE_NAME` - DynamoDB table name
- `AWS_REGION` - AWS region (default: us-east-1)
- `NOTEBOOK_STORAGE_DIR` - File storage path (default: backend/data/notebooks)

### Production Setup

1. Set environment variables
2. Enable DynamoDB for production storage
3. Configure CORS for your domain
4. Deploy with Dockerfile or ECS
5. Ensure single worker (in-memory state)

## Migration from Old Structure

If you have code using the old flat structure:

```python
# Old
from models import Notebook
from storage import save_notebook
from executor import execute_python_cell

# New
from app.models import Notebook
from app.storage import save_notebook
from app.execution import execute_python_cell
```

All functionality is preserved - only import paths have changed.

## License

See parent repository for license information.

