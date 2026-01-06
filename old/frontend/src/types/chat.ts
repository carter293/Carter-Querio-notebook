/**
 * Type definitions for LLM chat and tool interactions
 * These types correspond to the backend tool schemas in backend/llm_tools.py
 */

// Tool input types - match backend tool schemas
export type GetNotebookStateInput = {
  include_outputs?: boolean;
  cell_ids?: string[];
};

export type UpdateCellInput = {
  cell_id: string;
  code: string;
};

export type CreateCellInput = {
  cell_type: 'python' | 'sql';
  code: string;
  index?: number;
};

export type RunCellInput = {
  cell_id: string;
};

export type DeleteCellInput = {
  cell_id: string;
};

// Union type for all tool inputs
export type ToolInput =
  | GetNotebookStateInput
  | UpdateCellInput
  | CreateCellInput
  | RunCellInput
  | DeleteCellInput;

// Tool result types - match backend return values
export type SuccessResult = {
  status: 'ok' | 'success';
  cell_id?: string;
  revision?: number;
  output_preview?: string;
  output_type?: string;
  stdout?: string;
};

export type ErrorResult = {
  status: 'error' | 'blocked' | 'timeout';
  error: string;
  suggestion?: string;
};

export type GetNotebookStateResult = {
  status?: never; // GetNotebookState doesn't have a status field
  cells: Array<{
    id: string;
    type: string;
    code: string;
    status: string;
    reads: string[];
    writes: string[];
    output_preview?: string;
    output_type?: string;
    has_visual?: boolean;
    output_metadata?: Record<string, unknown>;
    stdout_preview?: string;
    error?: string;
  }>;
  revision: number;
  execution_in_progress: boolean;
  current_executing_cell: string | null;
  cell_count: number;
};

// Union type for all tool results
export type ToolResult =
  | SuccessResult
  | ErrorResult
  | GetNotebookStateResult;

// Type guards for narrowing ToolResult
export function isErrorResult(result: ToolResult): result is ErrorResult {
  return 'status' in result && (result.status === 'error' || result.status === 'blocked' || result.status === 'timeout');
}

export function isSuccessResult(result: ToolResult): result is SuccessResult {
  return 'status' in result && (result.status === 'ok' || result.status === 'success');
}

export function isGetNotebookStateResult(result: ToolResult): result is GetNotebookStateResult {
  return 'cells' in result && Array.isArray(result.cells);
}

// Chat message and tool call types
export interface ToolCall {
  tool: string;
  input: ToolInput;
  result?: ToolResult;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
}

// SSE event types from backend
export type SSEEvent =
  | { event: 'text_start'; data: Record<string, never> }
  | { event: 'text_delta'; data: { text: string } }
  | { event: 'tool_start'; data: { tool_id: string; tool_name: string } }
  | { event: 'tool_execute'; data: { tool_name: string; tool_input: ToolInput } }
  | { event: 'tool_result'; data: { tool_name: string; result: ToolResult } }
  | { event: 'turn_start'; data: { turn: number; max_turns: number } }
  | { event: 'content_block_stop'; data: Record<string, never> }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { error: string } };

// Chat request payload
export interface ChatRequest {
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
}

