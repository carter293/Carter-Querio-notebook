import { useState, useEffect, useCallback } from 'react';
import { Cell } from './Cell';
import { useWebSocket, WSMessage } from '../useWebSocket';
import * as api from '../api';

interface NotebookProps {
  notebookId: string;
}

export function Notebook({ notebookId }: NotebookProps) {
  const [notebook, setNotebook] = useState<api.Notebook | null>(null);
  const [dbConnString, setDbConnString] = useState('');
  const [loading, setLoading] = useState(true);

  // Load initial notebook
  useEffect(() => {
    api.getNotebook(notebookId).then(nb => {
      setNotebook(nb);
      setDbConnString(nb.db_conn_string || '');
      setLoading(false);
    });
  }, [notebookId]);

  // Handle WebSocket messages
  const handleWSMessage = useCallback((msg: WSMessage) => {
    setNotebook(prev => {
      if (!prev) return prev;

      const cells = prev.cells.map(cell => {
        if (cell.id !== msg.cellId) return cell;

        switch (msg.type) {
          case 'cell_status':
            if (msg.status === 'running') {
              // Clear outputs when execution starts (fixes double-run bug)
              return { ...cell, status: 'running', stdout: '', outputs: [], error: undefined };
            }
            return { ...cell, status: msg.status };

          case 'cell_stdout':
            return { ...cell, stdout: msg.data };

          case 'cell_error':
            return { ...cell, error: msg.error };

          case 'cell_output':
            const outputs = cell.outputs || [];
            return { ...cell, outputs: [...outputs, msg.output] };

          default:
            return cell;
        }
      });

      return { ...prev, cells };
    });
  }, []);

  const { sendMessage } = useWebSocket(notebookId, handleWSMessage);

  const handleRunCell = (cellId: string) => {
    sendMessage({ type: 'run_cell', cellId });
  };

  const handleUpdateCell = async (cellId: string, code: string) => {
    await api.updateCell(notebookId, cellId, code);
    const updated = await api.getNotebook(notebookId);
    setNotebook(updated);
  };

  const handleDeleteCell = async (cellId: string) => {
    if (notebook && notebook.cells.length <= 1) {
      alert('Cannot delete the last cell');
      return;
    }
    await api.deleteCell(notebookId, cellId);
    const updated = await api.getNotebook(notebookId);
    setNotebook(updated);
  };

  const handleAddCell = async (type: 'python' | 'sql') => {
    await api.createCell(notebookId, type);
    const updated = await api.getNotebook(notebookId);
    setNotebook(updated);
  };

  const handleUpdateDbConnection = async () => {
    await api.updateDbConnection(notebookId, dbConnString);
    alert('Database connection updated');
  };

  if (loading) {
    return <div style={{ padding: '24px', textAlign: 'center' }}>Loading notebook...</div>;
  }

  if (!notebook) {
    return <div style={{ padding: '24px', textAlign: 'center' }}>Notebook not found</div>;
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '24px' }}>
        Reactive Notebook
      </h1>

      {/* DB Connection */}
      <div style={{
        marginBottom: '24px',
        padding: '16px',
        backgroundColor: '#f9fafb',
        borderRadius: '8px'
      }}>
        <label style={{
          display: 'block',
          fontSize: '14px',
          fontWeight: 500,
          marginBottom: '8px'
        }}>
          PostgreSQL Connection String:
        </label>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={dbConnString}
            onChange={(e) => setDbConnString(e.target.value)}
            placeholder="postgresql://user:pass@host:5432/db"
            style={{
              flex: 1,
              padding: '8px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              fontSize: '14px'
            }}
          />
          <button
            onClick={handleUpdateDbConnection}
            style={{
              padding: '8px 16px',
              backgroundColor: '#059669',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
            onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#047857'}
            onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#059669'}
          >
            Update
          </button>
        </div>
      </div>

      {/* Cells */}
      {notebook.cells.map(cell => (
        <Cell
          key={cell.id}
          cell={cell}
          onRunCell={handleRunCell}
          onUpdateCell={handleUpdateCell}
          onDeleteCell={handleDeleteCell}
        />
      ))}

      {/* Add Cell Buttons */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          onClick={() => handleAddCell('python')}
          style={{
            padding: '8px 16px',
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
          onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#1d4ed8'}
          onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#2563eb'}
        >
          + Python Cell
        </button>
        <button
          onClick={() => handleAddCell('sql')}
          style={{
            padding: '8px 16px',
            backgroundColor: '#7c3aed',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
          onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#6d28d9'}
          onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#7c3aed'}
        >
          + SQL Cell
        </button>
      </div>

      {/* Instructions */}
      <div style={{
        marginTop: '32px',
        padding: '16px',
        backgroundColor: '#eff6ff',
        borderRadius: '8px',
        fontSize: '14px',
        color: '#1e40af'
      }}>
        <strong>How to use:</strong>
        <ul style={{ marginTop: '8px', marginLeft: '20px' }}>
          <li>Edit code in cells and press Ctrl+Enter (or click Run) to execute</li>
          <li>Cells automatically re-run when their dependencies change</li>
          <li>Use &#123;variable&#125; syntax in SQL cells to reference Python variables</li>
          <li>Circular dependencies are detected and shown as errors</li>
        </ul>
      </div>
    </div>
  );
}
