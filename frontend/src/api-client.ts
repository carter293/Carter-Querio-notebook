// API client wrapper using generated OpenAPI client
import {
  listNotebooksEndpointApiV1NotebooksGet,
  createNotebookApiV1NotebooksPost,
  getNotebookApiV1NotebooksNotebookIdGet,
  updateDbConnectionApiV1NotebooksNotebookIdDbPut,
  renameNotebookApiV1NotebooksNotebookIdNamePut,
  deleteNotebookEndpointApiV1NotebooksNotebookIdDelete,
  createCellApiV1NotebooksNotebookIdCellsPost,
  updateCellApiV1NotebooksNotebookIdCellsCellIdPut,
  deleteCellApiV1NotebooksNotebookIdCellsCellIdDelete,
} from './client';
import { client } from './client/client.gen';

// Configure API base URL from environment variable
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// WebSocket URL derived from API base URL
export const WS_BASE_URL = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// Initialize client without auth (will be configured per-request)
client.setConfig({
  baseUrl: API_BASE_URL,
});

// Import and re-export types from generated client
import type {
  CellResponse,
  NotebookResponse,
  ListNotebooksResponse,
  NotebookMetadataResponse,
  OutputResponse,
} from './client';

// Define types from inline unions
export type CellType = 'python' | 'sql';
export type CellStatus = 'idle' | 'running' | 'success' | 'error' | 'blocked';

// Re-export with convenient aliases
export type Cell = CellResponse;
export type Notebook = NotebookResponse;
export type NotebookMetadata = NotebookMetadataResponse;
export type Output = OutputResponse;

// Re-export TableData from generated client (now properly typed in OpenAPI spec)
export type { TableData } from './client';

// Helper to handle errors consistently
async function handleApiError(response: Response, operation: string): Promise<void> {
  let errorMessage = response.statusText || 'Unknown error';
  
  try {
    const errorData = await response.json();
    if (errorData.detail) {
      errorMessage = errorData.detail;
    } else if (typeof errorData === 'string') {
      errorMessage = errorData;
    } else if (errorData.message) {
      errorMessage = errorData.message;
    }
  } catch {
    // If JSON parsing fails, use status text
    errorMessage = response.statusText || `HTTP ${response.status}`;
  }
  
  throw new Error(`Failed to ${operation}: ${errorMessage}`);
}

// Notebook operations
export async function createNotebook(): Promise<{ notebook_id: string }> {
  const result = await createNotebookApiV1NotebooksPost();
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'create notebook');
  }
  
  return result.data as { notebook_id: string };
}

export async function getNotebook(id: string): Promise<Notebook> {
  const result = await getNotebookApiV1NotebooksNotebookIdGet({
    path: { notebook_id: id },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'get notebook');
  }
  
  return result.data as Notebook;
}

export async function listNotebooks(): Promise<NotebookMetadataResponse[]> {
  const result = await listNotebooksEndpointApiV1NotebooksGet();
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'list notebooks');
  }
  
  // Response is now properly typed as ListNotebooksResponse
  const data = result.data as ListNotebooksResponse;
  return data.notebooks;
}

export async function updateDbConnection(id: string, connString: string): Promise<void> {
  const result = await updateDbConnectionApiV1NotebooksNotebookIdDbPut({
    path: { notebook_id: id },
    body: { connection_string: connString },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'update DB connection');
  }
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const result = await renameNotebookApiV1NotebooksNotebookIdNamePut({
    path: { notebook_id: notebookId },
    body: { name },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'rename notebook');
  }
}

export async function deleteNotebook(notebookId: string): Promise<void> {
  const result = await deleteNotebookEndpointApiV1NotebooksNotebookIdDelete({
    path: { notebook_id: notebookId },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'delete notebook');
  }
}

// Cell operations
export async function createCell(
  notebookId: string, 
  type: 'python' | 'sql', 
  afterCellId?: string
): Promise<{ cell_id: string }> {
  const result = await createCellApiV1NotebooksNotebookIdCellsPost({
    path: { notebook_id: notebookId },
    body: { 
      type,
      after_cell_id: afterCellId 
    },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'create cell');
  }
  
  return result.data as { cell_id: string };
}

export async function updateCell(notebookId: string, cellId: string, code: string): Promise<void> {
  const result = await updateCellApiV1NotebooksNotebookIdCellsCellIdPut({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
    body: { code },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'update cell');
  }
}

export async function deleteCell(notebookId: string, cellId: string): Promise<void> {
  const result = await deleteCellApiV1NotebooksNotebookIdCellsCellIdDelete({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'delete cell');
  }
}

