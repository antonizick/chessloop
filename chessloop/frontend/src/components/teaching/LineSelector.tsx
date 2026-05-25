import { useState } from "react";
import type { Line } from "@/types";

interface Props {
  lines: Line[];
  selectedId: string | null;
  onSelect: (lineId: string) => void;
  onCreateNew: (name: string | null) => void;
  onRename: (lineId: string, newName: string) => Promise<void>;
  isCreating: boolean;
}

export function LineSelector({ lines, selectedId, onSelect, onCreateNew, onRename, isCreating }: Props) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [isRenaming, setIsRenaming] = useState(false);

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const nameToUse = newName.trim() || null;
    onCreateNew(nameToUse);
    setNewName("");
    setCreating(false);
  }

  async function handleRename(e: React.FormEvent, lineId: string) {
    e.preventDefault();
    if (!renameValue.trim()) return;
    setIsRenaming(true);
    try {
      await onRename(lineId, renameValue.trim());
    } finally {
      setIsRenaming(false);
      setRenamingId(null);
      setRenameValue("");
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Existing lines */}
      {lines.map((line) => (
        <div key={line.id} className="relative group">
          {renamingId === line.id ? (
            <form onSubmit={(e) => handleRename(e, line.id)} className="flex items-center gap-1">
              <input
                autoFocus
                className="input text-sm py-1 w-40"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
              />
              <button className="btn-primary py-1 text-xs" disabled={isRenaming}>
                {isRenaming ? "…" : "Save"}
              </button>
              <button
                type="button"
                className="btn-ghost py-1 text-xs"
                onClick={() => {
                  setRenamingId(null);
                  setRenameValue("");
                }}
              >
                ✕
              </button>
            </form>
          ) : (
            <button
              className={`rounded px-3 py-1.5 text-sm font-medium transition-colors
                ${selectedId === line.id
                  ? "bg-gold-500 text-ink-900"
                  : "bg-ink-700 text-ink-200 hover:bg-ink-600"
                }`}
              onClick={() => onSelect(line.id)}
              onDoubleClick={() => {
                setRenamingId(line.id);
                setRenameValue(line.name || "");
              }}
              title="Double-click to rename"
            >
              {line.name}
              <span className="ml-1.5 text-xs opacity-60">({line.moves.length})</span>
            </button>
          )}
        </div>
      ))}

      {/* New line form */}
      {creating ? (
        <form onSubmit={handleCreate} className="flex items-center gap-1">
          <input
            autoFocus
            className="input text-sm py-1 w-36"
            placeholder="Line name (optional)…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button className="btn-primary py-1 text-xs" disabled={isCreating}>
            {isCreating ? "…" : "Add"}
          </button>
          <button type="button" className="btn-ghost py-1 text-xs" onClick={() => setCreating(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <button
          className="rounded px-3 py-1.5 text-sm bg-ink-800 border border-ink-600
                     text-ink-300 hover:border-gold-500 hover:text-gold-400 transition-colors"
          onClick={() => setCreating(true)}
        >
          + New line
        </button>
      )}
    </div>
  );
}
