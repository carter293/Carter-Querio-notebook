import { useState, useEffect } from 'react';
import { Routes, Route, useParams, useNavigate, Navigate } from 'react-router-dom';
import { Notebook } from './components/Notebook';
import { NotebookSelector } from './components/NotebookSelector';
import * as api from './api';

function NotebookView() {
  const { notebookId: notebookIdFromUrl } = useParams<{ notebookId: string }>();
  const navigate = useNavigate();
  const [notebooks, setNotebooks] = useState<api.NotebookMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Determine the effective notebook ID (from URL or default to 'demo')
  const effectiveNotebookId = notebookIdFromUrl || 'demo';

  // Load notebook list on mount
  useEffect(() => {
    api.listNotebooks()
      .then(notebookList => {
        setNotebooks(notebookList);
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load notebooks: ' + err.message);
        setLoading(false);
      });
  }, []);

  const handleSelectNotebook = (selectedId: string) => {
    navigate(`/${selectedId}`);
    // Note: WebSocket will reconnect automatically via useWebSocket hook
    // when notebookId changes (see Notebook.tsx)
  };

  const handleCreateNew = async () => {
    try {
      setLoading(true);
      const { notebook_id } = await api.createNotebook();
      navigate(`/${notebook_id}`);
      // Refresh notebook list
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
      setLoading(false);
    } catch (err: any) {
      setError('Failed to create notebook: ' + err.message);
      setLoading(false);
    }
  };

  const handleRenameNotebook = async (notebookId: string, newName: string) => {
    try {
      await api.renameNotebook(notebookId, newName);
      // Refresh notebook list to get updated names
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
    } catch (err: any) {
      setError('Failed to rename notebook: ' + err.message);
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

  if (loading && !effectiveNotebookId) {
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
        selectedNotebookId={effectiveNotebookId}
        onSelectNotebook={handleSelectNotebook}
        onCreateNew={handleCreateNew}
        onRenameNotebook={handleRenameNotebook}
        loading={loading}
      />
      {effectiveNotebookId && <Notebook notebookId={effectiveNotebookId} />}
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/demo" replace />} />
      <Route path="/:notebookId" element={<NotebookView />} />
    </Routes>
  );
}
