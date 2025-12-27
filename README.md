# Reactive Notebook

A reactive notebook interface where code cells automatically re-execute when their dependencies change. Built for the Querio take-home challenge.

## Features

- **Reactive Execution**: Edit a cell and dependent cells automatically re-run
- **Python + SQL Support**: Mix Python logic with database queries
- **Real-time Updates**: WebSocket streaming shows execution status live
- **Dependency Tracking**: Static AST analysis builds accurate dependency graph
- **Error Handling**: Clear error messages, blocked state for failed dependencies
- **Template Variables**: Use Python variables in SQL with `{variable}` syntax
- **Cycle Detection**: Circular dependencies are automatically detected and reported

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (optional, for SQL cells)

### Backend Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or use the main.py directly
python main.py
```

Backend runs on `http://localhost:8000`

### Frontend Setup

```bash
# Install Node dependencies
cd frontend
npm install

# Start the development server
npm run dev
```

Frontend runs on `http://localhost:3000`

### API Client Generation

The TypeScript API client is automatically generated from the FastAPI OpenAPI specification using [@hey-api/openapi-ts](https://github.com/hey-api/openapi-ts).

#### Regenerating the Client

1. Start the backend server:
   ```bash
   cd backend && python main.py
   ```

2. Generate the client:
   ```bash
   cd frontend && npm run generate:api
   ```

3. The generated client will be in `frontend/src/client/`

#### When to Regenerate

- After adding new API endpoints
- After modifying request/response models
- After updating FastAPI route definitions

#### Using Static OpenAPI File (for CI/CD)

Instead of fetching from running server, you can export the OpenAPI spec:

```bash
cd backend && python export_openapi.py
```

Then update `frontend/openapi-ts.config.ts` to use the file:

```typescript
input: '../openapi.json', // Relative to frontend directory
```

### Running Tests

```bash
# Run backend tests
pytest backend/tests/ -v

# The core AST parser and graph tests should pass
# (Note: async executor tests require pytest-asyncio configuration)
```

## Architecture

### Backend (FastAPI + Python)

- **models.py**: Data structures (Notebook, Cell, Graph, KernelState)
- **ast_parser.py**: Static dependency extraction via Python AST
- **graph.py**: DAG construction, cycle detection, topological sort
- **executor.py**: Python/SQL execution engines
- **scheduler.py**: Reactive execution queue with dependency tracking
- **websocket.py**: Real-time event broadcasting
- **routes.py**: HTTP API endpoints and WebSocket handler
- **main.py**: FastAPI application entry point

### Frontend (React + TypeScript)

- **Cell.tsx**: Individual cell component with Monaco editor
- **Notebook.tsx**: Notebook container with WebSocket integration
- **App.tsx**: Main application component
- **api-client.ts**: Generated API client wrapper with type definitions (uses OpenAPI-generated client)
- **useWebSocket.ts**: WebSocket hook for live updates

## How It Works

1. **User edits cell code** → Frontend calls `PUT /api/notebooks/{id}/cells/{cell_id}`
2. **Backend extracts dependencies** → AST parser finds reads/writes
3. **Graph is rebuilt** → Edges created between cells with matching variables
4. **User runs cell** → WebSocket message `{"type": "run_cell", "cellId": "..."}`
5. **Scheduler executes** → Cell + all dependents in topological order
6. **Results stream back** → WebSocket broadcasts status/output/errors
7. **Frontend updates** → UI shows live execution state

## Dependency Extraction

### Python Cells

```python
x = 10          # writes: {x}
y = x * 2       # reads: {x}, writes: {y}
z = y + x       # reads: {x, y}, writes: {z}
```

Dependency graph: `x → y → z` (also `x → z`)

### SQL Cells

```sql
SELECT * FROM users WHERE id = {user_id}
-- reads: {user_id}, writes: {}
```

SQL cells read Python variables via template syntax but don't write any.

## API Reference

### HTTP Endpoints

- `POST /api/notebooks` - Create a new notebook
- `GET /api/notebooks/{id}` - Get notebook details
- `PUT /api/notebooks/{id}/db` - Update database connection string
- `POST /api/notebooks/{id}/cells` - Create a new cell
- `PUT /api/notebooks/{id}/cells/{cell_id}` - Update cell code
- `DELETE /api/notebooks/{id}/cells/{cell_id}` - Delete a cell

### WebSocket

- `WS /api/ws/notebooks/{id}` - Real-time updates

**Client → Server:**
```json
{"type": "run_cell", "cellId": "..."}
```

**Server → Client:**
```json
{"type": "cell_status", "cellId": "...", "status": "running"}
{"type": "cell_stdout", "cellId": "...", "data": "output"}
{"type": "cell_result", "cellId": "...", "result": {...}}
{"type": "cell_error", "cellId": "...", "error": "error message"}
```

## Usage Examples

### Basic Python Reactivity

1. Create a Python cell:
   ```python
   x = 10
   print(f"x = {x}")
   ```
   Run it → see output

2. Create another Python cell:
   ```python
   y = x * 2
   print(f"y = {y}")
   ```
   Run it → see `y = 20`

3. Edit first cell to `x = 20` → second cell automatically reruns → see `y = 40`

### SQL with Python Variables

1. Set database connection string in the UI

2. Create Python cell:
   ```python
   user_id = 5
   ```

3. Create SQL cell:
   ```sql
   SELECT * FROM users WHERE id = {user_id}
   ```

4. Run both → SQL query executes with `id = 5`

5. Edit Python cell to `user_id = 10` → SQL cell auto-reruns with new value

### Error Handling

1. Create cell A: `x = 10`
2. Create cell B: `y = x * 2`
3. Create cell C: `z = y + x`

4. Edit cell B to introduce error: `y = undefined_var`
5. Run cell B → see error message
6. Cell C shows "blocked" status (preserves last output)
7. Fix cell B → cell C automatically recovers and reruns

### Cycle Detection

1. Create cell A: `x = y + 1` (reads: {y}, writes: {x})
2. Create cell B: `y = x + 1` (reads: {x}, writes: {y})
3. Both cells show error: "Circular dependency detected"

## Project Structure

```
reactive-notebook/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── models.py            # Data models
│   ├── ast_parser.py        # AST dependency extraction
│   ├── graph.py             # DAG construction
│   ├── executor.py          # Execution engines
│   ├── scheduler.py         # Reactive scheduler
│   ├── websocket.py         # WebSocket broadcaster
│   ├── routes.py            # API endpoints
│   └── tests/
│       ├── __init__.py
│       ├── test_ast_parser.py
│       ├── test_graph.py
│       └── test_executor.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Cell.tsx
│   │   │   └── Notebook.tsx
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api.ts
│   │   ├── useWebSocket.ts
│   │   ├── index.css
│   │   └── vite-env.d.ts
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── requirements.txt
├── pytest.ini
└── README.md
```

## Known Limitations

### By Design (V1 Scope)

- **No mutation tracking**: `df.append()` or `list.pop()` not detected (only assignments)
- **Single worker only**: In-memory state doesn't support multi-worker deployment
- **No persistence**: Notebooks lost on server restart (in-memory only)
- **Simple SQL escaping**: Uses basic string replacement (production should use parameterized queries)
- **Import star ignored**: `from module import *` not tracked

### Technical Constraints

- No cell output history/versioning
- No undo/redo functionality
- No drag-and-drop cell reordering
- No rich visualizations beyond basic HTML tables
- No package installation within notebooks
- Dynamic `exec()`/`eval()` dependencies not detected

## Testing

### Automated Tests

```bash
# Run all tests
pytest backend/tests/ -v

# Run specific test file
pytest backend/tests/test_ast_parser.py -v
pytest backend/tests/test_graph.py -v
```

### Manual Testing Checklist

- [ ] Create notebook from scratch
- [ ] Add Python and SQL cells
- [ ] Edit code in cells
- [ ] Run cells and see execution status
- [ ] Create dependency chain (A → B → C)
- [ ] Edit upstream cell, verify downstream auto-reruns
- [ ] Create circular dependency, verify error shown
- [ ] Create error in cell, verify dependents blocked
- [ ] Fix error, verify dependents recover
- [ ] Delete cell, verify graph updates
- [ ] Set DB connection, verify SQL works
- [ ] Use {variable} in SQL, verify substitution
- [ ] Test Ctrl+Enter keyboard shortcut
- [ ] Test with 10+ cells (performance)

## Production Considerations

For production deployment, consider:

1. **Database persistence** - Store notebooks in PostgreSQL instead of in-memory
2. **Authentication** - Add user authentication and authorization
3. **Parameterized queries** - Use proper SQL parameterization instead of string substitution
4. **Code sandboxing** - Run code execution in isolated containers
5. **Multi-worker coordination** - Use Redis or message queue for shared state
6. **Cell output versioning** - Track execution history
7. **Rate limiting** - Prevent WebSocket abuse
8. **Input validation** - Sanitize all user inputs
9. **Error recovery** - Handle WebSocket disconnections gracefully
10. **Monitoring** - Add logging and metrics

## Technology Stack

**Backend:**
- FastAPI - Web framework
- Uvicorn - ASGI server
- asyncpg - PostgreSQL async driver
- Pydantic - Data validation
- pytest - Testing

**Frontend:**
- React - UI library
- TypeScript - Type safety
- Vite - Build tool
- Monaco Editor - Code editor
- Native WebSocket API - Real-time communication

## License

MIT

## Author

Built by Claude Code for the Querio Take-Home Challenge (December 2025)

## Development Timeline

- **Phase 1**: Backend foundation (models, AST parser, graph) - ✅ Complete
- **Phase 2**: Reactive execution & WebSocket - ✅ Complete
- **Phase 3**: SQL support & templates - ✅ Complete
- **Phase 4**: React frontend - ✅ Complete
- **Phase 5**: Testing & documentation - ✅ Complete

Total development time: ~4-6 hours of focused implementation
