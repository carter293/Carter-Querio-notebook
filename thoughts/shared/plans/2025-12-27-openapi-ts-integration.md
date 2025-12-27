---
date: 2025-12-27T18:06:06+00:00
planner: AI Assistant
topic: "OpenAPI TypeScript Client Integration: Integrating @hey-api/openapi-ts"
tags: [planning, implementation, openapi-ts, typescript, fastapi, api-client-generation, frontend]
status: draft
last_updated: 2025-12-27
last_updated_by: AI Assistant
---

# OpenAPI TypeScript Client Integration Implementation Plan

**Date**: 2025-12-27T18:06:06+00:00  
**Planner**: AI Assistant

## Overview

This plan implements the integration of [@hey-api/openapi-ts](https://github.com/hey-api/openapi-ts) to automatically generate type-safe TypeScript API clients from the FastAPI OpenAPI specification. This will replace the current manual TypeScript API module (`frontend/src/api.ts`) with generated code, ensuring type safety, reducing maintenance burden, and keeping frontend types automatically synchronized with backend changes.

## Current State Analysis

### Backend API Structure
- **Framework**: FastAPI (`backend/main.py:7`) automatically generates OpenAPI 3.x specification
- **OpenAPI Endpoint**: Available at `/openapi.json` when server is running
- **API Routes**: All REST endpoints defined in `backend/routes.py` under `/api` prefix
- **Request/Response Models**: Pydantic models defined in `backend/routes.py:17-34` and `backend/models.py`
- **Endpoints**:
  - `POST /api/notebooks` - Create notebook
  - `GET /api/notebooks` - List notebooks (returns `{"notebooks": [...]}`)
  - `GET /api/notebooks/{notebook_id}` - Get notebook details
  - `PUT /api/notebooks/{notebook_id}/db` - Update database connection
  - `PUT /api/notebooks/{notebook_id}/name` - Rename notebook
  - `POST /api/notebooks/{notebook_id}/cells` - Create cell
  - `PUT /api/notebooks/{notebook_id}/cells/{cell_id}` - Update cell
  - `DELETE /api/notebooks/{notebook_id}/cells/{cell_id}` - Delete cell
  - `WS /api/ws/notebooks/{notebook_id}` - WebSocket (not part of OpenAPI spec)

### Frontend API Consumption
- **Current Implementation**: Manual TypeScript module (`frontend/src/api.ts`)
- **Pattern**: Native `fetch` API with manual URL construction and type definitions
- **Type Definitions**: Manually maintained TypeScript interfaces (`frontend/src/api.ts:3-45`)
- **API Functions**: 8 functions using manual fetch calls (`frontend/src/api.ts:47-106`)
- **Usage**: Imported as `import * as api from '../api'` in components
  - `frontend/src/App.tsx:4` - Uses `api.listNotebooks()`, `api.createNotebook()`, `api.renameNotebook()`
  - `frontend/src/components/Notebook.tsx:4` - Uses `api.getNotebook()`, `api.updateCell()`, `api.deleteCell()`, `api.createCell()`, `api.updateDbConnection()`
  - `frontend/src/components/NotebookSelector.tsx:5` - Uses `api.NotebookMetadata[]` type

### Key Constraints Discovered
1. **Response Wrapping**: Some endpoints wrap responses (e.g., `listNotebooks` returns `{"notebooks": [...]}`) - need to handle unwrapping
2. **Error Handling**: Current implementation has inconsistent error handling (some functions check `res.ok`, others don't)
3. **WebSocket**: WebSocket endpoints are not part of OpenAPI spec and will remain manual
4. **Type Drift Risk**: Manual types can drift from backend Pydantic models

## System Context Analysis

The frontend API module (`frontend/src/api.ts`) serves as the single point of communication between the React frontend and the FastAPI backend. Components rely on this module for all REST API operations, while WebSocket communication is handled separately via `useWebSocket.ts`.

**This plan addresses a root cause**: The current manual API client implementation creates a maintenance burden and type safety risk. By generating the client from the OpenAPI specification, we establish a single source of truth (the backend API definition) that automatically keeps frontend types synchronized. This is a foundational improvement that will prevent type drift and reduce bugs.

The approach is justified because:
1. FastAPI already generates a complete OpenAPI specification
2. The manual API module is a clear abstraction layer that can be cleanly replaced
3. Generated clients provide better type safety than manual implementations
4. The migration can be done incrementally without breaking existing functionality

## Desired End State

After this plan is complete:

1. **Generated TypeScript Client**: Type-safe API client automatically generated from FastAPI OpenAPI spec
2. **Replaced Manual API Module**: `frontend/src/api.ts` replaced with generated client usage
3. **Type Safety**: Frontend types automatically match backend Pydantic models
4. **Automated Regeneration**: Scripts and documentation for regenerating client when API changes
5. **No Breaking Changes**: All existing component functionality continues to work identically
6. **WebSocket Unchanged**: WebSocket implementation remains manual and separate

### Verification Criteria
- All components compile without errors
- All API calls work identically to current implementation
- TypeScript type checking passes with no type errors
- Generated types match backend response models exactly
- Developer workflow includes easy client regeneration process

### Key Discoveries:
- FastAPI automatically exposes `/openapi.json` endpoint (`backend/main.py:7`)
- Current API module uses inconsistent error handling patterns
- Response wrapping (`{"notebooks": [...]}`) needs special handling
- Components import API functions directly, making migration straightforward
- WebSocket endpoints are separate and won't be affected

## What We're NOT Doing

1. **WebSocket Integration**: WebSocket endpoints (`/api/ws/notebooks/{notebook_id}`) are not part of OpenAPI spec and will remain manual
2. **Backend Changes**: No modifications to FastAPI routes or models (unless needed for OpenAPI spec completeness)
3. **Advanced Plugins**: Not implementing Zod validation or TanStack Query hooks in initial phase (can be added later)
4. **CI/CD Integration**: Not setting up automated CI/CD checks in this plan (documented for future)
5. **Response Model Changes**: Not changing backend response formats unless necessary for OpenAPI spec

## Implementation Approach

The integration will be done incrementally:

1. **Setup**: Install and configure `@hey-api/openapi-ts` with basic configuration
2. **Generate**: Generate initial TypeScript client from running FastAPI server
3. **Migrate**: Replace manual API calls one endpoint at a time
4. **Test**: Verify each migrated endpoint works correctly
5. **Cleanup**: Remove old manual API module once all endpoints migrated

This incremental approach allows testing at each step and minimizes risk.

## Phase 1: Setup and Configuration

### Overview
Install `@hey-api/openapi-ts` and create configuration file to generate TypeScript client from FastAPI OpenAPI specification.

### Changes Required:

#### 1. Install Dependencies
**File**: `frontend/package.json`
**Changes**: Add `@hey-api/openapi-ts` and `@hey-api/client-fetch` as dev dependencies

```json
{
  "devDependencies": {
    "@hey-api/openapi-ts": "^1.0.0",
    "@hey-api/client-fetch": "^1.0.0",
    // ... existing devDependencies
  }
}
```

**Note**: Pin exact version (`-E` flag) as library doesn't follow semantic versioning strictly.

#### 2. Create Configuration File
**File**: `frontend/openapi-ts.config.ts`
**Changes**: Create new configuration file for openapi-ts

```typescript
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: 'src/client',
    format: 'prettier',
  },
  client: '@hey-api/client-fetch',
});
```

#### 3. Add Generation Script
**File**: `frontend/package.json`
**Changes**: Add script to generate API client

```json
{
  "scripts": {
    "generate:api": "openapi-ts",
    // ... existing scripts
  }
}
```

#### 4. Create OpenAPI Export Script (Optional but Recommended)
**File**: `backend/export_openapi.py`
**Changes**: Create script to export OpenAPI spec to file for CI/CD

```python
#!/usr/bin/env python3
"""Export OpenAPI specification to JSON file."""
import json
from main import app

if __name__ == '__main__':
    with open('openapi.json', 'w') as f:
        json.dump(app.openapi(), f, indent=2)
    print('OpenAPI spec exported to openapi.json')
```

### Success Criteria:

#### Automated Verification:
- [ ] Package installation succeeds: `cd frontend && npm install`
- [ ] Configuration file exists: `test -f frontend/openapi-ts.config.ts`
- [ ] TypeScript compilation passes: `cd frontend && npm run build` (should still work)
- [ ] Script added to package.json: `grep -q "generate:api" frontend/package.json`

#### Manual Verification:
- [ ] Configuration file syntax is correct (no TypeScript errors)
- [ ] Documentation reviewed for `@hey-api/openapi-ts` configuration options

---

## Phase 2: Generate Initial Client

### Overview
Generate the TypeScript client from the FastAPI OpenAPI specification and review the generated code structure.

### Changes Required:

#### 1. Start Backend Server
**File**: N/A (runtime requirement)
**Changes**: Ensure backend is running to expose `/openapi.json` endpoint

```bash
cd backend && python main.py
```

#### 2. Generate TypeScript Client
**File**: N/A (generated files)
**Changes**: Run generation command to create client files

```bash
cd frontend && npm run generate:api
```

This will generate files in `frontend/src/client/` directory.

#### 3. Review Generated Structure
**File**: `frontend/src/client/` (generated)
**Changes**: Review generated files to understand structure

Expected structure:
- `index.ts` - Main client export
- `types.gen.ts` - Generated TypeScript types
- `client.gen.ts` - Generated client methods
- Other supporting files as needed

#### 4. Verify OpenAPI Spec Completeness
**File**: N/A (verification step)
**Changes**: Check that FastAPI generated complete OpenAPI spec

```bash
curl http://localhost:8000/openapi.json | jq '.paths'
```

Verify all endpoints are present:
- `/api/notebooks` (GET, POST)
- `/api/notebooks/{notebook_id}` (GET)
- `/api/notebooks/{notebook_id}/db` (PUT)
- `/api/notebooks/{notebook_id}/name` (PUT)
- `/api/notebooks/{notebook_id}/cells` (POST)
- `/api/notebooks/{notebook_id}/cells/{cell_id}` (PUT, DELETE)

### Success Criteria:

#### Automated Verification:
- [ ] Generation command runs without errors: `cd frontend && npm run generate:api`
- [ ] Generated files exist: `test -d frontend/src/client && test -f frontend/src/client/index.ts`
- [ ] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] No TypeScript errors in generated files: `cd frontend && npx tsc --noEmit`

#### Manual Verification:
- [ ] Generated client structure matches expected pattern
- [ ] All API endpoints are represented in generated code
- [ ] Generated types look correct (match backend models)
- [ ] OpenAPI spec includes all request/response models

---

## Phase 3: Create Client Wrapper Module

### Overview
Create a wrapper module that provides a clean API matching the current `api.ts` interface, handling response unwrapping and error handling consistently.

### Changes Required:

#### 1. Create Client Wrapper
**File**: `frontend/src/api-client.ts` (new file)
**Changes**: Create wrapper that uses generated client and matches current API interface

```typescript
import { client } from './client';

const API_BASE = 'http://localhost:8000/api';

// Re-export types from generated client for backward compatibility
export type {
  Notebook,
  Cell,
  Output,
  NotebookMetadata,
  CellType,
  CellStatus,
} from './client';

// Helper to handle errors consistently
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`API request failed: ${response.statusText}`);
  }
  return response.json();
}

// Notebook operations
export async function createNotebook(): Promise<{ notebook_id: string }> {
  const response = await client.POST('/api/notebooks', {});
  if (!response.response.ok) {
    throw new Error(`Failed to create notebook: ${response.response.statusText}`);
  }
  return response.data as { notebook_id: string };
}

export async function getNotebook(id: string): Promise<Notebook> {
  const response = await client.GET('/api/notebooks/{notebook_id}', {
    params: { path: { notebook_id: id } },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to get notebook: ${response.response.statusText}`);
  }
  return response.data as Notebook;
}

export async function listNotebooks(): Promise<NotebookMetadata[]> {
  const response = await client.GET('/api/notebooks');
  if (!response.response.ok) {
    throw new Error(`Failed to list notebooks: ${response.response.statusText}`);
  }
  // Handle response wrapping: {"notebooks": [...]}
  const data = response.data as { notebooks: NotebookMetadata[] };
  return data.notebooks;
}

export async function updateDbConnection(id: string, connString: string): Promise<void> {
  const response = await client.PUT('/api/notebooks/{notebook_id}/db', {
    params: { path: { notebook_id: id } },
    body: { connection_string: connString },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to update DB connection: ${response.response.statusText}`);
  }
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const response = await client.PUT('/api/notebooks/{notebook_id}/name', {
    params: { path: { notebook_id: notebookId } },
    body: { name },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to rename notebook: ${response.response.statusText}`);
  }
}

// Cell operations
export async function createCell(notebookId: string, type: 'python' | 'sql'): Promise<{ cell_id: string }> {
  const response = await client.POST('/api/notebooks/{notebook_id}/cells', {
    params: { path: { notebook_id: notebookId } },
    body: { type },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to create cell: ${response.response.statusText}`);
  }
  return response.data as { cell_id: string };
}

export async function updateCell(notebookId: string, cellId: string, code: string): Promise<void> {
  const response = await client.PUT('/api/notebooks/{notebook_id}/cells/{cell_id}', {
    params: {
      path: {
        notebook_id: notebookId,
        cell_id: cellId,
      },
    },
    body: { code },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to update cell: ${response.response.statusText}`);
  }
}

export async function deleteCell(notebookId: string, cellId: string): Promise<void> {
  const response = await client.DELETE('/api/notebooks/{notebook_id}/cells/{cell_id}', {
    params: {
      path: {
        notebook_id: notebookId,
        cell_id: cellId,
      },
    },
  });
  if (!response.response.ok) {
    throw new Error(`Failed to delete cell: ${response.response.statusText}`);
  }
}
```

**Note**: The exact API of the generated client may vary. This is a template that will need adjustment based on actual generated client structure.

### Success Criteria:

#### Automated Verification:
- [ ] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] No type errors: `cd frontend && npx tsc --noEmit`
- [ ] All exported functions match current `api.ts` interface
- [ ] Types are properly exported for backward compatibility

#### Manual Verification:
- [ ] Wrapper functions match current API function signatures
- [ ] Error handling is consistent across all functions
- [ ] Response unwrapping works correctly for wrapped responses
- [ ] Code follows project TypeScript style guidelines

---

## Phase 4: Migrate Components to Generated Client

### Overview
Update components to use the new generated client wrapper, replacing imports from `api.ts` with `api-client.ts`.

### Changes Required:

#### 1. Update App Component
**File**: `frontend/src/App.tsx`
**Changes**: Replace `import * as api from './api'` with `import * as api from './api-client'`

```typescript
// Change line 4
import * as api from './api-client';
```

#### 2. Update Notebook Component
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Replace `import * as api from '../api'` with `import * as api from '../api-client'`

```typescript
// Change line 4
import * as api from '../api-client';
```

#### 3. Update NotebookSelector Component
**File**: `frontend/src/components/NotebookSelector.tsx`
**Changes**: Replace type import if needed (types should be re-exported from api-client)

```typescript
// Update import if NotebookMetadata type is imported directly
import type { NotebookMetadata } from '../api-client';
```

### Success Criteria:

#### Automated Verification:
- [ ] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] No type errors: `cd frontend && npx tsc --noEmit`
- [ ] All imports resolve correctly
- [ ] No unused imports remain

#### Manual Verification:
- [ ] Application starts without errors: `cd frontend && npm run dev`
- [ ] All API calls work identically to before
- [ ] No runtime errors in browser console
- [ ] Type autocomplete works in IDE for API functions

---

## Phase 5: Testing and Validation

### Overview
Test all API endpoints through the UI to ensure they work correctly with the generated client.

### Changes Required:

#### 1. Test Notebook Operations
**File**: N/A (manual testing)
**Changes**: Test each notebook operation through UI

1. **Create Notebook**: Click "Create New" button, verify notebook appears
2. **List Notebooks**: Verify notebook list loads correctly
3. **Get Notebook**: Select notebook, verify details load
4. **Rename Notebook**: Rename notebook, verify name updates
5. **Update DB Connection**: Update connection string, verify it saves

#### 2. Test Cell Operations
**File**: N/A (manual testing)
**Changes**: Test each cell operation through UI

1. **Create Cell**: Add Python cell, add SQL cell, verify cells appear
2. **Update Cell**: Edit cell code, verify code updates
3. **Delete Cell**: Delete cell, verify it's removed
4. **Run Cell**: Execute cell, verify execution works

#### 3. Test Error Handling
**File**: N/A (manual testing)
**Changes**: Test error scenarios

1. **404 Errors**: Try accessing non-existent notebook/cell
2. **Network Errors**: Disconnect backend, verify error messages
3. **Validation Errors**: Submit invalid data, verify error handling

### Success Criteria:

#### Automated Verification:
- [ ] All TypeScript types are correct: `cd frontend && npx tsc --noEmit`
- [ ] Build succeeds: `cd frontend && npm run build`
- [ ] No linting errors: `cd frontend && npm run lint` (if lint script exists)

#### Manual Verification:
- [ ] All notebook operations work correctly
- [ ] All cell operations work correctly
- [ ] Error messages are user-friendly
- [ ] WebSocket functionality still works (unchanged)
- [ ] No regressions in existing functionality
- [ ] Performance is acceptable (no noticeable slowdown)

---

## Phase 6: Cleanup and Documentation

### Overview
Remove old manual API module and add documentation for client regeneration process.

### Changes Required:

#### 1. Remove Old API Module
**File**: `frontend/src/api.ts`
**Changes**: Delete file (no longer needed)

```bash
rm frontend/src/api.ts
```

#### 2. Update README
**File**: `README.md` or `frontend/README.md`
**Changes**: Add section on API client generation

```markdown
## API Client Generation

The TypeScript API client is automatically generated from the FastAPI OpenAPI specification.

### Regenerating the Client

1. Start the backend server:
   ```bash
   cd backend && python main.py
   ```

2. Generate the client:
   ```bash
   cd frontend && npm run generate:api
   ```

3. The generated client will be in `frontend/src/client/`

### When to Regenerate

- After adding new API endpoints
- After modifying request/response models
- After updating FastAPI route definitions

### Using Static OpenAPI File (for CI/CD)

Instead of fetching from running server, you can export the OpenAPI spec:

```bash
cd backend && python export_openapi.py
```

Then update `frontend/openapi-ts.config.ts` to use the file:

```typescript
input: '../openapi.json', // Relative to frontend directory
```
```

#### 3. Add .gitignore Entry (if needed)
**File**: `frontend/.gitignore`
**Changes**: Ensure generated client files are tracked (they should be committed)

**Note**: Generated client files should typically be committed to the repository for consistency, but verify project policy.

### Success Criteria:

#### Automated Verification:
- [ ] Old API file removed: `test ! -f frontend/src/api.ts`
- [ ] No references to old API file: `grep -r "from './api'" frontend/src` (should return nothing)
- [ ] Documentation file updated: `grep -q "generate:api" README.md` (or frontend/README.md)

#### Manual Verification:
- [ ] README instructions are clear and complete
- [ ] Developer can successfully regenerate client following instructions
- [ ] No broken imports or references remain

---

## Testing Strategy

### Unit Tests
- **Generated Client**: Verify generated client methods match expected signatures
- **Type Exports**: Verify all types are properly exported from wrapper
- **Error Handling**: Test error handling in wrapper functions

### Integration Tests
- **API Calls**: Test each API endpoint through the wrapper
- **Response Parsing**: Verify response unwrapping works correctly
- **Type Safety**: Verify TypeScript catches type mismatches

### Manual Testing Steps
1. **Start Backend**: `cd backend && python main.py`
2. **Start Frontend**: `cd frontend && npm run dev`
3. **Test Notebook CRUD**: Create, list, get, rename notebooks
4. **Test Cell CRUD**: Create, update, delete cells
5. **Test DB Connection**: Update connection string
6. **Test Error Cases**: Invalid IDs, network errors
7. **Verify WebSocket**: Ensure WebSocket still works (unchanged)

## Performance Considerations

- **Generation Time**: Client generation should complete in < 5 seconds
- **Bundle Size**: Generated client may increase bundle size slightly - monitor impact
- **Runtime Performance**: Generated client should have similar performance to manual fetch calls
- **Type Checking**: TypeScript compilation time may increase slightly with generated types

## Migration Notes

### Backward Compatibility
- The wrapper module (`api-client.ts`) maintains the same function signatures as `api.ts`
- Components don't need changes beyond import path
- Types are re-exported for backward compatibility

### Rollback Plan
If issues arise:
1. Revert component imports back to `'./api'`
2. Restore `frontend/src/api.ts` from git history
3. Remove generated client files if needed

### Future Enhancements
- Add Zod validation plugin for runtime type checking
- Add TanStack Query hooks plugin for caching and state management
- Set up CI/CD to regenerate client on API changes
- Consider using static OpenAPI file for more reliable generation

## References

- Original research: `thoughts/shared/research/2025-12-27-openapi-ts-integration.md`
- Backend API routes: `backend/routes.py`
- Backend models: `backend/models.py`
- Current API module: `frontend/src/api.ts` (to be replaced)
- Frontend components: `frontend/src/components/Notebook.tsx`, `frontend/src/App.tsx`
- [@hey-api/openapi-ts GitHub](https://github.com/hey-api/openapi-ts)
- [Hey API Documentation](https://heyapi.dev)
- [FastAPI OpenAPI Documentation](https://fastapi.tiangolo.com/advanced/openapi-customization/)

