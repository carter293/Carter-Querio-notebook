---
date: 2025-12-27T17:24:28+00:00
planner: AI Assistant
topic: "Loading and Saving Named Notebooks from Frontend Dropdown"
tags: [planning, implementation, frontend, backend, notebooks, persistence, ui]
status: draft
last_updated: 2025-12-27
last_updated_by: AI Assistant
---

# Loading and Saving Named Notebooks from Frontend Dropdown Implementation Plan

**Date**: 2025-12-27T17:24:28+00:00
**Planner**: AI Assistant

## Overview

Enable users to load and save named notebooks from a frontend dropdown interface. The persistence layer already exists, but there's no API endpoint or UI for discovering and selecting existing notebooks. This plan adds a list endpoint, optional notebook naming, and a dropdown UI component to enable notebook selection and switching.

## Current State Analysis

### What Exists

**Backend Persistence** (`backend/storage.py`):
- ✅ `save_notebook(notebook)` - Saves notebook to `backend/notebooks/{notebook.id}.json`
- ✅ `load_notebook(notebook_id)` - Loads notebook from JSON file
- ✅ `list_notebooks()` - Returns `List[str]` of notebook IDs (file stems without `.json` extension)
- ✅ Auto-save integrated in all CRUD operations (`backend/routes.py`)
- ✅ Startup loading in `backend/main.py` loads all notebooks into memory

**Backend API** (`backend/routes.py`):
- ✅ `POST /api/notebooks` - Create new notebook
- ✅ `GET /api/notebooks/{notebook_id}` - Get specific notebook
- ✅ `PUT /api/notebooks/{notebook_id}/db` - Update DB connection
- ✅ `PUT /api/notebooks/{notebook_id}/cells/{cell_id}` - Update cell
- ✅ `POST /api/notebooks/{notebook_id}/cells` - Create cell
- ✅ `DELETE /api/notebooks/{notebook_id}/cells/{cell_id}` - Delete cell

**Frontend** (`frontend/src/App.tsx`):
- ✅ Always creates new notebook on mount via `api.createNotebook()`
- ✅ Passes `notebookId` to `<Notebook>` component
- ✅ No mechanism to load existing notebooks

### What's Missing

1. **Backend API Endpoint**: No `GET /api/notebooks` endpoint to list all notebooks
2. **Notebook Naming**: No `name` field in Notebook model - only UUID IDs
3. **Frontend API Function**: No `listNotebooks()` function in `frontend/src/api.ts`
4. **Frontend Dropdown Component**: No dropdown/select UI component exists
5. **State Management**: App.tsx doesn't support switching between notebooks
6. **Rename Functionality**: No way to set or update notebook names

### Key Constraints

- **Single-Notebook Assumption**: Current architecture assumes one notebook per session
- **WebSocket Scoping**: WebSocket connections are scoped to a single notebook ID (`frontend/src/useWebSocket.ts:18`)
- **No Routing**: Frontend is a single-page app with no router library
- **In-Memory Cache**: Backend maintains `NOTEBOOKS` dict for fast access (`backend/routes.py:13`)

## System Context Analysis

**Root Cause Analysis**: The persistence layer was implemented for durability (surviving server restarts), but the UI layer was never updated to expose this capability. The frontend still follows a "create-only" pattern, assuming one notebook per session.

**Systemic Solution**: This plan addresses the root cause by:
1. Adding discovery capability (list endpoint) to expose persisted notebooks
2. Adding optional naming for user-friendly identification
3. Updating frontend state management to support notebook switching
4. Handling WebSocket reconnection when switching notebooks

**Not a Symptom Fix**: This is a genuine feature gap, not a bug. The persistence system works correctly but lacks UI integration.

## Desired End State

After implementation:

1. **Backend API**: `GET /api/notebooks` returns list of notebooks with id and optional name
2. **Notebook Naming**: Notebooks can have user-friendly names (optional, defaults to ID)
3. **Frontend Dropdown**: Users see a dropdown at the top of the app to select notebooks
4. **Notebook Switching**: Users can switch between notebooks, with WebSocket reconnection
5. **Create New**: Dropdown includes "Create New Notebook" option
6. **Rename Capability**: Users can rename notebooks (optional, can be added later)

### Verification:
- Manual: Open app, see dropdown with existing notebooks
- Manual: Select notebook from dropdown, verify it loads
- Manual: Create new notebook, verify it appears in dropdown
- Manual: Switch notebooks, verify WebSocket reconnects and state updates
- Automated: API endpoint returns correct notebook list
- Automated: Notebook name persists across saves/loads

## What We're NOT Doing

To maintain focused scope:

1. **Notebook Deletion**: Not adding delete functionality in this phase (can add later)
2. **Metadata**: Not returning last modified date, cell count, etc. (can add later)
3. **URL Integration**: Not adding routing/URL parameters for notebook selection
4. **Notebook Templates**: Not adding template/duplicate functionality
5. **Search/Filter**: Not adding search or filtering in dropdown
6. **Multi-select**: Not supporting multiple notebooks open simultaneously
7. **Notebook Import/Export**: Not adding import/export functionality

## Implementation Approach

**Strategy**: Incremental, backward-compatible changes

1. **Backend First**: Add list endpoint and optional name field
2. **Frontend API**: Add listNotebooks function
3. **UI Component**: Create simple dropdown using native HTML select
4. **State Management**: Update App.tsx to support notebook selection
5. **WebSocket Handling**: Close and reopen WebSocket on notebook switch

**Dependencies**:
- Phase 1 must complete before Phase 3 (need API endpoint)
- Phase 2 can run in parallel with Phase 1
- Phase 3 depends on Phase 1 and 2
- Phase 4 depends on Phase 3

---

## Phase 1: Backend API Endpoint and Notebook Naming

### Overview
Add `GET /api/notebooks` endpoint to list all notebooks, and add optional `name` field to Notebook model for user-friendly identification.

### Changes Required:

#### 1.1 Add Name Field to Notebook Model
**File**: `backend/models.py`
**Changes**: Add optional `name` field to Notebook dataclass

```python
@dataclass
class Notebook:
    id: str
    name: Optional[str] = None  # User-friendly name, defaults to None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
```

**Line reference**: Modify [models.py:77-83](backend/models.py#L77)

---

#### 1.2 Update Storage Functions for Name Field
**File**: `backend/storage.py`
**Changes**: Include `name` in save/load operations

```python
def save_notebook(notebook: Notebook) -> None:
    ensure_notebooks_dir()

    data = {
        "id": notebook.id,
        "name": notebook.name,  # NEW: Include name
        "db_conn_string": notebook.db_conn_string,
        "revision": notebook.revision,
        "cells": [
            {
                "id": cell.id,
                "type": cell.type.value,
                "code": cell.code,
                "reads": list(cell.reads),
                "writes": list(cell.writes)
            }
            for cell in notebook.cells
        ]
    }

    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def load_notebook(notebook_id: str) -> Notebook:
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"

    with open(file_path, 'r') as f:
        data = json.load(f)

    cells = [
        Cell(
            id=cell_data["id"],
            type=CellType(cell_data["type"]),
            code=cell_data["code"],
            status=CellStatus.IDLE,
            reads=set(cell_data.get("reads", [])),
            writes=set(cell_data.get("writes", []))
        )
        for cell_data in data["cells"]
    ]

    notebook = Notebook(
        id=data["id"],
        name=data.get("name"),  # NEW: Load name, defaults to None if missing
        db_conn_string=data.get("db_conn_string"),
        cells=cells,
        revision=data.get("revision", 0)
    )

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook
```

**Line references**: 
- Modify `save_notebook()` at [storage.py:12-34](backend/storage.py#L12)
- Modify `load_notebook()` at [storage.py:35-63](backend/storage.py#L35)

**Backward Compatibility**: Existing notebooks without `name` field will load with `name=None`, which is acceptable.

---

#### 1.3 Add List Notebooks Endpoint
**File**: `backend/routes.py`
**Changes**: Add GET endpoint to list all notebooks

```python
from storage import save_notebook, list_notebooks

@router.get("/notebooks")
async def list_notebooks_endpoint():
    """List all available notebooks"""
    notebook_ids = list_notebooks()
    
    notebooks = []
    for notebook_id in notebook_ids:
        if notebook_id in NOTEBOOKS:
            notebook = NOTEBOOKS[notebook_id]
            notebooks.append({
                "id": notebook.id,
                "name": notebook.name or notebook.id  # Use name if available, else ID
            })
        else:
            # Notebook exists on disk but not in memory (shouldn't happen, but handle gracefully)
            notebooks.append({
                "id": notebook_id,
                "name": notebook_id
            })
    
    return {"notebooks": notebooks}
```

**Insert location**: After [routes.py:55](backend/routes.py#L55), before `get_notebook` endpoint

**Error Handling**: Handles case where notebook exists on disk but not in memory cache (edge case from startup failures).

---

#### 1.4 Add Rename Notebook Endpoint (Optional)
**File**: `backend/routes.py`
**Changes**: Add PUT endpoint to update notebook name

```python
class RenameNotebookRequest(BaseModel):
    name: str

@router.put("/notebooks/{notebook_id}/name")
async def rename_notebook(notebook_id: str, request: RenameNotebookRequest):
    """Update notebook name"""
    if notebook_id not in NOTEBOOKS:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    notebook = NOTEBOOKS[notebook_id]
    notebook.name = request.name.strip() if request.name.strip() else None
    save_notebook(notebook)
    return {"status": "ok", "name": notebook.name}
```

**Insert location**: After [routes.py:99](backend/routes.py#L99), after `update_db_connection` endpoint

**Validation**: Strips whitespace and allows empty string to clear name (sets to None).

---

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd backend && python -m mypy routes.py storage.py models.py`
- [ ] Backend starts without errors: `cd backend && python -m uvicorn main:app --reload`
- [ ] API endpoint returns 200: `curl http://localhost:8000/api/notebooks`
- [ ] Response includes notebooks array with id and name fields
- [ ] Existing notebooks without name field load correctly (backward compatibility)

#### Manual Verification:
- [ ] `GET /api/notebooks` returns list of all notebooks in `backend/notebooks/`
- [ ] Response format: `{"notebooks": [{"id": "...", "name": "..."}, ...]}`
- [ ] Notebooks without names show ID as name
- [ ] Rename endpoint updates notebook name and persists to disk
- [ ] Server restart preserves notebook names

---

## Phase 2: Frontend API Function

### Overview
Add `listNotebooks()` function to frontend API layer and update TypeScript types.

### Changes Required:

#### 2.1 Add NotebookMetadata Interface
**File**: `frontend/src/api.ts`
**Changes**: Add interface and listNotebooks function

```typescript
export interface NotebookMetadata {
  id: string;
  name: string;  // Always present (backend returns ID if name is None)
}

export interface Notebook {
  id: string;
  name?: string;  // NEW: Optional name field
  db_conn_string?: string;
  cells: Cell[];
}

export async function listNotebooks(): Promise<NotebookMetadata[]> {
  const res = await fetch(`${API_BASE}/notebooks`);
  if (!res.ok) {
    throw new Error(`Failed to list notebooks: ${res.statusText}`);
  }
  const data = await res.json();
  return data.notebooks;
}
```

**Line references**:
- Add `NotebookMetadata` interface after [api.ts:35](frontend/src/api.ts#L35)
- Update `Notebook` interface at [api.ts:35](frontend/src/api.ts#L35) to include optional `name`
- Add `listNotebooks()` function after [api.ts:44](frontend/src/api.ts#L44)

---

#### 2.2 Add Rename Notebook Function (Optional)
**File**: `frontend/src/api.ts`
**Changes**: Add function to rename notebooks

```typescript
export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/notebooks/${notebookId}/name`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) {
    throw new Error(`Failed to rename notebook: ${res.statusText}`);
  }
}
```

**Insert location**: After `listNotebooks()` function

---

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd frontend && npm run typecheck` (or `npx tsc --noEmit`)
- [ ] No TypeScript errors in `api.ts`

#### Manual Verification:
- [ ] `listNotebooks()` returns array of notebook metadata
- [ ] Each notebook has `id` and `name` fields
- [ ] `renameNotebook()` successfully updates notebook name (if implemented)

---

## Phase 3: Frontend Dropdown Component

### Overview
Create a dropdown component to display and select notebooks, with "Create New Notebook" option.

### Changes Required:

#### 3.1 Create NotebookSelector Component
**File**: `frontend/src/components/NotebookSelector.tsx` (NEW FILE)

```typescript
import React from 'react';
import * as api from '../api';

interface NotebookSelectorProps {
  notebooks: api.NotebookMetadata[];
  selectedNotebookId: string | null;
  onSelectNotebook: (notebookId: string) => void;
  onCreateNew: () => void;
  loading?: boolean;
}

export function NotebookSelector({
  notebooks,
  selectedNotebookId,
  onSelectNotebook,
  onCreateNew,
  loading = false
}: NotebookSelectorProps) {
  return (
    <div style={{
      display: 'flex',
      gap: '8px',
      alignItems: 'center',
      marginBottom: '24px',
      padding: '12px',
      backgroundColor: '#f9fafb',
      borderRadius: '8px'
    }}>
      <label style={{
        fontSize: '14px',
        fontWeight: 500,
        whiteSpace: 'nowrap'
      }}>
        Notebook:
      </label>
      <select
        value={selectedNotebookId || ''}
        onChange={(e) => {
          if (e.target.value === '__create_new__') {
            onCreateNew();
          } else {
            onSelectNotebook(e.target.value);
          }
        }}
        disabled={loading}
        style={{
          flex: 1,
          padding: '8px 12px',
          border: '1px solid #d1d5db',
          borderRadius: '4px',
          fontSize: '14px',
          backgroundColor: loading ? '#f3f4f6' : 'white',
          cursor: loading ? 'not-allowed' : 'pointer'
        }}
      >
        {notebooks.map(nb => (
          <option key={nb.id} value={nb.id}>
            {nb.name}
          </option>
        ))}
        <option value="__create_new__" style={{ fontStyle: 'italic' }}>
          + Create New Notebook
        </option>
      </select>
      {loading && (
        <span style={{ fontSize: '12px', color: '#6b7280' }}>
          Loading...
        </span>
      )}
    </div>
  );
}
```

**Design Decisions**:
- Use native HTML `<select>` for simplicity (no external dependencies)
- "Create New Notebook" option at bottom of dropdown
- Loading state disables dropdown and shows indicator
- Styling matches existing UI patterns from `Notebook.tsx`

---

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd frontend && npm run typecheck`
- [ ] Component compiles without errors

#### Manual Verification:
- [ ] Dropdown displays list of notebooks with names
- [ ] Selecting notebook calls `onSelectNotebook` callback
- [ ] "Create New Notebook" option calls `onCreateNew` callback
- [ ] Loading state disables dropdown and shows "Loading..." text
- [ ] Styling matches existing UI (gray background, rounded corners)

---

## Phase 4: App State Management and Integration

### Overview
Update `App.tsx` to fetch notebook list on mount, display dropdown, and handle notebook selection/switching with WebSocket reconnection.

### Changes Required:

#### 4.1 Update App Component
**File**: `frontend/src/App.tsx`
**Changes**: Replace create-only flow with notebook selection flow

```typescript
import React, { useState, useEffect } from 'react';
import { Notebook } from './components/Notebook';
import { NotebookSelector } from './components/NotebookSelector';
import * as api from './api';

export default function App() {
  const [notebooks, setNotebooks] = useState<api.NotebookMetadata[]>([]);
  const [notebookId, setNotebookId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load notebook list on mount
  useEffect(() => {
    api.listNotebooks()
      .then(notebookList => {
        setNotebooks(notebookList);
        
        // Default behavior: select first notebook if available, otherwise create new
        if (notebookList.length > 0) {
          setNotebookId(notebookList[0].id);
        } else {
          // No notebooks exist, create a new one
          api.createNotebook()
            .then(({ notebook_id }) => {
              setNotebookId(notebook_id);
              // Refresh list to include new notebook
              return api.listNotebooks();
            })
            .then(notebookList => {
              setNotebooks(notebookList);
            })
            .catch(err => {
              setError('Failed to create notebook: ' + err.message);
            });
        }
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load notebooks: ' + err.message);
        setLoading(false);
      });
  }, []);

  const handleSelectNotebook = (selectedId: string) => {
    setNotebookId(selectedId);
    // Note: WebSocket will reconnect automatically via useWebSocket hook
    // when notebookId changes (see Notebook.tsx)
  };

  const handleCreateNew = async () => {
    try {
      setLoading(true);
      const { notebook_id } = await api.createNotebook();
      setNotebookId(notebook_id);
      // Refresh notebook list
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
      setLoading(false);
    } catch (err: any) {
      setError('Failed to create notebook: ' + err.message);
      setLoading(false);
    }
  };

  if (error) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: '#991b1b'
      }}>
        Error: {error}
      </div>
    );
  }

  if (loading && !notebookId) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center'
      }}>
        Loading notebooks...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
      <NotebookSelector
        notebooks={notebooks}
        selectedNotebookId={notebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNew={handleCreateNew}
        loading={loading}
      />
      {notebookId && <Notebook notebookId={notebookId} />}
    </div>
  );
}
```

**Line reference**: Replace entire file [App.tsx:1-44](frontend/src/App.tsx#L1)

**Key Changes**:
- Load notebook list on mount instead of always creating new
- Default to first notebook if available, otherwise create new
- Handle notebook selection and creation via callbacks
- WebSocket reconnection handled automatically by `useWebSocket` hook when `notebookId` changes

**WebSocket Handling**: The `useWebSocket` hook in `Notebook.tsx` already handles reconnection when `notebookId` prop changes (see [useWebSocket.ts:16-43](frontend/src/useWebSocket.ts#L16)). The `useEffect` dependency on `notebookId` will close the old connection and open a new one.

---

#### 4.2 Refresh Notebook List After Creation (Enhancement)
**File**: `frontend/src/components/Notebook.tsx`
**Changes**: Optional - Add callback to refresh notebook list when notebook is renamed

**Note**: This is optional and can be added later. For now, users can refresh the page to see renamed notebooks in the dropdown.

---

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd frontend && npm run typecheck`
- [ ] App component compiles without errors
- [ ] No TypeScript errors in App.tsx

#### Manual Verification:
- [ ] App loads and shows dropdown with existing notebooks
- [ ] Selecting notebook from dropdown loads that notebook
- [ ] "Create New Notebook" creates new notebook and adds to dropdown
- [ ] Switching notebooks closes old WebSocket and opens new one
- [ ] Notebook state (cells, DB connection) loads correctly when switching
- [ ] Loading state shows while fetching notebooks
- [ ] Error handling displays error message if API fails

---

## Testing Strategy

### Unit Tests:

**Backend** (`backend/tests/test_routes.py` or new test file):
- Test `GET /api/notebooks` returns correct notebook list
- Test `PUT /api/notebooks/{id}/name` updates name correctly
- Test backward compatibility (notebooks without name field)
- Test error handling (notebook not found for rename)

**Frontend** (if test setup exists):
- Test `listNotebooks()` API function
- Test `NotebookSelector` component renders correctly
- Test `App` component handles notebook selection

### Integration Tests:

**End-to-End Scenarios**:
1. **Load Existing Notebooks**:
   - Start server with existing notebooks
   - Open frontend
   - Verify dropdown shows all notebooks
   - Select notebook, verify it loads

2. **Create New Notebook**:
   - Open frontend
   - Select "Create New Notebook"
   - Verify new notebook appears in dropdown
   - Verify new notebook is selected and loads

3. **Switch Notebooks**:
   - Have multiple notebooks
   - Select notebook A, make changes
   - Switch to notebook B
   - Verify notebook B loads with its own state
   - Switch back to notebook A
   - Verify changes persisted

4. **Rename Notebook** (if Phase 1.4 implemented):
   - Select notebook
   - Rename via API or UI (if added)
   - Verify name updates in dropdown
   - Restart server, verify name persists

### Manual Testing Steps:

1. **Initial Load**:
   - Start backend: `cd backend && python -m uvicorn main:app --reload`
   - Start frontend: `cd frontend && npm run dev`
   - Open browser to `http://localhost:5173`
   - Verify dropdown appears with notebooks

2. **Notebook Selection**:
   - Select different notebook from dropdown
   - Verify notebook content loads
   - Verify WebSocket connects (check browser console)

3. **Create New**:
   - Select "Create New Notebook"
   - Verify new notebook appears in dropdown
   - Verify new notebook is selected

4. **Persistence**:
   - Create notebook, make changes
   - Restart backend server
   - Reload frontend
   - Verify notebook persists and appears in dropdown

5. **Edge Cases**:
   - Test with no notebooks (should create new)
   - Test with many notebooks (dropdown scrolls)
   - Test rapid switching between notebooks
   - Test WebSocket reconnection timing

---

## Performance Considerations

1. **Notebook List Caching**: The frontend fetches notebook list on mount. For many notebooks (100+), consider:
   - Pagination in list endpoint (out of scope)
   - Client-side caching with refresh button
   - Debouncing rapid dropdown changes

2. **WebSocket Reconnection**: Switching notebooks closes and reopens WebSocket. For frequent switching:
   - Current approach is acceptable (WebSocket overhead is minimal)
   - Could optimize by maintaining connection pool (out of scope)

3. **Memory**: Backend loads all notebooks into memory at startup. For many notebooks:
   - Current approach acceptable for <100 notebooks
   - Could add lazy loading (out of scope)

---

## Migration Notes

### Backward Compatibility

**Existing Notebooks**: Notebooks saved without `name` field will:
- Load correctly with `name=None`
- Display ID as name in dropdown (backend returns ID if name is None)
- Can be renamed via rename endpoint (if implemented)

**No Migration Required**: The `name` field is optional, so existing notebooks continue to work without changes.

### Data Migration (If Needed)

If you want to set default names for existing notebooks:

```python
# One-time migration script (optional)
from storage import list_notebooks, load_notebook, save_notebook

for notebook_id in list_notebooks():
    notebook = load_notebook(notebook_id)
    if notebook.name is None:
        # Set name to something user-friendly
        notebook.name = f"Notebook {notebook_id[:8]}"  # First 8 chars of UUID
        save_notebook(notebook)
```

---

## References

- Original research: `thoughts/shared/research/2025-12-27-loading-saving-named-notebooks-dropdown.md`
- Related plan: `thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md` (Phase 3: Notebook Persistence)
- Backend storage: `backend/storage.py`
- Backend routes: `backend/routes.py`
- Frontend API: `frontend/src/api.ts`
- Frontend App: `frontend/src/App.tsx`
- WebSocket handling: `frontend/src/useWebSocket.ts`

