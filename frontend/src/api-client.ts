// API client wrapper using generated OpenAPI client
import {
  listNotebooksEndpointApiNotebooksGet,
  createNotebookApiNotebooksPost,
  getNotebookApiNotebooksNotebookIdGet,
  updateDbConnectionApiNotebooksNotebookIdDbPut,
  renameNotebookApiNotebooksNotebookIdNamePut,
  deleteNotebookEndpointApiNotebooksNotebookIdDelete,
  createCellApiNotebooksNotebookIdCellsPost,
  updateCellApiNotebooksNotebookIdCellsCellIdPut,
  deleteCellApiNotebooksNotebookIdCellsCellIdDelete,
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

// ============================================================================
// Authentication Interceptor Setup
// ============================================================================

// Track interceptor ID to prevent duplicate registration in React Strict Mode
let requestInterceptorId: number | null = null;
let responseInterceptorId: number | null = null;

/**
 * Setup authentication interceptor that automatically injects Clerk token
 * into every request. Safe to call multiple times (idempotent).
 * 
 * @param getToken - Clerk's getToken function from useAuth()
 * @returns Cleanup function to remove interceptors
 */
export function setupAuthInterceptor(getToken: () => Promise<string | null>): () => void {
  // Prevent duplicate registration in React Strict Mode
  if (requestInterceptorId !== null) {
    console.warn('Auth interceptor already registered, skipping duplicate setup');
    return () => {}; // Return no-op cleanup
  }

  // Register request interceptor - injects token into Authorization header
  requestInterceptorId = client.interceptors.request.use(async (request, _options) => {
    try {
      // Call getToken() on EVERY request - Clerk caches and auto-refreshes
      const token = await getToken();
      
      if (token) {
        request.headers.set('Authorization', `Bearer ${token}`);
      } else {
        // Token not available yet (Clerk still loading or user not authenticated)
        console.warn('No auth token available for request:', request.url);
      }
    } catch (error) {
      console.error('Failed to get auth token:', error);
      // Continue with request even if token fetch fails - backend will return 401
    }
    
    return request;
  });

  // Register response interceptor - handle 401 with retry
  responseInterceptorId = client.interceptors.response.use(async (response, request, _options) => {
    // If 401, token may have expired - try once more with fresh token
    if (response.status === 401) {
      console.warn('Request failed with 401, attempting retry with fresh token');
      
      try {
        const token = await getToken();
        
        if (token) {
          // Clone request with new token
          const newRequest = request.clone();
          newRequest.headers.set('Authorization', `Bearer ${token}`);
          
          // Retry request with fresh token
          const retryResponse = await fetch(newRequest);
          return retryResponse;
        } else {
          console.error('No token available for retry, user may need to re-authenticate');
        }
      } catch (error) {
        console.error('Failed to retry request with fresh token:', error);
      }
    }
    
    return response;
  });

  // Return cleanup function
  return () => {
    if (requestInterceptorId !== null) {
      client.interceptors.request.eject(requestInterceptorId);
      requestInterceptorId = null;
    }
    if (responseInterceptorId !== null) {
      client.interceptors.response.eject(responseInterceptorId);
      responseInterceptorId = null;
    }
  };
}

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
  const result = await createNotebookApiNotebooksPost();
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'create notebook');
  }
  
  return result.data as { notebook_id: string };
}

export async function getNotebook(id: string): Promise<Notebook> {
  const result = await getNotebookApiNotebooksNotebookIdGet({
    path: { notebook_id: id },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'get notebook');
  }
  
  return result.data as Notebook;
}

export async function listNotebooks(): Promise<NotebookMetadataResponse[]> {
  const result = await listNotebooksEndpointApiNotebooksGet();
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'list notebooks');
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
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'update DB connection');
  }
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const result = await renameNotebookApiNotebooksNotebookIdNamePut({
    path: { notebook_id: notebookId },
    body: { name },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'rename notebook');
  }
}

export async function deleteNotebook(notebookId: string): Promise<void> {
  const result = await deleteNotebookEndpointApiNotebooksNotebookIdDelete({
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
  const result = await createCellApiNotebooksNotebookIdCellsPost({
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
  const result = await updateCellApiNotebooksNotebookIdCellsCellIdPut({
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
  const result = await deleteCellApiNotebooksNotebookIdCellsCellIdDelete({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
  });
  
  if (!result.response.ok) {
    await handleApiError(result.response, 'delete cell');
  }
}

