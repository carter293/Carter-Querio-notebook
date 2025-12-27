const API_BASE = 'http://localhost:8000/api';

// Table data structure for pandas DataFrames and SQL results
export interface TableData {
  type: 'table';
  columns: string[];
  rows: (string | number | boolean | null)[][];
  truncated?: string;
}

// Output data can be string (base64, HTML) or structured (JSON, table)
export type OutputData = string | TableData | Record<string, unknown>;

export interface Output {
  mime_type: string;
  data: OutputData;
  metadata?: Record<string, string | number | boolean>;
}

export type CellType = 'python' | 'sql';
export type CellStatus = 'idle' | 'running' | 'success' | 'error' | 'blocked';

export interface Cell {
  id: string;
  type: CellType;
  code: string;
  status: CellStatus;
  stdout?: string;
  outputs?: Output[];  // NEW: Replaces result
  error?: string;
  reads: string[];
  writes: string[];
}

export interface NotebookMetadata {
  id: string;
  name: string;
}

export interface Notebook {
  id: string;
  name?: string; 
  db_conn_string?: string;
  cells: Cell[];
}

export async function createNotebook(): Promise<{ notebook_id: string }> {
  const res = await fetch(`${API_BASE}/notebooks`, { method: 'POST' });
  return res.json();
}

export async function getNotebook(id: string): Promise<Notebook> {
  const res = await fetch(`${API_BASE}/notebooks/${id}`);
  return res.json();
}

export async function listNotebooks(): Promise<NotebookMetadata[]> {
  const res = await fetch(`${API_BASE}/notebooks`);
  if (!res.ok) {
    throw new Error(`Failed to list notebooks: ${res.statusText}`);
  }
  const data = await res.json();
  return data.notebooks;
}

export async function updateDbConnection(id: string, connString: string) {
  await fetch(`${API_BASE}/notebooks/${id}/db`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connection_string: connString })
  });
}

export async function createCell(notebookId: string, type: 'python' | 'sql') {
  const res = await fetch(`${API_BASE}/notebooks/${notebookId}/cells`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type })
  });
  return res.json();
}

export async function updateCell(notebookId: string, cellId: string, code: string) {
  await fetch(`${API_BASE}/notebooks/${notebookId}/cells/${cellId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code })
  });
}

export async function deleteCell(notebookId: string, cellId: string) {
  await fetch(`${API_BASE}/notebooks/${notebookId}/cells/${cellId}`, {
    method: 'DELETE'
  });
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/notebooks/${notebookId}/name`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  if (!res.ok) {
    throw new Error(`Failed to rename notebook: ${res.statusText}`);
  }
}
