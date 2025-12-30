---
date: 2025-12-30T14:58:43+00:00
planner: Matthew Carter
topic: "WebSocket React-Use-WebSocket Migration"
tags: [planning, implementation, websocket, react-use-websocket, react-18, strict-mode]
status: draft
last_updated: 2025-12-30
last_updated_by: Matthew Carter
related_research: thoughts/shared/research/2025-12-30-websocket-management-react-18-rewrite.md
---

# WebSocket React-Use-WebSocket Migration Implementation Plan

**Date**: 2025-12-30T14:58:43+00:00  
**Planner**: Matthew Carter

## Overview

Replace the custom `useWebSocket.ts` hook with a new `useNotebookWebSocket.ts` hook built on the `react-use-websocket` library. This migration eliminates ~180 lines of complex connection management code (8 refs, 5 guards, exponential backoff) in favor of a battle-tested library that handles React 18 Strict Mode out of the box.

## Current State Analysis

The existing `frontend/src/useWebSocket.ts` (277 lines total) suffers from:

1. **Over-engineered connection guards** (8 refs for tracking state):
   - `ws`, `reconnectTimeoutRef`, `reconnectAttempts`, `intentionalClose`
   - `lastConnectTime`, `isConnecting`, `currentNotebookId`, `onMessageRef`

2. **Race condition mitigation attempts** that have required multiple bug fixes:
   - `minTimeBetweenConnects` (500ms throttle)
   - Manual tracking of "our" WebSocket instance vs newer instances
   - `intentionalClose` flag to distinguish cleanup from errors

3. **Complex cleanup logic** (lines 244-264) that still has edge cases in React 18 Strict Mode

4. **Previous fixes documented** in `thoughts/shared/plans/2025-12-30-fix-websocket-infinite-loop-on-notebook-switch.md` show the ongoing maintenance burden

### Key Discoveries:

- **Backend Protocol**: In-band authentication via `{"type": "authenticate", "token": "..."}` after connection (no URL params/headers needed)
- **Message Types**: Discriminated union types already well-defined (`WSMessage` type with 7 variants)
- **Token Source**: Clerk's `getToken()` called in `NotebookApp.tsx:41-49`, token passed to hook
- **Single Consumer**: Only `NotebookApp.tsx` uses the WebSocket hook
- **Backend unchanged**: `backend/routes.py:504-658` WebSocket endpoint requires no modifications

## System Context Analysis

The WebSocket hook is the **single point of integration** between the React frontend and the real-time backend. All cell execution, status updates, and collaborative changes flow through this connection. The current implementation addresses symptoms (infinite loops, duplicate connections) with ref-based guards, but the **root cause** is attempting to manually manage WebSocket lifecycle in React 18's concurrent rendering environment.

**This plan addresses the root cause** by delegating lifecycle management to `react-use-websocket`, which is specifically designed for React 18's behavior.

## Desired End State

After this plan is complete:

1. **New hook** `useNotebookWebSocket.ts` (~50 lines) replaces `useWebSocket.ts` (~277 lines)
2. **Zero connection management code** - library handles Strict Mode, reconnection, cleanup
3. **Same message protocol** - backend requires no changes
4. **Same consumer interface** - minimal changes to `NotebookApp.tsx`
5. **Improved reliability** - exponential backoff, proper cleanup, no duplicate connections

### Verification:
- [ ] Switch notebooks rapidly → No infinite loops (same as before)
- [ ] React Strict Mode (dev) → Single connection per notebook
- [ ] WebSocket disconnection → Automatic reconnection with backoff
- [ ] Auth failure (1008 close code) → No reconnection, clean error
- [ ] Cell execution → Real-time status/output updates work
- [ ] Console shows clean connection logs, no errors

## What We're NOT Doing

1. **Changing the backend** - WebSocket protocol stays identical
2. **Changing message types** - `WSMessage` discriminated union preserved
3. **Adding new features** - No message queuing, no connection UI, no token refresh
4. **Refactoring NotebookApp** - Minimal changes to consumer code
5. **Supporting multiple WebSocket consumers** - Still single-consumer pattern

## Implementation Approach

**Strategy**: Create new hook alongside old one, migrate consumer, verify, then delete old hook.

This approach allows:
- Side-by-side comparison during development
- Easy rollback if issues discovered
- Clear before/after verification

---

## Phase 1: Install Dependency and Create New Hook

### Overview
Install `react-use-websocket` and create the new `useNotebookWebSocket.ts` hook that wraps the library with our authentication protocol.

### Changes Required:

#### 1. Install react-use-websocket
**Command**: 
```bash
cd frontend && npm install react-use-websocket
```

**Verification**: Package appears in `frontend/package.json` dependencies

#### 2. Create New Hook File
**File**: `frontend/src/useNotebookWebSocket.ts`
**Changes**: Create new file with complete implementation

```typescript
import useWebSocket, { ReadyState } from 'react-use-websocket';
import { useCallback, useRef, useEffect } from 'react';
import type { CellResponse, OutputResponse, CellStatus } from './client/types.gen';
import { WS_BASE_URL } from './api-client';

// Re-export WebSocket message types (keep existing discriminated union)
// These match the backend WebSocket broadcaster in backend/websocket.py
export type WSMessage =
  | { type: 'cell_updated'; cellId: string; cell: { code: string; reads: string[]; writes: string[]; status: string } }
  | { type: 'cell_created'; cellId: string; cell: CellResponse; index?: number }
  | { type: 'cell_deleted'; cellId: string }
  | { type: 'cell_status'; cellId: string; status: CellStatus }
  | { type: 'cell_stdout'; cellId: string; data: string }
  | { type: 'cell_error'; cellId: string; error: string }
  | { type: 'cell_output'; cellId: string; output: OutputResponse };

// Keep existing type guards for compatibility
export function isWSMessage(msg: unknown): msg is WSMessage {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    'type' in msg &&
    'cellId' in msg &&
    typeof (msg as { type: unknown; cellId: unknown }).type === 'string' &&
    typeof (msg as { cellId: unknown }).cellId === 'string'
  );
}

interface UseNotebookWebSocketOptions {
  onMessage: (msg: WSMessage) => void;
}

export function useNotebookWebSocket(
  notebookId: string | null,
  token: string | null,
  options: UseNotebookWebSocketOptions
) {
  const didUnmount = useRef(false);
  const isAuthenticated = useRef(false);
  const tokenRef = useRef(token);
  
  // Keep token ref updated for use in callbacks
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  // Only connect when we have both notebookId and token
  const socketUrl = notebookId && token
    ? `${WS_BASE_URL}/api/ws/notebooks/${notebookId}`
    : null;

  const {
    sendJsonMessage,
    readyState,
  } = useWebSocket(socketUrl, {
    // Send auth message immediately on open
    onOpen: () => {
      console.log('WebSocket connected, sending authentication...');
      isAuthenticated.current = false;
      sendJsonMessage({ type: 'authenticate', token: tokenRef.current });
    },

    // Handle all messages including auth response
    onMessage: (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle auth response
        if (data.type === 'authenticated') {
          console.log('WebSocket authenticated successfully');
          isAuthenticated.current = true;
          return;
        }

        // Handle errors
        if (data.type === 'error') {
          console.error('WebSocket error:', data.message);
          return;
        }

        // Validate and forward to consumer
        if (isWSMessage(data)) {
          options.onMessage(data);
        } else {
          console.error('Invalid WebSocket message structure:', data);
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    },

    onClose: (event) => {
      console.log('WebSocket disconnected', event.code, event.reason);
      isAuthenticated.current = false;
    },

    onError: (event) => {
      console.error('WebSocket error:', event);
    },

    // Reconnection with exponential backoff
    shouldReconnect: (closeEvent) => {
      // Don't reconnect on auth failure (1008) or clean close (1000)
      if (closeEvent.code === 1008 || closeEvent.code === 1000) {
        console.log(`WebSocket closed with code ${closeEvent.code}, not reconnecting`);
        return false;
      }
      // Don't reconnect if component unmounted
      if (didUnmount.current) {
        return false;
      }
      return true;
    },
    reconnectInterval: (attemptNumber) =>
      Math.min(Math.pow(2, attemptNumber) * 1000, 10000),
    reconnectAttempts: 5,
    retryOnError: true,

    // Don't share connection between hook instances
    share: false,
  }, !!socketUrl); // Enable only when URL is valid

  // Track unmount for reconnection logic
  useEffect(() => {
    didUnmount.current = false;
    return () => {
      didUnmount.current = true;
    };
  }, []);

  // Send run_cell command
  const runCell = useCallback((cellId: string) => {
    if (readyState === ReadyState.OPEN && isAuthenticated.current) {
      sendJsonMessage({ type: 'run_cell', cellId });
    } else {
      console.warn('WebSocket not ready, cannot run cell');
    }
  }, [readyState, sendJsonMessage]);

  // Generic send for any message (maintains old interface)
  const sendMessage = useCallback((message: object) => {
    if (readyState === ReadyState.OPEN) {
      sendJsonMessage(message);
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, [readyState, sendJsonMessage]);

  return {
    sendMessage,
    runCell,
    connected: readyState === ReadyState.OPEN && isAuthenticated.current,
    readyState,
  };
}
```

### Success Criteria:

#### Automated Verification:
- [x] Package installed: `grep "react-use-websocket" frontend/package.json`
- [x] File exists: `ls frontend/src/useNotebookWebSocket.ts`
- [x] TypeScript compiles: `cd frontend && npm run build`
- [x] No linting errors: `cd frontend && npm run lint`

#### Manual Verification:
- [x] New file created with correct content

---

## Phase 2: Migrate NotebookApp to New Hook

### Overview
Update `NotebookApp.tsx` to use the new hook. The change is minimal since the interface is nearly identical.

### Changes Required:

#### 1. Update Import
**File**: `frontend/src/components/NotebookApp.tsx`
**Line**: 12
**Changes**: Change import from old hook to new hook

```typescript
// Before
import { useWebSocket } from "../useWebSocket";

// After
import { useNotebookWebSocket } from "../useNotebookWebSocket";
```

#### 2. Update Hook Usage
**File**: `frontend/src/components/NotebookApp.tsx`
**Line**: 179
**Changes**: Update hook call to use new function name and signature

```typescript
// Before
const { sendMessage } = useWebSocket(notebookId || "", handleWebSocketMessage, notebookId && authToken ? authToken : null);

// After
const { sendMessage } = useNotebookWebSocket(
  notebookId,
  notebookId && authToken ? authToken : null,
  { onMessage: handleWebSocketMessage }
);
```

Note: The new hook accepts `null` for `notebookId` directly (no need for `|| ""`), and the callback is passed via options object.

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `cd frontend && npm run build`
- [x] No linting errors: `cd frontend && npm run lint`
- [x] Build completes: `cd frontend && npm run build`

#### Manual Verification:
- [ ] Application loads without errors
- [ ] WebSocket connects when notebook selected
- [ ] Console shows "WebSocket connected, sending authentication..."
- [ ] Console shows "WebSocket authenticated successfully"
- [ ] Cell execution works (click run, see output)
- [ ] Real-time updates work (create/delete cell, see changes)
- [ ] Notebook switch works without infinite loop

---

## Phase 3: Delete Old Hook and Cleanup

### Overview
Remove the old `useWebSocket.ts` file now that migration is complete.

### Changes Required:

#### 1. Delete Old Hook File
**File**: `frontend/src/useWebSocket.ts`
**Changes**: Delete entire file (277 lines)

```bash
rm frontend/src/useWebSocket.ts
```

#### 2. Verify No References
**Command**: 
```bash
grep -r "useWebSocket" frontend/src --include="*.ts" --include="*.tsx" | grep -v "useNotebookWebSocket"
```

Should return no results (only `useNotebookWebSocket` references remain).

### Success Criteria:

#### Automated Verification:
- [x] Old file deleted: `! ls frontend/src/useWebSocket.ts 2>/dev/null`
- [x] No stale imports: `grep -r "from.*useWebSocket" frontend/src --include="*.ts" --include="*.tsx" | wc -l` returns 0
- [x] TypeScript compiles: `cd frontend && npm run build`
- [x] Full build succeeds: `cd frontend && npm run build`

#### Manual Verification:
- [ ] Application still works after deletion
- [ ] All Phase 2 manual tests still pass

---

## Phase 4: End-to-End Testing

### Overview
Comprehensive testing of all WebSocket functionality to ensure the migration is complete and reliable.

### Test Scenarios:

#### Connection Lifecycle:
- [ ] Fresh page load → WebSocket connects and authenticates
- [ ] Page refresh → Clean reconnection
- [ ] Browser tab inactive → Connection maintained or graceful reconnect
- [ ] Network disconnect (DevTools) → Automatic reconnection with backoff
- [ ] Close tab → Clean disconnect (no errors in backend logs)

#### Notebook Operations:
- [ ] Select notebook → WebSocket connects to correct endpoint
- [ ] Switch notebook → Old connection closes, new connection opens
- [ ] Rapid notebook switching → No infinite loops, no duplicate connections
- [ ] Delete current notebook → Handles gracefully

#### Cell Operations:
- [ ] Create cell → Appears via WebSocket broadcast
- [ ] Update cell code → Synced via WebSocket broadcast
- [ ] Run cell → Status updates (running → idle)
- [ ] Run cell with output → Output appears incrementally
- [ ] Run cell with error → Error displayed correctly
- [ ] Delete cell → Removed via WebSocket broadcast

#### React 18 Strict Mode:
- [ ] Dev mode (Strict Mode enabled) → Single connection per notebook
- [ ] Effect double-invocation → No duplicate auth messages
- [ ] Fast refresh (save file) → Reconnects cleanly

#### Error Scenarios:
- [ ] Invalid token → Connection closes with 1008, no reconnect loop
- [ ] Backend restart → Automatic reconnection
- [ ] 5 failed reconnects → Stops attempting, logs error

### Success Criteria:

#### Automated Verification:
- [ ] All unit tests pass (if any): `cd frontend && npm test`
- [ ] Build succeeds: `cd frontend && npm run build`

#### Manual Verification:
- [ ] All test scenarios above pass
- [ ] Console logs are clean (info only, no errors during normal operation)
- [ ] Network tab shows single WebSocket connection per notebook
- [ ] No memory leaks (check DevTools Memory tab over time)

---

## Testing Strategy

### Unit Tests:
- The `react-use-websocket` library has its own test suite
- Type checking via TypeScript ensures message types match

### Integration Tests:
- Manual testing covers WebSocket ↔ Backend integration
- Real-time behavior cannot be easily unit tested

### Manual Testing Steps:
1. Start backend: `cd backend && uvicorn main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open browser DevTools (Console + Network tabs)
4. Run through Phase 4 test scenarios
5. Document any issues found

## Performance Considerations

| Metric | Before | After |
|--------|--------|-------|
| Hook code size | ~277 lines | ~120 lines |
| Refs managed | 8 | 2 |
| Guards | 5 manual checks | 0 (library handles) |
| Bundle impact | Custom code | +~3KB gzipped (library) |
| Reconnection | Custom backoff | Library backoff (identical behavior) |

The small bundle increase is offset by:
- Reduced custom code to maintain
- Battle-tested reconnection logic
- Proper React 18 lifecycle handling

## Migration Notes

### Breaking Changes:
- None for consumers - interface is compatible

### Rollback Plan:
1. Revert import in `NotebookApp.tsx` back to `useWebSocket`
2. Revert hook usage to old signature
3. Restore `useWebSocket.ts` from git
4. Remove `react-use-websocket` from dependencies

### Backwards Compatibility:
- Backend requires no changes
- Message format unchanged
- All existing functionality preserved

## References

- Original research: `thoughts/shared/research/2025-12-30-websocket-management-react-18-rewrite.md`
- Previous fix: `thoughts/shared/plans/2025-12-30-fix-websocket-infinite-loop-on-notebook-switch.md`
- Current hook: `frontend/src/useWebSocket.ts:1-277`
- Hook consumer: `frontend/src/components/NotebookApp.tsx:179`
- Backend endpoint: `backend/routes.py:504-658`
- Backend broadcaster: `backend/websocket.py:1-110`

