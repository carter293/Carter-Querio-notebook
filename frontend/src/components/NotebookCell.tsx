import { useEffect, useRef, useState } from "react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Play, Trash2, Loader2, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import type { CellData } from "./NotebookApp";
import { OutputRenderer } from "./OutputRenderer";
import Editor, { type Monaco } from "@monaco-editor/react";
import type { editor } from "monaco-editor";

interface NotebookCellProps {
  cell: CellData;
  onUpdateCode: (code: string) => Promise<void>;
  onRun: () => void;
  onDelete: () => void;
  isFocused: boolean;
  onFocus: () => void;
  onFocusPreviousCell: () => void;
  onFocusNextCell: () => void;
  onToggleKeyboardShortcuts: () => void;
}

export function NotebookCell({ 
  cell, 
  onUpdateCode, 
  onRun, 
  onDelete, 
  isFocused, 
  onFocus,
  onFocusPreviousCell,
  onFocusNextCell,
  onToggleKeyboardShortcuts,
}: NotebookCellProps) {
  const [localCode, setLocalCode] = useState(cell.code);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const [autoSaveTimer, setAutoSaveTimer] = useState<NodeJS.Timeout | null>(null);
  const AUTO_SAVE_DELAY = 1500; // 1.5 seconds

  // Store the latest callbacks in refs to avoid stale closures
  const callbacksRef = useRef({
    onFocusPreviousCell,
    onFocusNextCell,
    onToggleKeyboardShortcuts,
    onUpdateCode,
  });

  // Update refs when callbacks change
  useEffect(() => {
    callbacksRef.current = {
      onFocusPreviousCell,
      onFocusNextCell,
      onToggleKeyboardShortcuts,
      onUpdateCode,
    };
  }, [onFocusPreviousCell, onFocusNextCell, onToggleKeyboardShortcuts, onUpdateCode]);

  // Auto-save after typing stops (no auto-run)
  useEffect(() => {
    // Clear existing timer
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer);
    }

    // Don't auto-save if code hasn't changed
    if (localCode === cell.code) {
      return;
    }

    // Set auto-save timer
    const timer = setTimeout(async () => {
      if (localCode !== cell.code) {
        await onUpdateCode(localCode);
      }
    }, AUTO_SAVE_DELAY);

    setAutoSaveTimer(timer);

    return () => {
      clearTimeout(timer);
    };
  }, [localCode, cell.code]);

  // Focus the editor when this cell becomes focused
  useEffect(() => {
    if (isFocused && editorRef.current) {
      editorRef.current.focus();
    }
  }, [isFocused]);

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setLocalCode(value);
    }
  };

  const handleEditorBlur = async () => {
    // Cancel auto-save timer if active
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer);
      setAutoSaveTimer(null);
    }

    // If there are unsaved changes, save AND run
    if (localCode !== cell.code) {
      await onUpdateCode(localCode);

      // Run the cell after saving
      onRun();
    }
  };

  const handleRun = async () => {
    // Get the current code directly from the editor to avoid stale state
    const currentCode = editorRef.current?.getValue() ?? localCode;

    // Cancel auto-save timer if active
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer);
      setAutoSaveTimer(null);
    }

    // Always send update to ensure kernel has latest code before running
    await onUpdateCode(currentCode);

    // Then run the cell
    onRun();
  };

  const handleEditorMount = (editorInstance: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    editorRef.current = editorInstance;

    // Save on blur (when user clicks away from editor)
    editorInstance.onDidBlurEditorText(() => {
      handleEditorBlur();
    });

    // Use addKeybindingRules for global keybindings (disable defaults)
    monaco.editor.addKeybindingRules([
      {
        // Disable default F1 (command palette)
        keybinding: monaco.KeyCode.F1,
        command: null,
      },
      {
        // Disable default F8 (go to next error)
        keybinding: monaco.KeyCode.F8,
        command: null,
      },
      {
        // Disable default F9 (toggle breakpoint)
        keybinding: monaco.KeyCode.F9,
        command: null,
      },
    ]);

    // Register custom actions with keybindings
    // For instance-specific actions, keybindings must be in the action definition
    // Use callbacksRef.current to always get the latest callbacks (avoid stale closures)
    editorInstance.addAction({
      id: `notebook-cell-run-${cell.id}`,
      label: 'Run Cell',
      keybindings: [
        monaco.KeyMod.Shift | monaco.KeyCode.Enter,
      ],
      run: () => {
        handleRun();
      },
    });
    
    editorInstance.addAction({
      id: `notebook-cell-focus-previous-${cell.id}`,
      label: 'Focus Previous Cell',
      keybindings: [
        monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.UpArrow,
      ],
      run: () => {
        callbacksRef.current.onFocusPreviousCell();
      },
    });
    
    editorInstance.addAction({
      id: `notebook-cell-focus-next-${cell.id}`,
      label: 'Focus Next Cell',
      keybindings: [
        monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.DownArrow,
      ],
      run: () => {
        callbacksRef.current.onFocusNextCell();
      },
    });
    
    editorInstance.addAction({
      id: `notebook-cell-show-shortcuts-${cell.id}`,
      label: 'Show Keyboard Shortcuts',
      keybindings: [
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK,
      ],
      run: () => {
        callbacksRef.current.onToggleKeyboardShortcuts();
      },
    });
  };

  const statusConfig = {
    idle: { icon: null, color: "bg-muted", label: "Idle" },
    running: { icon: Loader2, color: "bg-primary", label: "Running" },
    success: { icon: CheckCircle2, color: "bg-green-500", label: "Success" },
    error: { icon: XCircle, color: "bg-destructive", label: "Error" },
    blocked: { icon: AlertCircle, color: "bg-yellow-500", label: "Blocked" },
  };

  const status = statusConfig[cell.status as keyof typeof statusConfig] || statusConfig.idle;
  const StatusIcon = status.icon;

  return (
    <Card className={`overflow-hidden transition-all ${isFocused ? "ring-2 ring-primary" : ""}`} onClick={onFocus}>
      {/* Cell Header */}
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-xs">
            {cell.type.toUpperCase()}
          </Badge>
          <div className="flex items-center gap-1">
            <div className={`h-2 w-2 rounded-full ${status.color}`} />
            {StatusIcon && <StatusIcon className={`h-3 w-3 ${cell.status === "running" ? "animate-spin" : ""}`} />}
            <span className="text-xs text-muted-foreground">{status.label}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              handleRun();
            }}
            disabled={cell.status === "running"}
            title="Run cell (Shift+Enter)"
          >
            <Play className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Code Editor */}
      <div className="h-48 border-b border-border">
        <Editor
          height="100%"
          language={cell.type === "python" ? "python" : "sql"}
          value={localCode}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            wordWrap: "on",
          }}
        />
      </div>

      {/* Stdout Area */}
      {cell.stdout && (
        <div className="bg-muted/50 p-4 font-mono text-sm border-b border-border">
          <pre className="whitespace-pre-wrap m-0">{cell.stdout}</pre>
        </div>
      )}

      {/* Output Area */}
      {cell.outputs && cell.outputs.length > 0 && (
        <div className="bg-muted/30 p-4 space-y-2">
          {cell.outputs.map((output, idx) => (
            <OutputRenderer key={idx} output={output} cellId={cell.id} outputIndex={idx} />
          ))}
        </div>
      )}

      {/* Metadata */}
      {((cell.reads?.length ?? 0) > 0 || (cell.writes?.length ?? 0) > 0) && (
        <div className="border-t border-border bg-card px-4 py-2 text-xs text-muted-foreground">
          {(cell.reads?.length ?? 0) > 0 && (
            <span className="mr-4">
              Reads: <code className="font-mono">{cell.reads?.join(", ")}</code>
            </span>
          )}
          {(cell.writes?.length ?? 0) > 0 && (
            <span>
              Writes: <code className="font-mono">{cell.writes?.join(", ")}</code>
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
