import { useState, useEffect, useCallback } from 'react';
import { Cell } from './Cell';
import { useWebSocket, WSMessage } from '../useWebSocket';
import * as api from '../api-client';

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
      
      switch (msg.type) {
        case 'cell_updated':
          // Update cell metadata (code, reads, writes, status)
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId
                ? { 
                    ...cell, 
                    code: msg.cell.code,
                    reads: msg.cell.reads,
                    writes: msg.cell.writes,
                    status: msg.cell.status as api.CellStatus
                  }
                : cell
            )
          };
        
        case 'cell_created':
          // Append new cell to end
          return { ...prev, cells: [...prev.cells, msg.cell] };
        
        case 'cell_deleted':
          return {
            ...prev,
            cells: prev.cells.filter(c => c.id !== msg.cellId)
          };
        
        // Existing execution handlers...
        case 'cell_status':
          const cells = prev.cells.map(cell => {
            if (cell.id !== msg.cellId) return cell;
            if (msg.status === 'running') {
              // Clear outputs when execution starts
              return { ...cell, status: msg.status, stdout: '', outputs: [], error: undefined };
            }
            return { ...cell, status: msg.status };
          });
          return { ...prev, cells };

        case 'cell_stdout':
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId ? { ...cell, stdout: msg.data } : cell
            )
          };

        case 'cell_error':
          return {
            ...prev,
            cells: prev.cells.map(cell =>
              cell.id === msg.cellId ? { ...cell, error: msg.error } : cell
            )
          };

        case 'cell_output':
          return {
            ...prev,
            cells: prev.cells.map(cell => {
              if (cell.id !== msg.cellId) return cell;
              const outputs = cell.outputs || [];
              return { ...cell, outputs: [...outputs, msg.output] };
            })
          };

        default:
          return prev;
      }
    });
  }, []);

  const { sendMessage, connected } = useWebSocket(notebookId, handleWSMessage);

  // Re-fetch notebook on reconnection to ensure sync
  useEffect(() => {
    if (connected && notebook) {
      // Re-fetch to ensure we have latest state after reconnection
      api.getNotebook(notebookId).then(nb => {
        setNotebook(nb);
      });
    }
  }, [connected, notebookId]); // Only run when connection status changes

  const handleRunCell = (cellId: string) => {
    sendMessage({ type: 'run_cell', cellId });
  };

  const handleUpdateCell = async (cellId: string, code: string) => {
    try {
      // Send mutation - WebSocket will update state
      await api.updateCell(notebookId, cellId, code);
      // No GET request! WebSocket cell_updated message will update state
    } catch (error) {
      console.error('Failed to update cell:', error);
      alert('Failed to update cell. Please try again.');
      // State remains unchanged - WebSocket message won't arrive on error
    }
  };

  const handleDeleteCell = async (cellId: string) => {
    if (notebook && notebook.cells.length <= 1) {
      alert('Cannot delete the last cell');
      return;
    }
    
    try {
      // Send mutation - WebSocket will update state
      await api.deleteCell(notebookId, cellId);
      // No GET request! WebSocket cell_deleted message will update state
    } catch (error) {
      console.error('Failed to delete cell:', error);
      alert('Failed to delete cell. Please try again.');
      // State remains unchanged - WebSocket message won't arrive on error
    }
  };

  const handleAddCell = async (type: 'python' | 'sql') => {
    try {
      await api.createCell(notebookId, type);
      // WebSocket will send cell_created message
    } catch (error) {
      console.error('Failed to create cell:', error);
      alert('Failed to create cell. Please try again.');
      // State remains unchanged - WebSocket message won't arrive on error
    }
  };

  const handleUpdateDbConnection = async () => {
    await api.updateDbConnection(notebookId, dbConnString);
    alert('Database connection updated');
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-text-primary">
        Loading notebook...
      </div>
    );
  }

  if (!notebook) {
    return (
      <div className="p-6 text-center text-text-primary">
        Notebook not found
      </div>
    );
  }

  return (
    <div>
      {/* DB Connection */}
      <div className="card-section">
        <label className="label">
          PostgreSQL Connection String:
        </label>
        <div className="flex-row-gap">
          <input
            type="text"
            value={dbConnString}
            onChange={(e) => setDbConnString(e.target.value)}
            placeholder="postgresql://user:pass@host:5432/db"
            className="flex-full input-field"
          />
          <button
            onClick={handleUpdateDbConnection}
            className="btn-success"
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
      <div className="flex-row-gap">
        <button
          onClick={() => handleAddCell('python')}
          className="btn-primary"
        >
          + Python Cell
        </button>
        <button
          onClick={() => handleAddCell('sql')}
          className="btn-primary"
        >
          + SQL Cell
        </button>
      </div>

      {/* Instructions */}
      <div className="card-info mt-8">
        <strong>How to use:</strong>
        <ul className="mt-2 ml-5 space-y-1">
          <li>Edit code in cells and press Ctrl+Enter (or click Run) to execute</li>
          <li>Cells automatically re-run when their dependencies change</li>
          <li>Use &#123;variable&#125; syntax in SQL cells to reference Python variables</li>
          <li>Circular dependencies are detected and shown as errors</li>
        </ul>
      </div>
    </div>
  );
}
