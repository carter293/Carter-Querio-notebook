import React, { useState, useEffect } from 'react';
import { Notebook } from './components/Notebook';
import * as api from './api';

export default function App() {
  const [notebookId, setNotebookId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Create or load notebook on mount
    api.createNotebook()
      .then(({ notebook_id }) => {
        setNotebookId(notebook_id);
      })
      .catch(err => {
        setError('Failed to create notebook: ' + err.message);
      });
  }, []);

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

  if (!notebookId) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center'
      }}>
        Creating notebook...
      </div>
    );
  }

  return <Notebook notebookId={notebookId} />;
}
