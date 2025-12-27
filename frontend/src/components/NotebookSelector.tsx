import { useState } from 'react';
import * as api from '../api';

interface NotebookSelectorProps {
  notebooks: api.NotebookMetadata[];
  selectedNotebookId: string | null;
  onSelectNotebook: (notebookId: string) => void;
  onCreateNew: () => void;
  onRenameNotebook: (notebookId: string, newName: string) => void;
  loading?: boolean;
}

export function NotebookSelector({
  notebooks,
  selectedNotebookId,
  onSelectNotebook,
  onCreateNew,
  onRenameNotebook,
  loading = false
}: NotebookSelectorProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState('');

  const selectedNotebook = notebooks.find(nb => nb.id === selectedNotebookId);
  const canRename = selectedNotebookId !== null && !loading;

  const handleStartRename = () => {
    if (selectedNotebook) {
      setRenameValue(selectedNotebook.name);
      setIsRenaming(true);
    }
  };

  const handleSaveRename = () => {
    if (selectedNotebookId && renameValue.trim()) {
      onRenameNotebook(selectedNotebookId, renameValue.trim());
      setIsRenaming(false);
      setRenameValue('');
    }
  };

  const handleCancelRename = () => {
    setIsRenaming(false);
    setRenameValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveRename();
    } else if (e.key === 'Escape') {
      handleCancelRename();
    }
  };

  return (
    <div style={{
      display: 'flex',
      gap: '8px',
      alignItems: 'center',
      marginBottom: '24px',
      padding: '12px',
      backgroundColor: '#f9fafb',
      borderRadius: '8px'
    }}>
      <label style={{
        fontSize: '14px',
        fontWeight: 500,
        whiteSpace: 'nowrap'
      }}>
        Notebook:
      </label>
      {isRenaming ? (
        <>
          <input
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
            style={{
              flex: 1,
              padding: '8px 12px',
              border: '1px solid #3b82f6',
              borderRadius: '4px',
              fontSize: '14px',
              backgroundColor: 'white'
            }}
          />
          <button
            onClick={handleSaveRename}
            disabled={!renameValue.trim()}
            style={{
              padding: '8px 16px',
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: renameValue.trim() ? 'pointer' : 'not-allowed',
              opacity: renameValue.trim() ? 1 : 0.5
            }}
          >
            Save
          </button>
          <button
            onClick={handleCancelRename}
            style={{
              padding: '8px 16px',
              backgroundColor: '#6b7280',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <select
            value={selectedNotebookId || ''}
            onChange={(e) => {
              if (e.target.value === '__create_new__') {
                onCreateNew();
              } else {
                onSelectNotebook(e.target.value);
              }
            }}
            disabled={loading}
            style={{
              flex: 1,
              padding: '8px 12px',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              fontSize: '14px',
              backgroundColor: loading ? '#f3f4f6' : 'white',
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            {notebooks.map(nb => (
              <option key={nb.id} value={nb.id}>
                {nb.name}
              </option>
            ))}
            <option value="__create_new__" style={{ fontStyle: 'italic' }}>
              + Create New Notebook
            </option>
          </select>
          {canRename && (
            <button
              onClick={handleStartRename}
              title="Rename notebook"
              style={{
                padding: '8px 12px',
                backgroundColor: '#f3f4f6',
                color: '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '14px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              Rename
            </button>
          )}
          {loading && (
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Loading...
            </span>
          )}
        </>
      )}
    </div>
  );
}

