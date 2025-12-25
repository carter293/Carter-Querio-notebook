const API_BASE = 'http://localhost:8000/api';

export interface Cell {
  id: string;
  type: 'python' | 'sql';
  code: string;
  status: 'idle' | 'running' | 'success' | 'error' | 'blocked';
  stdout?: string;
  result?: any;
  error?: string;
  reads: string[];
  writes: string[];
}

export interface Notebook {
  id: string;
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

export async function updateDbConnection(id: string, connString: string) {
  await fetch(`${API_BASE}/notebooks/${id}/db`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connection_string: connString })
  });
}

export async function createCell(notebookId: string, type: 'python' | 'sql', afterCellId?: string) {
  const res = await fetch(`${API_BASE}/notebooks/${notebookId}/cells`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, after_cell_id: afterCellId })
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
