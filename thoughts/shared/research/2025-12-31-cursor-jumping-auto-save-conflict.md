---
date: 2025-12-31T13:21:26Z
researcher: Matthew Carter
topic: "Cursor Jumping Issue: Auto-Save PUT and WebSocket Update Conflict"
tags: [research, codebase, frontend, websocket, cell-editing, race-condition]
status: complete
last_updated: 2025-12-31
last_updated_by: Matthew Carter
commit_hash: 3c05cb1990af99a7f88fdb3ab46d5561ee1d7223
branch: main
---

# Research: Cursor Jumping Issue: Auto-Save PUT and WebSocket Update Conflict

**Date**: 2025-12-31T13:21:26Z  
**Researcher**: Matthew Carter

## Research Question

Why does the cursor jump around when typing fast in notebook cells, and how can we remove auto-save to only save on explicit user actions (run or save button)?

## Summary

The cursor jumping issue is caused by a race condition between the frontend's auto-save mechanism and WebSocket updates. When a user types in a cell, changes are automatically saved via PUT request after 500ms of inactivity. The backend then broadcasts a `cell_updated` WebSocket message, which triggers a state update in the frontend. This state update resets the local code editor content, causing cursor position issues when the user is still typing.

**Root Cause**: The `useEffect` hook in `NotebookCell.tsx:42-44` syncs `localCode` with `cell.code` whenever `cell.code` changes from WebSocket updates, overriding any unsaved local edits and disrupting the cursor position.

**Solution**: Remove the debounced auto-save mechanism and only persist cell changes when the user explicitly clicks the run button or a new save button.

## Detailed Findings

### Architecture Overview: React State Management with WebSocket Sync

The notebook application uses a dual-state architecture:
1. **Local State** (`localCode` in NotebookCell): Immediate UI updates for responsive typing
2. **Global State** (`cells` in NotebookApp): Source of truth synced via WebSocket

This architecture works well for collaborative editing but creates issues when combined with automatic saves during active typing.

### Component 1: Auto-Save Mechanism (Frontend)

**Location**: `frontend/src/components/NotebookCell.tsx:46-61`

The cell editor implements a 500ms debounced auto-save:

```typescript
const handleEditorChange = (value: string | undefined) => {
  if (value !== undefined) {
    setLocalCode(value);

    // Debounce server updates to prevent spam
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    if (value !== cell.code) {
      debounceTimerRef.current = setTimeout(() => {
        onUpdateCode(value);  // Triggers PUT request
      }, 500); // 500ms debounce
    }
  }
};
```

**Key Aspects**:
- Maintains local state (`localCode`) for immediate UI updates
- Debounces API calls to prevent excessive requests
- Automatically triggers `onUpdateCode` after 500ms of inactivity
- **Problem**: Doesn't account for ongoing user edits when WebSocket updates arrive

### Component 2: PUT Request Flow

**Location**: `frontend/src/components/NotebookApp.tsx:225-233`

```typescript
const updateCellCode = async (id: string, code: string) => {
  if (!notebookId) return;

  try {
    await api.updateCell(notebookId, id, code);
  } catch (err) {
    console.error("Failed to update cell:", err);
  }
};
```

**API Client**: `frontend/src/api-client.ts:239-249`
- Sends PUT request to backend endpoint
- No optimistic locking or conflict detection

**Backend Processing**: `backend/routes.py:415-460` and `backend/notebook_operations.py:13-63`
- Updates cell with concurrency lock
- Increments notebook revision
- Persists to storage
- **Broadcasts `cell_updated` via WebSocket**

### Component 3: WebSocket Update Handling

**Location**: `frontend/src/components/NotebookApp.tsx:115-123`

```typescript
case "cell_updated":
  setCells((prev) =>
    prev.map((c) =>
      c.id === msg.cellId
        ? { ...c, code: msg.cell.code, reads: msg.cell.reads, writes: msg.cell.writes }
        : c
    )
  );
  break;
```

When the backend broadcasts a cell update, the frontend updates the global `cells` state.

**Location**: `frontend/src/components/NotebookCell.tsx:42-44`

```typescript
useEffect(() => {
  setLocalCode(cell.code);
}, [cell.code]);
```

**Critical Issue**: This effect synchronizes local editor state with WebSocket updates, **overriding any local edits in progress**.

### Component 4: Run Button (Explicit Action)

**Location**: `frontend/src/components/NotebookCell.tsx:132-143`

The run button already exists and sends execution via WebSocket (not HTTP):

```typescript
<Button
  variant="ghost"
  size="sm"
  onClick={(e) => {
    e.stopPropagation();
    onRun();  // Calls runCell via WebSocket
  }}
  disabled={cell.status === "running"}
  title="Run cell (Shift+Enter)"
>
  <Play className="h-3 w-3" />
</Button>
```

**Keyboard Shortcut**: `Shift+Enter` (lines 75-78)

**Backend**: Running a cell already saves the notebook after execution (`backend/scheduler.py:160-180`)

## The Race Condition

### Scenario

1. **T=0ms**: User types "hello world"
2. **T=500ms**: Debounce timer triggers, PUT request sent with "hello world"
3. **T=501ms**: User continues typing: "hello world and more"
4. **T=550ms**: Backend processes PUT, saves "hello world", broadcasts `cell_updated`
5. **T=560ms**: Frontend receives WebSocket message
6. **T=560ms**: `setCells` updates `cells` state with `code: "hello world"`
7. **T=561ms**: `useEffect` in NotebookCell triggers, calls `setLocalCode("hello world")`
8. **T=562ms**: Monaco editor content reset to "hello world"
9. **Result**: User's additional text "and more" is lost, cursor position disrupted

### Why the Cursor Jumps

When `setLocalCode` is called while the user is actively typing or has their cursor positioned:
- Monaco editor's value is programmatically changed
- Cursor position is reset (Monaco attempts to preserve it but often fails with conflicting updates)
- If the user has made local edits not yet debounced, they're overwritten
- The visual "jump" occurs when the editor content changes under the user's cursor

## Code References

### Key Files
- `frontend/src/components/NotebookCell.tsx:46-61` - Debounced auto-save trigger
- `frontend/src/components/NotebookCell.tsx:42-44` - WebSocket sync effect (conflict point)
- `frontend/src/components/NotebookApp.tsx:115-123` - WebSocket `cell_updated` handler
- `frontend/src/components/NotebookApp.tsx:225-233` - PUT request for cell updates
- `frontend/src/api-client.ts:239-249` - API client PUT call
- `backend/routes.py:415-460` - Backend PUT endpoint
- `backend/notebook_operations.py:13-63` - Concurrency-safe cell update
- `backend/websocket.py:84-100` - WebSocket broadcast logic

### Run Button Integration
- `frontend/src/components/NotebookCell.tsx:132-143` - Run button UI
- `frontend/src/components/NotebookApp.tsx:235-237` - Run cell via WebSocket
- `backend/scheduler.py:160-180` - Cell execution with automatic save

## Proposed Solution

### Remove Auto-Save, Keep Explicit Actions Only

1. **Remove the debounced auto-save** in `NotebookCell.tsx:50-59`
   - Keep `localCode` state for responsive editing
   - Remove the debounce timer logic
   - Remove the `onUpdateCode(value)` call

2. **Save on Run** (Already Works)
   - The run button already triggers cell execution
   - Backend already saves notebook after execution
   - No changes needed

3. **Add Explicit Save Button** (New Feature)
   - Add a save icon button next to the run button
   - Call `onUpdateCode(localCode)` when clicked
   - This will trigger the PUT request and WebSocket broadcast
   - Since it's explicit, no conflict with user typing

4. **Optional: Save on Blur**
   - Consider saving when user clicks away from the cell
   - Less intrusive than continuous auto-save
   - Only triggers when user is done editing

### Implementation Changes Required

**File**: `frontend/src/components/NotebookCell.tsx`

Changes:
1. Remove debounce timer logic from `handleEditorChange`
2. Add new `handleSaveClick` function that calls `onUpdateCode(localCode)`
3. Add save button to the UI next to the run button
4. Optionally add `onBlur` handler to editor that saves when user clicks away

**File**: `frontend/src/components/NotebookApp.tsx`

No changes required - the `updateCellCode` function already exists and works correctly.

### Benefits of This Approach

1. **Eliminates race condition**: No auto-save means no unexpected WebSocket updates during typing
2. **Predictable behavior**: Users know exactly when their code is saved
3. **Collaborative-friendly**: Still supports WebSocket updates from other users or backend operations
4. **Preserves cursor position**: Local edits stay local until explicitly saved
5. **Maintains existing patterns**: Run button already saves, just extends this pattern

## Architecture Insights

### State Management Pattern
The application uses **optimistic local state with eventual consistency**:
- Local state (`localCode`) for immediate UI feedback
- Global state (`cells`) as source of truth
- WebSocket for real-time synchronization

This pattern works well when updates are **explicit and user-initiated**, but breaks down with **automatic implicit updates** during active editing.

### Concurrency Control
The backend uses:
- `asyncio` locks for cell operations (`notebook._lock`)
- Revision numbers for conflict detection
- WebSocket broadcasts to propagate changes

However, **the frontend lacks optimistic locking or conflict detection**, which combined with auto-save creates the race condition.

### Notebook Persistence Strategy
- Every cell update persists the entire notebook (file or DynamoDB)
- Cell execution also persists outputs/errors
- This "save everything" approach is reliable but requires careful timing to avoid conflicts

## Related Research

No existing research documents found on this specific issue.

## Open Questions

1. **Should we add optimistic locking to the frontend?**
   - Could use revision numbers to detect conflicts
   - Would require handling conflict resolution UI

2. **Should we distinguish between self-initiated vs. external updates?**
   - Track which WebSocket updates came from this user's actions
   - Only sync external changes to `localCode`

3. **Should we add visual indicators for unsaved changes?**
   - Show a "modified" indicator when `localCode !== cell.code`
   - Help users know when they need to save

4. **Should we auto-save on cell blur instead?**
   - Less intrusive than continuous debouncing
   - Still explicit (user moved away from cell)
   - Reduces manual save button clicks

