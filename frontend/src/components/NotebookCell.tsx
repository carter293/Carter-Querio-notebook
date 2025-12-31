import { useEffect, useRef, useState } from "react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Play, Trash2, Loader2, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import type { CellData } from "./NotebookApp";
import { OutputRenderer } from "./OutputRenderer";
import Editor from "@monaco-editor/react";



interface NotebookCellProps {
  cell: CellData;
  onUpdateCode: (code: string) => void;
  onRun: () => void;
  onDelete: () => void;
  isFocused: boolean;
  onFocus: () => void;
  // Application-level keyboard shortcuts
  onFocusPreviousCell: () => void;
  onFocusNextCell: () => void;
  onToggleKeyboardShortcuts: () => void;
  onToggleChat: () => void;
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
  onToggleChat
}: NotebookCellProps) {
  const [localCode, setLocalCode] = useState(cell.code);
  const editorRef = useRef<any>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setLocalCode(cell.code);
  }, [cell.code]);

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setLocalCode(value);

      // Debounce server updates to prevent spam
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      if (value !== cell.code) {
        debounceTimerRef.current = setTimeout(() => {
          onUpdateCode(value);
        }, 500); // 500ms debounce
      }
    }
  };

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleEditorMount = (editor: any, monaco: any) => {
    editorRef.current = editor;

    // Shift+Enter to run cell (Jupyter standard)
    editor.addCommand(monaco.KeyMod.Shift | monaco.KeyCode.Enter, () => {
      onRun();
    });
    
    // Ctrl/Cmd+Shift+Up - Focus previous cell
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.UpArrow,
      () => onFocusPreviousCell()
    );
    
    // Ctrl/Cmd+Shift+Down - Focus next cell
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.DownArrow,
      () => onFocusNextCell()
    );
    
    // Cmd/Ctrl+K - Show keyboard shortcuts
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK,
      () => onToggleKeyboardShortcuts()
    );
    
    // Cmd/Ctrl+B - Toggle chat panel
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB,
      () => onToggleChat()
    );
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
              onRun();
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
      {(cell.reads.length > 0 || cell.writes.length > 0) && (
        <div className="border-t border-border bg-card px-4 py-2 text-xs text-muted-foreground">
          {cell.reads.length > 0 && (
            <span className="mr-4">
              Reads: <code className="font-mono">{cell.reads.join(", ")}</code>
            </span>
          )}
          {cell.writes.length > 0 && (
            <span>
              Writes: <code className="font-mono">{cell.writes.join(", ")}</code>
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
