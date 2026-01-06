# Frontend - Multi-Notebook Support Implementation Plan

## Overview

Update the frontend to support multiple notebooks with a dropdown selector, leveraging patterns from the old implementation. Remove hardcoded notebook ID and enable notebook creation, selection, renaming, and deletion.

## Current State Analysis

**Current frontend (`frontend/src/components/NotebookApp.tsx`):**
- Hardcoded notebook ID: `"RESET AFTER UPDATING BACKEND AND RERUNNING HEY API"`
- Single notebook view only
- No notebook selector UI
- WebSocket connects to single notebook

**Old frontend (`old/frontend/src/components/NotebookApp.tsx`):**
- Dynamic notebook selection with `<Select>` dropdown
- Create, rename, delete notebook functionality
- In-dropdown rename with inline `<Input>`
- Quick rename via pencil icon next to dropdown
- URL routing with `/notebook/{notebookId}` pattern
- WebSocket reconnection when notebook changes

## System Context Analysis

This plan updates the **frontend only** to work with the multi-notebook REST API that already exists in the Interface Layer. The backend already supports:
- `GET /api/v1/notebooks/` - List all notebooks
- `POST /api/v1/notebooks/` - Create new notebook
- `PUT /api/v1/notebooks/{id}/name` - Rename notebook
- `DELETE /api/v1/notebooks/{id}` - Delete notebook

No backend changes needed - we're just wiring up the frontend UI to these existing endpoints.

## Desired End State

A frontend that:
- Shows a notebook selector dropdown in the header
- Lists all available notebooks with their names
- Allows creating new notebooks via "+ Create New Notebook" option
- Supports renaming notebooks (both inline in dropdown and via pencil icon)
- Allows deleting notebooks via trash icon (with confirmation)
- Updates URL when notebook selection changes (`/notebook/{id}`)
- Reconnects WebSocket when switching notebooks
- Loads notebook from URL parameter on initial page load

### Verification
- Can create, select, rename, and delete notebooks from UI
- URL updates reflect current notebook selection
- Refreshing page loads the correct notebook from URL
- WebSocket reconnects when switching notebooks
- No errors in console during notebook operations

## What We're NOT Doing

- Authentication/authorization (removed Clerk integration)
- User profile button (no auth = no user)
- Chat panel integration (out of scope for v1)
- Collaborative editing (multi-user conflict resolution)
- Keyboard shortcut for notebook switcher
- Notebook search/filter (future enhancement)

## Implementation Approach

**Strategy:** Port the multi-notebook patterns from the old frontend while removing auth/chat features.

**Key changes:**
1. Replace hardcoded notebook ID with state management
2. Add notebook selector dropdown with create/rename/delete actions
3. Add URL routing with `react-router-dom`
4. Update WebSocket hook to reconnect on notebook change
5. Add initialization logic to load notebook list and select first/URL notebook

---

## Phase 1: State Management & API Integration

### Overview
Replace hardcoded notebook ID with dynamic state and load notebook list on mount.

### Changes Required:

#### 1. Update NotebookApp Component State
**File**: `frontend/src/components/NotebookApp.tsx`

**Changes:**
```typescript
// Add to imports
import { useEffect } from "react";

// Replace line 23:
// OLD: const notebookId = "RESET AFTER UPDATING BACKEND AND RERUNNING HEY API"
// NEW:
const [notebookId, setNotebookId] = useState<string | null>(null);
const [notebooks, setNotebooks] = useState<NotebookMetadataResponse[]>([]);
const [isInitialized, setIsInitialized] = useState(false);

// Add initialization effect (after state declarations):
useEffect(() => {
  if (isInitialized) return;

  async function loadNotebooks() {
    try {
      const response = await api.listNotebooks();
      setNotebooks(response.notebooks);

      // Auto-select first notebook if available
      if (response.notebooks.length > 0) {
        setNotebookId(response.notebooks[0].id);
      }

      setIsInitialized(true);
    } catch (err) {
      console.error("Failed to load notebooks:", err);
    }
  }

  loadNotebooks();
}, [isInitialized]);
```

#### 2. Update Notebook Loading Effect
**File**: `frontend/src/components/NotebookApp.tsx`

**Add new effect:**
```typescript
// Load notebook data when notebookId changes
useEffect(() => {
  if (!notebookId) return;

  async function loadNotebook(id: string) {
    try {
      const notebook = await api.getNotebook(id);
      setCells(notebook.cells || []);
      setDbConnection(notebook.db_conn_string || "");
    } catch (err) {
      console.error("Failed to load notebook:", err);
    }
  }

  loadNotebook(notebookId);
}, [notebookId]);
```

#### 3. Update Functions to Check for notebookId
**File**: `frontend/src/components/NotebookApp.tsx`

**Changes to existing functions:**
```typescript
const addCell = async (type: CellType, afterCellId?: string) => {
  if (!notebookId) return; // Add this guard
  // ... rest of function
};

const deleteCell = async (id: string) => {
  if (!notebookId) return; // Add this guard
  // ... rest of function
};

const updateCellCode = async (id: string, code: string) => {
  if (!notebookId) return; // Add this guard
  // ... rest of function
};

const handleDbConnectionUpdate = async () => {
  if (!notebookId) return; // Add this guard
  // ... rest of function
};
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles without errors: `npm run build`
- [x] No console errors when page loads
- [x] API client correctly fetches notebook list

#### Manual Verification:
- [x] First notebook is auto-selected on page load
- [x] Cells load correctly from selected notebook
- [x] Can add/edit/delete cells (same as before)

---

## Phase 2: Notebook Selector UI

### Overview
Add dropdown selector with create/rename/delete actions, following patterns from old frontend.

### Changes Required:

#### 1. Add UI Imports
**File**: `frontend/src/components/NotebookApp.tsx`

```typescript
// Add to existing imports:
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { FileText, Pencil, Trash2 } from "lucide-react";
```

#### 2. Add Rename State
**File**: `frontend/src/components/NotebookApp.tsx`

```typescript
// Add to state declarations:
const [renamingNotebookId, setRenamingNotebookId] = useState<string | null>(null);
const [renameValue, setRenameValue] = useState("");
const [notebookSelectOpen, setNotebookSelectOpen] = useState(false);
const [isRenamingCurrent, setIsRenamingCurrent] = useState(false);
const [currentNotebookRenameValue, setCurrentNotebookRenameValue] = useState("");
```

#### 3. Add Notebook Management Functions
**File**: `frontend/src/components/NotebookApp.tsx`

```typescript
const handleCreateNotebook = async () => {
  try {
    const { notebook_id } = await api.createNotebook();
    const response = await api.listNotebooks();
    setNotebooks(response.notebooks);
    setNotebookId(notebook_id);
  } catch (err) {
    console.error("Failed to create notebook:", err);
  }
};

const handleRenameNotebook = async (id: string, name: string, keepSelectOpen = true) => {
  if (!name.trim()) return;

  try {
    await api.renameNotebook(id, name);
    const response = await api.listNotebooks();
    setNotebooks(response.notebooks);
    setRenamingNotebookId(null);
    setRenameValue("");
    if (keepSelectOpen) {
      setNotebookSelectOpen(true);
    }
  } catch (err) {
    console.error("Failed to rename notebook:", err);
  }
};

const handleDeleteNotebook = async (id: string) => {
  if (!confirm("Are you sure you want to delete this notebook?")) {
    return;
  }

  try {
    await api.deleteNotebook(id);

    // Refresh notebook list
    const response = await api.listNotebooks();
    setNotebooks(response.notebooks);

    // If deleted notebook was selected, switch to another
    if (notebookId === id) {
      if (response.notebooks.length > 0) {
        setNotebookId(response.notebooks[0].id);
      } else {
        setNotebookId(null);
        setCells([]);
      }
    }

    setNotebookSelectOpen(false);
  } catch (err) {
    console.error("Failed to delete notebook:", err);
    alert(`Failed to delete notebook: ${err instanceof Error ? err.message : 'Unknown error'}`);
  }
};
```

#### 4. Update API Client Functions
**File**: `frontend/src/api-client.ts`

**Add these functions (if not already present):**
```typescript
export async function createNotebook(): Promise<{ notebook_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/notebooks/`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to create notebook');
  return response.json();
}

export async function listNotebooks(): Promise<{ notebooks: NotebookMetadataResponse[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/notebooks/`);
  if (!response.ok) throw new Error('Failed to list notebooks');
  return response.json();
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/notebooks/${notebookId}/name`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error('Failed to rename notebook');
}

export async function deleteNotebook(notebookId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/notebooks/${notebookId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete notebook');
}

export type NotebookMetadataResponse = {
  id: string;
  name: string;
};
```

#### 5. Replace Header Section with Notebook Selector
**File**: `frontend/src/components/NotebookApp.tsx`

**Replace the header section (around line 210-227) with:**
```typescript
<header className="flex items-center justify-between gap-2 border-b border-border bg-card px-3 py-2 lg:px-6 lg:py-3">
  {/* Left side */}
  <div className="flex items-center gap-2 lg:gap-4 min-w-0 flex-1">
    {/* Title - hidden on small screens, shown on medium+ */}
    <h1 className="hidden md:block font-mono text-lg lg:text-xl font-semibold whitespace-nowrap">
      Reactive Notebook
    </h1>

    {/* Notebook Selector */}
    <div className="flex items-center gap-1 lg:gap-2 min-w-0 flex-1 md:flex-initial">
      {isRenamingCurrent ? (
        <Pencil className="h-4 w-4 text-muted-foreground shrink-0" />
      ) : (
        <div
          className="group/icon cursor-pointer"
          onClick={() => {
            if (notebookId) {
              const currentNotebook = notebooks.find(nb => nb.id === notebookId);
              setCurrentNotebookRenameValue(currentNotebook?.name || notebookId);
              setIsRenamingCurrent(true);
            }
          }}
        >
          <FileText className="h-4 w-4 text-muted-foreground shrink-0 group-hover/icon:hidden" />
          <Pencil className="h-4 w-4 text-muted-foreground shrink-0 hidden group-hover/icon:block" />
        </div>
      )}

      {isRenamingCurrent ? (
        <Input
          value={currentNotebookRenameValue}
          onChange={(e) => setCurrentNotebookRenameValue(e.target.value)}
          onBlur={async () => {
            if (currentNotebookRenameValue.trim() && notebookId) {
              await handleRenameNotebook(notebookId, currentNotebookRenameValue, false);
            }
            setIsRenamingCurrent(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && notebookId) {
              handleRenameNotebook(notebookId, currentNotebookRenameValue, false);
              setIsRenamingCurrent(false);
            } else if (e.key === "Escape") {
              setIsRenamingCurrent(false);
            }
          }}
          autoFocus
          className="h-10 w-full md:w-[200px] lg:w-[250px]"
        />
      ) : (
        <Select
          value={notebookId || ""}
          open={notebookSelectOpen}
          onOpenChange={(open: boolean) => {
            // Don't close if we're in rename mode
            if (!open && renamingNotebookId !== null) {
              return;
            }
            setNotebookSelectOpen(open);
          }}
          onValueChange={(value: string) => {
            if (value === "__create_new__") {
              handleCreateNotebook();
            } else if (value) {
              setNotebookId(value);
            }
          }}
        >
          <SelectTrigger className="w-full md:w-[200px] lg:w-[250px]">
            <SelectValue placeholder="Choose a notebook" />
          </SelectTrigger>
          <SelectContent>
            {notebooks.map((nb) => (
              <div key={nb.id} className="relative group">
                {renamingNotebookId === nb.id ? (
                  <div className="flex items-center gap-1 px-2 py-1.5">
                    <Input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          handleRenameNotebook(nb.id, renameValue);
                        } else if (e.key === "Escape") {
                          setRenamingNotebookId(null);
                          setRenameValue("");
                        }
                      }}
                      onBlur={() => {
                        if (renameValue.trim()) {
                          handleRenameNotebook(nb.id, renameValue);
                        } else {
                          setRenamingNotebookId(null);
                          setRenameValue("");
                        }
                      }}
                      autoFocus
                      className="h-7 text-sm"
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>
                ) : (
                  <div className="flex items-center justify-between pr-2">
                    <SelectItem value={nb.id} className="flex-1">
                      {nb.name || nb.id}
                    </SelectItem>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteNotebook(nb.id);
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
            <SelectItem value="__create_new__" className="text-primary">
              + Create New Notebook
            </SelectItem>
          </SelectContent>
        </Select>
      )}
    </div>

    {/* Keyboard shortcuts button */}
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setShowKeyboardShortcuts(true)}
      title="Keyboard shortcuts (⌘K)"
      className="hidden lg:flex shrink-0"
    >
      <Keyboard className="h-4 w-4" />
    </Button>
  </div>

  {/* Right side - DB Connection */}
  <div className="flex items-center gap-1 lg:gap-2 shrink-0">
    <Input
      placeholder="PostgreSQL connection string..."
      value={dbConnection}
      onChange={(e) => setDbConnection(e.target.value)}
      onBlur={handleDbConnectionUpdate}
      className="hidden xl:block w-64 2xl:w-80"
    />
  </div>
</header>
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles without errors
- [x] No console warnings about missing props
- [x] Select component renders correctly

#### Manual Verification:
- [x] Notebook dropdown shows list of notebooks
- [x] Can select different notebooks from dropdown
- [x] "+ Create New Notebook" creates and selects new notebook
- [x] Pencil icon next to dropdown enables inline rename
- [x] Trash icon in dropdown deletes notebook (with confirmation)
- [x] Inline rename in dropdown works (click, type, Enter/blur to save)

---

## Phase 3: URL Routing (Optional Enhancement)

### Overview
Add URL routing to support `/notebook/{id}` pattern and browser back/forward navigation.

**Note:** This phase is optional - the app works without URL routing. Implement if time allows.

### Changes Required:

#### 1. Install React Router
**Command:**
```bash
cd frontend
npm install react-router-dom
```

#### 2. Update Main App Entry Point
**File**: `frontend/src/main.tsx`

```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Wrap App in Router:
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/notebook" replace />} />
        <Route path="/notebook/:notebookId?" element={<NotebookApp />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
```

#### 3. Update NotebookApp to Use URL Params
**File**: `frontend/src/components/NotebookApp.tsx`

```typescript
// Add to imports:
import { useParams, useNavigate } from 'react-router-dom';

// Add inside component:
const { notebookId: urlNotebookId } = useParams<{ notebookId?: string }>();
const navigate = useNavigate();

// Update initialization effect to check URL:
useEffect(() => {
  if (isInitialized) return;

  async function loadNotebooks() {
    try {
      const response = await api.listNotebooks();
      setNotebooks(response.notebooks);

      // If we have a notebook ID from URL, verify it exists
      if (urlNotebookId) {
        const notebookExists = response.notebooks.some(nb => nb.id === urlNotebookId);
        if (notebookExists) {
          setNotebookId(urlNotebookId);
        } else if (response.notebooks.length > 0) {
          setNotebookId(response.notebooks[0].id);
        }
      } else if (response.notebooks.length > 0) {
        setNotebookId(response.notebooks[0].id);
      }

      setIsInitialized(true);
    } catch (err) {
      console.error("Failed to load notebooks:", err);
    }
  }

  loadNotebooks();
}, [isInitialized, urlNotebookId]);

// Add effect to update URL when notebookId changes:
useEffect(() => {
  if (notebookId && notebookId !== urlNotebookId) {
    navigate(`/notebook/${notebookId}`, { replace: true });
  }
}, [notebookId, urlNotebookId, navigate]);
```

### Success Criteria:

#### Automated Verification:
- [x] App builds without errors
- [x] No router-related console errors

#### Manual Verification:
- [x] URL updates when selecting different notebooks
- [x] Refreshing page loads the correct notebook from URL
- [x] Browser back/forward buttons work correctly
- [x] Invalid notebook ID in URL falls back to first notebook

---

## Testing Strategy

### Manual Testing Steps
1. Start backend and frontend servers
2. Open `http://localhost:5173`
3. Verify first notebook is auto-selected
4. Click notebook dropdown - verify list appears
5. Click "+ Create New Notebook" - verify new notebook created and selected
6. Click pencil icon next to dropdown - verify inline rename works
7. Click into dropdown, hover over notebook - verify trash icon appears
8. Click trash icon - verify confirmation and deletion works
9. Switch between notebooks - verify cells update correctly
10. Add cell to notebook A, switch to notebook B, switch back - verify cell persists
11. If URL routing enabled: verify URL updates and page refresh works

### Edge Cases to Test
- Creating notebook when none exist
- Deleting last notebook
- Deleting currently selected notebook
- Renaming to empty string (should not save)
- Rapid notebook switching (WebSocket reconnection)
- Network errors during notebook operations

## Performance Considerations

- **Notebook list refresh**: Currently refetches full list after each create/rename/delete operation
  - Future: Use optimistic updates to avoid re-fetch
- **WebSocket reconnection**: Currently disconnects and reconnects when switching notebooks
  - Acceptable for v1 (notebooks are independent)
  - Future: Consider connection pooling

## Migration Notes

**From old frontend:**
- ✅ Keep: Dropdown selector pattern, inline rename, trash icon
- ❌ Remove: Clerk auth integration, UserButton component
- ❌ Remove: Chat panel toggle and state
- ❌ Remove: `onToggleChat` prop in NotebookCell

**Dependencies to remove:**
```bash
npm uninstall @clerk/clerk-react  # If present
```

## References

- Old frontend: `old/frontend/src/components/NotebookApp.tsx`
- Interface Layer API: `thoughts/shared/plans/2026-01-06-interface-layer-file-based-notebooks.md`
- shadcn/ui Select: https://ui.shadcn.com/docs/components/select
- React Router: https://reactrouter.com/en/main
