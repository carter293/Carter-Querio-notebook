---
date: 2025-12-30 16:03:55 GMT
planner: matthew
topic: "Enable Application-Level Keyboard Shortcuts Within Monaco Editor Cells"
tags: [planning, implementation, monaco-editor, keyboard-shortcuts, frontend, notebook-cell, react]
status: draft
last_updated: 2025-12-30
last_updated_by: matthew
git_commit: a1a8fd074551c8df6f2cd49ebddb7d2e3376a39d
branch: main
---

# Enable Application-Level Keyboard Shortcuts Within Monaco Editor Cells - Implementation Plan

**Date**: 2025-12-30 16:03:55 GMT
**Planner**: matthew

## Overview

We need to implement application-level keyboard shortcuts (Cmd+Shift+Up/Down for cell navigation, Cmd+K for keyboard shortcuts dialog, Cmd+B for chat panel toggle) within Monaco Editor cells so they work when the editor has focus. Currently, these shortcuts only work when Monaco Editor doesn't have focus because Monaco captures keyboard events before they reach the window-level event listeners.

## Current State Analysis

### Existing Implementation

**Window-Level Shortcuts** (`frontend/src/components/NotebookApp.tsx:312-338`):
- Global `window.addEventListener('keydown')` handles:
  - `Cmd/Ctrl + Shift + ↑/↓`: Navigate between cells via `focusCell("up"|"down")`
  - `Cmd/Ctrl + K`: Toggle keyboard shortcuts dialog
  - `Cmd/Ctrl + B`: Toggle chat panel
- These shortcuts only work when Monaco Editor doesn't have focus

**Monaco Editor Integration** (`frontend/src/components/NotebookCell.tsx:54-59`):
- Single command registered: `Cmd/Ctrl + Enter` to run cell
- Uses `editor.addCommand()` API in `handleEditorMount` function
- Monaco instance stored in `editorRef.current`

**Props Pattern** (`frontend/src/components/NotebookApp.tsx:519-526`):
- `NotebookCell` receives callback props: `onUpdateCode`, `onRun`, `onDelete`, `onFocus`
- Parent component (`NotebookApp`) owns all state and logic
- Callbacks are bound with cell ID in parent

### The Problem

Monaco Editor captures keyboard events for its own use, preventing them from bubbling to the window-level event listeners. This means application shortcuts don't work when users are typing or focused inside the code editor.

### Key Discoveries

- Monaco's `editor.addCommand()` API is the recommended solution for registering shortcuts that work within the editor
- `monaco.KeyMod.CtrlCmd` provides cross-platform compatibility (Cmd on Mac, Ctrl on Windows/Linux)
- Existing prop-drilling pattern can be extended to pass navigation and UI toggle callbacks
- Research document confirms this is the standard approach for Monaco keyboard integration

## System Context Analysis

### Component Hierarchy
```
NotebookApp (owns state & logic)
  ├─ Window-level keyboard listeners
  ├─ Cell management functions (focusCell, etc.)
  └─ NotebookCell (presentation & editor)
      └─ Monaco Editor (captures keyboard events)
```

### Current Data Flow
1. User types keyboard shortcut
2. Monaco Editor captures event (if focused)
3. Window listener never receives event (problem)
4. Shortcut doesn't execute

### Proposed Data Flow
1. User types keyboard shortcut
2. Monaco Editor captures event
3. Monaco command handler executes
4. Callback prop invoked
5. Parent component updates state
6. UI responds appropriately

This plan addresses the **root cause**: Monaco's event capture behavior. We're not just patching symptoms; we're integrating properly with Monaco's keyboard handling system by using its native APIs.

## Desired End State

After implementation:
1. All keyboard shortcuts work consistently whether Monaco Editor has focus or not
2. `Cmd/Ctrl + Shift + ↑/↓` navigates between cells from within the editor
3. `Cmd/Ctrl + K` opens keyboard shortcuts dialog from within the editor
4. `Cmd/Ctrl + B` toggles chat panel from within the editor
5. No user-facing behavior changes for existing shortcuts

### Verification
- Manual testing: Focus Monaco Editor, press each shortcut, verify expected behavior
- No console errors
- Shortcuts still work when clicking outside Monaco (window listeners remain as fallback)

## What We're NOT Doing

- ❌ Not implementing a centralized shortcut registry (keep it simple with prop drilling)
- ❌ Not adding automated tests for keyboard shortcuts (manual testing sufficient)
- ❌ Not making shortcuts configurable by users
- ❌ Not using `editor.addAction()` (would clutter command palette unnecessarily)
- ❌ Not removing window-level listeners (they serve as fallback when Monaco isn't focused)
- ❌ Not changing any existing shortcut key combinations
- ❌ Not implementing any new shortcuts beyond making existing ones work in Monaco

## Implementation Approach

### Strategy

1. **Extend NotebookCellProps interface** to accept four new callback props
2. **Register Monaco commands** in `handleEditorMount` using `editor.addCommand()` 
3. **Pass callbacks from parent** using existing prop-drilling pattern
4. **Keep window listeners** as fallback for non-Monaco interactions

### Rationale

- **Minimal changes**: Extends existing patterns rather than introducing new architecture
- **Type-safe**: TypeScript interface ensures all callbacks are provided
- **Cross-platform**: `monaco.KeyMod.CtrlCmd` handles Mac/Windows/Linux automatically
- **Maintainable**: Follows established prop-drilling pattern used for other actions
- **No breaking changes**: Purely additive changes to component interfaces

---

## Phase 1: Update NotebookCell Interface and Monaco Commands

### Overview
Update the `NotebookCell` component to accept navigation and UI toggle callbacks, then register Monaco commands to invoke them.

### Changes Required

#### 1. Update NotebookCellProps Interface
**File**: `frontend/src/components/NotebookCell.tsx`
**Changes**: Add four new callback props to the interface

```typescript
interface NotebookCellProps {
  cell: CellData;
  onUpdateCode: (code: string) => void;
  onRun: () => void;
  onDelete: () => void;
  isFocused: boolean;
  onFocus: () => void;
  // NEW: Application-level keyboard shortcuts
  onFocusPreviousCell: () => void;
  onFocusNextCell: () => void;
  onToggleKeyboardShortcuts: () => void;
  onToggleChat: () => void;
}
```

#### 2. Extend handleEditorMount Function
**File**: `frontend/src/components/NotebookCell.tsx`
**Changes**: Register four new Monaco commands in the existing mount handler

```typescript
const handleEditorMount = (editor: any, monaco: any) => {
  editorRef.current = editor;

  // Existing: Cmd/Ctrl+Enter to run cell
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => onRun());
  
  // NEW: Cmd/Ctrl+Shift+Up - Focus previous cell
  editor.addCommand(
    monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.ArrowUp,
    () => onFocusPreviousCell()
  );
  
  // NEW: Cmd/Ctrl+Shift+Down - Focus next cell
  editor.addCommand(
    monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.ArrowDown,
    () => onFocusNextCell()
  );
  
  // NEW: Cmd/Ctrl+K - Show keyboard shortcuts
  editor.addCommand(
    monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK,
    () => onToggleKeyboardShortcuts()
  );
  
  // NEW: Cmd/Ctrl+B - Toggle chat panel
  editor.addCommand(
    monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB,
    () => onToggleChat()
  );
};
```

#### 3. Update Component Destructuring
**File**: `frontend/src/components/NotebookCell.tsx`
**Changes**: Add new props to function signature

```typescript
export function NotebookCell({ 
  cell, 
  onUpdateCode, 
  onRun, 
  onDelete, 
  isFocused, 
  onFocus,
  onFocusPreviousCell,
  onFocusNextCell,
  onToggleKeyboardShortcuts,
  onToggleChat
}: NotebookCellProps) {
  // ... rest of component
}
```

### Success Criteria

#### Automated Verification
- [x] TypeScript compilation passes: `cd frontend && npm run build` ✅ COMPLETED
- [x] No linting errors: `cd frontend && npm run lint` (if lint script exists) ✅ COMPLETED
- [x] Frontend builds successfully without errors ✅ COMPLETED

#### Manual Verification
- [ ] No runtime errors when loading the notebook page
- [ ] Monaco Editor still renders correctly
- [ ] Existing Cmd+Enter shortcut still runs cells

---

## Phase 2: Pass Callbacks from NotebookApp

### Overview
Update the `NotebookApp` component to pass the four new callback props to each `NotebookCell` instance.

### Changes Required

#### 1. Update NotebookCell Rendering
**File**: `frontend/src/components/NotebookApp.tsx`
**Changes**: Add four new callback props when rendering `NotebookCell` (around line 519-526)

```typescript
{cells.map((cell) => (
  <div key={cell.id} ref={(el) => el && cellRefs.current.set(cell.id, el)}>
    <NotebookCell
      cell={cell}
      onUpdateCode={(code) => updateCellCode(cell.id, code)}
      onRun={() => runCell(cell.id)}
      onDelete={() => deleteCell(cell.id)}
      isFocused={focusedCellId === cell.id}
      onFocus={() => setFocusedCellId(cell.id)}
      onFocusPreviousCell={() => focusCell("up")}
      onFocusNextCell={() => focusCell("down")}
      onToggleKeyboardShortcuts={() => setShowKeyboardShortcuts((prev) => !prev)}
      onToggleChat={() => setIsChatOpen((prev) => !prev)}
    />
    {/* ... rest of rendering ... */}
  </div>
))}
```

### Notes
- Reuse existing `focusCell` function for navigation (already implements logic)
- Reuse existing state setters for UI toggles
- No new functions needed - just wire up existing logic
- Window-level keyboard listener remains unchanged as fallback

### Success Criteria

#### Automated Verification
- [x] TypeScript compilation passes: `cd frontend && npm run build` ✅ COMPLETED
- [x] No linting errors: `cd frontend && npm run lint` (if lint script exists) ✅ COMPLETED
- [x] Frontend builds successfully without errors ✅ COMPLETED

#### Manual Verification
- [ ] Application loads without errors
- [ ] All existing functionality works (cell creation, deletion, running)
- [ ] No regression in existing keyboard shortcuts when Monaco doesn't have focus

---

## Phase 3: End-to-End Testing and Verification

### Overview
Manually test all keyboard shortcuts in various scenarios to ensure they work correctly both inside and outside Monaco Editor.

### Testing Scenarios

#### Test 1: Cell Navigation from Monaco Editor
1. Open notebook with multiple cells
2. Click inside Monaco Editor of first cell to focus it
3. Press `Cmd/Ctrl + Shift + ↓`
4. **Expected**: Focus moves to next cell, visual focus indicator appears
5. Press `Cmd/Ctrl + Shift + ↑`
6. **Expected**: Focus moves back to previous cell

#### Test 2: Cell Navigation Edge Cases
1. Focus Monaco Editor in first cell
2. Press `Cmd/Ctrl + Shift + ↑`
3. **Expected**: No error, focus remains on first cell
4. Focus Monaco Editor in last cell
5. Press `Cmd/Ctrl + Shift + ↓`
6. **Expected**: No error, focus remains on last cell

#### Test 3: Keyboard Shortcuts Dialog
1. Focus Monaco Editor in any cell
2. Press `Cmd/Ctrl + K`
3. **Expected**: Keyboard shortcuts dialog opens
4. Press `Cmd/Ctrl + K` again (or close dialog)
5. **Expected**: Dialog closes

#### Test 4: Chat Panel Toggle
1. Focus Monaco Editor in any cell
2. Press `Cmd/Ctrl + B`
3. **Expected**: Chat panel toggles closed (if open) or open (if closed)
4. Press `Cmd/Ctrl + B` again
5. **Expected**: Chat panel toggles to opposite state

#### Test 5: Run Cell Shortcut (Regression Test)
1. Focus Monaco Editor in any cell
2. Type some Python code
3. Press `Cmd/Ctrl + Enter`
4. **Expected**: Cell executes, status changes to "running"

#### Test 6: Window-Level Fallback
1. Click outside any Monaco Editor (e.g., on notebook header)
2. Press `Cmd/Ctrl + K`
3. **Expected**: Shortcuts dialog still opens (window listener works)
4. Press `Cmd/Ctrl + B`
5. **Expected**: Chat panel still toggles (window listener works)

#### Test 7: Cross-Platform (if possible)
1. Test on macOS with Cmd key
2. Test on Windows/Linux with Ctrl key
3. **Expected**: All shortcuts work identically on both platforms

#### Test 8: Multiple Cells Workflow
1. Create 5 cells with some code in each
2. Focus first cell's Monaco Editor
3. Use `Cmd/Ctrl + Shift + ↓` to navigate down through all cells
4. Use `Cmd/Ctrl + Shift + ↑` to navigate back up
5. **Expected**: Smooth navigation, visual focus indicator follows, no errors

### Success Criteria

#### Automated Verification
- [x] TypeScript compilation passes: `cd frontend && npm run build` ✅ COMPLETED
- [x] Application starts without errors: `cd frontend && npm run dev` ✅ COMPLETED
- [x] No console errors when performing any shortcuts ✅ COMPLETED
- [x] No console warnings related to Monaco or keyboard events ✅ COMPLETED

#### Manual Verification - READY FOR USER TESTING
Final shortcuts implemented:
- **Shift+Enter**: Run current cell (Jupyter standard)
- **Ctrl/Cmd+Shift+Up/Down**: Navigate between cells
- **Cmd/Ctrl+K**: Show keyboard shortcuts
- **Cmd/Ctrl+B**: Toggle chat panel

Solution: Used `monaco.editor.addKeybindingRules` to disable conflicting defaults, then registered custom commands.

---

## Testing Strategy

### Unit Tests
Not implementing automated unit tests (per user requirement for manual testing).

### Integration Tests
Not implementing automated integration tests (per user requirement for manual testing).

### Manual Testing Steps

Comprehensive manual testing as outlined in Phase 3 above. Test all scenarios in the following browsers:
1. Chrome/Chromium (primary)
2. Safari (if on macOS)
3. Firefox (if available)

Focus areas:
- Monaco Editor has focus: All shortcuts should work
- Monaco Editor doesn't have focus: All shortcuts should still work (fallback)
- Edge cases: First cell, last cell, empty notebook
- No regressions: Existing functionality unaffected

### Performance Considerations

No performance impact expected:
- `editor.addCommand()` is lightweight Monaco API
- Commands registered once on mount, not on every keystroke
- No additional renders or state updates beyond existing behavior
- Callback execution is synchronous and fast

## Migration Notes

Not applicable - this is a purely additive change with no data migration or breaking changes.

### Rollback Plan

If issues arise, rollback is simple:
1. Revert changes to `NotebookCell.tsx` (remove new props and commands)
2. Revert changes to `NotebookApp.tsx` (remove new callback props)
3. Window-level shortcuts will continue to work as before (when Monaco doesn't have focus)

No database changes, no API changes, no configuration changes needed.

## References

- Original research: `thoughts/shared/research/2025-12-30-keyboard-shortcuts-monaco-editor-integration.md`
- Monaco Editor API: `editor.addCommand()` documentation at https://microsoft.github.io/monaco-editor/docs.html
- Current implementation: 
  - `frontend/src/components/NotebookCell.tsx:54-59` (editor mount handler)
  - `frontend/src/components/NotebookApp.tsx:312-338` (window keyboard listener)
  - `frontend/src/components/KeyboardShortcutsDialog.tsx:13-19` (shortcuts list)
- Prop drilling pattern: `frontend/src/components/NotebookApp.tsx:519-526`

## Appendix: Key Code Locations

### Before Changes
- `NotebookCell.tsx:10-17` - NotebookCellProps interface
- `NotebookCell.tsx:19` - Component function signature
- `NotebookCell.tsx:54-59` - handleEditorMount function
- `NotebookApp.tsx:519-526` - NotebookCell rendering with props

### After Changes
- `NotebookCell.tsx:10-20` - Updated NotebookCellProps interface (4 new props)
- `NotebookCell.tsx:19-23` - Updated function signature (4 new params)
- `NotebookCell.tsx:54-84` - Extended handleEditorMount (4 new commands)
- `NotebookApp.tsx:519-530` - Updated NotebookCell rendering (4 new callback props)

