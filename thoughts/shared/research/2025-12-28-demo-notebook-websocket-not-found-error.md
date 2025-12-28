---
date: 2025-12-28T17:35:27Z
researcher: AI Assistant
topic: "Demo Notebook WebSocket 'Not Found' Error - Race Condition Analysis"
tags: [research, codebase, websocket, authentication, notebook-loading, race-condition]
status: complete
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Research: Demo Notebook WebSocket 'Not Found' Error - Race Condition Analysis

**Date**: 2025-12-28 17:35:27 GMT  
**Researcher**: AI Assistant  
**Git Commit**: b14a7ea2737939d1b9b5e481ff5ba15db76d60c6

## Research Question

User reported receiving a WebSocket error when accessing the demo notebook:
```
useWebSocket.ts:97 Invalid WebSocket message structure: 
{type: 'error', message: 'Notebook not found'}
```

The error occurs on first access to the demo notebook, but works correctly when switching between notebooks in the dropdown. The demo notebook should be automatically duplicated for each user accessing it.

## Summary

**Root Cause**: Race condition between WebSocket connection establishment and backend notebook provisioning.

The issue occurs because:
1. **WebSocket connects immediately** when the `Notebook` component mounts (`Notebook.tsx:115`)
2. **Notebook provisioning happens lazily** only when `GET /api/notebooks` is called (`routes.py:126-154`)
3. **WebSocket is unauthenticated** and cannot trigger user-specific notebook creation
4. **In-memory NOTEBOOKS dictionary** is only populated from disk at startup, not dynamically

When a user first accesses `/demo`, the frontend establishes a WebSocket connection to a notebook that doesn't exist yet in the in-memory `NOTEBOOKS` dictionary. The notebook is only created when the HTTP endpoint is called, which happens after the WebSocket connection.

## Detailed Findings

### Architecture: Notebook Loading and Provisioning

#### Backend Startup (`backend/main.py:130-145`)
- At application startup, all saved notebooks are loaded from disk into the in-memory `NOTEBOOKS` dictionary
- Only notebooks that exist as JSON files in `backend/notebooks/` are loaded
- User-specific demo notebooks (`demo-{user_id}`) are **not** created at startup

#### Lazy Notebook Provisioning (`backend/routes.py:126-154`)
- When a user calls `GET /api/notebooks`, the endpoint checks if they have a `blank-{user_id}` and `demo-{user_id}` notebook
- If missing, it creates them on-demand:
  ```python
  demo_id = f"demo-{user_id}"
  user_has_demo = any(nb.id == demo_id and nb.user_id == user_id for nb in NOTEBOOKS.values())
  if not user_has_demo:
      demo_notebook = create_demo_notebook(user_id)
      demo_notebook.id = demo_id
      NOTEBOOKS[demo_id] = demo_notebook  # Added to in-memory dict
      save_notebook(demo_notebook)  # Saved to disk
  ```
- This provisioning only happens during the HTTP `GET /api/notebooks` call, not during WebSocket connection

#### Legacy ID Handling (`backend/routes.py:172-177`)
- The `GET /api/notebooks/{notebook_id}` endpoint handles legacy IDs by rewriting them:
  ```python
  if notebook_id == "demo":
      notebook_id = f"demo-{user_id}"
  ```
- This ensures backwards compatibility with the old `demo` ID

### Frontend Loading Flow

#### Component Mounting Sequence (`frontend/src/components/Notebook.tsx`)

1. **Initial Notebook Load** (lines 19-36):
   ```typescript
   useEffect(() => {
     async function loadNotebook() {
       const token = await getToken();
       configureClientAuth(token);
       const data = await api.getNotebook(notebookId);  // HTTP GET
       setNotebook(data);
       setLoading(false);
     }
     loadNotebook();
   }, [notebookId, getToken]);
   ```

2. **WebSocket Connection** (line 115):
   ```typescript
   const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage);
   ```
   - This hook establishes the WebSocket connection **immediately** when the component mounts
   - The connection happens **in parallel** with the HTTP notebook load

3. **WebSocket Reconnection Handler** (lines 118-135):
   ```typescript
   useEffect(() => {
     async function refetchNotebook() {
       if (connected && notebook) {
         const nb = await api.getNotebook(notebookId);
         setNotebook(nb);
       }
     }
     refetchNotebook();
   }, [connected, notebookId, getToken]);
   ```

#### App-Level Notebook List Loading (`frontend/src/App.tsx:22-37`)

```typescript
useEffect(() => {
  async function loadNotebooks() {
    const token = await getToken();
    configureClientAuth(token);
    const notebookList = await api.listNotebooks();  // Triggers provisioning!
    setNotebooks(notebookList);
    setLoading(false);
  }
  loadNotebooks();
}, [getToken]);
```

This is where the backend provisions the demo notebook, but it happens **independently** of the `Notebook` component mounting.

### WebSocket Authentication Gap

#### WebSocket Endpoint is Unauthenticated (`backend/routes.py:425-458`)

```python
@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    await websocket.accept()
    
    # TODO: Authenticate WebSocket connection
    # For now, WebSocket is unauthenticated (security risk)
    # Future: Extract token from query params or initial message
    
    await broadcaster.connect(notebook_id, websocket)
    
    try:
        while True:
            message = await websocket.receive_json()
            if message["type"] == "run_cell":
                cell_id = message["cellId"]
                if notebook_id not in NOTEBOOKS:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Notebook not found"  # THIS IS THE ERROR!
                    })
                    continue
```

**Key Issues:**
- No user authentication or context in WebSocket endpoint
- Cannot determine which user is connecting
- Cannot trigger user-specific notebook provisioning
- Can only check if notebook exists in `NOTEBOOKS` dictionary

#### Frontend WebSocket Connection (`frontend/src/useWebSocket.ts:70-83`)

```typescript
const connect = useCallback(() => {
  const wsBaseUrl = (() => {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    return apiBaseUrl.replace('https://', 'wss://').replace('http://', 'ws://');
  })();

  const websocket = new WebSocket(
    `${wsBaseUrl}/api/ws/notebooks/${notebookId}`
  );
  // No authentication token passed!
```

**No token is included** in the WebSocket connection URL or headers.

### Race Condition Timeline

#### Scenario 1: First-Time User Access to `/demo`

1. **User navigates to `/demo`** → React Router loads `NotebookView` component
2. **`App.tsx` mounts** → Triggers `loadNotebooks()` (HTTP call to `GET /api/notebooks`)
3. **`Notebook` component mounts** → Two parallel actions:
   - HTTP: `api.getNotebook("demo")` starts loading
   - WebSocket: `useWebSocket("demo", ...)` **immediately connects**
4. **WebSocket connects first** (faster than HTTP):
   - Connects to `/ws/notebooks/demo`
   - Backend checks: `if "demo" not in NOTEBOOKS` → **TRUE** (not provisioned yet!)
   - Sends error: `{type: 'error', message: 'Notebook not found'}`
5. **HTTP `GET /api/notebooks` completes**:
   - Backend creates `demo-{user_id}` notebook
   - Adds to `NOTEBOOKS` dictionary
   - Saves to disk
6. **HTTP `GET /api/notebooks/demo` completes**:
   - Backend rewrites `demo` → `demo-{user_id}`
   - Returns notebook data
   - Frontend renders successfully

**Result**: WebSocket error logged, but notebook loads and works fine.

#### Scenario 2: Switching Between Notebooks

1. **User switches from `blank-{user_id}` to `demo-{user_id}`**
2. **`Notebook` component re-mounts** with new `notebookId`
3. **WebSocket connects** to `/ws/notebooks/demo-{user_id}`
4. **Backend checks**: `if "demo-{user_id}" not in NOTEBOOKS` → **FALSE** (already exists!)
5. **No error** → WebSocket works correctly

**Result**: No error because notebook already exists in memory.

## Code References

### Backend Files

- `backend/routes.py:425-458` - WebSocket endpoint (unauthenticated, notebook lookup)
- `backend/routes.py:126-154` - `GET /api/notebooks` (lazy provisioning of demo/blank notebooks)
- `backend/routes.py:172-177` - Legacy ID rewriting (`demo` → `demo-{user_id}`)
- `backend/main.py:130-145` - Startup event (loads notebooks from disk)
- `backend/storage.py:36-65` - `load_notebook()` function
- `backend/storage.py:67-70` - `list_notebooks()` function
- `backend/websocket.py:11-41` - WebSocket broadcaster implementation

### Frontend Files

- `frontend/src/components/Notebook.tsx:19-36` - Initial notebook HTTP load
- `frontend/src/components/Notebook.tsx:115` - WebSocket connection establishment
- `frontend/src/components/Notebook.tsx:118-135` - WebSocket reconnection handler
- `frontend/src/App.tsx:22-37` - Notebook list loading (triggers provisioning)
- `frontend/src/useWebSocket.ts:70-83` - WebSocket connection logic
- `frontend/src/useWebSocket.ts:91-104` - WebSocket message handling and validation

## Architecture Insights

### In-Memory vs. Persistent Storage

The application uses a **hybrid storage model**:
- **In-memory**: `NOTEBOOKS` dictionary (`routes.py:15`) for fast access during runtime
- **Persistent**: JSON files in `backend/notebooks/` directory for durability

**Critical Gap**: Notebooks are only loaded into memory at:
1. Application startup (from disk)
2. Lazy provisioning during HTTP calls

WebSocket connections cannot trigger notebook loading because they lack user context.

### Authentication Architecture

**HTTP Endpoints**: Fully authenticated
- Use Clerk JWT tokens via `Authorization: Bearer <token>` header
- Extract `user_id` from token's `sub` claim
- Enforce notebook ownership on all operations

**WebSocket Endpoint**: Unauthenticated (documented security risk)
- No token validation
- No user context
- Cannot enforce ownership
- Cannot trigger user-specific provisioning

From `backend/routes.py:430-433`:
```python
# TODO: Authenticate WebSocket connection
# For now, WebSocket is unauthenticated (security risk)
# Future: Extract token from query params or initial message
```

### Notebook ID Convention

**User-Specific IDs**: `{type}-{user_id}`
- `demo-user_37U0GVSi47Y4pucE7h9iZVesr4b`
- `blank-user_37U0GVSi47Y4pucE7h9iZVesr4b`

**Legacy IDs**: `demo`, `blank`
- Rewritten to user-specific IDs by HTTP endpoints
- Not handled by WebSocket endpoint

## Historical Context (from thoughts/)

### Clerk Authentication Implementation

From `thoughts/shared/plans/2025-12-28-clerk-authentication-integration-implementation-summary.md`:

- Clerk authentication was recently integrated (2025-12-28)
- All HTTP endpoints now require authentication and extract `user_id`
- **WebSocket authentication is explicitly listed as a TODO**:
  > "Phase 5: WebSocket Authentication (TODO) - Not yet implemented due to complexity"

### WebSocket-Only Architecture

From `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`:

The application follows a **WebSocket-first architecture** where:
- HTTP is used for initial load and mutations
- WebSocket is the single source of truth for real-time updates
- State changes are broadcast to all connected clients

This architecture assumes WebSocket connections are established to **existing** notebooks.

### Notebook Provisioning

From `thoughts/shared/plans/2025-12-27-loading-saving-named-notebooks-dropdown.md`:

- Notebooks are provisioned lazily when users list their notebooks
- Each user gets their own copy of demo and blank notebooks
- Provisioning happens server-side during `GET /api/notebooks`

## Related Research

- `thoughts/shared/research/2025-12-28-clerk-authentication-implementation-research.md` - Clerk authentication patterns
- `thoughts/shared/research/2025-12-27-websocket-only-architecture.md` - WebSocket-first design rationale
- `thoughts/shared/plans/2025-12-28-clerk-authentication-integration.md` - Original authentication plan

## Open Questions

1. **Should WebSocket authentication be prioritized?**
   - Would enable user-specific notebook provisioning on WebSocket connect
   - Would close security gap

2. **Should notebooks be eagerly provisioned at user sign-in?**
   - Would eliminate race condition
   - Would require session management or database

3. **Should WebSocket connection be delayed until after HTTP load?**
   - Would ensure notebook exists before WebSocket connects
   - Would add latency to initial page load

4. **Should the error be suppressed if notebook is loading?**
   - Would improve UX (no console error)
   - Would hide potential real errors

## Recommendations

### Short-Term Fix (Low Effort)

**Delay WebSocket connection until notebook is loaded:**

```typescript
// frontend/src/components/Notebook.tsx
const [notebook, setNotebook] = useState<api.Notebook | null>(null);

// Only connect WebSocket after notebook is loaded
const { sendMessage, connected } = useWebSocket(
  notebook ? notebookId : null,  // Pass null to prevent connection
  handleWSMessage
);
```

**Pros**: Simple, eliminates race condition  
**Cons**: Slightly delays WebSocket connection, doesn't fix authentication gap

### Medium-Term Fix (Medium Effort)

**Implement WebSocket authentication with token in query params:**

```typescript
// Frontend
const websocket = new WebSocket(
  `${wsBaseUrl}/api/ws/notebooks/${notebookId}?token=${token}`
);
```

```python
# Backend
@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str, token: str = None):
    user_id = await verify_token(token)  # Verify JWT
    
    # Provision notebook if missing
    if notebook_id == "demo":
        notebook_id = f"demo-{user_id}"
    
    if notebook_id not in NOTEBOOKS:
        # Check if it's a user-specific notebook that needs provisioning
        if notebook_id.startswith("demo-") or notebook_id.startswith("blank-"):
            await provision_notebook(notebook_id, user_id)
```

**Pros**: Fixes authentication gap, enables dynamic provisioning  
**Cons**: Requires backend changes, token in query params (less secure than headers)

### Long-Term Fix (High Effort)

**Implement proper WebSocket authentication with initial handshake:**

1. Accept WebSocket connection without auth
2. Require first message to be authentication message with token
3. Verify token and establish user context
4. Provision notebooks as needed
5. Begin normal message handling

**Pros**: Most secure, follows WebSocket best practices  
**Cons**: Significant refactoring required

## Conclusion

The "Notebook not found" WebSocket error is caused by a **race condition** between WebSocket connection establishment and lazy notebook provisioning. The WebSocket connects before the notebook is created in the in-memory `NOTEBOOKS` dictionary, resulting in a "not found" error.

The issue resolves itself once the HTTP endpoints provision the notebook, which is why switching between notebooks works correctly (notebooks already exist in memory).

The root cause is the **lack of WebSocket authentication**, which prevents the WebSocket endpoint from knowing which user is connecting and provisioning user-specific notebooks on-demand.

**Immediate Action**: Implement the short-term fix to delay WebSocket connection until after notebook load.

**Future Work**: Prioritize WebSocket authentication implementation to close the security gap and enable proper user-specific notebook provisioning.

