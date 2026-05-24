import { useState } from "react";
import type { Line } from "@/types";

interface Props {
  lines: Line[];
  selectedId: string | null;
  onSelect: (lineId: string) => void;
  onCreateNew: (name: string) => void;
  isCreating: boolean;
}

export function LineSelector({ lines, selectedId, onSelect, onCreateNew, isCreating }: Props) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    onCreateNew(newName.trim());
    setNewName("");
    setCreating(false);
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Existing lines */}
      {lines.map((line) => (
        <button
          key={line.id}
          className={`rounded px-3 py-1.5 text-sm font-medium transition-colors
            ${selectedId === line.id
              ? "bg-gold-500 text-ink-900"
              : "bg-ink-700 text-ink-200 hover:bg-ink-600"
            }`}
          onClick={() => onSelect(line.id)}
        >
          {line.name ?? "Untitled"}
          <span className="ml-1.5 text-xs opacity-60">({line.moves.length})</span>
        </button>
      ))}

      {/* New line form */}
      {creating ? (
        <form onSubmit={handleCreate} className="flex items-center gap-1">
          <input
            autoFocus
            className="input text-sm py-1 w-36"
            placeholder="Line name…"
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
