import { useState, useRef, useEffect } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { KeyMod, KeyCode } from 'monaco-editor';
import { Cell as CellType } from '../api';

interface CellProps {
  cell: CellType;
  onRunCell: (cellId: string) => void;
  onUpdateCell: (cellId: string, code: string) => void;
  onDeleteCell: (cellId: string) => void;
}

// Modern Mac detection (navigator.platform is deprecated)
// navigator.userAgentData is not yet supported on macOS/iOS, so we use userAgent
const isMac = navigator.userAgent.includes('Mac OS X');

const statusColors = {
  idle: '#9ca3af',
  running: '#3b82f6',
  success: '#10b981',
  error: '#ef4444',
  blocked: '#f59e0b'
};

const statusIcons = {
  idle: '○',
  running: '⟳',
  success: '✓',
  error: '✗',
  blocked: '⚠'
};

export function Cell({ cell, onRunCell, onUpdateCell, onDeleteCell }: CellProps) {
  const [code, setCode] = useState(cell.code);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const codeRef = useRef(code);
  const runCellRef = useRef<() => void>();

  // Keep codeRef in sync with code state
  useEffect(() => {
    codeRef.current = code;
  }, [code]);

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setCode(value);
    }
  };

  const handleRunClick = () => {
    // Save code first if changed
    if (codeRef.current !== cell.code) {
      onUpdateCell(cell.id, codeRef.current);
    }
    // Small delay to ensure save completes
    setTimeout(() => onRunCell(cell.id), 100);
  };

  // Keep runCellRef in sync so Monaco action uses latest handler
  useEffect(() => {
    runCellRef.current = handleRunClick;
  });

  const handleEditorMount: OnMount = (editor) => {
    editorRef.current = editor;
    
    // Register Cmd/Ctrl+Enter keyboard shortcut directly with Monaco
    // This ensures it works when the editor has focus
    editor.addAction({
      id: 'run-cell',
      label: 'Run Cell',
      keybindings: [
        // KeyMod.CtrlCmd maps to Cmd on Mac, Ctrl on Windows/Linux
        KeyMod.CtrlCmd | KeyCode.Enter
      ],
      run: () => {
        runCellRef.current?.();
      }
    });

    editor.onDidBlurEditorText(() => {
      if (codeRef.current !== cell.code) {
        onUpdateCell(cell.id, codeRef.current);
      }
    });
  };

  return (
    <div style={{
      border: '1px solid #d1d5db',
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '16px',
      backgroundColor: 'white',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: '12px',
            height: '12px',
            borderRadius: '50%',
            backgroundColor: statusColors[cell.status],
            animation: cell.status === 'running' ? 'pulse 1.5s infinite' : 'none'
          }} title={cell.status} />
          <span style={{ fontSize: '14px', fontWeight: 500 }}>
            {statusIcons[cell.status]} {cell.type.toUpperCase()}
          </span>
          {cell.writes.length > 0 && (
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              writes: {cell.writes.join(', ')}
            </span>
          )}
          {cell.reads.length > 0 && (
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              reads: {cell.reads.join(', ')}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={handleRunClick}
            style={{
              padding: '6px 12px',
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
            Run ({isMac ? '⌘' : 'Ctrl'}+Enter)
          </button>
          <button
            onClick={() => onDeleteCell(cell.id)}
            style={{
              padding: '6px 12px',
              backgroundColor: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
            onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#b91c1c'}
            onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#dc2626'}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Code Editor */}
      <div style={{ border: '1px solid #d1d5db', borderRadius: '4px' }}>
        <Editor
          height="150px"
          language={cell.type === 'python' ? 'python' : 'sql'}
          value={code}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true
          }}
        />
      </div>

      {/* Output */}
      {cell.status !== 'idle' && (
        <div style={{ marginTop: '12px' }}>
          {cell.stdout && (
            <pre style={{
              backgroundColor: '#f3f4f6',
              padding: '8px',
              borderRadius: '4px',
              fontSize: '13px',
              overflow: 'auto',
              margin: '8px 0'
            }}>
              {cell.stdout}
            </pre>
          )}

          {cell.result && (
            <div style={{
              backgroundColor: '#f3f4f6',
              padding: '8px',
              borderRadius: '4px',
              fontSize: '13px',
              marginTop: '8px'
            }}>
              {cell.result.type === 'table' && (
                <div>
                  <table style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '12px'
                  }}>
                    <thead>
                      <tr style={{ backgroundColor: '#e5e7eb' }}>
                        {cell.result.columns.map((col: string) => (
                          <th key={col} style={{
                            border: '1px solid #d1d5db',
                            padding: '4px 8px',
                            textAlign: 'left'
                          }}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {cell.result.rows.map((row: any[], idx: number) => (
                        <tr key={idx}>
                          {row.map((val, i) => (
                            <td key={i} style={{
                              border: '1px solid #d1d5db',
                              padding: '4px 8px'
                            }}>{String(val)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {cell.result.truncated && (
                    <p style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                      {cell.result.truncated}
                    </p>
                  )}
                </div>
              )}
              {cell.result.type === 'empty' && (
                <p style={{ fontSize: '12px', color: '#6b7280' }}>
                  {cell.result.message}
                </p>
              )}
            </div>
          )}

          {cell.error && (
            <pre style={{
              backgroundColor: '#fef2f2',
              color: '#991b1b',
              padding: '8px',
              borderRadius: '4px',
              fontSize: '13px',
              overflow: 'auto',
              marginTop: '8px'
            }}>
              {cell.error}
            </pre>
          )}

          {cell.status === 'blocked' && !cell.error && (
            <div style={{
              backgroundColor: '#fffbeb',
              color: '#92400e',
              padding: '8px',
              borderRadius: '4px',
              fontSize: '13px',
              marginTop: '8px'
            }}>
              ⚠️ Upstream dependency failed. This cell cannot run until upstream errors are fixed.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
