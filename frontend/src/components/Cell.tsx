import { useState, useRef, useEffect } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { KeyMod, KeyCode } from 'monaco-editor';
import { Cell as CellType } from '../api-client';
import { OutputRenderer } from './OutputRenderer';
import { useTheme } from '../contexts/ThemeContext';

interface CellProps {
  cell: CellType;
  onRunCell: (cellId: string) => void;
  onUpdateCell: (cellId: string, code: string) => void;
  onDeleteCell: (cellId: string) => void;
}

// Modern Mac detection (navigator.platform is deprecated)
// navigator.userAgentData is not yet supported on macOS/iOS, so we use userAgent
const isMac = navigator.userAgent.includes('Mac OS X');


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
  const { theme } = useTheme();

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
    <div className="card-cell">
      {/* Header */}
      <div className="flex-row-between mb-2">
        <div className="flex-row-center">
          <div 
            className={`status-dot-${cell.status}`}
            title={cell.status}
          />
          <span className="text-label">
            {statusIcons[cell.status]} {cell.type.toUpperCase()}
          </span>
          {cell.writes.length > 0 && (
            <span className="text-helper">
              writes: {cell.writes.join(', ')}
            </span>
          )}
          {cell.reads.length > 0 && (
            <span className="text-helper">
              reads: {cell.reads.join(', ')}
            </span>
          )}
        </div>
        <div className="flex-row-gap">
          <button
            onClick={handleRunClick}
            className="btn-primary-sm"
          >
            Run ({isMac ? '⌘' : 'Ctrl'}+Enter)
          </button>
          <button
            onClick={() => onDeleteCell(cell.id)}
            className="btn-danger-sm"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Code Editor */}
      <div className="editor-container">
        <Editor
          height="150px"
          language={cell.type === 'python' ? 'python' : 'sql'}
          value={code}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          theme={theme === 'dark' ? 'vs-dark' : 'vs'}
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
        <div className="mt-3">
          {/* Stdout */}
          {cell.stdout && (
            <pre className="output-pre">
              {cell.stdout}
            </pre>
          )}

          {/* Rich outputs */}
          {cell.outputs && cell.outputs.map((output, idx) => (
            <div key={`${cell.id}-output-${idx}-${cell.status}`} className="output-block">
              <OutputRenderer output={output} cellId={cell.id} outputIndex={idx} />
            </div>
          ))}

          {/* Error */}
          {cell.error && (
            <pre className="output-error">
              {cell.error}
            </pre>
          )}

          {/* Blocked status */}
          {cell.status === 'blocked' && !cell.error && (
            <div className="output-warning">
              ⚠️ Upstream dependency failed.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
