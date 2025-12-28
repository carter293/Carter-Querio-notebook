// API client wrapper using generated OpenAPI client
import {
  listNotebooksEndpointApiNotebooksGet,
  createNotebookApiNotebooksPost,
  getNotebookApiNotebooksNotebookIdGet,
  updateDbConnectionApiNotebooksNotebookIdDbPut,
  renameNotebookApiNotebooksNotebookIdNamePut,
  createCellApiNotebooksNotebookIdCellsPost,
  updateCellApiNotebooksNotebookIdCellsCellIdPut,
  deleteCellApiNotebooksNotebookIdCellsCellIdDelete,
} from './client';
import { client } from './client/client.gen';

// Configure API base URL from environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
client.setConfig({
  baseUrl: API_BASE_URL,
});

// WebSocket URL derived from API base URL
export const WS_BASE_URL = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// Import and re-export types from generated client
import type {
  CellType,
  CellStatus,
  CellResponse,
  NotebookResponse,
  ListNotebooksResponse,
  NotebookMetadataResponse,
  OutputResponse,
} from './client';

// Re-export with convenient aliases
export type { CellType, CellStatus };
export type Cell = CellResponse;
export type Notebook = NotebookResponse;
export type NotebookMetadata = NotebookMetadataResponse;
export type Output = OutputResponse;

// Re-export TableData from generated client (now properly typed in OpenAPI spec)
export type { TableData } from './client';

// Helper to handle errors consistently
function handleApiError(response: Response, operation: string): never {
  throw new Error(`Failed to ${operation}: ${response.statusText}`);
}

// Notebook operations
export async function createNotebook(): Promise<{ notebook_id: string }> {
  const result = await createNotebookApiNotebooksPost();
  
  if (result.error) {
    throw new Error(`Failed to create notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'create notebook');
  }
  
  return result.data as { notebook_id: string };
}

export async function getNotebook(id: string): Promise<Notebook> {
  const result = await getNotebookApiNotebooksNotebookIdGet({
    path: { notebook_id: id },
  });
  
  if (result.error) {
    throw new Error(`Failed to get notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'get notebook');
  }
  
  return result.data as Notebook;
}

export async function listNotebooks(): Promise<NotebookMetadataResponse[]> {
  const result = await listNotebooksEndpointApiNotebooksGet();
  
  if (result.error) {
    throw new Error(`Failed to list notebooks: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'list notebooks');
  }
  
  // Response is now properly typed as ListNotebooksResponse
  const data = result.data as ListNotebooksResponse;
  return data.notebooks;
}

export async function updateDbConnection(id: string, connString: string): Promise<void> {
  const result = await updateDbConnectionApiNotebooksNotebookIdDbPut({
    path: { notebook_id: id },
    body: { connection_string: connString },
  });
  
  if (result.error) {
    throw new Error(`Failed to update DB connection: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'update DB connection');
  }
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const result = await renameNotebookApiNotebooksNotebookIdNamePut({
    path: { notebook_id: notebookId },
    body: { name },
  });
  
  if (result.error) {
    throw new Error(`Failed to rename notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'rename notebook');
  }
}

// Cell operations
export async function createCell(notebookId: string, type: 'python' | 'sql'): Promise<{ cell_id: string }> {
  const result = await createCellApiNotebooksNotebookIdCellsPost({
    path: { notebook_id: notebookId },
    body: { type },
  });
  
  if (result.error) {
    throw new Error(`Failed to create cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'create cell');
  }
  
  return result.data as { cell_id: string };
}

export async function updateCell(notebookId: string, cellId: string, code: string): Promise<void> {
  const result = await updateCellApiNotebooksNotebookIdCellsCellIdPut({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
    body: { code },
  });
  
  if (result.error) {
    throw new Error(`Failed to update cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'update cell');
  }
}

export async function deleteCell(notebookId: string, cellId: string): Promise<void> {
  const result = await deleteCellApiNotebooksNotebookIdCellsCellIdDelete({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
  });
  
  if (result.error) {
    throw new Error(`Failed to delete cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'delete cell');
  }
}

