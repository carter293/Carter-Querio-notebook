import * as api from '../api';

interface NotebookSelectorProps {
  notebooks: api.NotebookMetadata[];
  selectedNotebookId: string | null;
  onSelectNotebook: (notebookId: string) => void;
  onCreateNew: () => void;
  loading?: boolean;
}

export function NotebookSelector({
  notebooks,
  selectedNotebookId,
  onSelectNotebook,
  onCreateNew,
  loading = false
}: NotebookSelectorProps) {
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
      {loading && (
        <span style={{ fontSize: '12px', color: '#6b7280' }}>
          Loading...
        </span>
      )}
    </div>
  );
}

