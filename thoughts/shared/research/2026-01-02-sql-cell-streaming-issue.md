---
date: 2026-01-02T10:12:40Z
researcher: AI Assistant
topic: "SQL cell type doesn't stream results to frontend on initial execution"
tags: [research, codebase, sql, websocket, streaming, race-condition]
status: complete
last_updated: 2026-01-02
last_updated_by: AI Assistant
---

# Research: SQL Cell Type Doesn't Stream Results to Frontend

**Date**: 2026-01-02T10:12:40 GMT
**Researcher**: AI Assistant

## Research Question

Why doesn't the SQL cell type stream results to the frontend on initial execution, but works correctly after page refresh?

## Summary

The issue is a **race condition between WebSocket connection establishment and cell execution**. When a SQL cell is executed immediately after page load:

1. **WebSocket connection is still authenticating** when the cell starts executing
2. **Cell output is broadcast before the WebSocket is registered** with the broadcaster
3. **Frontend never receives the `cell_output` messages** because the connection wasn't registered yet
4. **On page refresh, outputs are loaded from storage** via HTTP GET, which is why they appear

**Root Cause**: The WebSocket connection goes through an authentication flow (accept → authenticate → register) that takes time. If a cell executes during this window, the output broadcasts are sent to an empty connection set, and the frontend misses them.

**Key Finding**: Outputs ARE persisted to storage (as of commit 5fa2492), so they appear on refresh. The streaming issue is purely a timing problem with WebSocket registration.

## Detailed Findings

### System Architecture: WebSocket Connection Flow

The notebook uses a **dual-channel architecture** for state synchronization:
- **HTTP REST API**: Initial state load and cell operations (create, update, delete)
- **WebSocket**: Real-time execution updates (status, stdout, outputs, errors)

#### WebSocket Authentication Sequence

**Backend** (`backend/routes.py:498-598`):
1. Line 511: `await websocket.accept()` - Connection accepted immediately
2. Lines 517-520: Wait for authentication message (10 second timeout)
3. Lines 554-564: Verify JWT token with Clerk
4. Line 567: Send `{"type": "authenticated"}` confirmation
5. Lines 578-595: Verify notebook exists and user has access
6. **Line 598: `await broadcaster.connect(notebook_id, websocket)`** - Connection registered for broadcasts

**Frontend** (`frontend/src/useNotebookWebSocket.ts:56-136`):
1. Lines 61-67: `onOpen` - Send authentication message immediately
2. Lines 75-79: Wait for `{"type": "authenticated"}` response
3. Line 78: Set `isAuthenticated.current = true`
4. Line 79: Set connection status to `'connected'`

**Critical Timing Window**: From WebSocket open to registration takes multiple round-trips:
- Frontend → Backend: Authentication message
- Backend validates token (may involve external JWKS fetch)
- Backend → Frontend: Authenticated confirmation
- Backend registers connection with broadcaster

During this window (typically 100-500ms), any cell executions will broadcast to an empty connection set.

### Cell Execution and Output Broadcasting

#### SQL Cell Execution Flow

**Execution** (`backend/executor.py:162-235`):
1. Lines 179-180: Substitute SQL variables using Python globals
2. Lines 183-185: Connect to PostgreSQL database
3. Line 185: `result = await conn.fetch(substituted_sql)` - Execute query
4. Lines 189-206: Convert result to table format:
   ```python
   table_data = {
       "type": "table",
       "columns": columns,
       "rows": rows,
       "truncated": truncated_msg
   }
   outputs.append(Output(mime_type=MimeType.JSON, data=table_data))
   ```
5. Lines 211-215: Return `ExecutionResult` with outputs

**Broadcasting** (`backend/scheduler.py:160-166`):
```python
# Broadcast outputs
for output in result.outputs:
    await broadcaster.broadcast_cell_output(notebook_id, cell.id, {
        "mime_type": output.mime_type,
        "data": output.data,
        "metadata": output.metadata
    })
```

**WebSocket Broadcast** (`backend/websocket.py:70-82`):
```python
async def broadcast_cell_output(self, notebook_id: str, cell_id: str, output: dict):
    message = {
        "type": "cell_output",
        "cellId": cell_id,
        "output": output
    }
    await self.broadcast(notebook_id, message)
```

**Key Issue**: `broadcast()` (lines 26-40) only sends to connections in `self.connections[notebook_id]`. If the WebSocket hasn't been registered yet, this set is empty, and the message is sent to nobody.

### Frontend Output Handling

#### Initial State Load

**NotebookApp** (`frontend/src/components/NotebookApp.tsx:96-110`):
```typescript
useEffect(() => {
  if (!notebookId) return;
  
  async function loadNotebook(id: string) {
    try {
      const notebook = await api.getNotebook(id);
      setCells(notebook.cells || []);  // Includes outputs from storage
      setDbConnection(notebook.db_conn_string || "");
    } catch (err) {
      console.error("Failed to load notebook:", err);
    }
  }
  loadNotebook(notebookId);
}, [notebookId]);
```

This loads the full notebook state including **persisted outputs** from storage.

#### WebSocket Message Handling

**Output Messages** (`frontend/src/components/NotebookApp.tsx:160-166`):
```typescript
case "cell_output":
  setCells((prev) =>
    prev.map((c) =>
      c.id === msg.cellId ? { ...c, outputs: [...(c.outputs || []), msg.output] } : c
    )
  );
  break;
```

**Status Messages** (`frontend/src/components/NotebookApp.tsx:139-150`):
```typescript
case "cell_status":
  setCells((prev) =>
    prev.map((c) => {
      if (c.id !== msg.cellId) return c;
      if (msg.status === 'running') {
        // Clear outputs and stdout when execution starts
        return { ...c, status: msg.status, outputs: [], stdout: "", error: undefined };
      }
      return { ...c, status: msg.status };
    })
  );
  break;
```

**Critical Detail**: When `status='running'` is received, outputs are cleared (line 145). But if the WebSocket isn't connected yet, this message is never received, so old outputs remain visible until the next execution.

### Output Persistence

**Storage Layer** (`backend/scheduler.py:168-171`):
```python
# Save notebook to persist stdout, outputs, and error to storage
from storage import save_notebook
async with notebook._lock:
    await save_notebook(notebook)
```

**Storage Implementation** (`backend/storage.py:70-80`):
```python
"outputs": [
    {
        "mime_type": output.mime_type,
        "data": output.data,
        "metadata": output.metadata
    }
    for output in cell.outputs
],
```

**Key Finding**: Outputs ARE saved to storage after execution completes. This is why they appear on page refresh - the HTTP GET loads them from the persisted notebook file.

### Race Condition Scenarios

#### Scenario 1: Execute During WebSocket Authentication (CONFIRMED)

**Timeline**:
1. `t=0ms`: Page loads, WebSocket connection initiated
2. `t=50ms`: User clicks "Run" on SQL cell
3. `t=100ms`: Cell execution starts, broadcasts `cell_status: running`
4. `t=150ms`: SQL query completes, broadcasts `cell_output` with table data
5. `t=200ms`: WebSocket authentication completes, connection registered
6. **Result**: All broadcasts sent to empty connection set, frontend never receives outputs

**Why refresh works**:
- Outputs were saved to storage at `t=150ms`
- On refresh, HTTP GET loads outputs from storage
- WebSocket has time to authenticate before user runs cell

#### Scenario 2: Fast Execution Before WebSocket Ready

**Timeline**:
1. `t=0ms`: Page loads, WebSocket connecting
2. `t=100ms`: WebSocket still authenticating
3. `t=150ms`: Reactive execution triggers SQL cell (due to dependency)
4. `t=200ms`: SQL completes, broadcasts output
5. `t=300ms`: WebSocket authentication completes
6. **Result**: Output broadcast missed, but saved to storage

**Evidence**: This explains why SQL cells that execute automatically (via dependencies) often don't show results until refresh.

#### Scenario 3: Slow Authentication (Network Latency)

**Timeline**:
1. `t=0ms`: Page loads, WebSocket connecting
2. `t=500ms`: JWT validation slow (external JWKS fetch)
3. `t=1000ms`: User runs cell (WebSocket still authenticating)
4. `t=1200ms`: Cell completes, broadcasts output
5. `t=1500ms`: WebSocket finally authenticated and registered
6. **Result**: Output broadcast missed

**Evidence**: This would be more common on slow networks or when Clerk's JWKS endpoint is slow.

## Code References

### Backend
- `backend/routes.py:498-598` - WebSocket endpoint with authentication flow
- `backend/routes.py:598` - Connection registration (critical timing point)
- `backend/websocket.py:15-21` - `connect()` method that registers connections
- `backend/websocket.py:26-40` - `broadcast()` method that sends to registered connections
- `backend/websocket.py:70-82` - `broadcast_cell_output()` implementation
- `backend/executor.py:162-235` - `execute_sql_cell()` implementation
- `backend/scheduler.py:160-166` - Output broadcasting loop
- `backend/scheduler.py:168-171` - Output persistence to storage
- `backend/storage.py:70-80` - Output serialization format

### Frontend
- `frontend/src/useNotebookWebSocket.ts:56-136` - WebSocket connection hook
- `frontend/src/useNotebookWebSocket.ts:61-67` - Authentication message sending
- `frontend/src/useNotebookWebSocket.ts:75-79` - Authentication confirmation handling
- `frontend/src/components/NotebookApp.tsx:96-110` - Initial notebook load (includes outputs)
- `frontend/src/components/NotebookApp.tsx:139-150` - Cell status message handler
- `frontend/src/components/NotebookApp.tsx:160-166` - Cell output message handler
- `frontend/src/components/OutputRenderer.tsx:80-113` - Table rendering for SQL results

## Architecture Insights

### WebSocket Authentication Pattern

The application uses **in-band authentication** for WebSocket connections:
- Connection accepted immediately (no pre-authentication)
- Authentication happens over the WebSocket itself
- Only authenticated connections are registered for broadcasts

**Trade-off**: This pattern is secure (prevents unauthenticated connections from receiving data) but creates a timing window where broadcasts can be missed.

**Alternative Pattern**: Some systems use **query parameter authentication** (token in WebSocket URL), which allows immediate registration. However, this exposes tokens in URLs and has security implications.

### Dual-Channel State Synchronization

The application uses two channels for state updates:
1. **HTTP GET**: Authoritative source of truth, includes persisted outputs
2. **WebSocket**: Real-time streaming updates during execution

**Benefit**: Outputs are never truly "lost" - they're saved to storage and loaded on refresh.

**Drawback**: Creates a confusing UX where outputs appear missing until refresh.

### Output Persistence Strategy

Outputs are persisted to storage after every cell execution (`scheduler.py:168-171`). This is a **synchronous persistence** pattern:
- Execution completes → Save to storage → Continue
- Ensures outputs survive server restarts
- Enables the "refresh to see outputs" workaround

**Design Decision**: This suggests the system was designed with persistence in mind, but the WebSocket streaming was added later and has this timing bug.

## Historical Context (from thoughts/)

### Related Research Documents

**Cell Output Wiping** (`thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md`):
- Documented a similar race condition between HTTP GET and WebSocket updates
- Root cause: `setNotebook(updated)` replaces state before WebSocket messages arrive
- Solution: Merge GET response with current state instead of replacing

**Print/Stdout Rendering** (`thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md`):
- Documented missing `cell_stdout` handler in frontend
- Shows the pattern of incomplete WebSocket message handling
- Similar architectural issue: backend broadcasts, frontend doesn't handle

**WebSocket Architecture** (`thoughts/shared/research/2025-12-27-websocket-only-architecture.md`):
- Discusses eliminating GET requests after initial load
- Proposes using WebSocket as single source of truth
- Would eliminate the race condition by removing dual-channel pattern

### Related Implementation Plans

**WebSocket-Only Implementation** (`thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`):
- Comprehensive plan to eliminate HTTP GET after initial load
- Would solve this issue by making WebSocket the only update channel
- Not yet implemented

**WebSocket Authentication Improvements** (`thoughts/shared/plans/2025-12-28-fix-notebook-selection-ux-and-websocket-auth.md`):
- Plan to improve WebSocket authentication flow
- Addresses race conditions and security
- Partially implemented (authentication exists, but timing issue remains)

## Recommended Solutions

### Solution 1: Wait for WebSocket Before Allowing Execution (Immediate Fix)

**Frontend**: Disable "Run" button until WebSocket is authenticated.

**Implementation** (`frontend/src/components/NotebookCell.tsx:210-221`):

```typescript
// Add connected prop to NotebookCell
interface NotebookCellProps {
  // ... existing props
  isWebSocketConnected: boolean;  // NEW
}

// Disable run button if not connected
<Button
  variant="ghost"
  size="sm"
  onClick={(e) => {
    e.stopPropagation();
    handleRun();
  }}
  disabled={cell.status === "running" || !isWebSocketConnected}  // MODIFIED
  title={
    !isWebSocketConnected 
      ? "Connecting..." 
      : "Run cell (Shift+Enter)"
  }
>
  <Play className="h-3 w-3" />
</Button>
```

**Pass connection status from NotebookApp**:

```typescript
// In NotebookApp.tsx
const { sendMessage, connected } = useNotebookWebSocket(...);

// Pass to cells
<NotebookCell
  // ... existing props
  isWebSocketConnected={connected}
/>
```

**Pros**:
- Simple, low-risk fix
- Prevents the race condition entirely
- Clear UX feedback (button disabled with "Connecting..." tooltip)

**Cons**:
- Delays user interaction (100-500ms)
- Doesn't fix automatic execution (reactive cells)

### Solution 2: Buffer Broadcasts Until Connection Registered (Robust Fix)

**Backend**: Buffer broadcasts for recently created notebooks, replay when connection registers.

**Implementation** (`backend/websocket.py`):

```python
class WebSocketBroadcaster:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.pending_messages: Dict[str, List[Tuple[dict, float]]] = {}  # NEW
        self.MESSAGE_BUFFER_TIME = 5.0  # Buffer for 5 seconds
    
    async def connect(self, notebook_id: str, websocket: WebSocket):
        """Add a WebSocket connection and replay buffered messages"""
        if notebook_id not in self.connections:
            self.connections[notebook_id] = set()
        self.connections[notebook_id].add(websocket)
        
        # Replay buffered messages
        if notebook_id in self.pending_messages:
            import time
            current_time = time.time()
            for message, timestamp in self.pending_messages[notebook_id]:
                if current_time - timestamp < self.MESSAGE_BUFFER_TIME:
                    try:
                        await websocket.send_json(message)
                    except Exception:
                        pass
            del self.pending_messages[notebook_id]
    
    async def broadcast(self, notebook_id: str, message: dict):
        """Send message to all connected clients, buffer if none connected"""
        if notebook_id not in self.connections or not self.connections[notebook_id]:
            # No connections yet - buffer the message
            import time
            if notebook_id not in self.pending_messages:
                self.pending_messages[notebook_id] = []
            self.pending_messages[notebook_id].append((message, time.time()))
            return
        
        # Send to connected clients
        dead_connections = set()
        for websocket in self.connections[notebook_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.add(websocket)
        
        for ws in dead_connections:
            self.connections[notebook_id].discard(ws)
```

**Pros**:
- Fixes the issue completely, including reactive execution
- No UX delay - users can run cells immediately
- Handles all race condition scenarios

**Cons**:
- More complex implementation
- Memory overhead for buffered messages
- Need to handle buffer cleanup (time-based expiry)

### Solution 3: Optimistic Updates + Reconciliation (Advanced Fix)

**Frontend**: Show outputs immediately (optimistically), reconcile with WebSocket when it connects.

**Implementation** (`frontend/src/components/NotebookApp.tsx`):

```typescript
// Track optimistic outputs
const [optimisticOutputs, setOptimisticOutputs] = useState<Map<string, Output[]>>(new Map());

// When running a cell, immediately show loading state
const runCell = (id: string) => {
  // Clear old optimistic outputs
  setOptimisticOutputs(prev => {
    const next = new Map(prev);
    next.delete(id);
    return next;
  });
  
  // Send run command
  sendMessage({ type: 'run_cell', cellId: id });
  
  // Poll for outputs if WebSocket not connected
  if (!connected) {
    const pollInterval = setInterval(async () => {
      try {
        const notebook = await api.getNotebook(notebookId);
        const cell = notebook.cells.find(c => c.id === id);
        if (cell && cell.outputs.length > 0) {
          setOptimisticOutputs(prev => {
            const next = new Map(prev);
            next.set(id, cell.outputs);
            return next;
          });
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error("Failed to poll outputs:", err);
      }
    }, 500);
    
    // Stop polling after 10 seconds
    setTimeout(() => clearInterval(pollInterval), 10000);
  }
};

// Merge optimistic outputs when rendering
const getCellOutputs = (cell: CellData) => {
  if (optimisticOutputs.has(cell.id)) {
    return optimisticOutputs.get(cell.id);
  }
  return cell.outputs;
};
```

**Pros**:
- Best UX - outputs appear immediately
- Graceful degradation if WebSocket is slow/broken
- Works with existing backend

**Cons**:
- Most complex implementation
- Polling adds server load
- Potential for output duplication if WebSocket connects mid-poll

### Solution 4: WebSocket-Only Architecture (Long-term Fix)

**Eliminate HTTP GET after initial load**, use WebSocket as single source of truth.

See `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md` for full plan.

**Key Changes**:
- Initial load: HTTP GET (includes all outputs from storage)
- All updates: WebSocket only (no more GET after operations)
- Cell operations (create/update/delete) return immediately, WebSocket confirms

**Pros**:
- Eliminates dual-channel race conditions entirely
- Simpler mental model (one source of truth)
- Better performance (fewer HTTP requests)

**Cons**:
- Large refactor (touches many files)
- Need robust WebSocket reconnection logic
- Need to handle WebSocket disconnection gracefully

## Recommended Implementation Order

1. **Immediate**: Solution 1 (disable run button) - Quick fix for user-initiated runs
2. **Short-term**: Solution 2 (buffer broadcasts) - Robust fix for all scenarios
3. **Long-term**: Solution 4 (WebSocket-only) - Architectural improvement

## Open Questions

1. **Should we also buffer `cell_status` and `cell_stdout` messages?** Currently only `cell_output` is discussed, but the same race condition affects all broadcast types.

2. **What's the typical authentication time?** Measuring this would help tune the buffer timeout and inform UX decisions.

3. **Should reactive execution wait for WebSocket?** Currently, dependency-triggered execution can happen before WebSocket is ready. Should we delay it?

4. **How do we handle WebSocket disconnection during execution?** If the WebSocket disconnects mid-execution, outputs are lost until refresh. Should we implement automatic reconnection with state sync?

5. **Should we show a "Connecting..." indicator?** Users might not understand why the run button is disabled. A connection status indicator would help.

## Related Research

- `thoughts/shared/research/2025-12-27-cell-output-wiping-on-blur.md` - Similar race condition between GET and WebSocket
- `thoughts/shared/research/2025-12-30-print-stdout-and-fig-show-not-rendering.md` - Missing WebSocket message handlers
- `thoughts/shared/research/2025-12-27-websocket-only-architecture.md` - Proposed architectural fix
- `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md` - Detailed implementation plan
- `thoughts/shared/plans/2025-12-28-fix-notebook-selection-ux-and-websocket-auth.md` - WebSocket authentication improvements

