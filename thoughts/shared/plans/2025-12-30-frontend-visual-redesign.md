# Frontend Visual Redesign Implementation Plan

## Overview

Redesign the reactive notebook frontend to match the modern, clean aesthetic of the design_inspo mockup. This is a visual-only refactor that preserves all existing functionality (WebSocket updates, SSE streaming, cell execution, auth, etc.) while improving the UI/UX with shadcn/ui components, better layouts, and proper theming.

## Current State Analysis

### Key Issues Identified:
1. **Wrong background colors** - Using navy (`--color-bg-output`) for page background instead of proper surface colors
2. **Page-level constraints** - Everything wrapped in `max-w-4xl` causing unnecessary width limits
3. **Fixed chat width** - Chat panel is 384px fixed instead of proportional 1/3 of viewport
4. **Missing shadcn/ui components** - Using custom CSS classes instead of proper component library
5. **Inconsistent spacing** - Mix of hardcoded Tailwind utilities instead of design system
6. **Cell header layout** - Status info cramped, buttons inconsistent
7. **No focus states** - Cells don't show visual feedback on focus

### What Works Well:
- WebSocket state management in [Notebook.tsx:44-118](frontend/src/components/Notebook.tsx#L44-L118)
- SSE streaming in [ChatPanel.tsx](frontend/src/components/ChatPanel.tsx)
- Monaco editor integration with keyboard shortcuts [Cell.tsx:62-84](frontend/src/components/Cell.tsx#L62-L84)
- Theme toggle implementation with CSS variables
- Clerk authentication

## System Context Analysis

The frontend uses a **local-first state management** pattern where:
1. WebSocket messages update React state optimistically
2. SSE streams handle LLM chat responses
3. Monaco editor state is managed locally with blur-based persistence

This redesign only touches **presentational components** - the state management, WebSocket handlers, and business logic remain unchanged. We're refactoring the UI layer from custom CSS classes to shadcn/ui components while maintaining the exact same data flow and event handlers.

## Desired End State

A visually polished notebook interface that:
- Matches the clean, modern aesthetic of design_inspo
- Uses consistent shadcn/ui components throughout
- Has proper spacing, colors, and typography
- Maintains 100% functional parity with current implementation
- Supports dark/light themes seamlessly

### Verification:
- All cell execution, WebSocket updates, and chat streaming work identically
- Visual appearance matches design_inspo mockup
- No console errors or warnings
- Theme toggle works without visual glitches
- All keyboard shortcuts preserved (Cmd/Ctrl+Enter, etc.)

## What We're NOT Doing

- **NOT** changing backend APIs or WebSocket message format
- **NOT** modifying state management patterns
- **NOT** adding new features (keyboard navigation, virtualization, etc.) - these are optional Phase 5 only
- **NOT** changing authentication or authorization logic
- **NOT** touching notebook execution engine or dependency graph
- **NOT** migrating to a different UI framework (staying with Tailwind + shadcn/ui)

## Implementation Approach

Incremental, phase-by-phase refactor with testing after each step. Each phase produces a working, deployable state. We'll use shadcn/ui components copied directly from design_inspo to ensure consistency.

---

## Phase 1: Foundation & Dependencies

### Overview
Install dependencies and create utility functions needed for shadcn/ui components.

### Changes Required:

#### 1. Install Dependencies
**File**: `frontend/package.json`

**Changes**: Add missing dependencies

```bash
npm install class-variance-authority clsx tailwind-merge
npm install lucide-react  # Already installed, verify version
```

#### 2. Create Utilities Helper
**File**: `frontend/src/lib/utils.ts` (new)

**Changes**: Add `cn()` helper for className merging

```typescript
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

#### 3. Copy shadcn/ui Button Component
**File**: `frontend/src/components/ui/button.tsx` (new)

**Changes**: Copy from design_inspo with minor adjustments

```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow hover:bg-primary-hover",
        destructive: "bg-error text-white shadow-sm hover:bg-error-hover",
        outline: "border border-border bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary-hover",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

#### 4. Copy shadcn/ui Card Component
**File**: `frontend/src/components/ui/card.tsx` (new)

**Changes**: Copy from design_inspo

```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
      className
    )}
    {...props}
  />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6", className)}
    {...props}
  />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("font-semibold leading-none tracking-tight", className)}
    {...props}
  />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center p-6 pt-0", className)}
    {...props}
  />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
```

#### 5. Copy shadcn/ui Badge Component
**File**: `frontend/src/components/ui/badge.tsx` (new)

**Changes**: Copy from design_inspo (already exists there)

```typescript
import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 transition-colors overflow-hidden',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        destructive: 'border-transparent bg-destructive text-white',
        outline: 'text-foreground',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<'span'> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'span'

  return (
    <Comp
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
```

#### 6. Copy shadcn/ui Input Component
**File**: `frontend/src/components/ui/input.tsx` (new)

**Changes**: Create input component

```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-border bg-surface px-3 py-1 text-sm text-text-primary shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-text-primary placeholder:text-text-tertiary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-focus disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
```

#### 7. Update CSS Variables
**File**: `frontend/src/index.css`

**Changes**: Add missing shadcn/ui CSS variables to `:root` and `.dark`

Add to `:root` block (line 6):
```css
:root {
  /* Existing variables... */

  /* shadcn/ui compatibility */
  --color-card: var(--color-surface);
  --color-card-foreground: var(--color-text-primary);
  --color-popover: var(--color-surface-elevated);
  --color-popover-foreground: var(--color-text-primary);
  --color-muted: var(--color-surface-secondary);
  --color-muted-foreground: var(--color-text-secondary);
  --color-accent: var(--color-surface-elevated);
  --color-accent-foreground: var(--color-text-primary);
  --color-destructive: var(--color-error);
  --color-destructive-foreground: 255 255 255;
  --color-ring: var(--color-border-focus);
}
```

Add to `.dark` block (line 60):
```css
.dark {
  /* Existing variables... */

  /* shadcn/ui compatibility */
  --color-card: var(--color-surface);
  --color-card-foreground: var(--color-text-primary);
  --color-popover: var(--color-surface-elevated);
  --color-popover-foreground: var(--color-text-primary);
  --color-muted: var(--color-surface-secondary);
  --color-muted-foreground: var(--color-text-secondary);
  --color-accent: var(--color-surface-elevated);
  --color-accent-foreground: var(--color-text-primary);
  --color-destructive: var(--color-error);
  --color-destructive-foreground: 255 255 255;
  --color-ring: var(--color-border-focus);
}
```

Update Tailwind config to expose new colors:
```javascript
// Add to theme.extend.colors in tailwind.config.js (line 10)
card: {
  DEFAULT: 'rgb(var(--color-card) / <alpha-value>)',
  foreground: 'rgb(var(--color-card-foreground) / <alpha-value>)',
},
popover: {
  DEFAULT: 'rgb(var(--color-popover) / <alpha-value>)',
  foreground: 'rgb(var(--color-popover-foreground) / <alpha-value>)',
},
muted: {
  DEFAULT: 'rgb(var(--color-muted) / <alpha-value>)',
  foreground: 'rgb(var(--color-muted-foreground) / <alpha-value>)',
},
accent: {
  DEFAULT: 'rgb(var(--color-accent) / <alpha-value>)',
  foreground: 'rgb(var(--color-accent-foreground) / <alpha-value>)',
},
destructive: {
  DEFAULT: 'rgb(var(--color-destructive) / <alpha-value>)',
  foreground: 'rgb(var(--color-destructive-foreground) / <alpha-value>)',
},
ring: 'rgb(var(--color-ring) / <alpha-value>)',
```

#### 8. Update TypeScript Path Alias
**File**: `frontend/tsconfig.json`

**Changes**: Add `@/*` path alias for imports

```json
{
  "compilerOptions": {
    // ... existing config
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

**File**: `frontend/vite.config.ts`

**Changes**: Add resolver for `@/*` alias

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

### Success Criteria:

#### Automated Verification:
- [x] Dependencies install without errors: `npm install`
- [x] TypeScript compiles: `npm run build`
- [x] Dev server starts: `npm run dev`
- [x] No console errors on page load

#### Manual Verification:
- [x] shadcn/ui components render correctly in isolation
- [x] `cn()` utility merges classNames properly
- [x] Path alias `@/*` resolves correctly

---

## Phase 2: Background & Layout Foundation

### Overview
Fix the fundamental layout issues: remove page-level width constraint, fix background colors, and establish proper viewport-based layout.

### Changes Required:

#### 1. Fix Background Colors & Remove Width Constraint
**File**: `frontend/src/App.tsx`

**Changes**: Remove `max-w-4xl` and fix background

```typescript
// Line 84-143: Replace the NotebookView return statement
return (
  <div className="min-h-screen bg-background">
    <div className="px-6 py-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex-row-between mb-6">
          <h1 className="text-2xl font-bold text-text-primary">
            Reactive Notebook
          </h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <UserButton afterSignOutUrl="/" />
          </div>
        </div>

        <NotebookSelector
          notebooks={notebooks}
          selectedNotebookId={notebookId || null}
          onSelectNotebook={handleSelectNotebook}
          onCreateNew={handleCreateNew}
          onRenameNotebook={handleRenameNotebook}
          loading={loading}
        />
      </div>

      {/* Only render Notebook component if a notebook is selected */}
      {notebookId ? (
        <Notebook notebookId={notebookId} />
      ) : (
        // Empty state when no notebook selected
        <div className="max-w-5xl mx-auto">
          <div className="card-section mt-6 text-center">
            {/* ... existing empty state content ... */}
          </div>
        </div>
      )}
    </div>
  </div>
);
```

Key changes:
- `bg-output` → `bg-background` (proper surface color)
- Remove `max-w-4xl mx-auto` from outer div
- Add `max-w-5xl mx-auto` to header/selector only
- Notebook component gets full width (will handle its own constraints)

#### 2. Update CSS Variables for Background
**File**: `frontend/src/index.css`

**Changes**: Fix background color to use proper surface color

```css
/* Line 7-8: Update :root background */
:root {
  /* Existing surface colors stay the same */
  --color-background: var(--color-surface); /* NEW: proper background */
  --color-foreground: var(--color-text-primary); /* NEW: proper text */

  /* Existing variables... */
}

/* Line 60-61: Update .dark background */
.dark {
  --color-background: var(--color-surface); /* NEW: proper dark background */
  --color-foreground: var(--color-text-primary); /* NEW: proper dark text */

  /* Existing variables... */
}
```

Update base styles (line 114-126):
```css
html {
  background-color: rgb(var(--color-background));
}

body {
  background-color: rgb(var(--color-background));
  color: rgb(var(--color-foreground));
  /* ... rest stays the same ... */
}
```

Add to tailwind.config.js:
```javascript
background: {
  DEFAULT: 'rgb(var(--color-background) / <alpha-value>)',
},
foreground: 'rgb(var(--color-foreground) / <alpha-value>)',
```

#### 3. Convert Notebook to Full-Height Flex Layout
**File**: `frontend/src/components/Notebook.tsx`

**Changes**: Replace fixed layout with flex-based proportional layout

Line 228-330: Replace entire return statement:
```typescript
return (
  <div className="flex h-[calc(100vh-180px)]">
    {/* Left: Notebook (2/3 width) */}
    <div className="flex-1 overflow-auto">
      <div className="max-w-5xl mx-auto px-6">
        {/* DB Connection */}
        <div className="card-section">
          <label className="label">
            PostgreSQL Connection String:
          </label>
          <div className="flex-row-gap">
            <input
              type="text"
              value={dbConnString}
              onChange={(e) => setDbConnString(e.target.value)}
              placeholder="postgresql://user:pass@host:5432/db"
              className="flex-full input-field"
              disabled={isLLMWorking}
            />
            <button
              onClick={handleUpdateDbConnection}
              className="btn-success"
              disabled={isLLMWorking}
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
            disabled={isLLMWorking}
            onRunCell={handleRunCell}
            onUpdateCell={handleUpdateCell}
            onDeleteCell={handleDeleteCell}
          />
        ))}

        {/* Add Cell Buttons */}
        <div className="flex-row-gap">
          <button
            onClick={() => handleAddCell('python')}
            className="btn-primary"
            disabled={isLLMWorking}
          >
            + Python Cell
          </button>
          <button
            onClick={() => handleAddCell('sql')}
            className="btn-primary"
            disabled={isLLMWorking}
          >
            + SQL Cell
          </button>
        </div>

        {/* Instructions */}
        <div className="card-info mt-8 mb-8">
          <strong>How to use:</strong>
          <ul className="mt-2 ml-5 space-y-1">
            <li>Edit code in cells and press Ctrl+Enter (or click Run) to execute</li>
            <li>Cells automatically re-run when their dependencies change</li>
            <li>Use &#123;variable&#125; syntax in SQL cells to reference Python variables</li>
            <li>Circular dependencies are detected and shown as errors</li>
          </ul>
        </div>
      </div>
    </div>

    {/* Right: Chat Panel (1/3 width) */}
    {showChat && (
      <div className="w-1/3 border-l border-border">
        <ChatPanel
          notebookId={notebookId}
          isLLMWorking={isLLMWorking}
          onLLMWorkingChange={setIsLLMWorking}
        />
      </div>
    )}

    {/* Toggle Chat Button */}
    <button
      onClick={() => setShowChat(!showChat)}
      className="fixed bottom-4 right-4 bg-primary text-white rounded-full p-3 shadow-lg hover:bg-primary-hover z-50"
    >
      {showChat ? '✕' : '💬'}
    </button>

    {/* LLM Working Overlay */}
    {isLLMWorking && (
      <div className="fixed top-4 right-4 bg-blue-100 dark:bg-blue-900 border border-blue-300 dark:border-blue-700 rounded-lg px-4 py-2 shadow-lg z-50">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-blue-600 rounded-full animate-pulse" />
          <span className="text-sm font-medium">AI Assistant is working...</span>
        </div>
      </div>
    )}
  </div>
);
```

Key changes:
- Outer container: `flex h-[calc(100vh-180px)]` for full viewport height
- Notebook panel: `flex-1` (takes remaining space)
- Chat panel: `w-1/3` (proportional, not fixed 384px)
- Add `max-w-5xl mx-auto` inside notebook scroll area for content width
- Remove hardcoded `w-96` from chat panel
- Remove hardcoded `style={{ right: showChat ? '400px' : '16px' }}` from toggle button

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `npm run build`
- [x] No linting errors: `npm run typecheck`
- [x] Dev server runs without errors: `npm run dev`

#### Manual Verification:
- [x] Background is clean white/dark gray (not navy)
- [x] Layout is full-width, not constrained to 4xl
- [x] Chat panel is proportional 1/3 width
- [x] Notebook content has max-w-5xl inside scroll area
- [x] All cells render and execute correctly
- [x] WebSocket updates still work

---

## Phase 3: Cell Component Redesign

### Overview
Refactor the Cell component to use shadcn/ui components (Card, Badge, Button) with lucide-react icons, matching the design_inspo aesthetic.

### Changes Required:

#### 1. Refactor Cell Component
**File**: `frontend/src/components/Cell.tsx`

**Changes**: Replace custom classes with shadcn/ui components

Add imports at top:
```typescript
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Card } from './ui/card';
import { Play, Trash2, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
```

Replace status icons object (line 22-28):
```typescript
const statusConfig = {
  idle: { icon: null, color: 'bg-muted', label: 'Idle' },
  running: { icon: Loader2, color: 'bg-primary', label: 'Running' },
  success: { icon: CheckCircle2, color: 'bg-success', label: 'Success' },
  error: { icon: XCircle, color: 'bg-destructive', label: 'Error' },
  blocked: { icon: AlertCircle, color: 'bg-warning', label: 'Blocked' },
};
```

Replace entire return statement (line 86-181):
```typescript
const status = statusConfig[cell.status];
const StatusIcon = status.icon;

return (
  <Card className="overflow-hidden mb-4">
    {/* Cell Header */}
    <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="font-mono text-xs">
          {cell.type.toUpperCase()}
        </Badge>
        <div className="flex items-center gap-1">
          <div className={`h-2 w-2 rounded-full ${status.color}`} />
          {StatusIcon && <StatusIcon className={`h-3 w-3 ${cell.status === 'running' ? 'animate-spin' : ''}`} />}
          <span className="text-xs text-muted-foreground">{status.label}</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRunClick}
          disabled={disabled || cell.status === 'running'}
          title={`Run cell (${isMac ? '⌘' : 'Ctrl'}+Enter)`}
        >
          <Play className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDeleteCell(cell.id)}
          disabled={disabled}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>

    {/* Code Editor */}
    <div className={`h-48 border-b border-border ${disabled ? 'pointer-events-none opacity-50' : ''}`}>
      <Editor
        height="100%"
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
          automaticLayout: true,
          readOnly: disabled
        }}
      />
    </div>

    {/* Output Area */}
    {cell.status !== 'idle' && (
      <div className="bg-muted/30 p-4">
        {/* Stdout */}
        {cell.stdout && (
          <pre className="output-pre">
            {cell.stdout}
          </pre>
        )}

        {/* Rich outputs */}
        {cell.outputs && cell.outputs.map((output, idx) => (
          <div key={`${cell.id}-output-${idx}-${cell.status}`} className="output-block">
            <OutputRenderer output={output} cellId={cell.id} outputIndex={idx} />
          </div>
        ))}

        {/* Error */}
        {cell.error && (
          <pre className="output-error">
            {cell.error}
          </pre>
        )}

        {/* Blocked status */}
        {cell.status === 'blocked' && !cell.error && (
          <div className="output-warning">
            ⚠️ Upstream dependency failed.
          </div>
        )}
      </div>
    )}

    {/* Metadata Footer */}
    {(cell.reads.length > 0 || cell.writes.length > 0) && (
      <div className="border-t border-border bg-card px-4 py-2 text-xs text-muted-foreground">
        {cell.reads.length > 0 && (
          <span className="mr-4">
            Reads: <code className="font-mono">{cell.reads.join(', ')}</code>
          </span>
        )}
        {cell.writes.length > 0 && (
          <span>
            Writes: <code className="font-mono">{cell.writes.join(', ')}</code>
          </span>
        )}
      </div>
    )}
  </Card>
);
```

Key changes:
- Replace `.card-cell` with `<Card>` component
- Replace custom buttons with `<Button variant="ghost" size="sm">`
- Replace status text with inline dot + icon + label
- Add metadata footer section (only shown if reads/writes exist)
- Use lucide-react icons (Play, Trash2, Loader2, etc.)
- Remove `.editor-container` class, use direct border

#### 2. Remove Deprecated CSS Classes
**File**: `frontend/src/index.css`

**Changes**: Remove unused cell-specific classes (keep base utilities)

Remove these classes (lines will shift after Phase 2 changes):
```css
/* Remove .card-cell */
/* Remove .btn-primary-sm */
/* Remove .btn-danger-sm */
/* Keep .output-pre, .output-error, .output-warning, .output-block */
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `npm run build`
- [x] No unused CSS warnings
- [x] Dev server runs: `npm run dev`

#### Manual Verification:
- [x] Cells render with shadcn/ui Card styling
- [x] Status indicators show dot + icon + label
- [x] Run/Delete buttons use lucide-react icons
- [x] Monaco editor still works (Cmd/Ctrl+Enter shortcut)
- [x] Cell outputs render correctly (stdout, errors, tables, charts)
- [x] Metadata footer appears when reads/writes exist
- [x] Theme toggle works on cells

---

## Phase 4: Update Add Cell & DB Connection Buttons

### Overview
Replace remaining custom buttons with shadcn/ui Button components and Input component.

### Changes Required:

#### 1. Update Add Cell Buttons
**File**: `frontend/src/components/Notebook.tsx`

**Changes**: Import and use shadcn/ui components

Add imports:
```typescript
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Plus } from 'lucide-react';
```

Replace Add Cell Buttons (around line 270):
```typescript
{/* Add Cell Buttons */}
<div className="flex gap-2 mb-8">
  <Button
    onClick={() => handleAddCell('python')}
    disabled={isLLMWorking}
    variant="default"
  >
    <Plus className="h-4 w-4" />
    Python Cell
  </Button>
  <Button
    onClick={() => handleAddCell('sql')}
    disabled={isLLMWorking}
    variant="default"
  >
    <Plus className="h-4 w-4" />
    SQL Cell
  </Button>
</div>
```

#### 2. Update DB Connection Input & Button
**File**: `frontend/src/components/Notebook.tsx`

**Changes**: Replace input-field with Input component

Replace DB Connection section (around line 234):
```typescript
{/* DB Connection */}
<div className="card-section">
  <label className="label">
    PostgreSQL Connection String:
  </label>
  <div className="flex gap-2">
    <Input
      type="text"
      value={dbConnString}
      onChange={(e) => setDbConnString(e.target.value)}
      placeholder="postgresql://user:pass@host:5432/db"
      className="flex-1"
      disabled={isLLMWorking}
    />
    <Button
      onClick={handleUpdateDbConnection}
      variant="default"
      disabled={isLLMWorking}
    >
      Update
    </Button>
  </div>
</div>
```

#### 3. Update NotebookSelector Buttons
**File**: `frontend/src/components/NotebookSelector.tsx`

**Changes**: Import and use Button component

Add imports:
```typescript
import { Button } from './ui/button';
import { Plus, Edit2 } from 'lucide-react';
```

Update buttons throughout component (read file first for exact locations).

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `npm run build`
- [x] No console errors: `npm run dev`

#### Manual Verification:
- [x] Add cell buttons have icons and proper styling
- [x] DB connection input uses shadcn/ui Input
- [x] Update button styled correctly
- [x] NotebookSelector buttons match design
- [x] All buttons respond to clicks

---

## Phase 5: Chat Panel Redesign

### Overview
Update ChatPanel to use shadcn/ui components while preserving SSE streaming logic.

### Changes Required:

#### 1. Refactor ChatPanel Component
**File**: `frontend/src/components/ChatPanel.tsx`

**Changes**: Replace custom styling with shadcn/ui

Add imports:
```typescript
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ScrollArea } from '@radix-ui/react-scroll-area';
import { Send, Bot, User } from 'lucide-react';
```

Update component structure to use Card-like styling with proper message bubbles:
- Replace hardcoded colors with CSS variables
- Add Bot/User icons to messages
- Use ScrollArea for message list
- Use Input + Button for message input
- Preserve SSE streaming logic entirely

Read the current ChatPanel.tsx first to preserve the exact SSE implementation, then refactor only the JSX/styling.

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `npm run build`
- [x] No console errors: `npm run dev`

#### Manual Verification:
- [x] Chat messages display with proper styling
- [x] SSE streaming still works (messages stream in real-time)
- [x] User/Bot avatars show correctly
- [x] Input and send button styled properly
- [x] Chat scroll behavior works
- [x] LLM working state shows correctly

---

## Phase 6: Polish & Optional Enhancements

### Overview
Final polish pass and optional quality-of-life features.

### Changes Required:

#### 1. Update Theme Toggle Button
**File**: `frontend/src/components/ThemeToggle.tsx`

**Changes**: Use shadcn/ui Button

Replace with:
```typescript
import { Button } from './ui/button';
import { Moon, Sun } from 'lucide-react';

// ... component logic ...

return (
  <Button
    variant="outline"
    size="sm"
    onClick={toggleTheme}
    className="gap-2"
  >
    {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    {theme === 'dark' ? 'Light' : 'Dark'}
  </Button>
);
```

#### 2. Update LLM Working Indicator
**File**: `frontend/src/components/Notebook.tsx`

**Changes**: Use proper shadcn/ui styling

Replace LLM Working Overlay (around line 300):
```typescript
{isLLMWorking && (
  <div className="fixed top-4 right-4 bg-primary/10 border border-primary/20 rounded-lg px-4 py-2 shadow-lg z-50">
    <div className="flex items-center gap-2">
      <Loader2 className="h-3 w-3 animate-spin text-primary" />
      <span className="text-sm font-medium text-foreground">AI Assistant is working...</span>
    </div>
  </div>
)}
```

#### 3. Optional: Add Focus Ring to Cells
**File**: `frontend/src/components/Cell.tsx`

**Changes**: Add focus state tracking (OPTIONAL - only if time permits)

Add state:
```typescript
const [isFocused, setIsFocused] = useState(false);
```

Update Card className:
```typescript
<Card
  className={`overflow-hidden mb-4 transition-all ${isFocused ? 'ring-2 ring-primary' : ''}`}
  onClick={() => setIsFocused(true)}
  onBlur={() => setIsFocused(false)}
>
```

#### 4. Optional: Keyboard Shortcuts Dialog
**File**: `frontend/src/components/KeyboardShortcutsDialog.tsx` (NEW - OPTIONAL)

**Changes**: Create a Cmd/Ctrl+K dialog showing shortcuts (only if time permits)

This is a nice-to-have, not required for MVP.

### Success Criteria:

#### Automated Verification:
- [x] Final build succeeds: `npm run build`
- [x] No TypeScript errors: `npm run typecheck`
- [x] Production build works: `npm run preview`

#### Manual Verification:
- [x] Theme toggle uses new Button styling
- [x] LLM working indicator matches design
- [x] All interactions feel polished
- [x] No visual regressions
- [x] Dark/light mode toggle is smooth

---

## Testing Strategy

### Unit Tests:
- **NOT REQUIRED** - This is a visual refactor, no new business logic
- Existing functionality tests (if any) should still pass

### Integration Tests:
- **Manual testing sufficient** - Focus on E2E scenarios

### Manual Testing Steps:
1. **Basic Functionality**
   - [x] Create new notebook
   - [x] Add Python cell, write code, execute
   - [x] Add SQL cell, write query, execute
   - [x] Verify cell outputs render (text, tables, charts)
   - [x] Delete cells
   - [x] Switch notebooks

2. **WebSocket Updates**
   - [x] Open notebook in two browser tabs
   - [x] Edit cell in tab 1, verify tab 2 updates
   - [x] Run cell in tab 1, verify tab 2 shows execution status
   - [x] Create/delete cell in tab 1, verify tab 2 updates

3. **Chat Panel**
   - [x] Open chat panel
   - [x] Send message to LLM
   - [x] Verify streaming response appears
   - [x] Verify `isLLMWorking` state disables notebook during chat
   - [x] Verify tool calls execute (if applicable)
   - [x] Close chat panel

4. **Theme Toggle**
   - [x] Toggle between light/dark mode
   - [x] Verify all components update colors
   - [x] Verify Monaco editor theme updates
   - [x] Verify no flashing or layout shift

5. **Responsive Layout**
   - [x] Resize browser window
   - [x] Verify chat panel stays proportional (1/3)
   - [x] Verify notebook content respects max-w-5xl
   - [x] Verify toggle chat button appears correctly

6. **Edge Cases**
   - [x] Long cell output (verify scroll)
   - [x] Many cells (verify performance)
   - [x] WebSocket reconnection (verify state sync)
   - [x] Error handling (verify error outputs styled correctly)

## Performance Considerations

- **CSS-in-JS overhead**: Using Tailwind classes (not runtime CSS-in-JS), so performance impact is negligible
- **Component bundle size**: Adding shadcn/ui components increases bundle by ~10-15KB (acceptable)
- **No virtualization**: Cell list is not virtualized - acceptable for <100 cells, consider react-virtual if users have 100+ cells
- **Monaco editor**: Already optimized, no changes needed

## Migration Notes

- **No database migrations** - This is frontend-only
- **No API changes** - Backend remains untouched
- **No breaking changes** - Existing notebooks work identically
- **Gradual rollout**: Can deploy incrementally (each phase is independently functional)

## References

- Original research: [thoughts/shared/research/2025-12-30-frontend-design-redesign-gap-analysis.md](thoughts/shared/research/2025-12-30-frontend-design-redesign-gap-analysis.md)
- Design inspiration: `design_inspo/components/notebook-cell.tsx`
- shadcn/ui docs: https://ui.shadcn.com/
- Tailwind CSS docs: https://tailwindcss.com/
- lucide-react icons: https://lucide.dev/icons/
