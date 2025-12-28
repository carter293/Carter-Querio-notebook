import { useState } from 'react';
import * as api from '../api-client';

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
    <div className="card-section-sm flex-row-center">
      <label className="text-label whitespace-nowrap">
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
            className="flex-full input-field-active"
          />
          <button
            onClick={handleSaveRename}
            disabled={!renameValue.trim()}
            className="btn-primary"
          >
            Save
          </button>
          <button
            onClick={handleCancelRename}
            className="btn-secondary"
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
            className="flex-full select-field"
          >
            {notebooks.map(nb => (
              <option key={nb.id} value={nb.id}>
                {nb.name}
              </option>
            ))}
            <option value="__create_new__" className="italic">
              + Create New Notebook
            </option>
          </select>
          {canRename && (
            <button
              onClick={handleStartRename}
              title="Rename notebook"
              className="btn-icon"
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
            <span className="text-helper">
              Loading...
            </span>
          )}
        </>
      )}
    </div>
  );
}

