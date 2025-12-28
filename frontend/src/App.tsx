import { useState, useEffect } from 'react';
import { Routes, Route, useParams, useNavigate } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn, UserButton, useAuth } from '@clerk/clerk-react';
import { Notebook } from './components/Notebook';
import { NotebookSelector } from './components/NotebookSelector';
import { ThemeToggle } from './components/ThemeToggle';
import * as api from './api-client';
import { configureClientAuth } from './api-client';

function NotebookView() {
  const { notebookId } = useParams<{ notebookId?: string }>();  // Make optional
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const [notebooks, setNotebooks] = useState<api.NotebookMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load notebook list on mount
  useEffect(() => {
    async function loadNotebooks() {
      try {
        const token = await getToken();
        configureClientAuth(token);
        
        const notebookList = await api.listNotebooks();
        setNotebooks(notebookList);
        setLoading(false);
      } catch (err: any) {
        setError('Failed to load notebooks: ' + err.message);
        setLoading(false);
      }
    }
    loadNotebooks();
  }, [getToken]);

  const handleSelectNotebook = (selectedId: string) => {
    navigate(`/${selectedId}`);
    // Note: WebSocket will reconnect automatically via useWebSocket hook
    // when notebookId changes (see Notebook.tsx)
  };

  const handleCreateNew = async () => {
    try {
      setLoading(true);
      const token = await getToken();
      configureClientAuth(token);
      
      const { notebook_id } = await api.createNotebook();
      navigate(`/${notebook_id}`);
      
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
      const token = await getToken();
      configureClientAuth(token);
      
      await api.renameNotebook(notebookId, newName);
      
      const notebookList = await api.listNotebooks();
      setNotebooks(notebookList);
    } catch (err: any) {
      setError('Failed to rename notebook: ' + err.message);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-output flex items-center justify-center">
        <div className="p-6 text-center text-error">
          Error: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-output">
      <div className="max-w-4xl mx-auto px-6 py-6">
        <div className="flex-row-between mb-6">
          <h1 className="text-2xl font-bold text-text-primary">
            Reactive Notebook
          </h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <UserButton afterSignOutUrl="/" />
          </div>
        </div>
        
        <NotebookSelector
          notebooks={notebooks}
          selectedNotebookId={notebookId || null}  // Pass null if no notebook selected
          onSelectNotebook={handleSelectNotebook}
          onCreateNew={handleCreateNew}
          onRenameNotebook={handleRenameNotebook}
          loading={loading}
        />
        
        {/* Only render Notebook component if a notebook is selected */}
        {notebookId ? (
          <Notebook notebookId={notebookId} />
        ) : (
          // Empty state when no notebook selected
          <div className="card-section mt-6 text-center">
            <div className="text-text-secondary mb-4">
              <svg 
                className="mx-auto h-24 w-24 text-text-tertiary" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={1.5} 
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" 
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-text-primary mb-2">
              No Notebook Selected
            </h2>
            <p className="text-text-secondary mb-6">
              Choose a notebook from the dropdown above to get started, or create a new one.
            </p>
            <div className="card-info text-left">
              <strong>Available Notebooks:</strong>
              <ul className="mt-2 ml-5 space-y-1">
                <li><strong>Demo Notebook</strong> - Interactive examples with Python and SQL</li>
                <li><strong>Blank Notebook</strong> - Start fresh with an empty notebook</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Root route - no auto-redirect, show empty state */}
      <Route 
        path="/" 
        element={
          <>
            <SignedIn>
              <NotebookView />
            </SignedIn>
            <SignedOut>
              <RedirectToSignIn />
            </SignedOut>
          </>
        } 
      />
      {/* Notebook route with optional ID */}
      <Route 
        path="/:notebookId" 
        element={
          <>
            <SignedIn>
              <NotebookView />
            </SignedIn>
            <SignedOut>
              <RedirectToSignIn />
            </SignedOut>
          </>
        } 
      />
    </Routes>
  );
}
