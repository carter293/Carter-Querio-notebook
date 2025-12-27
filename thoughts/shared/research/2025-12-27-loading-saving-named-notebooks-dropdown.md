---
date: 2025-12-27T17:03:49+00:00
researcher: AI Assistant
topic: "Loading and Saving Named Notebooks from Frontend Dropdown"
tags: [research, codebase, frontend, backend, notebooks, persistence]
status: complete
last_updated: 2025-12-27
last_updated_by: AI Assistant
---

# Research: Loading and Saving Named Notebooks from Frontend Dropdown

**Date**: 2025-12-27T17:03:49+00:00
**Researcher**: AI Assistant

## Research Question

What would be needed to enable loading and saving of named notebooks from the frontend in a dropdown? The persistence system was just implemented, and we need to understand the current architecture and what's missing for a user-facing notebook selection interface.

## Summary

The codebase has a complete persistence layer that saves notebooks to JSON files, but **no frontend UI or API endpoints** for listing and selecting existing notebooks. Currently, the frontend always creates a new notebook on mount. To enable a dropdown for loading/saving named notebooks, we need:

1. **Backend API endpoint** to list all notebooks (GET `/api/notebooks`)
2. **Optional: Notebook naming** - Add `name` field to Notebook model for user-friendly display
3. **Frontend API function** to fetch the list of notebooks
4. **Frontend dropdown component** (no existing dropdown components in codebase)
5. **State management** in App.tsx to switch between notebooks instead of always creating new
6. **Save/rename functionality** - Allow users to name notebooks and update names

## Detailed Findings

### Current Notebook Loading Flow

**Frontend Entry Point** (`frontend/src/App.tsx:9-18`):
- On mount, `App` component calls `api.createNotebook()` which always creates a new notebook
- The returned `notebook_id` (UUID) is stored in state and passed to `<Notebook>` component
- No mechanism exists to load an existing notebook from the frontend

**Backend Creation** (`backend/routes.py:35-55`):
- `POST /api/notebooks` creates a new notebook with UUID ID
- Notebook is immediately saved to disk via `save_notebook(notebook)`
- Returns `{ notebook_id: str }` response

**Notebook Loading** (`frontend/src/components/Notebook.tsx:17-22`):
- `Notebook` component receives `notebookId` as prop
- Calls `api.getNotebook(notebookId)` to fetch notebook data
- All operations (cells, DB connection) are scoped to this `notebookId`

### Storage Layer Capabilities

**Persistence Implementation** (`backend/storage.py`):
- ✅ `save_notebook(notebook)` - Saves notebook to `backend/notebooks/{notebook.id}.json`
- ✅ `load_notebook(notebook_id)` - Loads notebook from JSON file
- ✅ `list_notebooks()` - Returns `List[str]` of notebook IDs (file stems without `.json` extension)

**Storage Location** (`backend/storage.py:7`):
- Notebooks stored in `backend/notebooks/` directory
- Files named `{notebook_id}.json`
- Currently contains: `demo.json`, `08c56eab-0c47-414d-be68-b19ea1f5689e.json`, etc.

**Startup Loading** (`backend/main.py:18-36`):
- On server startup, `list_notebooks()` is called
- All notebooks are loaded into in-memory `NOTEBOOKS` dict
- If no notebooks exist, creates demo notebook

### Missing API Endpoints

**No List Endpoint**:
- `list_notebooks()` function exists but is only used internally at startup
- No `GET /api/notebooks` endpoint to return list of available notebooks
- Frontend has no way to discover existing notebooks

**Current Endpoints** (`backend/routes.py`):
- `POST /api/notebooks` - Create new notebook
- `GET /api/notebooks/{notebook_id}` - Get specific notebook
- `PUT /api/notebooks/{notebook_id}/db` - Update DB connection
- No endpoint to list all notebooks or get notebook metadata

### Notebook Model Structure

**Current Model** (`backend/models.py:77-83`):
```python
@dataclass
class Notebook:
    id: str  # UUID or "demo"
    db_conn_string: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    kernel: KernelState = field(default_factory=KernelState)
    revision: int = 0
```

**No Name Field**:
- Notebooks are identified only by `id` (UUIDs like `08c56eab-0c47-414d-be68-b19ea1f5689e`)
- No user-friendly `name` or `title` field exists
- Demo notebook uses `id="demo"` as a special case

**Storage Format** (`backend/notebooks/demo.json`):
- JSON structure includes: `id`, `db_conn_string`, `revision`, `cells`
- No `name` field in saved JSON files

### Frontend Architecture

**No Routing** (`frontend/src/App.tsx`, `frontend/src/main.tsx`):
- Single-page application with no router library
- No URL parameters or hash fragments for navigation
- All state managed via React state and API calls

**Current Flow**:
1. App mounts → Creates new notebook → Sets `notebookId` state
2. Renders `<Notebook notebookId={notebookId} />`
3. All interactions scoped to this single notebook

**No Dropdown Components**:
- No existing dropdown, select, or menu navigation components
- UI uses only basic HTML elements: `<button>`, `<input type="text">`, `<div>`
- Would need to create dropdown component from scratch or use a library

### Frontend API Layer

**Current Functions** (`frontend/src/api.ts`):
- `createNotebook()` - Creates new notebook
- `getNotebook(id)` - Gets specific notebook
- `updateDbConnection()`, `createCell()`, `updateCell()`, `deleteCell()` - Cell operations
- **Missing**: `listNotebooks()` function

**API Base** (`frontend/src/api.ts:1`):
- Base URL: `http://localhost:8000/api`
- All endpoints follow RESTful pattern

## Code References

### Backend Files
- `backend/storage.py:65-67` - `list_notebooks()` function returns list of notebook IDs
- `backend/routes.py:35-55` - `POST /api/notebooks` creates new notebook
- `backend/routes.py:57-88` - `GET /api/notebooks/{notebook_id}` gets specific notebook
- `backend/models.py:77-83` - `Notebook` dataclass definition (no name field)
- `backend/main.py:18-36` - Startup event loads all notebooks into memory

### Frontend Files
- `frontend/src/App.tsx:9-18` - Creates new notebook on mount
- `frontend/src/App.tsx:43` - Renders Notebook component with notebookId prop
- `frontend/src/components/Notebook.tsx:17-22` - Loads notebook data on mount
- `frontend/src/api.ts:41-44` - `createNotebook()` API function
- `frontend/src/api.ts:46-49` - `getNotebook(id)` API function

### Storage Files
- `backend/notebooks/demo.json` - Example notebook JSON structure
- `backend/notebooks/` - Directory containing all saved notebooks

## Architecture Insights

### Current Pattern: Create-Only Flow
The application follows a "create-only" pattern where:
- Frontend always creates a new notebook on mount
- No way to select or switch between notebooks
- Notebooks persist to disk but are inaccessible from UI

### Persistence vs. Discovery Gap
The persistence layer is complete, but there's a **discovery gap**:
- ✅ Backend can save/load notebooks
- ✅ Backend can list notebook IDs
- ❌ No API endpoint exposes notebook list to frontend
- ❌ No frontend UI to select notebooks

### Single-Notebook Assumption
The current architecture assumes one notebook per session:
- `App` component manages single `notebookId` state
- `Notebook` component receives single `notebookId` prop
- WebSocket connections are scoped to single notebook
- No multi-notebook state management

## Implementation Requirements

### 1. Backend API Endpoint (Required)

**Add GET `/api/notebooks` endpoint** (`backend/routes.py`):
```python
@router.get("/notebooks")
async def list_notebooks_endpoint():
    """List all available notebooks"""
    notebook_ids = list_notebooks()
    return {
        "notebooks": [
            {"id": nb_id, "name": nb_id}  # Or use actual name if added
            for nb_id in notebook_ids
        ]
    }
```

**Considerations**:
- Could return just IDs, or include metadata (name, last modified, cell count)
- Should handle case where notebooks directory doesn't exist
- May want to filter out notebooks that fail to load

### 2. Notebook Naming (Optional but Recommended)

**Add `name` field to Notebook model** (`backend/models.py`):
```python
@dataclass
class Notebook:
    id: str
    name: Optional[str] = None  # User-friendly name
    db_conn_string: Optional[str] = None
    # ... rest of fields
```

**Update storage functions** (`backend/storage.py`):
- `save_notebook()` - Include `name` in JSON
- `load_notebook()` - Load `name` from JSON
- Default `name` to `id` if not provided (backward compatibility)

**Add rename endpoint** (`backend/routes.py`):
```python
@router.put("/notebooks/{notebook_id}/name")
async def rename_notebook(notebook_id: str, request: RenameNotebookRequest):
    # Update name and save
```

### 3. Frontend API Function (Required)

**Add to `frontend/src/api.ts`**:
```typescript
export interface NotebookMetadata {
  id: string;
  name?: string;
}

export async function listNotebooks(): Promise<NotebookMetadata[]> {
  const res = await fetch(`${API_BASE}/notebooks`);
  const data = await res.json();
  return data.notebooks;
}
```

### 4. Frontend Dropdown Component (Required)

**Create new component** (`frontend/src/components/NotebookSelector.tsx`):
- Native `<select>` element or custom dropdown
- Display notebook names (or IDs if no name)
- Handle selection to switch notebooks
- Include "Create New Notebook" option

**Alternative**: Use a UI library like:
- React Select (`react-select`)
- Headless UI (`@headlessui/react`)
- Material UI (`@mui/material`)

### 5. App State Management (Required)

**Modify `frontend/src/App.tsx`**:
- Replace `createNotebook()` on mount with `listNotebooks()`
- Show dropdown to select existing notebook or create new
- Update `notebookId` state when selection changes
- Re-render `<Notebook>` component when `notebookId` changes

**Considerations**:
- Handle WebSocket reconnection when switching notebooks
- Clear previous notebook state when switching
- Show loading state during notebook switch

### 6. Save/Rename UI (Optional)

**Add to `Notebook` component** (`frontend/src/components/Notebook.tsx`):
- Input field or button to rename current notebook
- Save button (though auto-save already exists)
- Display current notebook name in header

## Historical Context (from thoughts/)

- `thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md` - Implementation plan for persistence system
  - Phase 3 (Notebook Persistence) was completed
  - Storage layer (`storage.py`) created with save/load functions
  - Auto-save integrated in routes.py
  - Startup loading in main.py
  - **Note**: Plan focused on persistence, not on UI for notebook selection

## Related Research

None yet - this is the first research on notebook selection UI.

## Open Questions

1. **Naming Strategy**: Should notebooks have user-friendly names, or is ID sufficient? The demo notebook uses `id="demo"` which suggests names might be useful.

2. **Default Behavior**: When app loads, should it:
   - Show dropdown immediately (no default selection)?
   - Auto-select demo notebook if it exists?
   - Auto-select most recently modified notebook?

3. **Notebook Creation**: Should "Create New Notebook" prompt for a name immediately, or create with UUID and allow renaming later?

4. **WebSocket Handling**: When switching notebooks, should WebSocket connections be:
   - Closed and reopened?
   - Maintained in parallel?
   - Pooled per notebook?

5. **Notebook Deletion**: Should the dropdown include delete functionality, or keep that separate?

6. **Metadata**: Should the list endpoint return additional metadata (last modified date, cell count, etc.) for better UX?

7. **URL Integration**: Should notebook selection be reflected in URL (e.g., `/notebooks/{id}`) for bookmarking/sharing, even though no router exists currently?

