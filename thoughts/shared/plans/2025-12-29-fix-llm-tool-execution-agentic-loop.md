---
date: 2025-12-29T13:42:36+00:00
planner: Cursor AI
topic: "Fix LLM Tool Execution - Implement Proper Agentic Loop"
tags: [planning, implementation, llm, chat, anthropic, tools, sse]
status: draft
last_updated: 2025-12-29
last_updated_by: Cursor AI
---

# Fix LLM Tool Execution - Implement Proper Agentic Loop

**Date**: 2025-12-29T13:42:36+00:00  
**Planner**: Cursor AI

## Overview

The LLM chat assistant's tool calls are not affecting the notebook because the backend doesn't follow the correct Anthropic API pattern for agentic tool use. The current implementation only executes tools from the first response, but doesn't continue the loop when follow-up responses contain additional tool calls. This plan fixes the backend to use a proper agentic loop that continues until `stop_reason != "tool_use"`.

## Current State Analysis

### What Exists Now

The chat endpoint (`backend/chat.py`) has a partial implementation:
1. ✅ First stream correctly calls `get_final_message()` and executes tools
2. ✅ Tool results are sent back to Claude in a follow-up request
3. ❌ Follow-up stream does NOT call `get_final_message()`
4. ❌ Follow-up stream does NOT execute any tool_use blocks
5. ❌ No check for `stop_reason` to determine if more tools are needed
6. ❌ Only handles 2 turns max (initial + one follow-up)

### Key Code Locations

- `backend/chat.py:30-280` - Chat endpoint with SSE streaming
- `backend/chat.py:136-184` - First stream tool execution (works)
- `backend/chat.py:186-268` - Follow-up stream handling (broken)
- `backend/llm_tools.py:381-429` - Tool dispatcher (correct)
- `frontend/src/components/ChatPanel.tsx:104-186` - SSE event handling (correct)

### Evidence of the Bug

From the user's SSE trace:
```
data: {"event": "tool_start", "data": {"tool_name": "update_cell"}}
data: {"event": "content_block_stop", "data": {}}
data: {"event": "done", "data": {}}  <-- Stream ends WITHOUT executing update_cell!
```

The `update_cell` tool was requested by Claude in the follow-up response but never executed.

## System Context Analysis

This plan addresses a **root cause**, not a symptom. The Anthropic API requires a loop pattern for agentic tool use:

```
while stop_reason == "tool_use":
    execute tools
    send results back
    get next response
```

Our implementation only does ONE iteration. This is an architectural fix to the chat streaming logic.

## Desired End State

After implementation:
1. LLM tool calls will actually modify the notebook (create cells, update code, run cells, etc.)
2. Multi-turn tool chains will work (e.g., get_state → update_cell → run_cell)
3. The frontend will see `tool_execute` and `tool_result` events for ALL tools, not just the first batch
4. Maximum turn limit prevents infinite loops

### Verification Criteria

1. Ask the LLM to "create an example notebook with some data analysis"
2. Observe in the frontend:
   - `get_notebook_state` tool executes → returns cell info
   - `update_cell` or `create_cell` tools execute → notebook UI updates
   - `run_cell` tools execute → outputs appear
3. All tool executions should be visible in the chat UI
4. The notebook should reflect the changes made by the LLM

## What We're NOT Doing

- **Inline tool display in chat UI** - Tool calls will still appear at the bottom of messages (this is a separate UX enhancement)
- **Streaming tool input JSON to client** - The SDK handles accumulation, we don't need real-time partial JSON display
- **Frontend changes** - The existing SSE event handling is correct; only backend needs fixing
- **New SSE event types** - We'll use the existing event types

## Implementation Approach

Refactor `chat.py` to use a single agentic loop that:
1. Streams from Anthropic
2. Always calls `get_final_message()` after the stream
3. Checks `stop_reason` to decide whether to continue
4. Executes tools and appends to message history
5. Loops until `stop_reason != "tool_use"` or max turns reached

---

## Phase 1: Refactor chat.py to Agentic Loop

### Overview

Replace the current two-step approach (initial stream + optional follow-up) with a proper while loop that continues until no more tools are needed.

### Changes Required

#### 1. Backend Chat Endpoint

**File**: `backend/chat.py`  
**Changes**: Complete rewrite of the `event_generator` function

```python
"""
LLM chat endpoint with Server-Sent Events streaming.
"""
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from typing import List
import json
import os

from routes import get_current_user_dependency, NOTEBOOKS
from scheduler import scheduler
from websocket import broadcaster
from llm_tools import TOOL_SCHEMAS, execute_tool, tool_get_notebook_state
from audit import log_llm_action

router = APIRouter()

# Maximum number of tool turns to prevent infinite loops
MAX_TOOL_TURNS = 10


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


def sse_event(event_type: str, data: dict) -> dict:
    """Helper to format SSE events consistently."""
    return {
        "data": json.dumps({
            "event": event_type,
            "data": data
        })
    }


@router.post("/chat/{notebook_id}")
async def chat_with_notebook(
    notebook_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    """
    Stream LLM chat responses with tool execution.
    Uses Server-Sent Events for streaming.
    Implements proper agentic loop that continues until no more tools.
    """
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    async def event_generator():
        """Generate SSE events for chat stream with agentic tool loop."""
        client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Convert messages to Anthropic format
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        # Build system prompt with notebook context
        notebook_state = await tool_get_notebook_state(notebook, include_outputs=False)
        
        system_prompt = f"""You are an AI assistant helping with a reactive Python/SQL notebook.

Current notebook: "{notebook.name or 'Untitled'}"
Number of cells: {len(notebook_state['cells'])}

Available tools:
- get_notebook_state: See all cells and their outputs
- create_cell: Add new Python or SQL cells
- update_cell: Modify existing cell code
- run_cell: Execute a cell (waits up to 30s for completion)
- delete_cell: Remove a cell

Important:
- Always use get_notebook_state first to understand the current state
- When creating data analysis code, use pandas for data manipulation and plotly for visualization
- For SQL cells, use {{variable}} syntax to reference Python variables
- Be concise and helpful
- If a cell fails, read the error and suggest fixes

Cell statuses:
- idle: Not executed yet
- running: Currently executing
- success: Executed successfully
- error: Execution failed
- blocked: Waiting for dependencies
"""
        
        try:
            turn_count = 0
            
            # Agentic loop - continues until no more tools or max turns
            while turn_count < MAX_TOOL_TURNS:
                turn_count += 1
                
                # Stream from Anthropic with tools
                async with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    system=system_prompt
                ) as stream:
                    # Stream events to client as they arrive
                    async for event in stream:
                        if event.type == "content_block_start":
                            if event.content_block.type == "text":
                                yield sse_event("text_start", {})
                            elif event.content_block.type == "tool_use":
                                yield sse_event("tool_start", {
                                    "tool_id": event.content_block.id,
                                    "tool_name": event.content_block.name
                                })
                        
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                yield sse_event("text_delta", {"text": event.delta.text})
                            # Note: input_json_delta is handled by SDK's get_final_message()
                        
                        elif event.type == "content_block_stop":
                            yield sse_event("content_block_stop", {})
                    
                    # Get final message with accumulated tool inputs
                    final_message = await stream.get_final_message()
                
                # Check stop_reason - KEY DECISION POINT
                if final_message.stop_reason != "tool_use":
                    # No more tools requested, we're done
                    break
                
                # Execute all tools from this turn
                tool_results = []
                for block in final_message.content:
                    if block.type == "tool_use":
                        yield sse_event("tool_execute", {
                            "tool_name": block.name,
                            "tool_input": block.input
                        })
                        
                        # Log tool execution for audit
                        log_llm_action(
                            notebook_id=notebook_id,
                            user_id=user_id,
                            action=f"tool_{block.name}",
                            details=block.input
                        )
                        
                        # Execute tool (with locks!)
                        result = await execute_tool(
                            block.name,
                            block.input,
                            notebook,
                            scheduler,
                            broadcaster
                        )
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        })
                        
                        yield sse_event("tool_result", {
                            "tool_name": block.name,
                            "result": result
                        })
                
                # Append assistant message and tool results to history for next turn
                messages.append({
                    "role": "assistant",
                    "content": final_message.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
            
            # Stream complete
            yield sse_event("done", {})
        
        except Exception as e:
            yield sse_event("error", {"error": str(e)})
    
    return EventSourceResponse(event_generator())
```

### Success Criteria

#### Automated Verification:
- [x] Backend starts without errors: `cd backend && source venv/bin/activate && python -c "from chat import router; print('OK')"`
- [x] Type checking passes (if using mypy)
- [x] Existing tests pass: `cd backend && pytest tests/`

#### Manual Verification:
- [x] Send "check the notebook state" → `get_notebook_state` executes and returns
- [x] Send "create an example notebook with data analysis" → multiple tools execute:
  - `get_notebook_state` executes
  - `update_cell` or `create_cell` executes AND notebook UI updates
  - `run_cell` executes AND outputs appear
- [x] All tool calls visible in chat panel
- [x] Max turn limit works (send request that would loop forever)

---

## Phase 2: Add Turn Count Event (Optional Enhancement)

### Overview

Add an SSE event to inform the frontend which turn we're on, useful for debugging and UX.

### Changes Required

#### 1. New SSE Event Type

**File**: `frontend/src/types/chat.ts`  
**Changes**: Add `turn_start` event type

```typescript
export type SSEEvent =
  | { event: 'text_start'; data: Record<string, never> }
  | { event: 'text_delta'; data: { text: string } }
  | { event: 'tool_start'; data: { tool_id: string; tool_name: string } }
  | { event: 'tool_execute'; data: { tool_name: string; tool_input: ToolInput } }
  | { event: 'tool_result'; data: { tool_name: string; result: ToolResult } }
  | { event: 'follow_up_start'; data: Record<string, never> }  // Keep for backwards compat
  | { event: 'turn_start'; data: { turn: number; max_turns: number } }  // NEW
  | { event: 'content_block_stop'; data: Record<string, never> }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { error: string } };
```

#### 2. Emit Turn Start Event

**File**: `backend/chat.py`  
**Changes**: Add at the start of each loop iteration

```python
while turn_count < MAX_TOOL_TURNS:
    turn_count += 1
    
    # Emit turn start event (useful for debugging/UX)
    if turn_count > 1:
        yield sse_event("turn_start", {
            "turn": turn_count,
            "max_turns": MAX_TOOL_TURNS
        })
    
    # ... rest of loop
```

### Success Criteria

#### Automated Verification:
- [x] TypeScript compiles: `cd frontend && npm run build`

#### Manual Verification:
- [x] Console shows turn numbers during multi-turn conversations
- [x] No frontend errors on new event type

---

## Testing Strategy

### Unit Tests

**File**: `backend/tests/test_chat.py` (new file)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from chat import chat_with_notebook, MAX_TOOL_TURNS


@pytest.mark.asyncio
async def test_max_turns_limit():
    """Verify the loop terminates at MAX_TOOL_TURNS."""
    # Mock Anthropic client that always returns tool_use
    # Verify we exit after MAX_TOOL_TURNS iterations
    pass


@pytest.mark.asyncio  
async def test_loop_exits_on_end_turn():
    """Verify loop exits when stop_reason is 'end_turn'."""
    pass


@pytest.mark.asyncio
async def test_tools_executed_every_turn():
    """Verify tools are executed on every turn, not just the first."""
    pass
```

### Integration Tests

1. **Multi-turn tool chain test**:
   - Send "create a cell with x=1, run it, then show me the state"
   - Verify: create_cell → run_cell → get_notebook_state all execute
   - Verify: notebook state reflects all changes

2. **Error recovery test**:
   - Send request that causes a tool to error
   - Verify: error is returned, loop continues or terminates gracefully

### Manual Testing Steps

1. Start backend: `cd backend && source venv/bin/activate && uvicorn main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open browser to localhost, select a notebook
4. Test cases:
   - "What's in this notebook?" → `get_notebook_state` executes
   - "Add a cell that prints hello world" → `create_cell` or `update_cell` executes, UI updates
   - "Run all cells" → `run_cell` executes for each cell
   - "Create a data analysis example with a chart" → multi-tool chain works

## Performance Considerations

1. **Turn limit**: MAX_TOOL_TURNS = 10 prevents runaway loops
2. **Token usage**: Each turn uses more tokens (conversation history grows)
3. **Latency**: Multi-turn conversations have multiple round-trips to Anthropic
4. **WebSocket broadcasts**: Each tool execution broadcasts to connected clients

## Migration Notes

No migration needed - this is a pure code change. The SSE event types remain compatible with the existing frontend.

## References

- Research document: `thoughts/shared/research/2025-12-29-llm-tool-execution-issues.md`
- Anthropic Streaming Docs: https://docs.anthropic.com/en/api/streaming
- Existing chat endpoint: `backend/chat.py`
- Tool implementations: `backend/llm_tools.py`

