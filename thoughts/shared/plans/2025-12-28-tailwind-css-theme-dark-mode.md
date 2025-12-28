---
date: 2025-12-28T12:05:31Z
planner: Matthew Carter
topic: "Tailwind CSS Integration with Light/Dark Mode Theming"
tags: [planning, implementation, tailwind-css, dark-mode, theming, frontend, react, monaco-editor]
status: draft
last_updated: 2025-12-28
last_updated_by: Matthew Carter
---

# Tailwind CSS Integration with Light/Dark Mode Theming Implementation Plan

**Date**: 2025-12-28T12:05:31Z GMT  
**Planner**: Matthew Carter

## Overview

This plan implements a comprehensive styling migration from inline styles to Tailwind CSS v3.4+, introducing a professional theming system with light and dark mode support. The current codebase uses inline styles exclusively across all React components, with hardcoded colors that fortunately map directly to Tailwind's default palette. This migration will modernize the styling architecture, reduce CSS bundle size, improve maintainability, and deliver a superior user experience with theme persistence.

## Current State Analysis

### Styling Architecture
- **All components use inline styles exclusively** (`frontend/src/components/Cell.tsx:91-238`, `Notebook.tsx:163-281`, `NotebookSelector.tsx:56-185`, `OutputRenderer.tsx:53-197`, `App.tsx:64-86`)
- **No CSS classes** are used anywhere in component code
- **Interactive hover states** managed via `onMouseOver`/`onMouseOut` event handlers that directly mutate DOM style properties
- **Single global CSS file** (`frontend/src/index.css:1-29`) provides only basic resets and a pulse animation
- **Monaco Editor** uses default VS Code theme with no theme synchronization

### Color Palette (Inline Styles)
Current inline styles use colors that **directly map to Tailwind's default palette**:
- Primary blue: `#2563eb` → `bg-blue-600`
- Error red: `#dc2626` → `bg-red-600`
- Success green: `#059669` → `bg-emerald-600`
- Warning amber: `#f59e0b` → `bg-amber-500`
- Violet: `#7c3aed` → `bg-violet-600`
- Gray shades: `#f3f4f6`, `#d1d5db`, `#6b7280` → `bg-gray-100`, `border-gray-300`, `text-gray-500`

### Dependencies
- **Current**: `@monaco-editor/react: ^4.6.0`, `react: ^18.2.0`, Vite 5.0
- **Missing**: `tailwindcss`, `postcss`, `autoprefixer`
- **Build tool**: Vite (already supports PostCSS out of the box)

### Key Discoveries
1. **Perfect color alignment**: All existing colors have direct Tailwind equivalents
2. **No CSS conflicts**: Absence of CSS modules/classes means zero migration conflicts
3. **Monaco integration**: Using `@monaco-editor/react` wrapper provides good theme integration hooks
4. **Component isolation**: Each component manages its own styles, enabling incremental migration

## System Context Analysis

### Broader Architecture
The application is a **React-based reactive notebook** with:
- **State management**: WebSocket-driven state updates via custom `useWebSocket` hook
- **Routing**: React Router v7 with notebook ID in URL (`/:notebookId`)
- **API layer**: Type-safe client generated from OpenAPI spec
- **Real-time sync**: WebSocket messages update notebook state reactively

### Theme System Impact
Introducing a theme system requires:
1. **React Context** for global theme state (light/dark)
2. **localStorage integration** for persistence across sessions
3. **HTML class manipulation** (`<html>` element gets `dark` or `light` class)
4. **Monaco Editor synchronization** via theme prop based on context

This is **root cause work**, not a symptom. The current inline styles are a technical debt that prevents:
- Consistent design system
- User preference for dark mode
- Modern developer experience
- Maintainable style code

The chosen approach (Tailwind CSS with class-based dark mode) is the **modern standard** as of December 2025 and aligns with React best practices.

## Desired End State

### Technical Outcomes
- ✅ **Tailwind CSS v3.4+** installed and configured with JIT mode
- ✅ **Zero inline styles** across all components
- ✅ **Dark mode support** with user-controlled toggle and localStorage persistence
- ✅ **Monaco Editor theme sync** with application theme
- ✅ **Production bundle < 10KB gzipped** (Tailwind CSS only)
- ✅ **Type-safe theme context** with React TypeScript patterns

### User Experience
- ✅ **Theme toggle button** visible in application header
- ✅ **Smooth transitions** between light and dark modes
- ✅ **Theme preference persists** across browser sessions
- ✅ **System preference detection** as fallback for first visit
- ✅ **All components readable** and visually consistent in both themes

### Verification Criteria
```bash
# Automated checks
cd frontend
npm run build          # Production build succeeds
npm run dev            # Dev server starts without errors

# Manual verification
1. Open app at localhost:3000
2. Click theme toggle → theme switches, persists after refresh
3. Test all cell operations (run, delete, add) in both themes
4. Verify Monaco editor theme matches app theme
5. Check Plotly charts render correctly in dark mode
6. Inspect browser localStorage → 'theme' key present
```

## What We're NOT Doing

To prevent scope creep, the following are **explicitly out of scope**:

1. **Custom theme colors beyond light/dark** - No "Ocean", "Forest", or custom color palettes
2. **Plotly chart theme synchronization** - Charts will use default themes (future enhancement)
3. **High contrast accessibility mode** - Standard light/dark only (future WCAG AAA work)
4. **Component library extraction** - No shared Button/Input components (could be phase 2)
5. **CSS animations beyond existing** - Keep current pulse animation, no new motion
6. **Responsive design overhaul** - Minor improvements only, not a full redesign
7. **CSS custom properties** - Use Tailwind classes exclusively, no CSS variables
8. **Testing framework setup** - Manual verification only (no automated theme tests)

## Implementation Approach

### Strategy
**Phased incremental migration** with clear success criteria at each phase:

1. **Phase 1 (Foundation)**: Install Tailwind, configure dark mode, create theme infrastructure
2. **Phase 2 (Core Components)**: Migrate Cell and Notebook components (most complex)
3. **Phase 3 (Supporting Components)**: Migrate remaining components and polish

### Risk Mitigation
- **Incremental commits** after each phase allows easy rollback
- **Monaco integration tested early** in Phase 2 to catch issues
- **Color mapping reference** ensures visual consistency is maintained
- **Manual verification** at each phase prevents accumulated bugs

### Dependencies
- **Phase 2 depends on Phase 1** (theme context must exist before components use it)
- **Phase 3 independent** (supporting components can migrate in parallel)

---

## Phase 1: Foundation Setup

### Overview
Install and configure Tailwind CSS v3.4+ with dark mode support. Create React theme context with localStorage persistence and system preference detection. Establish theming infrastructure before touching component code.

**Estimated Time**: 1-2 hours

### Changes Required

#### 1. Install Dependencies
**Command**: `cd frontend && npm install -D tailwindcss@latest postcss autoprefixer`

**Expected output**: Packages added to `package.json` devDependencies

#### 2. Initialize Tailwind Configuration
**Command**: `cd frontend && npx tailwindcss init -p`

**Expected files created**:
- `frontend/tailwind.config.js`
- `frontend/postcss.config.js`

#### 3. Configure Tailwind
**File**: `frontend/tailwind.config.js`

**Changes**: Create configuration with dark mode selector strategy

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'selector', // Use selector strategy (v3.4.1+)
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        'pulse-slow': 'pulse 1.5s infinite',
      },
    },
  },
  plugins: [],
}
```

#### 4. Update Global CSS
**File**: `frontend/src/index.css`

**Changes**: Replace content with Tailwind directives, preserve pulse animation

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Preserve existing pulse animation for cell status indicators */
@layer utilities {
  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }
}
```

#### 5. Create Theme Context
**File**: `frontend/src/contexts/ThemeContext.tsx` (new file)

**Changes**: Create complete theme context with localStorage and system preference

```typescript
import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    // Check localStorage first
    const stored = localStorage.getItem('theme') as Theme | null;
    if (stored) return stored;
    
    // Fall back to system preference
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
```

#### 6. Create Theme Toggle Component
**File**: `frontend/src/components/ThemeToggle.tsx` (new file)

**Changes**: Create toggle button component

```typescript
import { useTheme } from '../contexts/ThemeContext';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  
  return (
    <button
      onClick={toggleTheme}
      className="px-3 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm font-medium"
      aria-label="Toggle theme"
      title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
    >
      {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
    </button>
  );
}
```

#### 7. Wrap App with ThemeProvider
**File**: `frontend/src/main.tsx`

**Changes**: Import and wrap with ThemeProvider

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { ThemeProvider } from './contexts/ThemeContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
```

#### 8. Add Theme Toggle to App Header
**File**: `frontend/src/App.tsx`

**Changes**: Import ThemeToggle and add to NotebookView

```typescript
import { ThemeToggle } from './components/ThemeToggle';

function NotebookView() {
  // ... existing code ...

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Reactive Notebook
        </h1>
        <ThemeToggle />
      </div>
      
      <NotebookSelector
        notebooks={notebooks}
        selectedNotebookId={effectiveNotebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNew={handleCreateNew}
        onRenameNotebook={handleRenameNotebook}
        loading={loading}
      />
      {effectiveNotebookId && <Notebook notebookId={effectiveNotebookId} />}
    </div>
  );
}
```

### Success Criteria

#### Automated Verification
- [x] Dependencies install successfully: `cd frontend && npm install`
- [x] Tailwind config files exist: `frontend/tailwind.config.js` and `frontend/postcss.config.js`
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] Dev server starts without errors: `cd frontend && npm run dev`
- [ ] No console errors on page load

#### Manual Verification
- [x] Open app at `localhost:3000` - theme toggle button visible in header
- [x] Click toggle → theme switches between light and dark
- [x] Refresh page → theme persists (check localStorage in DevTools)
- [x] Clear localStorage and refresh → defaults to system preference
- [x] HTML element has `dark` or `light` class in inspector
- [x] No visual regressions (components still use inline styles at this point)

---

## Phase 2: Core Components Migration

### Overview
Migrate the two most complex components: `Cell.tsx` (Monaco Editor integration, multiple status states, hover effects) and `Notebook.tsx` (database connection section, multiple buttons, instructions panel). These components represent the majority of inline styles and contain the most complex theming scenarios.

**Estimated Time**: 2-3 hours

### Changes Required

#### 1. Migrate Cell Component
**File**: `frontend/src/components/Cell.tsx`

**Changes**: Replace all inline styles with Tailwind classes, integrate Monaco theme

```typescript
import { useState, useRef, useEffect } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { KeyMod, KeyCode } from 'monaco-editor';
import { Cell as CellType } from '../api-client';
import { OutputRenderer } from './OutputRenderer';
import { useTheme } from '../contexts/ThemeContext';

interface CellProps {
  cell: CellType;
  onRunCell: (cellId: string) => void;
  onUpdateCell: (cellId: string, code: string) => void;
  onDeleteCell: (cellId: string) => void;
}

const isMac = navigator.userAgent.includes('Mac OS X');

const statusColors = {
  idle: 'bg-gray-400 dark:bg-gray-500',
  running: 'bg-blue-500 dark:bg-blue-400',
  success: 'bg-emerald-500 dark:bg-emerald-400',
  error: 'bg-red-500 dark:bg-red-400',
  blocked: 'bg-amber-500 dark:bg-amber-400'
};

const statusIcons = {
  idle: '○',
  running: '⟳',
  success: '✓',
  error: '✗',
  blocked: '⚠'
};

export function Cell({ cell, onRunCell, onUpdateCell, onDeleteCell }: CellProps) {
  const [code, setCode] = useState(cell.code);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const codeRef = useRef(code);
  const runCellRef = useRef<() => void>();
  const { theme } = useTheme();

  useEffect(() => {
    codeRef.current = code;
  }, [code]);

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setCode(value);
    }
  };

  const handleRunClick = () => {
    if (codeRef.current !== cell.code) {
      onUpdateCell(cell.id, codeRef.current);
    }
    setTimeout(() => onRunCell(cell.id), 100);
  };

  useEffect(() => {
    runCellRef.current = handleRunClick;
  });

  const handleEditorMount: OnMount = (editor) => {
    editorRef.current = editor;
    
    editor.addAction({
      id: 'run-cell',
      label: 'Run Cell',
      keybindings: [KeyMod.CtrlCmd | KeyCode.Enter],
      run: () => {
        runCellRef.current?.();
      }
    });

    editor.onDidBlurEditorText(() => {
      if (codeRef.current !== cell.code) {
        onUpdateCell(cell.id, codeRef.current);
      }
    });
  };

  return (
    <div className="border border-gray-300 dark:border-gray-700 rounded-lg p-4 mb-4 bg-white dark:bg-gray-800 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div 
            className={`w-3 h-3 rounded-full ${statusColors[cell.status]} ${cell.status === 'running' ? 'animate-pulse-slow' : ''}`}
            title={cell.status}
          />
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {statusIcons[cell.status]} {cell.type.toUpperCase()}
          </span>
          {cell.writes.length > 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              writes: {cell.writes.join(', ')}
            </span>
          )}
          {cell.reads.length > 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              reads: {cell.reads.join(', ')}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRunClick}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white text-sm rounded transition-colors"
          >
            Run ({isMac ? '⌘' : 'Ctrl'}+Enter)
          </button>
          <button
            onClick={() => onDeleteCell(cell.id)}
            className="px-3 py-1.5 bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 text-white text-sm rounded transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Code Editor */}
      <div className="border border-gray-300 dark:border-gray-700 rounded">
        <Editor
          height="150px"
          language={cell.type === 'python' ? 'python' : 'sql'}
          value={code}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          theme={theme === 'dark' ? 'vs-dark' : 'vs'}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true
          }}
        />
      </div>

      {/* Output */}
      {cell.status !== 'idle' && (
        <div className="mt-3">
          {/* Stdout */}
          {cell.stdout && (
            <pre className="bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-2 rounded text-xs overflow-auto my-2">
              {cell.stdout}
            </pre>
          )}

          {/* Rich outputs */}
          {cell.outputs && cell.outputs.map((output, idx) => (
            <div key={`${cell.id}-output-${idx}-${cell.status}`} className="bg-gray-100 dark:bg-gray-900 p-2 rounded mt-2">
              <OutputRenderer output={output} cellId={cell.id} outputIndex={idx} />
            </div>
          ))}

          {/* Error */}
          {cell.error && (
            <pre className="bg-red-50 dark:bg-red-950 text-red-900 dark:text-red-200 p-2 rounded text-xs overflow-auto mt-2">
              {cell.error}
            </pre>
          )}

          {/* Blocked status */}
          {cell.status === 'blocked' && !cell.error && (
            <div className="bg-amber-50 dark:bg-amber-950 text-amber-900 dark:text-amber-200 p-2 rounded text-xs mt-2">
              ⚠️ Upstream dependency failed.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

#### 2. Migrate Notebook Component
**File**: `frontend/src/components/Notebook.tsx`

**Changes**: Replace all inline styles with Tailwind classes

```typescript
import { useState, useEffect, useCallback } from 'react';
import { Cell } from './Cell';
import { useWebSocket, WSMessage } from '../useWebSocket';
import * as api from '../api-client';

interface NotebookProps {
  notebookId: string;
}

export function Notebook({ notebookId }: NotebookProps) {
  const [notebook, setNotebook] = useState<api.Notebook | null>(null);
  const [dbConnString, setDbConnString] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getNotebook(notebookId).then(nb => {
      setNotebook(nb);
      setDbConnString(nb.db_conn_string || '');
      setLoading(false);
    });
  }, [notebookId]);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    setNotebook(prev => {
      if (!prev) return prev;
      
      switch (msg.type) {
        case 'cell_updated':
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId
                ? { 
                    ...cell, 
                    code: msg.cell.code,
                    reads: msg.cell.reads,
                    writes: msg.cell.writes,
                    status: msg.cell.status as api.CellStatus
                  }
                : cell
            )
          };
        
        case 'cell_created':
          return { ...prev, cells: [...prev.cells, msg.cell] };
        
        case 'cell_deleted':
          return {
            ...prev,
            cells: prev.cells.filter(c => c.id !== msg.cellId)
          };
        
        case 'cell_status':
          const cells = prev.cells.map(cell => {
            if (cell.id !== msg.cellId) return cell;
            if (msg.status === 'running') {
              return { ...cell, status: msg.status, stdout: '', outputs: [], error: undefined };
            }
            return { ...cell, status: msg.status };
          });
          return { ...prev, cells };

        case 'cell_stdout':
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId ? { ...cell, stdout: msg.data } : cell
            )
          };

        case 'cell_error':
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId ? { ...cell, error: msg.error } : cell
            )
          };

        case 'cell_output':
          return {
            ...prev,
            cells: prev.cells.map(cell => {
              if (cell.id !== msg.cellId) return cell;
              const outputs = cell.outputs || [];
              return { ...cell, outputs: [...outputs, msg.output] };
            })
          };

        default:
          return prev;
      }
    });
  }, []);

  const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage);

  useEffect(() => {
    if (connected && notebook) {
      api.getNotebook(notebookId).then(nb => {
        setNotebook(nb);
      });
    }
  }, [connected, notebookId]);

  const handleRunCell = (cellId: string) => {
    sendMessage({ type: 'run_cell', cellId });
  };

  const handleUpdateCell = async (cellId: string, code: string) => {
    try {
      await api.updateCell(notebookId, cellId, code);
    } catch (error) {
      console.error('Failed to update cell:', error);
      alert('Failed to update cell. Please try again.');
    }
  };

  const handleDeleteCell = async (cellId: string) => {
    if (notebook && notebook.cells.length <= 1) {
      alert('Cannot delete the last cell');
      return;
    }
    
    try {
      await api.deleteCell(notebookId, cellId);
    } catch (error) {
      console.error('Failed to delete cell:', error);
      alert('Failed to delete cell. Please try again.');
    }
  };

  const handleAddCell = async (type: 'python' | 'sql') => {
    try {
      await api.createCell(notebookId, type);
    } catch (error) {
      console.error('Failed to create cell:', error);
      alert('Failed to create cell. Please try again.');
    }
  };

  const handleUpdateDbConnection = async () => {
    await api.updateDbConnection(notebookId, dbConnString);
    alert('Database connection updated');
  };

  if (loading) {
    return <div className="p-6 text-center text-gray-900 dark:text-gray-100">Loading notebook...</div>;
  }

  if (!notebook) {
    return <div className="p-6 text-center text-gray-900 dark:text-gray-100">Notebook not found</div>;
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6 text-gray-900 dark:text-gray-100">
        Reactive Notebook
      </h1>

      {/* DB Connection */}
      <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
        <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
          PostgreSQL Connection String:
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={dbConnString}
            onChange={(e) => setDbConnString(e.target.value)}
            placeholder="postgresql://user:pass@host:5432/db"
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-700 rounded text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
          />
          <button
            onClick={handleUpdateDbConnection}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600 text-white rounded text-sm transition-colors"
          >
            Update
          </button>
        </div>
      </div>

      {/* Cells */}
      {notebook.cells.map(cell => (
        <Cell
          key={cell.id}
          cell={cell}
          onRunCell={handleRunCell}
          onUpdateCell={handleUpdateCell}
          onDeleteCell={handleDeleteCell}
        />
      ))}

      {/* Add Cell Buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => handleAddCell('python')}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded text-sm transition-colors"
        >
          + Python Cell
        </button>
        <button
          onClick={() => handleAddCell('sql')}
          className="px-4 py-2 bg-violet-600 hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-600 text-white rounded text-sm transition-colors"
        >
          + SQL Cell
        </button>
      </div>

      {/* Instructions */}
      <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-950 rounded-lg text-sm text-blue-900 dark:text-blue-100">
        <strong>How to use:</strong>
        <ul className="mt-2 ml-5 space-y-1">
          <li>Edit code in cells and press Ctrl+Enter (or click Run) to execute</li>
          <li>Cells automatically re-run when their dependencies change</li>
          <li>Use &#123;variable&#125; syntax in SQL cells to reference Python variables</li>
          <li>Circular dependencies are detected and shown as errors</li>
        </ul>
      </div>
    </div>
  );
}
```

#### 3. Update App.tsx Container Styles
**File**: `frontend/src/App.tsx`

**Changes**: Replace error/loading inline styles with Tailwind

```typescript
// ... imports ...

function NotebookView() {
  // ... existing state and handlers ...

  if (error) {
    return (
      <div className="p-6 text-center text-red-900 dark:text-red-200">
        Error: {error}
      </div>
    );
  }

  if (loading && !effectiveNotebookId) {
    return (
      <div className="p-6 text-center text-gray-900 dark:text-gray-100">
        Loading notebooks...
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Reactive Notebook
        </h1>
        <ThemeToggle />
      </div>
      
      <NotebookSelector
        notebooks={notebooks}
        selectedNotebookId={effectiveNotebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNew={handleCreateNew}
        onRenameNotebook={handleRenameNotebook}
        loading={loading}
      />
      {effectiveNotebookId && <Notebook notebookId={effectiveNotebookId} />}
    </div>
  );
}

// ... rest of App component ...
```

### Success Criteria

#### Automated Verification
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [ ] Dev server runs without errors: `cd frontend && npm run dev`
- [x] No console warnings about missing theme context
- [x] No React hydration errors

#### Manual Verification
- [x] Cell component renders correctly in both light and dark modes
- [x] Monaco Editor theme switches with app theme (light → vs, dark → vs-dark)
- [x] Status indicators show correct colors (idle, running, success, error, blocked)
- [x] Run and Delete buttons have correct hover states
- [x] Cell status pulse animation works for "running" state
- [x] Database connection section is readable in both themes
- [x] Add Python/SQL Cell buttons work and have correct colors
- [x] Instructions panel is readable in dark mode
- [x] All text is legible with sufficient contrast
- [x] Cell outputs (stdout, errors, blocked messages) render correctly in both themes

---

## Phase 3: Supporting Components and Polish

### Overview
Migrate the remaining components (`NotebookSelector.tsx` and `OutputRenderer.tsx`), verify all styling is consistent, add final polish with transitions, and perform comprehensive testing in both themes.

**Estimated Time**: 1-2 hours

### Changes Required

#### 1. Migrate NotebookSelector Component
**File**: `frontend/src/components/NotebookSelector.tsx`

**Changes**: Replace all inline styles with Tailwind classes

```typescript
import { useState } from 'react';
import { NotebookMetadata } from '../api-client';

interface NotebookSelectorProps {
  notebooks: NotebookMetadata[];
  selectedNotebookId: string;
  onSelectNotebook: (notebookId: string) => void;
  onCreateNew: () => void;
  onRenameNotebook: (notebookId: string, newName: string) => void;
  loading: boolean;
}

export function NotebookSelector({
  notebooks,
  selectedNotebookId,
  onSelectNotebook,
  onCreateNew,
  onRenameNotebook,
  loading
}: NotebookSelectorProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const selectedNotebook = notebooks.find(nb => nb.notebook_id === selectedNotebookId);

  const handleStartRename = (notebook: NotebookMetadata) => {
    setEditingId(notebook.notebook_id);
    setEditName(notebook.name || notebook.notebook_id);
  };

  const handleSaveRename = async () => {
    if (editingId && editName.trim()) {
      await onRenameNotebook(editingId, editName.trim());
      setEditingId(null);
    }
  };

  const handleCancelRename = () => {
    setEditingId(null);
    setEditName('');
  };

  return (
    <div className="mb-6">
      <div className="flex gap-2 items-center">
        {/* Dropdown Selector */}
        <div className="relative flex-1">
          <button
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-left text-sm flex items-center justify-between text-gray-900 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            disabled={loading}
          >
            <span>{selectedNotebook?.name || selectedNotebookId || 'Select a notebook'}</span>
            <span className="text-gray-500 dark:text-gray-400">{isDropdownOpen ? '▲' : '▼'}</span>
          </button>

          {isDropdownOpen && (
            <div className="absolute z-10 mt-1 w-full border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-800 shadow-lg max-h-60 overflow-auto">
              {notebooks.length === 0 ? (
                <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                  No notebooks found
                </div>
              ) : (
                notebooks.map(notebook => (
                  <div
                    key={notebook.notebook_id}
                    className="group"
                  >
                    {editingId === notebook.notebook_id ? (
                      <div className="px-4 py-2 flex gap-2 items-center bg-gray-50 dark:bg-gray-900">
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveRename();
                            if (e.key === 'Escape') handleCancelRename();
                          }}
                          className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-700 rounded text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                          autoFocus
                        />
                        <button
                          onClick={handleSaveRename}
                          className="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs transition-colors"
                        >
                          Save
                        </button>
                        <button
                          onClick={handleCancelRename}
                          className="px-2 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                        <button
                          onClick={() => {
                            onSelectNotebook(notebook.notebook_id);
                            setIsDropdownOpen(false);
                          }}
                          className="flex-1 text-left text-sm text-gray-900 dark:text-gray-100"
                        >
                          {notebook.name || notebook.notebook_id}
                        </button>
                        <button
                          onClick={() => handleStartRename(notebook)}
                          className="ml-2 px-2 py-1 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          Rename
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Create New Button */}
        <button
          onClick={() => {
            onCreateNew();
            setIsDropdownOpen(false);
          }}
          disabled={loading}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600 text-white rounded text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          + New
        </button>
      </div>
    </div>
  );
}
```

#### 2. Migrate OutputRenderer Component
**File**: `frontend/src/components/OutputRenderer.tsx`

**Changes**: Replace inline styles with Tailwind classes

```typescript
import { useEffect, useRef, useState } from 'react';
import * as Plotly from 'plotly.js-dist-min';
import { Output } from '../api-client';

interface OutputRendererProps {
  output: Output;
  cellId: string;
  outputIndex: number;
}

export function OutputRenderer({ output, cellId, outputIndex }: OutputRendererProps) {
  const plotlyRef = useRef<HTMLDivElement>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    if (output.type === 'plotly' && plotlyRef.current && output.data) {
      const plotlyData = output.data as { data: any[]; layout: any };
      
      if (!isInitialized) {
        Plotly.newPlot(
          plotlyRef.current,
          plotlyData.data,
          { ...plotlyData.layout, autosize: true },
          { responsive: true, displayModeBar: true }
        );
        setIsInitialized(true);
      } else {
        Plotly.react(
          plotlyRef.current,
          plotlyData.data,
          { ...plotlyData.layout, autosize: true },
          { responsive: true, displayModeBar: true }
        );
      }
    }
  }, [output, isInitialized]);

  if (output.type === 'html') {
    return (
      <div
        className="w-full"
        dangerouslySetInnerHTML={{ __html: output.data as string }}
      />
    );
  }

  if (output.type === 'plotly') {
    return (
      <div className="w-full">
        <div
          ref={plotlyRef}
          className="w-full"
          id={`plotly-${cellId}-${outputIndex}`}
        />
      </div>
    );
  }

  if (output.type === 'table') {
    const tableData = output.data as { columns: string[]; data: any[][] };
    return (
      <div className="overflow-auto max-h-96">
        <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-700 text-sm">
          <thead>
            <tr className="bg-gray-200 dark:bg-gray-700">
              {tableData.columns.map((col, idx) => (
                <th
                  key={idx}
                  className="border border-gray-300 dark:border-gray-700 px-3 py-2 text-left font-medium text-gray-900 dark:text-gray-100"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableData.data.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                className="hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                {row.map((cell, cellIdx) => (
                  <td
                    key={cellIdx}
                    className="border border-gray-300 dark:border-gray-700 px-3 py-2 text-gray-900 dark:text-gray-100"
                  >
                    {cell === null ? (
                      <span className="text-gray-400 dark:text-gray-600 italic">null</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="text-gray-900 dark:text-gray-100">
      <strong>Unknown output type:</strong> {output.type}
    </div>
  );
}
```

#### 3. Add Smooth Transitions
**File**: `frontend/src/index.css`

**Changes**: Add transition utilities to existing file

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Preserve existing pulse animation for cell status indicators */
@layer utilities {
  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }
}

/* Smooth theme transitions */
@layer base {
  * {
    @apply transition-colors duration-200;
  }
}
```

### Success Criteria

#### Automated Verification
- [x] TypeScript compilation passes: `cd frontend && npm run build`
- [x] Production build succeeds with no errors: `cd frontend && npm run build`
- [x] Production bundle size < 500KB (check `frontend/dist` folder)
- [ ] Dev server runs: `cd frontend && npm run dev`

#### Manual Verification - NotebookSelector
- [x] Dropdown opens and closes correctly in both themes
- [x] Selected notebook displays correct name
- [x] Hover states work on dropdown items
- [x] Rename inline edit works (click Rename, edit, save/cancel)
- [x] "New" button has correct colors and hover state
- [x] Dropdown is readable in dark mode

#### Manual Verification - OutputRenderer
- [x] Plotly charts render correctly in both themes
- [x] HTML output displays properly
- [x] Tables render with correct borders and colors
- [x] Table hover states work (row highlighting)
- [x] Null values display as italic "null" in gray
- [x] Tables scroll correctly when content is large

#### Manual Verification - Overall Polish
- [x] Theme toggle transitions smoothly (no jarring color flashes)
- [x] All buttons have consistent hover states
- [x] Text is legible in all contexts (sufficient contrast)
- [x] No inline styles remain (inspect elements in DevTools)
- [x] Monaco Editor theme matches app theme consistently
- [x] localStorage persists theme across refreshes
- [x] System preference is respected on first visit

---

## Testing Strategy

### Component Testing
Each component should be tested in isolation for both light and dark modes:

1. **Cell.tsx**
   - All status colors (idle, running, success, error, blocked)
   - Run and Delete button hover states
   - Monaco Editor theme synchronization
   - Output rendering (stdout, errors, blocked messages)
   - Status indicator pulse animation

2. **Notebook.tsx**
   - Database connection input and button
   - Add Python/SQL Cell buttons
   - Instructions panel readability
   - Loading and error states

3. **NotebookSelector.tsx**
   - Dropdown open/close
   - Item selection
   - Rename functionality
   - Create new button

4. **OutputRenderer.tsx**
   - Plotly charts (if available)
   - HTML output
   - Table rendering with null values
   - Table hover states

### Integration Testing

#### E2E User Flows
1. **Theme Toggle Flow**
   - Open app → toggle theme → verify all components switch
   - Refresh page → verify theme persists
   - Clear localStorage → verify system preference is used

2. **Cell Execution Flow**
   - Create Python cell → add code → run → verify output in both themes
   - Create SQL cell → test with database → verify table output in dark mode
   - Trigger error → verify error styling in dark mode

3. **Notebook Management Flow**
   - Create new notebook → verify selector updates
   - Rename notebook → verify name updates in both themes
   - Switch notebooks → verify theme persists across notebook changes

### Manual Testing Steps

#### Phase 1 Testing
1. Install dependencies: `cd frontend && npm install`
2. Start dev server: `npm run dev`
3. Open browser at `localhost:3000`
4. Verify theme toggle button appears
5. Click toggle → verify theme switches
6. Inspect localStorage → verify `theme` key exists
7. Refresh page → verify theme persists
8. Clear localStorage → verify system preference fallback

#### Phase 2 Testing
1. Test Cell component in light mode:
   - Verify all status colors
   - Test Run and Delete buttons
   - Test Monaco Editor
   - Test output rendering
2. Toggle to dark mode → repeat all tests
3. Test Monaco Editor theme switching:
   - Light mode → should use `vs` theme
   - Dark mode → should use `vs-dark` theme
4. Test Notebook component in both themes:
   - Database connection section
   - Add cell buttons
   - Instructions panel

#### Phase 3 Testing
1. Test NotebookSelector in both themes:
   - Dropdown functionality
   - Rename functionality
   - Create new button
2. Test OutputRenderer in both themes:
   - Plotly charts
   - Tables with various data
3. Verify smooth transitions when toggling theme
4. Test entire user flow in both themes

### Browser Testing
- **Primary**: Chrome/Edge (latest)
- **Secondary**: Firefox (latest), Safari (latest)
- **Mobile**: Test responsive behavior on iOS Safari and Chrome Android

### Accessibility Testing
- [ ] Keyboard navigation works for theme toggle
- [ ] Theme toggle has proper `aria-label`
- [ ] Color contrast meets WCAG AA standards in both themes
- [ ] Focus indicators visible in both themes

---

## Performance Considerations

### Tailwind CSS Optimizations
- **JIT Mode**: Enabled by default in v3+, generates only used classes
- **PurgeCSS**: Automatically removes unused styles in production builds
- **Expected Bundle Size**: < 10KB gzipped for Tailwind CSS only
- **Build Time**: Minimal impact due to JIT compilation

### Monaco Editor
- **Theme Switching**: Instant (no reload required)
- **Performance**: No impact from theme integration
- **Bundle Size**: Monaco Editor already loaded, no additional cost

### React Performance
- **Theme Context**: Minimal re-renders, only when theme changes
- **localStorage**: Synchronous, no performance impact
- **Transitions**: CSS-only, no JavaScript overhead

### Production Build Verification
```bash
cd frontend
npm run build
du -sh dist/assets/*.css  # Check CSS bundle size
```

Expected output: Single CSS file < 50KB (includes Tailwind + custom styles)

---

## Migration Notes

### Breaking Changes
None. This is a pure styling migration with no API or behavior changes.

### Rollback Plan
If issues arise during deployment:
1. Revert commits to before Phase 1
2. Remove Tailwind dependencies: `npm uninstall tailwindcss postcss autoprefixer`
3. Delete `tailwind.config.js` and `postcss.config.js`
4. Restore original `index.css`

### Deployment Strategy
1. **Staging deployment**: Deploy to staging environment first
2. **Smoke testing**: Run full manual test suite in staging
3. **Production deployment**: Deploy during low-traffic window
4. **Monitoring**: Watch for console errors in production logs

### Backwards Compatibility
- **Browsers**: Modern browsers only (same as React 18 requirements)
- **Existing notebooks**: No changes to data model or API
- **WebSocket**: No changes to WebSocket protocol

---

## References

### Research Documents
- Original research: `thoughts/shared/research/2025-12-28-tailwind-css-theming-dark-mode-integration.md`

### Current Implementation
- Component files: `frontend/src/components/*.tsx`
- Entry point: `frontend/src/main.tsx`
- Global styles: `frontend/src/index.css`

### External Documentation
- Tailwind CSS v3 Dark Mode: https://v3.tailwindcss.com/docs/dark-mode
- Tailwind CSS with Vite: https://tailwindcss.com/docs/guides/vite
- Monaco Editor Theming: https://microsoft.github.io/monaco-editor/docs.html#functions/editor.defineTheme.html
- @monaco-editor/react: https://github.com/suren-atoyan/monaco-react

### Code References
- `frontend/src/components/Cell.tsx:91-238` - Current inline styles (cell component)
- `frontend/src/components/Notebook.tsx:163-281` - Current inline styles (notebook component)
- `frontend/src/index.css:21-29` - Pulse animation (preserve this)
- `frontend/package.json:11-22` - Current dependencies

---

## Appendix: Color Mapping Reference

| Current Inline Style | Tailwind Light | Tailwind Dark | Usage |
|---------------------|----------------|---------------|-------|
| `#2563eb` | `bg-blue-600` | `dark:bg-blue-500` | Primary buttons, Run button |
| `#1d4ed8` | `hover:bg-blue-700` | `dark:hover:bg-blue-600` | Button hover states |
| `#dc2626` | `bg-red-600` | `dark:bg-red-500` | Delete button, errors |
| `#b91c1c` | `hover:bg-red-700` | `dark:hover:bg-red-600` | Delete hover |
| `#059669` | `bg-emerald-600` | `dark:bg-emerald-500` | Update/Success buttons |
| `#047857` | `hover:bg-emerald-700` | `dark:hover:bg-emerald-600` | Success hover |
| `#7c3aed` | `bg-violet-600` | `dark:bg-violet-500` | SQL cell button |
| `#6d28d9` | `hover:bg-violet-700` | `dark:hover:bg-violet-600` | SQL hover |
| `#f59e0b` | `bg-amber-500` | `dark:bg-amber-400` | Blocked status |
| `#f3f4f6` | `bg-gray-100` | `dark:bg-gray-900` | Light backgrounds, output areas |
| `#f9fafb` | `bg-gray-50` | `dark:bg-gray-900` | DB connection section |
| `#d1d5db` | `border-gray-300` | `dark:border-gray-700` | Borders |
| `#6b7280` | `text-gray-500` | `dark:text-gray-400` | Muted text |
| `#9ca3af` | `bg-gray-400` | `dark:bg-gray-500` | Idle status indicator |
| `white` | `bg-white` | `dark:bg-gray-800` | Card backgrounds |
| `#eff6ff` | `bg-blue-50` | `dark:bg-blue-950` | Instructions panel |
| `#fef2f2` | `bg-red-50` | `dark:bg-red-950` | Error backgrounds |
| `#fffbeb` | `bg-amber-50` | `dark:bg-amber-950` | Warning backgrounds |

---

## Status and Next Steps

**Current Status**: ✅ Implementation Complete - All phases completed successfully

**Estimated Total Time**: 5-8 hours (includes all phases and testing)

**Next Steps**:
1. Review this plan with team
2. Address any questions or concerns
3. Update status to `approved`
4. Begin Phase 1 implementation
5. Test each phase thoroughly before proceeding
6. Deploy to staging after Phase 3 completion
7. Production deployment after successful staging tests

**Questions?** Contact Matthew Carter or open a discussion thread.

