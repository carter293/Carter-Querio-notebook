import React, { useState, useEffect } from 'react';
import { Notebook } from './components/Notebook';
import { NotebookSelector } from './components/NotebookSelector';
import * as api from './api';

export default function App() {
  const [notebooks, setNotebooks] = useState<api.NotebookMetadata[]>([]);
  const [notebookId, setNotebookId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load notebook list on mount
  useEffect(() => {
    api.listNotebooks()
      .then(notebookList => {
        setNotebooks(notebookList);
        
        // Default behavior: select first notebook if available, otherwise create new
        if (notebookList.length > 0) {
          setNotebookId(notebookList[0].id);
        } else {
          // No notebooks exist, create a new one
          api.createNotebook()
            .then(({ notebook_id }) => {
              setNotebookId(notebook_id);
              // Refresh list to include new notebook
              return api.listNotebooks();
            })
            .then(notebookList => {
              setNotebooks(notebookList);
            })
            .catch(err => {
              setError('Failed to create notebook: ' + err.message);
            });
        }
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load notebooks: ' + err.message);
        setLoading(false);
      });
  }, []);

  const handleSelectNotebook = (selectedId: string) => {
    setNotebookId(selectedId);
    // Note: WebSocket will reconnect automatically via useWebSocket hook
    // when notebookId changes (see Notebook.tsx)
  };

  const handleCreateNew = async () => {
    try {
      setLoading(true);
      const { notebook_id } = await api.createNotebook();
      setNotebookId(notebook_id);
      // Refresh notebook list
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
      setLoading(false);
    } catch (err: any) {
      setError('Failed to create notebook: ' + err.message);
      setLoading(false);
    }
  };

  if (error) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: '#991b1b'
      }}>
        Error: {error}
      </div>
    );
  }

  if (loading && !notebookId) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center'
      }}>
        Loading notebooks...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '24px' }}>
      <NotebookSelector
        notebooks={notebooks}
        selectedNotebookId={notebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNew={handleCreateNew}
        loading={loading}
      />
      {notebookId && <Notebook notebookId={notebookId} />}
    </div>
  );
}
