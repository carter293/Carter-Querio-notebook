---
date: 2025-12-27T18:30:00+00:00
researcher: Composer
topic: "Optimistic updates vs WebSocket confirmation for notebook state"
tags: [research, frontend, state-management, websocket, optimistic-updates]
status: complete
---

# Research: Optimistic Updates vs WebSocket Confirmation

**Date**: 2025-12-27T18:30:00+00:00 GMT  
**Researcher**: Composer

## Research Question

Should we use optimistic updates for notebook state mutations, or wait for WebSocket confirmation? What do best-in-class real-time applications do?

## Current Situation

### User Flow
1. User types code in Monaco editor → **sees it immediately** (local editor state)
2. User blurs editor → triggers `onUpdateCell`
3. Frontend sends PUT request → backend processes
4. Backend sends WebSocket `cell_updated` message (<100ms typically)
5. Frontend receives WebSocket message → updates notebook state

### What Needs Updating
- **Code**: Already visible in editor (local state)
- **Reads/Writes**: Computed by backend (dependency analysis)
- **Status**: Determined by backend (cycle detection, etc.)
- **Cell order**: Determined by backend (for create/delete)

## Research Findings

### Best Practices from Real-Time Applications

#### 1. **Google Docs / Figma** (Operational Transforms / CRDTs)
- **Approach**: Wait for server confirmation
- **Reason**: Complex state with conflicts - optimistic updates would cause inconsistencies
- **Pattern**: Server is source of truth, client applies server-confirmed operations

#### 2. **marimo** (Reactive Notebook)
- **Approach**: Optimistic updates WITH WebSocket confirmation
- **Reason**: Fast feedback for code changes
- **Pattern**: Update UI immediately, WebSocket confirms/overrides

#### 3. **Jupyter** (Notebook)
- **Approach**: Wait for WebSocket confirmation
- **Reason**: Execution results must be accurate
- **Pattern**: WebSocket messages are authoritative

#### 4. **Slack / Discord** (Real-time Chat)
- **Approach**: Optimistic updates for simple actions (sending message)
- **Reason**: High success rate, low consequence if fails
- **Pattern**: Show immediately, rollback on error

### Key Insights

1. **Optimistic updates are best for:**
   - High success rate actions (>95%)
   - Low consequence if fails (likes, simple UI state)
   - Simple state changes (no complex computation)

2. **Wait for confirmation when:**
   - Data consistency is critical (notebooks, documents)
   - Backend computes derived state (dependencies, errors)
   - WebSocket latency is low (<200ms)

3. **Hybrid approach:**
   - Optimistic for UI feedback (loading states, visual feedback)
   - Wait for server for actual state updates

## Analysis for Our Use Case

### Current Mutations

#### 1. **Update Cell Code**
- **Frequency**: On blur (low frequency)
- **Latency**: WebSocket arrives <100ms
- **Derived State**: Reads/writes computed by backend
- **Error Cases**: Cycle detection, validation
- **User Perception**: Code already visible in editor

**Recommendation**: **Wait for WebSocket** - code is already visible, dependencies unknown until backend computes

#### 2. **Create Cell**
- **Frequency**: User-initiated (low frequency)
- **Latency**: WebSocket arrives <100ms
- **Derived State**: Cell ID, position determined by backend
- **Error Cases**: Notebook not found, validation errors
- **User Perception**: Would see cell appear immediately

**Recommendation**: **Optional optimistic update** - but WebSocket confirmation is fast enough

#### 3. **Delete Cell**
- **Frequency**: User-initiated (low frequency)
- **Latency**: WebSocket arrives <100ms
- **Derived State**: None (simple removal)
- **Error Cases**: Last cell, notebook not found
- **User Perception**: Would see cell disappear immediately

**Recommendation**: **Optional optimistic update** - but WebSocket confirmation is fast enough

### Key Factors

1. **WebSocket is fast**: <100ms latency means users won't notice delay
2. **Backend computes dependencies**: We can't know reads/writes until backend analyzes code
3. **Error handling**: Cycle detection, validation errors need backend confirmation
4. **Code is already visible**: User sees their typing in Monaco editor immediately
5. **Simplicity**: No rollback logic needed if we wait for confirmation

## Proposed Solution

### Approach: **WebSocket-Only Updates (No Optimistic Updates)**

**Rationale:**
1. WebSocket messages arrive quickly (<100ms)
2. Backend computes derived state (reads/writes, errors)
3. Simpler implementation (no rollback logic)
4. Always consistent (server is source of truth)
5. User already sees code changes in editor

**Implementation:**
- Send mutation request (PUT/POST/DELETE)
- Show subtle loading indicator if needed (optional)
- Wait for WebSocket `cell_updated`/`cell_created`/`cell_deleted` message
- Update state from WebSocket message
- Handle errors via WebSocket error messages

**Benefits:**
- ✅ Simpler code (no rollback logic)
- ✅ Always consistent state
- ✅ No race conditions
- ✅ Error handling is straightforward
- ✅ WebSocket is fast enough (<100ms)

**Trade-offs:**
- ⚠️ Slight delay (<100ms) before state updates
- ⚠️ User doesn't see cell disappear immediately on delete (but WebSocket is fast)

### Alternative: **Minimal Optimistic Updates**

If we want immediate feedback for create/delete:

**For Create:**
- Optimistically add cell with temporary ID
- WebSocket message replaces with real ID and position

**For Delete:**
- Optimistically remove cell
- WebSocket message confirms (or rollback on error)

**For Update:**
- No optimistic update (code already visible, dependencies unknown)

**Trade-offs:**
- ✅ Immediate feedback for create/delete
- ⚠️ More complex (need rollback logic)
- ⚠️ Need to handle temporary IDs
- ⚠️ Potential inconsistencies if WebSocket fails

## Recommendation

**Use WebSocket-only updates (no optimistic updates)** because:

1. **WebSocket is fast enough**: <100ms latency is imperceptible to users
2. **Code is already visible**: User sees their typing in Monaco editor
3. **Backend computes state**: Dependencies, errors need backend analysis
4. **Simplicity**: No rollback logic, fewer edge cases
5. **Consistency**: Server is always source of truth

**Optional enhancement**: Add subtle loading indicators during mutations for better UX feedback.

## Implementation Impact

### Phase 3 Changes (Remove GET Requests)
- Remove optimistic updates from `handleUpdateCell`
- Remove optimistic updates from `handleAddCell`  
- Remove optimistic updates from `handleDeleteCell`
- Just send mutation, wait for WebSocket

### Phase 4 Changes (Handle WebSocket Messages)
- WebSocket messages become the only update path
- No need for rollback logic
- Simpler error handling

## References

- Original plan: `thoughts/shared/plans/2025-12-27-websocket-only-implementation-comprehensive.md`
- WebSocket architecture research: `thoughts/shared/research/2025-12-27-websocket-only-architecture.md`

