---
date: 2025-12-29T13:35:28+00:00
researcher: Cursor AI
topic: "LLM Tool Execution Issues - Tool Calls Not Affecting Notebook"
tags: [research, codebase, llm-tools, chat, sse, websocket, anthropic-api]
status: complete
last_updated: 2025-12-29T14:00:00+00:00
last_updated_by: Cursor AI
---

# Research: LLM Tool Execution Issues - Tool Calls Not Affecting Notebook

**Date**: 2025-12-29T13:35:28+00:00  
**Updated**: 2025-12-29T14:00:00+00:00  
**Researcher**: Cursor AI

## Research Question

User reported several issues with the LLM chat assistant:
1. Tool calls appear at the bottom of messages instead of inline
2. The `update_cell` tool call shows no content in the UI
3. **CRITICAL**: Tool calls aren't affecting the notebook at all

## Summary

**Root Cause Identified**: The implementation doesn't follow the correct Anthropic API pattern for agentic tool use. According to the official docs:

1. **Tool inputs are streamed as partial JSON** via `input_json_delta` events
2. **The `stop_reason` field indicates when the model wants to use tools** - when `stop_reason == "tool_use"`, you must execute tools and continue the conversation
3. **This requires a loop** that continues until `stop_reason != "tool_use"`

Our implementation only does ONE iteration of this loop - it executes tools from the first response but doesn't check `stop_reason` and doesn't continue the loop for follow-up tool calls.

## Anthropic Streaming API Reference (from official docs)

### Event Flow
1. `message_start`: contains a `Message` object with empty `content`
2. A series of content blocks, each with:
   - `content_block_start`
   - One or more `content_block_delta` events
   - `content_block_stop` event
3. `message_delta` events (includes **`stop_reason`**)
4. `message_stop` event

### Tool Use Streaming Format

When the model wants to use a tool, you get:

```json
event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01T1x1fJ34qAmk2tNTrN7Up6","name":"get_weather","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"location\":"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":" \"San"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":" Francisco, CA\"}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use","stop_sequence":null},"usage":{"output_tokens":89}}

event: message_stop
data: {"type":"message_stop"}
```

**Key Points:**
- Tool inputs come as `input_json_delta` events with `partial_json` strings
- You accumulate these strings and parse JSON at `content_block_stop`
- **The SDK's `get_final_message()` handles this accumulation automatically**
- **`stop_reason: "tool_use"` tells you to execute tools and continue**

### Correct Agentic Loop Pattern

Per the docs, when `stop_reason == "tool_use"`:
1. Execute the tool(s)
2. Send a new request with tool results
3. Get next response
4. **Repeat until `stop_reason != "tool_use"`**

## Detailed Findings

### Issue 1: Missing Agentic Loop

**Current Implementation (WRONG):**

```python
# chat.py - current structure (simplified)
async with client.messages.stream(...) as stream:
    async for event in stream:
        yield format_event(event)
    final_message = await stream.get_final_message()

# Execute tools from first response
tool_results = []
for block in final_message.content:
    if block.type == "tool_use":
        result = await execute_tool(...)
        tool_results.append(...)

# Send ONE follow-up with tool results
if tool_results:
    async with client.messages.stream(...) as follow_stream:
        async for event in follow_stream:
            yield format_event(event)
        # ❌ NO get_final_message() called!
        # ❌ NO tool execution!
        # ❌ NO check for stop_reason!

yield done_event()
```

**Problems:**
1. Follow-up stream doesn't call `get_final_message()`
2. Follow-up stream doesn't execute tool_use blocks
3. No check for `stop_reason` to know if more tools are needed
4. Not a proper loop - only handles 2 turns max

### Issue 2: Tool Input Not Captured for Follow-up Tools

**Evidence from SSE Trace:**
```
data: {"event": "tool_start", "data": {"tool_id": "toolu_01Ez5VfgWBfqyGtTguah9W8q", "tool_name": "update_cell"}}
data: {"event": "content_block_stop", "data": {}}
data: {"event": "done", "data": {}}  <-- Stream ends, no tool_input shown!
```

The `update_cell` tool_start event appears but:
- We never emit the `input_json_delta` data to the client (minor, since SDK accumulates)
- We never call `get_final_message()` to get the accumulated input
- We never execute the tool

### Issue 3: UI Shows Tool Calls at Bottom (Not Inline)

**Frontend Structure (`ChatPanel.tsx`):**
The current message structure appends tool calls to a `toolCalls` array, rendered after text:

```tsx
<p className="whitespace-pre-wrap">{msg.content}</p>
{msg.toolCalls && msg.toolCalls.length > 0 && (
  <div className="mt-2 space-y-1">
    {msg.toolCalls.map((tool, i) => (...))}
  </div>
)}
```

**Fix (lower priority):** Use content blocks model for inline display.

### Issue 4: Tool Schemas and Execution Are Correct

The tool schemas in `llm_tools.py` and the `execute_tool()` dispatcher are correctly implemented. When tools ARE executed, they:
- Use proper async locks
- Broadcast WebSocket updates
- Save to storage

The frontend correctly handles WebSocket `cell_updated` messages.

**The tools work fine - they just aren't being called in follow-up turns.**

## Code References

- `backend/chat.py:136-184` - First stream tool execution (partially correct)
- `backend/chat.py:186-268` - Follow-up stream handling (MISSING tool execution)
- `backend/llm_tools.py:290-378` - Tool schemas (correct)
- `backend/llm_tools.py:381-429` - Tool dispatcher (correct)

## Recommended Fix: True Agentic Loop

Refactor `chat.py` to use a proper loop that checks `stop_reason`:

```python
async def event_generator():
    """Generate SSE events for chat stream with agentic tool loop."""
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Build initial messages
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]
    
    MAX_TOOL_TURNS = 10  # Prevent infinite loops
    turn_count = 0
    
    while turn_count < MAX_TOOL_TURNS:
        turn_count += 1
        
        # Stream from Anthropic
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=messages,
            tools=TOOL_SCHEMAS,
            system=system_prompt
        ) as stream:
            # Stream events to client
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
                    # Note: input_json_delta handled by SDK's get_final_message()
                
                elif event.type == "content_block_stop":
                    yield sse_event("content_block_stop", {})
            
            # Get final message with accumulated tool inputs
            final_message = await stream.get_final_message()
        
        # Check stop_reason - KEY PART!
        if final_message.stop_reason != "tool_use":
            # No more tools, we're done
            break
        
        # Execute all tools from this turn
        tool_results = []
        for block in final_message.content:
            if block.type == "tool_use":
                yield sse_event("tool_execute", {
                    "tool_name": block.name,
                    "tool_input": block.input
                })
                
                log_llm_action(notebook_id, user_id, f"tool_{block.name}", block.input)
                
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
        
        # Add assistant message and tool results for next turn
        messages.append({"role": "assistant", "content": final_message.content})
        messages.append({"role": "user", "content": tool_results})
    
    # Done
    yield sse_event("done", {})
```

**Key Changes:**
1. **Loop until `stop_reason != "tool_use"`** - per Anthropic docs
2. **Always call `get_final_message()`** - to get accumulated tool inputs
3. **Execute tools every turn** - not just the first
4. **Append to messages array** - build conversation history correctly
5. **Max turn limit** - prevent infinite loops

## Testing Checklist

- [ ] Send message that triggers `get_notebook_state` → executes correctly
- [ ] After `get_notebook_state`, LLM uses `update_cell` → ALSO executes
- [ ] Verify `stop_reason` is checked after each stream
- [ ] Multi-tool chains work (e.g., get_state → create_cell → run_cell)
- [ ] Max turn limit prevents infinite loops
- [ ] WebSocket broadcasts reach frontend for all tool executions
- [ ] UI shows all tool calls (even if not inline yet)

## Open Questions

1. Should we stream `input_json_delta` to the client for real-time tool input display?
2. What's the right max turn limit? (10 seems reasonable)
3. How to surface "continuing..." indicator to user during multi-turn execution?
4. Should inline tool display be part of this fix or a separate PR?
