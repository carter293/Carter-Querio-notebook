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

router = APIRouter()

# Maximum number of tool turns to prevent infinite loops
MAX_TOOL_TURNS = 10


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/chat/{notebook_id}")
async def chat_with_notebook(
    notebook_id: str,
    request: ChatRequest,
    user_id: str = Depends(get_current_user_dependency)
):
    """
    Stream LLM chat responses with tool execution.
    Uses Server-Sent Events for streaming.
    """
    notebook = NOTEBOOKS.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    
    if notebook.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    def sse_event(event_type: str, data: dict) -> dict:
        """Helper to format SSE events consistently."""
        return {
            "data": json.dumps({
                "event": event_type,
                "data": data
            })
        }
    
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
- When creating data analysis code, use pandas for data manipulation
- For visualizations, use matplotlib (static charts), plotly (interactive charts), or altair (declarative charts)
- CRITICAL: Return the figure/chart object as the last line (e.g., `fig` not `fig.show()`)
- Do NOT call .show() methods - they will fail in this server environment
- For matplotlib, use `plt.gcf()` as the last expression to display the current figure
- For SQL cells, use {{variable}} syntax to reference Python variables
- Be concise and helpful
- If a cell fails, read the error and suggest fixes

Supported output types:
- Matplotlib figures (rendered as PNG images)
- Plotly figures (rendered as interactive charts)
- Altair charts (rendered as Vega-Lite visualizations)
- Pandas DataFrames (rendered as tables)
- Plain text and print() statements

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
                
                # Emit turn start event (useful for debugging/UX)
                if turn_count > 1:
                    yield sse_event("turn_start", {
                        "turn": turn_count,
                        "max_turns": MAX_TOOL_TURNS
                    })
                
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

