import { useState, useRef, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { NotebookCell } from "./NotebookCell";
import { KeyboardShortcutsDialog } from "./KeyboardShortcutsDialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Plus, Keyboard, FileText, Pencil, Trash2 } from "lucide-react";
import * as api from "../api-client";
import { WSMessage, useNotebookWebSocket } from "../useNotebookWebSocket";
import type { Cell, CellType, CellStatus, NotebookMetadata } from "../api-client";

export type { CellType, CellStatus };

export interface CellData extends Cell {
  // Extend Cell type from API with any additional frontend-only fields if needed
}

export function NotebookApp() {
  const { notebookId: urlNotebookId } = useParams<{ notebookId?: string }>();
  const navigate = useNavigate();

  const [cells, setCells] = useState<CellData[]>([]);
  const [focusedCellId, setFocusedCellId] = useState<string | null>(null);
  const [dbConnection, setDbConnection] = useState("");
  const [showKeyboardShortcuts, setShowKeyboardShortcuts] = useState(false);
  const cellRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [notebookId, setNotebookId] = useState<string | null>(null);
  const [notebooks, setNotebooks] = useState<NotebookMetadata[]>([]);
  const [renamingNotebookId, setRenamingNotebookId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [notebookSelectOpen, setNotebookSelectOpen] = useState(false);
  const [isRenamingCurrent, setIsRenamingCurrent] = useState(false);
  const [currentNotebookRenameValue, setCurrentNotebookRenameValue] = useState("");
  const [isInitialized, setIsInitialized] = useState(false);
  const createdCellsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (isInitialized) return;

    // Load notebook list on mount
    async function loadNotebooks() {
      try {
        const notebooks = await api.listNotebooks();
        setNotebooks(notebooks);

        // If we have a notebook ID from URL, verify it exists
        if (urlNotebookId) {
          const notebookExists = notebooks.some(nb => nb.id === urlNotebookId);
          if (notebookExists) {
            setNotebookId(urlNotebookId);
          } else if (notebooks.length > 0) {
            setNotebookId(notebooks[0].id);
          }
        } else if (notebooks.length > 0) {
          setNotebookId(notebooks[0].id);
        } else {
          // Create a new notebook if none exist
          const response = await api.createNotebook();
          setNotebookId(response.notebook_id);
          // Reload notebooks list to include the newly created one
          const updatedNotebooks = await api.listNotebooks();
          setNotebooks(updatedNotebooks);
        }

        setIsInitialized(true);
      } catch (err) {
        console.error("Failed to load notebooks:", err);
      }
    }

    loadNotebooks();
  }, [isInitialized, urlNotebookId]);

  useEffect(() => {
    // Load notebook cells when notebookId changes
    if (notebookId) {
      api.getNotebook(notebookId).then(notebook => {
        setCells(notebook.cells || []);
        setDbConnection(notebook.db_conn_string || "");
      });
    }
  }, [notebookId]);

  // Update URL when notebookId changes
  useEffect(() => {
    if (notebookId && notebookId !== urlNotebookId) {
      navigate(`/notebook/${notebookId}`, { replace: true });
    }
  }, [notebookId, urlNotebookId, navigate]);
  
  const handleWebSocketMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case "cell_updated":
        setCells((prev) =>
          prev.map((c) =>
            c.id === msg.cellId
              ? { ...c, code: msg.cell.code, reads: msg.cell.reads, writes: msg.cell.writes }
              : c
          )
        );
        break;
      case "cell_created":
        setCells((prev) => {
          // Use ref inside the updater to prevent duplicate additions
          // This handles React Strict Mode calling the updater twice
          if (createdCellsRef.current.has(msg.cell.id)) {
            return prev;
          }

          // Also check if cell already exists in state
          if (prev.some(c => c.id === msg.cell.id)) {
            createdCellsRef.current.add(msg.cell.id);
            return prev;
          }

          createdCellsRef.current.add(msg.cell.id);

          const newCells = [...prev];
          // Insert at the specified index, or append if index not provided
          if (typeof msg.index === 'number') {
            newCells.splice(msg.index, 0, msg.cell);
          } else {
            newCells.push(msg.cell);
          }
          return newCells;
        });
        break;
      case "cell_deleted":
        setCells((prev) => prev.filter((c) => c.id !== msg.cellId));
        break;
      case "cell_status":
        setCells((prev) =>
          prev.map((c) => {
            if (c.id !== msg.cellId) return c;
            if (msg.status === 'running') {
              // Clear outputs and stdout when execution starts
              return { ...c, status: msg.status, outputs: [], stdout: "", error: undefined };
            }
            return { ...c, status: msg.status };
          })
        );
        break;
      case "cell_stdout":
        setCells((prev) =>
          prev.map((c) =>
            c.id === msg.cellId
              ? { ...c, stdout: (c.stdout || "") + msg.data }
              : c
          )
        );
        break;
      case "cell_output":
        setCells((prev) =>
          prev.map((c) =>
            c.id === msg.cellId ? { ...c, outputs: [...(c.outputs || []), msg.output] } : c
          )
        );
        break;
      case "cell_error":
        setCells((prev) =>
          prev.map((c) =>
            c.id === msg.cellId
              ? {
                  ...c,
                  status: "error" as CellStatus,
                  outputs: [
                    ...(c.outputs || []),
                    { mime_type: "text/plain", data: msg.error },
                  ],
                }
              : c
          )
        );
        break;
      case "db_connection_updated":
        if (msg.status === 'error') {
          console.error("Failed to update DB connection:", msg.error);
          // Optionally: show toast notification
        } else {
          console.log("DB connection updated successfully");
          // Optionally: show success toast
        }
        break;
      case "kernel_error":
        console.error("Kernel error:", msg.error);
        alert(`Kernel crashed: ${msg.error}\n\nPlease refresh the page.`);
        break;
    }
  }, []); // Empty deps - uses functional setState to avoid needing cells in deps

  // Connect WebSocket
  const { sendMessage } = useNotebookWebSocket(
    { notebookId, onMessage: handleWebSocketMessage }
  );

  const addCell = async (type: CellType, afterCellId?: string) => {
    if (!notebookId) return;

    // Send cell creation via WebSocket
    sendMessage({
      type: 'create_cell',
      cellType: type,
      afterCellId: afterCellId
    });
  };

  const deleteCell = async (id: string) => {
    if (!notebookId) return;

    if (cells.length <= 1) {
      await updateCellCode(id, "");
      return;
    }

    // Send cell deletion via WebSocket
    sendMessage({
      type: 'delete_cell',
      cellId: id
    });

    if (focusedCellId === id) {
      const index = cells.findIndex((c) => c.id === id);
      const nextCell = cells[index + 1] || cells[index - 1];
      setFocusedCellId(nextCell?.id || null);
    }
  };

  const updateCellCode = async (id: string, code: string) => {
    if (!notebookId) return;
    
    // Send cell update via WebSocket
    sendMessage({ 
        type: 'cell_update', 
        cellId: id, 
        code: code 
    });
  };

  const runCell = (id: string) => {
    sendMessage({ type: 'run_cell', cellId: id });
  };

  const focusCell = useCallback((direction: "up" | "down") => {
    if (!focusedCellId) {
      setFocusedCellId(cells[0]?.id || null);
      return;
    }

    const currentIndex = cells.findIndex((c) => c.id === focusedCellId);
    if (currentIndex === -1) return;

    const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
    if (nextIndex >= 0 && nextIndex < cells.length) {
      const nextId = cells[nextIndex].id;
      setFocusedCellId(nextId);
      cellRefs.current.get(nextId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focusedCellId, cells]);

  const handleDbConnectionUpdate = async () => {
    if (!notebookId) return;
    
    sendMessage({ 
        type: 'update_db_connection', 
        connectionString: dbConnection 
    });
  };

  const handleCreateNotebook = async () => {
    try {
      const { notebook_id } = await api.createNotebook();
      const updatedNotebooks = await api.listNotebooks();
      setNotebooks(updatedNotebooks);
      setNotebookId(notebook_id);
    } catch (err) {
      console.error("Failed to create notebook:", err);
    }
  };

  const handleRenameNotebook = async (id: string, name: string, keepSelectOpen = true) => {
    if (!name.trim()) return;

    try {
      await api.renameNotebook(id, name);
      const updatedNotebooks = await api.listNotebooks();
      setNotebooks(updatedNotebooks);
      setRenamingNotebookId(null);
      setRenameValue("");
      if (keepSelectOpen) {
        setNotebookSelectOpen(true);
      }
    } catch (err) {
      console.error("Failed to rename notebook:", err);
    }
  };

  const handleDeleteNotebook = async (id: string) => {
    if (!confirm("Are you sure you want to delete this notebook?")) {
      return;
    }

    try {
      await api.deleteNotebook(id);

      // Refresh notebook list
      const updatedNotebooks = await api.listNotebooks();
      setNotebooks(updatedNotebooks);

      // If deleted notebook was selected, switch to another
      if (notebookId === id) {
        if (updatedNotebooks.length > 0) {
          setNotebookId(updatedNotebooks[0].id);
        } else {
          setNotebookId(null);
          setCells([]);
        }
      }

      setNotebookSelectOpen(false);
    } catch (err) {
      console.error("Failed to delete notebook:", err);
      alert(`Failed to delete notebook: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if the event comes from inside a Monaco editor
      // Monaco editors handle their own keybindings
      const target = e.target as HTMLElement;
      if (target.closest('.monaco-editor')) {
        return;
      }

      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modKey = isMac ? e.metaKey : e.ctrlKey;

      // Cmd/Ctrl + Shift + Up/Down - Navigate cells
      if (modKey && e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        e.preventDefault();
        focusCell(e.key === "ArrowUp" ? "up" : "down");
      }

      // Cmd/Ctrl + K - Toggle keyboard shortcuts
      if (modKey && e.key === "k") {
        e.preventDefault();
        setShowKeyboardShortcuts((prev) => !prev);
      }

    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [focusedCellId, cells]);

  return (
    <div className="flex h-screen bg-background text-foreground dark">
      {/* Left: Notebook Area */}
      <div className={`flex flex-col transition-all duration-300 w-full`}>
        {/* Header */}
        <header className="flex items-center justify-between gap-2 border-b border-border bg-card px-3 py-2 lg:px-6 lg:py-3">
          {/* Left side */}
          <div className="flex items-center gap-2 lg:gap-4 min-w-0 flex-1">
            {/* Title - hidden on small screens, shown on medium+ */}
            <h1 className="hidden md:block font-mono text-lg lg:text-xl font-semibold whitespace-nowrap">
              Reactive Notebook
            </h1>

            {/* Notebook Selector */}
            <div className="flex items-center gap-1 lg:gap-2 min-w-0 flex-1 md:flex-initial">
              {isRenamingCurrent ? (
                <Pencil className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <div
                  className="group/icon cursor-pointer"
                  onClick={() => {
                    if (notebookId) {
                      const currentNotebook = notebooks.find(nb => nb.id === notebookId);
                      setCurrentNotebookRenameValue(currentNotebook?.name || notebookId);
                      setIsRenamingCurrent(true);
                    }
                  }}
                >
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0 group-hover/icon:hidden" />
                  <Pencil className="h-4 w-4 text-muted-foreground shrink-0 hidden group-hover/icon:block" />
                </div>
              )}

              {isRenamingCurrent ? (
                <Input
                  value={currentNotebookRenameValue}
                  onChange={(e) => setCurrentNotebookRenameValue(e.target.value)}
                  onBlur={async () => {
                    if (currentNotebookRenameValue.trim() && notebookId) {
                      await handleRenameNotebook(notebookId, currentNotebookRenameValue, false);
                    }
                    setIsRenamingCurrent(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && notebookId) {
                      handleRenameNotebook(notebookId, currentNotebookRenameValue, false);
                      setIsRenamingCurrent(false);
                    } else if (e.key === "Escape") {
                      setIsRenamingCurrent(false);
                    }
                  }}
                  autoFocus
                  className="h-10 w-full md:w-[200px] lg:w-[250px]"
                />
              ) : (
                <Select
                  value={notebookId || ""}
                  open={notebookSelectOpen}
                  onOpenChange={(open: boolean) => {
                    // Don't close if we're in rename mode
                    if (!open && renamingNotebookId !== null) {
                      return;
                    }
                    setNotebookSelectOpen(open);
                  }}
                  onValueChange={(value: string) => {
                    if (value === "__create_new__") {
                      handleCreateNotebook();
                    } else if (value) {
                      setNotebookId(value);
                    }
                  }}
                >
                  <SelectTrigger className="w-full md:w-[200px] lg:w-[250px]">
                    <SelectValue placeholder="Choose a notebook" />
                  </SelectTrigger>
                  <SelectContent>
                    {notebooks.map((nb) => (
                      <div key={nb.id} className="relative group">
                        {renamingNotebookId === nb.id ? (
                          <div className="flex items-center gap-1 px-2 py-1.5">
                            <Input
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  handleRenameNotebook(nb.id, renameValue);
                                } else if (e.key === "Escape") {
                                  setRenamingNotebookId(null);
                                  setRenameValue("");
                                }
                              }}
                              onBlur={() => {
                                if (renameValue.trim()) {
                                  handleRenameNotebook(nb.id, renameValue);
                                } else {
                                  setRenamingNotebookId(null);
                                  setRenameValue("");
                                }
                              }}
                              autoFocus
                              className="h-7 text-sm"
                              onClick={(e) => e.stopPropagation()}
                            />
                          </div>
                        ) : (
                          <div className="flex items-center justify-between pr-2">
                            <SelectItem value={nb.id} className="flex-1">
                              {nb.name || nb.id}
                            </SelectItem>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteNotebook(nb.id);
                              }}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        )}
                      </div>
                    ))}
                    <SelectItem value="__create_new__" className="text-primary">
                      + Create New Notebook
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Keyboard shortcuts button */}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setShowKeyboardShortcuts(true)}
              title="Keyboard shortcuts (⌘K)"
              className="hidden lg:flex shrink-0"
            >
              <Keyboard className="h-4 w-4" />
            </Button>
          </div>

          {/* Right side - DB Connection */}
          <div className="flex items-center gap-1 lg:gap-2 shrink-0">
            <Input
              placeholder="PostgreSQL connection string..."
              value={dbConnection}
              onChange={(e) => setDbConnection(e.target.value)}
              onBlur={handleDbConnectionUpdate}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.currentTarget.blur();
                }
              }}
              className="w-32 sm:w-40 md:w-48 lg:w-56 xl:w-64 2xl:w-80"
            />
          </div>
        </header>

        {/* Notebook Cells */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="mx-auto max-w-5xl space-y-4">
            {cells.map((cell) => (
              <div key={cell.id} ref={el => {
                el && cellRefs.current.set(cell.id, el);
              }}>
                <NotebookCell
                  cell={cell}
                  onUpdateCode={(code) => updateCellCode(cell.id, code)}
                  onRun={() => runCell(cell.id)}
                  onDelete={() => deleteCell(cell.id)}
                  isFocused={focusedCellId === cell.id}
                  onFocus={() => setFocusedCellId(cell.id)}
                  onFocusPreviousCell={() => focusCell("up")}
                  onFocusNextCell={() => focusCell("down")}
                  onToggleKeyboardShortcuts={() => setShowKeyboardShortcuts((prev) => !prev)}
                />

                {/* Add Cell Buttons */}
                <div className="flex justify-center gap-2 py-2 transition-opacity">
                  <Button variant="ghost" size="sm" onClick={() => addCell("python", cell.id)} className="h-7 text-xs">
                    <Plus className="mr-1 h-3 w-3" />
                    Python
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => addCell("sql", cell.id)} className="h-7 text-xs">
                    <Plus className="mr-1 h-3 w-3" />
                    SQL
                  </Button>
                </div>
              </div>
            ))}

            {cells.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
                <p className="mb-4">No cells yet. Add your first cell:</p>
                <div className="flex gap-2">
                  <Button onClick={() => addCell("python")}>
                    <Plus className="mr-2 h-4 w-4" />
                    Python Cell
                  </Button>
                  <Button onClick={() => addCell("sql")} variant="outline">
                    <Plus className="mr-2 h-4 w-4" />
                    SQL Cell
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {/* Keyboard Shortcuts Dialog */}
      <KeyboardShortcutsDialog open={showKeyboardShortcuts} onOpenChange={setShowKeyboardShortcuts} />
    </div>
  );
}
