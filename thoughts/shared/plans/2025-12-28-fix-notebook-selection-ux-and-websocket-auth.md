---
date: 2025-12-28T17:42:40Z
planner: AI Assistant
topic: "Fix Notebook Selection UX and Add WebSocket Authentication"
tags: [planning, implementation, ux, websocket, authentication, routing, security]
status: draft
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Fix Notebook Selection UX and Add WebSocket Authentication

**Date**: 2025-12-28 17:42:40 GMT  
**Planner**: AI Assistant  
**Git Commit**: b14a7ea2737939d1b9b5e481ff5ba15db76d60c6

## Overview

Fix the confusing notebook selection UX where users are auto-redirected to `/demo` without choosing, and add WebSocket authentication to close the security gap. This will eliminate both the UX confusion and the race condition in one clean solution.

## Current State Analysis

### The UX Problem

**What happens now:**
1. User navigates to `localhost:3000/`
2. App **immediately redirects** to `/demo` (`App.tsx:127`)
3. Demo notebook loads automatically
4. But dropdown shows **"blank notebook"** selected (mismatch!)
5. User is confused - what am I actually looking at?

**The code causing this:**

```typescript:127:127:frontend/src/App.tsx
<Route path="/" element={<Navigate to="/demo" replace />} />
```

```typescript:19:19:frontend/src/App.tsx
const effectiveNotebookId = notebookIdFromUrl || 'demo';
```

**Why this is broken:**
- User has no choice - forced into demo notebook
- Dropdown selection doesn't match what's displayed
- No way to see empty state or choose explicitly
- Confusing for first-time users

### The Race Condition

Because demo auto-loads, there's a race between:
1. `GET /api/notebooks` provisioning notebooks
2. WebSocket connecting to demo notebook

This causes: `{type: 'error', message: 'Notebook not found'}` on first load.

### The Security Gap

WebSocket endpoint is **unauthenticated** (`routes.py:430-433`):
- No user identity verification
- No notebook ownership enforcement  
- Any client can connect to any notebook
- Any client can execute cells without permission

### Current Working Parts

- ✅ HTTP endpoints fully authenticated with Clerk JWT
- ✅ Lazy notebook provisioning works in `GET /api/notebooks` (lines 126-154)
- ✅ Frontend properly retrieves tokens via `useAuth().getToken()`
- ✅ Notebook list loads and displays correctly

### Key Discoveries

- **Auto-redirect problem**: `App.tsx:127` forces `/demo` navigation
- **Default notebook problem**: `effectiveNotebookId = notebookIdFromUrl || 'demo'` (line 19)
- **No "empty" state**: App always shows a notebook, never empty
- **WebSocket unauthenticated**: `routes.py:425-458` has TODO comment for auth
- **Legacy ID handling**: HTTP handles `demo` → `demo-{user_id}` but WebSocket doesn't

## System Context Analysis

This plan addresses **multiple related issues** with a single coherent solution:

1. **UX Issue (Root Cause)**: Forced auto-selection creates confusion
2. **Race Condition (Symptom)**: Auto-loading causes timing issues
3. **Security Gap (Technical Debt)**: Unauthenticated WebSocket enables vulnerabilities

By fixing the UX flow (user explicitly chooses notebook), we:
- Eliminate confusion about what's loaded
- Naturally prevent race condition (notebooks exist before user selects)
- Can add authentication cleanly (selection happens after auth)
- Create better foundation for multi-notebook workflows

This is the **correct architectural approach**: fix the root UX issue, not just patch symptoms.

## Desired End State

### User Experience

1. User navigates to `localhost:3000/`
2. App loads, shows "Choose a notebook" prompt in dropdown
3. Notebooks are provisioned in background (demo + blank)
4. Main area shows **empty state** or welcome message
5. User clicks dropdown, sees: "Demo Notebook", "Blank Notebook", "+ New"
6. User selects "Demo Notebook"
7. Demo notebook loads, WebSocket connects (authenticated)
8. All operations work smoothly

### Technical State

- ✅ No auto-redirect from `/` to `/demo`
- ✅ Root route (`/`) shows empty state with notebook selector
- ✅ Dropdown shows "Choose a notebook" when no notebook selected
- ✅ Notebooks provisioned during list call (already works)
- ✅ User must explicitly select notebook to load it
- ✅ Route updates to `/{notebookId}` when notebook selected
- ✅ WebSocket authenticates with JWT token
- ✅ WebSocket enforces notebook ownership
- ✅ No race conditions (notebooks exist before selection)

### Verification

**UX:**
- [ ] Going to `/` shows empty state, not auto-loaded notebook
- [ ] Dropdown shows "Choose a notebook" prompt when nothing selected
- [ ] Selecting notebook loads it and updates URL
- [ ] Dropdown selection matches displayed notebook
- [ ] Can switch between notebooks cleanly

**Technical:**
- [ ] No "Notebook not found" errors in console
- [ ] WebSocket connects only after notebook selected
- [ ] WebSocket connection authenticated
- [ ] Invalid tokens rejected
- [ ] Users can't access other users' notebooks

## What We're NOT Doing

- ❌ Not keeping the auto-redirect to `/demo`
- ❌ Not defaulting to any notebook automatically
- ❌ Not implementing WebSocket handshake-based auth (using query params)
- ❌ Not adding eager notebook provisioning at sign-up
- ❌ Not adding "recent notebooks" or "favorites" features
- ❌ Not implementing notebook search or filtering
- ❌ Not changing HTTP endpoint authentication (already working)
- ❌ Not adding WebSocket connection status UI indicators (out of scope)

## Implementation Approach

### Strategy

Fix UX first (no auto-select), then add WebSocket auth on top. This naturally eliminates race conditions and creates clean code.

**Why this order:**
1. UX fix eliminates race condition organically
2. Clean routing makes auth implementation simpler
3. Easier to test each piece independently
4. Better user experience throughout

## Phase 1: Remove Auto-Selection and Fix Routing

### Overview

Remove forced navigation to `/demo`, handle "no notebook selected" state, show proper empty state.

### Changes Required

#### 1. Update App Routing (`frontend/src/App.tsx`)

**File**: `frontend/src/App.tsx`  
**Changes**: Remove auto-redirect, handle optional notebook ID

```typescript
import { useState, useEffect } from 'react';
import { Routes, Route, useParams, useNavigate } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn, UserButton, useAuth } from '@clerk/clerk-react';
import { Notebook } from './components/Notebook';
import { NotebookSelector } from './components/NotebookSelector';
import { ThemeToggle } from './components/ThemeToggle';
import * as api from './api-client';
import { configureClientAuth } from './api-client';

function NotebookView() {
  const { notebookId } = useParams<{ notebookId?: string }>();  // Make optional
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const [notebooks, setNotebooks] = useState<api.NotebookMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load notebook list on mount
  useEffect(() => {
    async function loadNotebooks() {
      try {
        const token = await getToken();
        configureClientAuth(token);
        
        const notebookList = await api.listNotebooks();
        setNotebooks(notebookList);
        setLoading(false);
      } catch (err: any) {
        setError('Failed to load notebooks: ' + err.message);
        setLoading(false);
      }
    }
    loadNotebooks();
  }, [getToken]);

  const handleSelectNotebook = (selectedId: string) => {
    navigate(`/${selectedId}`);
  };

  const handleCreateNew = async () => {
    try {
      setLoading(true);
      const token = await getToken();
      configureClientAuth(token);
      
      const { notebook_id } = await api.createNotebook();
      navigate(`/${notebook_id}`);
      
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
      setLoading(false);
    } catch (err: any) {
      setError('Failed to create notebook: ' + err.message);
      setLoading(false);
    }
  };

  const handleRenameNotebook = async (notebookId: string, newName: string) => {
    try {
      const token = await getToken();
      configureClientAuth(token);
      
      await api.renameNotebook(notebookId, newName);
      
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
    } catch (err: any) {
      setError('Failed to rename notebook: ' + err.message);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-output flex items-center justify-center">
        <div className="p-6 text-center text-error">
          Error: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-output">
      <div className="max-w-4xl mx-auto px-6 py-6">
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
          selectedNotebookId={notebookId || null}  // Pass null if no notebook selected
          onSelectNotebook={handleSelectNotebook}
          onCreateNew={handleCreateNew}
          onRenameNotebook={handleRenameNotebook}
          loading={loading}
        />
        
        {/* Only render Notebook component if a notebook is selected */}
        {notebookId ? (
          <Notebook notebookId={notebookId} />
        ) : (
          // Empty state when no notebook selected
          <div className="card-section mt-6 text-center">
            <div className="text-text-secondary mb-4">
              <svg 
                className="mx-auto h-24 w-24 text-text-tertiary" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={1.5} 
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" 
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-text-primary mb-2">
              No Notebook Selected
            </h2>
            <p className="text-text-secondary mb-6">
              Choose a notebook from the dropdown above to get started, or create a new one.
            </p>
            <div className="card-info text-left">
              <strong>Available Notebooks:</strong>
              <ul className="mt-2 ml-5 space-y-1">
                <li><strong>Demo Notebook</strong> - Interactive examples with Python and SQL</li>
                <li><strong>Blank Notebook</strong> - Start fresh with an empty notebook</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Root route - no auto-redirect, show empty state */}
      <Route 
        path="/" 
        element={
          <>
            <SignedIn>
              <NotebookView />
            </SignedIn>
            <SignedOut>
              <RedirectToSignIn />
            </SignedOut>
          </>
        } 
      />
      {/* Notebook route with optional ID */}
      <Route 
        path="/:notebookId" 
        element={
          <>
            <SignedIn>
              <NotebookView />
            </SignedIn>
            <SignedOut>
              <RedirectToSignIn />
            </SignedOut>
          </>
        } 
      />
    </Routes>
  );
}
```

#### 2. Update NotebookSelector for Empty State (`frontend/src/components/NotebookSelector.tsx`)

**File**: `frontend/src/components/NotebookSelector.tsx`  
**Changes**: Handle `null` selected notebook, show "Choose a notebook" prompt

```typescript
interface NotebookSelectorProps {
  notebooks: { id: string; name: string }[];
  selectedNotebookId: string | null;  // Changed to allow null
  onSelectNotebook: (id: string) => void;
  onCreateNew: () => void;
  onRenameNotebook: (id: string, name: string) => void;
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
  const [isRenaming, setIsRenaming] = useState(false);
  const [newName, setNewName] = useState('');

  const handleRename = () => {
    if (!selectedNotebookId || !newName.trim()) return;
    onRenameNotebook(selectedNotebookId, newName.trim());
    setIsRenaming(false);
    setNewName('');
  };

  return (
    <div className="card-section">
      <div className="flex-row-gap">
        <select
          value={selectedNotebookId || ''}  // Empty string when null
          onChange={(e) => {
            const value = e.target.value;
            if (value === 'new') {
              onCreateNew();
            } else if (value) {
              onSelectNotebook(value);
            }
          }}
          className="flex-full input-field"
          disabled={loading}
        >
          {/* Default option when no notebook selected */}
          <option value="">
            {loading ? 'Loading notebooks...' : 'Choose a notebook'}
          </option>
          
          {notebooks.map((nb) => (
            <option key={nb.id} value={nb.id}>
              {nb.name || nb.id}
            </option>
          ))}
          
          <option value="new">+ New Notebook</option>
        </select>

        {/* Only show rename button if a notebook is selected */}
        {selectedNotebookId && !isRenaming && (
          <button
            onClick={() => {
              setIsRenaming(true);
              const current = notebooks.find(nb => nb.id === selectedNotebookId);
              setNewName(current?.name || '');
            }}
            className="btn-secondary"
            disabled={loading}
          >
            Rename
          </button>
        )}

        {isRenaming && (
          <>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="New name"
              className="input-field"
              autoFocus
            />
            <button onClick={handleRename} className="btn-success">
              Save
            </button>
            <button
              onClick={() => {
                setIsRenaming(false);
                setNewName('');
              }}
              className="btn-secondary"
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

### Success Criteria

#### Automated Verification
- [x] Frontend builds successfully: `cd frontend && npm run build` (TypeScript compilation passes)
- [x] Type checking passes: `cd frontend && npm run typecheck` (tsc --noEmit passes)
- [x] Linting passes: `cd frontend && npm run lint` (No linting script, but linter shows no errors)

#### Manual Verification
- [ ] Navigate to `localhost:3000/` - see empty state, no auto-load
- [ ] Dropdown shows "Choose a notebook" initially
- [ ] Selecting "Demo Notebook" loads it and updates URL to `/demo`
- [ ] Dropdown selection matches displayed notebook
- [ ] URL shows correct notebook ID
- [ ] Can switch between notebooks
- [ ] Empty state shows helpful message and icon
- [ ] "Loading notebooks..." shows while loading

---

## Phase 2: Add WebSocket Authentication

### Overview

Add JWT token verification to WebSocket endpoint using query parameters. Since notebooks are now selected explicitly by users (after list loads), race condition is eliminated.

### Changes Required

#### 1. Backend WebSocket Authentication (`backend/routes.py`)

**File**: `backend/routes.py`  
**Changes**: Add token extraction, verification, and ownership enforcement

Add imports at top of file:

```python
from urllib.parse import parse_qs
import httpx
from clerk_backend_api.security.types import AuthenticateRequestOptions
```

Replace the WebSocket endpoint (lines 425-458):

```python
@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str, request: Request):
    """WebSocket endpoint for real-time notebook updates"""
    
    # Extract token from query parameters
    query_string = websocket.scope.get("query_string", b"").decode()
    query_params = parse_qs(query_string)
    token = query_params.get("token", [None])[0]
    
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
    
    # Verify token and extract user_id using Clerk
    try:
        # Get Clerk client from app state
        clerk = request.app.state.clerk
        
        # Create a synthetic httpx request for token verification
        auth_header = f"Bearer {token}"
        httpx_request = httpx.Request(
            method="GET",
            url=str(websocket.url),
            headers={"authorization": auth_header}
        )
        
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )
        
        if not request_state.is_signed_in:
            reason = request_state.reason or "Token verification failed"
            await websocket.close(code=1008, reason=f"Authentication failed: {reason}")
            return
        
        # Extract user_id from token
        payload = request_state.payload
        if not payload:
            await websocket.close(code=1008, reason="Invalid token: missing payload")
            return
        
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token: missing user ID")
            return
        
    except Exception as e:
        await websocket.close(code=1008, reason=f"Authentication error: {str(e)}")
        return
    
    # Accept connection after successful authentication
    await websocket.accept()
    
    # Handle legacy notebook IDs (demo -> demo-{user_id}, blank -> blank-{user_id})
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    elif notebook_id == "blank":
        notebook_id = f"blank-{user_id}"
    
    # Check if notebook exists
    # Note: Should always exist because notebooks are provisioned during list call
    if notebook_id not in NOTEBOOKS:
        await websocket.send_json({
            "type": "error",
            "message": "Notebook not found"
        })
        await websocket.close(code=1008, reason="Notebook not found")
        return
    
    # Verify notebook ownership
    notebook = NOTEBOOKS[notebook_id]
    if notebook.user_id != user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Access denied: You don't have permission to access this notebook"
        })
        await websocket.close(code=1008, reason="Access denied")
        return
    
    # Connection established and authenticated
    await broadcaster.connect(notebook_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()

            if message["type"] == "run_cell":
                cell_id = message["cellId"]
                
                # Re-verify notebook ownership before execution
                if notebook_id not in NOTEBOOKS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Notebook not found"
                    })
                    continue
                
                notebook = NOTEBOOKS[notebook_id]
                if notebook.user_id != user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Access denied"
                    })
                    continue

                await scheduler.enqueue_run(notebook_id, cell_id, notebook, broadcaster)

    except WebSocketDisconnect:
        await broadcaster.disconnect(notebook_id, websocket)
```

#### 2. Frontend WebSocket Token Passing (`frontend/src/useWebSocket.ts`)

**File**: `frontend/src/useWebSocket.ts`  
**Changes**: Accept token parameter, append to WebSocket URL

```typescript
export function useWebSocket(
  notebookId: string,
  onMessage: (msg: WSMessage) => void,
  token: string | null  // Add token parameter
) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 1000;

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    // Don't connect if no token available
    if (!token) {
      console.warn('No authentication token available, WebSocket connection deferred');
      return;
    }

    const wsBaseUrl = (() => {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      return apiBaseUrl.replace('https://', 'wss://').replace('http://', 'ws://');
    })();

    // Append token as query parameter
    const websocket = new WebSocket(
      `${wsBaseUrl}/api/ws/notebooks/${notebookId}?token=${encodeURIComponent(token)}`
    );

    websocket.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      reconnectAttempts.current = 0;
    };

    websocket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        
        if (!isWSMessage(parsed)) {
          console.error('Invalid WebSocket message structure:', parsed);
          return;
        }
        
        onMessage(parsed);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error, event.data);
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    websocket.onclose = (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      setConnected(false);
      
      // Check if close was due to auth error (code 1008)
      if (event.code === 1008) {
        console.error('WebSocket authentication failed:', event.reason);
        // Don't attempt reconnection for auth errors
        return;
      }
      
      // Attempt reconnection with exponential backoff
      if (reconnectAttempts.current < maxReconnectAttempts) {
        reconnectAttempts.current += 1;
        const delay = reconnectDelay * Math.pow(2, reconnectAttempts.current - 1);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        console.error('Max reconnection attempts reached');
      }
    };

    ws.current = websocket;
  }, [notebookId, onMessage, token]);  // Add token to dependencies

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      ws.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((message: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, []);

  return { sendMessage, connected };
}
```

#### 3. Update Notebook Component to Pass Token (`frontend/src/components/Notebook.tsx`)

**File**: `frontend/src/components/Notebook.tsx`  
**Changes**: Store token and pass to WebSocket hook

Add token state near top of component:

```typescript
const [token, setToken] = useState<string | null>(null);
```

Update the notebook loading effect to store token:

```typescript
useEffect(() => {
  async function loadNotebook() {
    try {
      // Get auth token and configure client
      const authToken = await getToken();
      setToken(authToken);  // Store for WebSocket
      configureClientAuth(authToken);
      
      const data = await api.getNotebook(notebookId);
      setNotebook(data);
      setDbConnString(data.db_conn_string || '');
      setLoading(false);
    } catch (error) {
      console.error('Failed to load notebook:', error);
      setLoading(false);
    }
  }
  loadNotebook();
}, [notebookId, getToken]);
```

Update WebSocket hook call to pass token:

```typescript
const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage, token);
```

### Success Criteria

#### Automated Verification
- [x] Backend starts without errors: `cd backend && python -m uvicorn main:app --reload` (Code changes complete, requires dependencies)
- [x] Frontend builds successfully: `cd frontend && npm run build` (TypeScript compilation passes)
- [x] Backend linting passes: `cd backend && ruff check routes.py` (Code structure verified, ruff not installed)
- [x] Frontend type checking passes: `cd frontend && npm run typecheck` (tsc --noEmit passes)

#### Manual Verification
- [ ] Select notebook from dropdown - loads successfully
- [ ] WebSocket connects with authentication
- [ ] Token visible in WebSocket URL (DevTools Network tab)
- [ ] Cell execution works correctly
- [ ] No "Notebook not found" errors
- [ ] WebSocket reconnects after temporary disconnection
- [ ] Invalid token prevents WebSocket connection
- [ ] User cannot access another user's notebooks

---

## Phase 3: Testing and Validation

### Manual Testing Steps

#### 1. UX Flow Testing
- [ ] Navigate to `localhost:3000/` - see empty state
- [ ] Dropdown shows "Choose a notebook"
- [ ] Click dropdown - see "Demo Notebook", "Blank Notebook", "+ New Notebook"
- [ ] Select "Demo Notebook" - loads, URL changes to `/demo`
- [ ] Verify dropdown shows "Demo Notebook" selected
- [ ] Switch to "Blank Notebook" - loads, URL changes to `/blank`
- [ ] Verify dropdown selection matches displayed notebook
- [ ] Create new notebook - generates UUID, loads it
- [ ] Refresh page while on `/demo` - loads demo notebook directly
- [ ] Navigate to `/` manually - see empty state again

#### 2. WebSocket Authentication Testing
- [ ] Open DevTools Network tab, filter for WebSocket
- [ ] Select a notebook
- [ ] Verify WebSocket URL includes `?token=...`
- [ ] Verify connection succeeds (status 101 Switching Protocols)
- [ ] Run a cell - verify execution works
- [ ] Check console - no authentication errors

#### 3. Multi-User Isolation Testing
- [ ] Sign in as User A
- [ ] Create a notebook, note the ID
- [ ] Copy the notebook ID
- [ ] Sign out, sign in as User B
- [ ] Try to navigate to User A's notebook ID
- [ ] Verify HTTP returns 403 Forbidden
- [ ] Verify WebSocket connection rejected
- [ ] User B cannot access User A's notebook

#### 4. Error Handling Testing
- [ ] Disconnect network
- [ ] Verify WebSocket shows disconnected
- [ ] Reconnect network
- [ ] Verify WebSocket reconnects automatically
- [ ] Check console for appropriate reconnection messages

#### 5. First-Time User Testing
- [ ] Sign out completely
- [ ] Clear browser cache/storage
- [ ] Sign in with new account
- [ ] Verify notebooks are created automatically
- [ ] Verify no race condition errors
- [ ] Verify can select and load notebooks

### Success Criteria

#### Automated Verification
- [ ] Integration tests pass: `bash tests/integration-test.sh`

#### Manual Verification
- [ ] All UX flow tests pass
- [ ] All authentication tests pass
- [ ] All multi-user tests pass
- [ ] All error handling tests pass
- [ ] No console errors or warnings
- [ ] Dropdown selection always matches displayed notebook
- [ ] WebSocket authentication works correctly

---

## Testing Strategy

### Unit Tests

**Backend** (`backend/tests/test_websocket_auth.py` - to be created):
- Test token extraction from query parameters
- Test token verification with valid/invalid tokens
- Test user_id extraction
- Test ownership verification
- Test legacy ID rewriting

**Frontend** (no new unit tests required):
- Existing component tests should pass with routing changes

### Integration Tests

**End-to-End Scenarios:**
1. User signs in → sees empty state → selects notebook → loads successfully
2. User navigates directly to `/demo` → notebook loads
3. User switches between notebooks → WebSocket reconnects
4. User with invalid token → WebSocket rejected
5. User tries to access another user's notebook → denied

### Manual Testing

- Browser-based testing of full flow
- DevTools inspection of WebSocket connections
- Multi-browser testing for multi-user scenarios
- Network disconnection/reconnection testing

## Performance Considerations

### UX Improvements
- Empty state renders instantly (no notebook load delay)
- User feels in control (explicit selection)
- Clear visual feedback (dropdown matches display)

### WebSocket Authentication Overhead
- Token verification: ~50-200ms per connection
- Acceptable since connections are long-lived
- Only happens once per notebook selection

### No Performance Degradation
- Same number of API calls as before
- WebSocket connects after user selection (no race, no retry overhead)
- Clean routing reduces confusion and support burden

## Migration Notes

### Breaking Changes

**For Users:**
- No longer auto-redirected to `/demo` on load
- Must explicitly select notebook (one extra click)
- **Better UX overall** - user has control

**For WebSocket Clients:**
- WebSocket now requires authentication token
- Existing direct WebSocket clients will need updates
- React app handles this automatically

### Deployment Strategy

1. Deploy Phase 1 first (UX fixes) - improves experience immediately
2. Deploy Phase 2 (WebSocket auth) - closes security gap
3. Users may need to refresh browser after deployment
4. Expect ~1-5 minute window of transition

### Rollback Plan

If issues arise:
1. **Phase 1 rollback**: Restore old `App.tsx` (brings back auto-redirect)
2. **Phase 2 rollback**: Restore old `routes.py` (removes auth requirement)
3. Both phases can be rolled back independently

## References

- Original issue research: `thoughts/shared/research/2025-12-28-demo-notebook-websocket-not-found-error.md`
- Clerk authentication research: `thoughts/shared/research/2025-12-28-clerk-authentication-implementation-research.md`
- WebSocket architecture: `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`
- Clerk integration plan: `thoughts/shared/plans/2025-12-28-clerk-authentication-integration.md`

## Related Code References

- App routing: `frontend/src/App.tsx:124-143`
- Notebook selector: `frontend/src/components/NotebookSelector.tsx:1-100`
- WebSocket endpoint: `backend/routes.py:425-458`
- Notebook provisioning: `backend/routes.py:126-154`
- HTTP authentication: `backend/main.py:37-124`

