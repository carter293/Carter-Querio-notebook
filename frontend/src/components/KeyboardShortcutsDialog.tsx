import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Badge } from "./ui/badge";

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsDialogProps) {
  const isMac = typeof navigator !== "undefined" && navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  const modKey = isMac ? "⌘" : "Ctrl";

  const shortcuts = [
    { keys: [modKey, "Enter"], description: "Run current cell" },
    { keys: [modKey, "Shift", "↑"], description: "Focus previous cell" },
    { keys: [modKey, "Shift", "↓"], description: "Focus next cell" },
    { keys: [modKey, "K"], description: "Show keyboard shortcuts" },
    { keys: [modKey, "B"], description: "Toggle chat panel" },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>Keyboard Shortcuts</span>
          </DialogTitle>
          <DialogDescription>
            View and use keyboard shortcuts to navigate the notebook faster
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-4">
          {shortcuts.map((shortcut, index) => (
            <div
              key={index}
              className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-4 py-3"
            >
              <span className="text-sm">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, i) => (
                  <Badge key={i} variant="outline" className="font-mono text-xs px-2 py-1">
                    {key}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
          <p>
            Press{" "}
            <Badge variant="outline" className="mx-1 font-mono">
              {modKey}
            </Badge>{" "}
            +
            <Badge variant="outline" className="mx-1 font-mono">
              K
            </Badge>{" "}
            anytime to view this menu
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
