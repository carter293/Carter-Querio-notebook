---
date: 2025-12-27T17:58:30+00:00
researcher: AI Assistant
topic: "openapi-ts Integration: Introducing @hey-api/openapi-ts and Integration Plan"
tags: [research, codebase, openapi-ts, typescript, fastapi, api-client-generation]
status: complete
last_updated: 2025-12-27
last_updated_by: AI Assistant
---

# Research: openapi-ts Integration

**Date**: 2025-12-27T17:58:30+00:00
**Researcher**: AI Assistant

## Research Question

Research the [@hey-api/openapi-ts](https://github.com/hey-api/openapi-ts) library and create a plan for integrating it into this project to generate TypeScript API clients from the FastAPI OpenAPI specification.

## Summary

[@hey-api/openapi-ts](https://github.com/hey-api/openapi-ts) is a production-ready OpenAPI to TypeScript code generator that can automatically generate type-safe TypeScript clients, Zod schemas, TanStack Query hooks, and more from OpenAPI specifications. The current project uses FastAPI (which automatically generates OpenAPI specs) on the backend and manual TypeScript fetch calls on the frontend. Integrating openapi-ts would provide:

1. **Type-safe API clients** - Eliminate manual TypeScript type definitions
2. **Automatic code generation** - Keep frontend types in sync with backend changes
3. **Reduced boilerplate** - Replace manual fetch calls with generated SDK methods
4. **Optional plugins** - Add Zod validation, TanStack Query hooks, or other integrations

The integration path involves:
1. Configuring FastAPI to expose OpenAPI schema
2. Installing and configuring openapi-ts
3. Generating TypeScript client from the OpenAPI spec
4. Migrating existing API calls to use the generated client
5. Setting up CI/CD to regenerate on API changes

## Detailed Findings

### What is @hey-api/openapi-ts?

[@hey-api/openapi-ts](https://github.com/hey-api/openapi-ts) is an OpenAPI to TypeScript code generator that:

- **Generates production-ready SDKs** from OpenAPI specifications
- **Supports multiple HTTP clients**: Fetch API (native), Axios, Angular, Next.js, Nuxt, and more
- **Provides 20+ plugins** for popular libraries (Zod, TanStack Query, Valibot, etc.)
- **Highly customizable** via plugin system
- **Used by major companies**: Vercel, OpenCode, PayPal
- **MIT licensed** and actively maintained (3.7k+ stars, 284 forks)

### Key Features

1. **Type-safe SDK generation**: Automatically generates TypeScript interfaces and client methods
2. **Multiple output formats**: Can generate SDKs, types, schemas, or hooks
3. **Plugin ecosystem**: Native support for popular libraries
4. **CLI and programmatic API**: Can be run via CLI or imported as a library
5. **Configuration flexibility**: Supports multiple config file formats (TypeScript, JavaScript, JSON)

### Current Project Architecture

#### Backend API Structure

The backend uses **FastAPI** which automatically generates OpenAPI documentation:

- **Entry point**: `backend/main.py` - FastAPI app with title "Reactive Notebook"
- **API routes**: `backend/routes.py` - Contains all REST endpoints using `APIRouter`
- **API prefix**: All routes are under `/api` prefix
- **OpenAPI endpoints**: FastAPI automatically exposes:
  - `/docs` - Swagger UI documentation
  - `/openapi.json` - OpenAPI JSON schema

**Current API Endpoints** ([`backend/routes.py`](backend/routes.py)):
- `POST /api/notebooks` - Create notebook
- `GET /api/notebooks` - List notebooks
- `GET /api/notebooks/{notebook_id}` - Get notebook details
- `PUT /api/notebooks/{notebook_id}/db` - Update database connection
- `PUT /api/notebooks/{notebook_id}/name` - Rename notebook
- `POST /api/notebooks/{notebook_id}/cells` - Create cell
- `PUT /api/notebooks/{notebook_id}/cells/{cell_id}` - Update cell
- `DELETE /api/notebooks/{notebook_id}/cells/{cell_id}` - Delete cell
- `WS /api/ws/notebooks/{notebook_id}` - WebSocket for real-time updates

**Request/Response Models** ([`backend/routes.py:17-34`](backend/routes.py:17-34)):
- `CreateNotebookRequest` / `CreateNotebookResponse`
- `UpdateDbConnectionRequest`
- `CreateCellRequest`
- `UpdateCellRequest`
- `RenameNotebookRequest`

**Data Models** ([`backend/models.py`](backend/models.py)):
- `Notebook` - Main notebook structure
- `Cell` - Individual cell with code, status, outputs
- `Output` - Cell output with MIME type and data
- `CellType` (enum) - Python or SQL
- `CellStatus` (enum) - Idle, Running, Success, Error, Blocked

#### Frontend API Consumption

The frontend currently uses **manual TypeScript fetch calls**:

- **API module**: `frontend/src/api.ts` - Centralized API functions
- **Pattern**: Native `fetch` API with manual URL construction
- **Type definitions**: Manual TypeScript interfaces defined in `api.ts`
- **Error handling**: Manual error checking with `res.ok` checks
- **No type safety**: Types are manually maintained and can drift from backend

**Current API Functions** ([`frontend/src/api.ts`](frontend/src/api.ts)):
```typescript
- createNotebook(): Promise<{ notebook_id: string }>
- getNotebook(id: string): Promise<Notebook>
- listNotebooks(): Promise<NotebookMetadata[]>
- updateDbConnection(id: string, connString: string)
- createCell(notebookId: string, type: 'python' | 'sql', afterCellId?: string)
- updateCell(notebookId: string, cellId: string, code: string)
- deleteCell(notebookId: string, cellId: string)
- renameNotebook(notebookId: string, name: string): Promise<void>
```

**Component Usage** ([`frontend/src/components/Notebook.tsx`](frontend/src/components/Notebook.tsx)):
- Components import `import * as api from '../api'`
- API calls made in `useEffect` hooks and event handlers
- WebSocket handled separately via `useWebSocket.ts` hook

### Integration Benefits

1. **Type Safety**: Generated types ensure frontend matches backend exactly
2. **Reduced Maintenance**: No manual type definitions to keep in sync
3. **Better DX**: Autocomplete and type checking for all API calls
4. **Consistency**: Single source of truth (OpenAPI spec) for API contract
5. **Future-proof**: Easy to add validation (Zod), caching (TanStack Query), etc.

### Integration Plan

#### Phase 1: Setup and Configuration

1. **Install openapi-ts**:
   ```bash
   cd frontend
   npm install @hey-api/openapi-ts -D -E
   ```
   Note: Pin exact version (`-E` flag) as the library doesn't follow semantic versioning

2. **Create configuration file** (`frontend/openapi-ts.config.ts`):
   ```typescript
   import { defineConfig } from '@hey-api/openapi-ts';

   export default defineConfig({
     input: 'http://localhost:8000/openapi.json', // FastAPI OpenAPI endpoint
     output: 'src/client', // Generated client location
     client: '@hey-api/client-fetch', // Use native Fetch API
   });
   ```

3. **Add npm script** (`frontend/package.json`):
   ```json
   {
     "scripts": {
       "generate:api": "openapi-ts"
     }
   }
   ```

#### Phase 2: Generate Initial Client

1. **Start backend server** to expose OpenAPI spec:
   ```bash
   cd backend
   python main.py
   ```

2. **Generate TypeScript client**:
   ```bash
   cd frontend
   npm run generate:api
   ```

3. **Review generated files** in `frontend/src/client/`:
   - Types and interfaces
   - Client SDK methods
   - Request/response types

#### Phase 3: Migration Strategy

1. **Gradual migration**: Keep existing `api.ts` alongside generated client
2. **Update one endpoint at a time**: Start with simple endpoints (e.g., `listNotebooks`)
3. **Update components**: Replace `api.listNotebooks()` with generated client method
4. **Remove old code**: Once all endpoints migrated, remove `api.ts`

**Example Migration**:
```typescript
// Before (frontend/src/api.ts)
export async function listNotebooks(): Promise<NotebookMetadata[]> {
  const res = await fetch(`${API_BASE}/notebooks`);
  if (!res.ok) {
    throw new Error(`Failed to list notebooks: ${res.statusText}`);
  }
  const data = await res.json();
  return data.notebooks;
}

// After (using generated client)
import { client } from './client';
const { data } = await client.GET('/api/notebooks');
return data.notebooks;
```

#### Phase 4: Advanced Configuration (Optional)

1. **Add Zod validation**:
   ```typescript
   export default defineConfig({
     input: 'http://localhost:8000/openapi.json',
     output: 'src/client',
     client: '@hey-api/client-fetch',
     plugins: ['@hey-api/schemas'], // Generate Zod schemas
   });
   ```

2. **Add TanStack Query hooks** (if using React Query):
   ```typescript
   plugins: [
     '@hey-api/sdk',
     '@tanstack/react-query', // Generate useQuery hooks
   ],
   ```

3. **Customize output**:
   ```typescript
   output: {
     path: 'src/client',
     format: 'prettier', // Auto-format generated code
   },
   ```

#### Phase 5: CI/CD Integration

1. **Pre-commit hook**: Regenerate client before commits
2. **CI check**: Verify generated client is up-to-date
3. **Documentation**: Add instructions for regenerating after API changes

### Configuration Options

#### Basic Configuration
```typescript
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: 'src/client',
  client: '@hey-api/client-fetch',
});
```

#### Advanced Configuration with Plugins
```typescript
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: 'src/client',
    format: 'prettier',
  },
  client: '@hey-api/client-fetch',
  plugins: [
    '@hey-api/typescript', // TypeScript types (default)
    '@hey-api/sdk', // SDK methods (default)
    '@hey-api/schemas', // Zod schemas (optional)
    // '@tanstack/react-query', // React Query hooks (optional)
  ],
});
```

### Potential Challenges

1. **WebSocket Support**: openapi-ts focuses on REST APIs. WebSocket endpoints (`/api/ws/notebooks/{notebook_id}`) will need to remain manual or use a different approach.

2. **FastAPI OpenAPI Schema**: Need to verify FastAPI generates complete OpenAPI 3.x spec with all request/response models properly documented.

3. **Response Wrapping**: Current API wraps some responses (e.g., `{"notebooks": [...]}`). May need to adjust backend or handle unwrapping in generated client.

4. **Error Handling**: Generated client may have different error handling patterns than current manual implementation.

5. **Development Workflow**: Need to ensure backend is running when generating client, or use a static OpenAPI file.

### Recommended Approach

1. **Start Simple**: Begin with basic configuration and native Fetch client
2. **Test Incrementally**: Generate client and test with one endpoint first
3. **Iterate**: Add plugins and customization as needed
4. **Document**: Update README with generation instructions
5. **Automate**: Add scripts to make regeneration easy

### Alternative: Static OpenAPI File

Instead of fetching from running server, can export OpenAPI spec to file:

```python
# backend/export_openapi.py
import json
from main import app

with open('openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
```

Then configure openapi-ts to use file:
```typescript
input: './openapi.json', // Relative to frontend directory
```

## Code References

### Backend API Definition
- `backend/main.py:7` - FastAPI app initialization
- `backend/main.py:38` - Router inclusion with `/api` prefix
- `backend/routes.py:15` - APIRouter definition
- `backend/routes.py:17-34` - Request/Response Pydantic models
- `backend/routes.py:38-256` - All REST API endpoints
- `backend/models.py` - Data models (Notebook, Cell, Output, etc.)

### Frontend API Consumption
- `frontend/src/api.ts:1` - API base URL constant
- `frontend/src/api.ts:3-45` - TypeScript type definitions
- `frontend/src/api.ts:47-106` - API function implementations
- `frontend/src/components/Notebook.tsx:13-20` - API usage in components
- `frontend/src/App.tsx:12-40` - API calls in main app component

### FastAPI OpenAPI Endpoints
- FastAPI automatically exposes `/openapi.json` endpoint
- FastAPI automatically exposes `/docs` Swagger UI
- These are available when backend server is running

## Architecture Insights

### Current Pattern
- **Backend**: FastAPI with Pydantic models → Auto-generates OpenAPI spec
- **Frontend**: Manual TypeScript types + fetch calls → No type safety guarantee
- **Gap**: Types can drift between backend and frontend

### Proposed Pattern
- **Backend**: FastAPI with Pydantic models → Auto-generates OpenAPI spec
- **Codegen**: openapi-ts reads OpenAPI spec → Generates TypeScript client
- **Frontend**: Uses generated client → Type-safe API calls
- **Benefit**: Single source of truth (OpenAPI spec) ensures type safety

### WebSocket Consideration
- WebSocket endpoints (`/api/ws/notebooks/{notebook_id}`) are not part of OpenAPI spec
- Current `useWebSocket.ts` hook will remain unchanged
- Only REST endpoints will benefit from openapi-ts generation

## Historical Context (from thoughts/)

No existing research documents found on API client generation or OpenAPI integration in this project.

## Related Research

No related research documents found. This is the first exploration of API client generation tools.

## Open Questions

1. **OpenAPI Spec Completeness**: Does FastAPI generate a complete OpenAPI 3.x spec with all request/response models? Need to verify by checking `/openapi.json` endpoint.

2. **Response Format**: Some endpoints return wrapped responses (e.g., `{"notebooks": [...]}`). Will generated client handle this correctly, or do we need to adjust backend response models?

3. **Error Response Format**: How does FastAPI format error responses? Will generated client handle HTTP exceptions correctly?

4. **Plugin Selection**: Should we start with basic SDK generation, or include Zod schemas or TanStack Query hooks from the beginning?

5. **Development Workflow**: Should we use live OpenAPI endpoint or export static file? Static file might be better for CI/CD.

6. **Version Pinning**: The library recommends pinning exact versions. Should we commit `package-lock.json` changes?

7. **Generated Code Location**: Is `src/client` the best location, or should it be `src/generated` or `src/api-client`?

8. **Type Naming**: How will generated types be named? Will they conflict with existing types in `api.ts`?

## Next Steps

1. **Verify OpenAPI Spec**: Start backend and check `/openapi.json` endpoint to see generated spec
2. **Install and Configure**: Install openapi-ts and create basic configuration
3. **Generate Test Client**: Run generation and inspect output
4. **Migrate One Endpoint**: Update one component to use generated client
5. **Document Process**: Update README with generation instructions
6. **Plan Full Migration**: Create migration checklist for all endpoints

## References

- [@hey-api/openapi-ts GitHub Repository](https://github.com/hey-api/openapi-ts)
- [Hey API Documentation](https://heyapi.dev)
- [FastAPI OpenAPI Documentation](https://fastapi.tiangolo.com/advanced/openapi-customization/)

