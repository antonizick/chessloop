import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { linesApi } from "@/api/lines";

export function LibraryDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [renamingLineId, setRenamingLineId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const { data: lib } = useQuery({
    queryKey: ["library", id],
    queryFn: () => librariesApi.get(id!),
    enabled: !!id,
  });

  const { data: lines } = useQuery({
    queryKey: ["lines", id],
    queryFn: () => linesApi.listForLibrary(id!),
    enabled: !!id,
  });

  const toggleActive = useMutation({
    mutationFn: (is_active: boolean) => librariesApi.setActive(id!, is_active),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library", id] });
      qc.invalidateQueries({ queryKey: ["libraries"] });
      qc.invalidateQueries({ queryKey: ["due-count"] });
    },
  });

  const createLine = useMutation({
    mutationFn: () => linesApi.create(id!, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lines", id] }),
  });

  const renameLine = useMutation({
    mutationFn: ({ lineId, newName }: { lineId: string; newName: string }) =>
      linesApi.update(lineId, { name: newName }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lines", id] });
      setRenamingLineId(null);
      setRenameValue("");
    },
  });

  const removeLine = useMutation({
    mutationFn: (lineId: string) => linesApi.remove(lineId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lines", id] });
      setDeleteConfirmId(null);
    },
  });

  const publishLib = useMutation({
    mutationFn: () => librariesApi.publish(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library", id] });
      qc.invalidateQueries({ queryKey: ["libraries"] });
    },
  });

  const exportPgn = useMutation({
    mutationFn: async () => {
      const blob = await librariesApi.exportPgn(id!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${lib?.name.replace(/\s+/g, "_")}.pgn`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  });

  if (!lib) return <p className="text-ink-300">Loading…</p>;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <Link to="/libraries" className="text-sm text-ink-300">← All libraries</Link>
        <div className="flex items-center justify-between mt-1">
          <h1>{lib.name}</h1>

          {/* Active toggle */}
          <div className="flex items-center gap-2">
            <span
              className={[
                "text-sm font-medium",
                lib.is_active ? "text-green-400" : "text-ink-500",
              ].join(" ")}
            >
              {lib.is_active ? "Active in practice" : "Inactive (excluded from practice)"}
            </span>
            <button
              onClick={() => toggleActive.mutate(!lib.is_active)}
              disabled={toggleActive.isPending}
              title={lib.is_active ? "Click to exclude from practice" : "Click to include in practice"}
              className={[
                "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-150",
                lib.is_active
                  ? "bg-green-500 border-green-500"
                  : "bg-ink-600 border-ink-600",
                toggleActive.isPending ? "opacity-50" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform duration-150",
                  lib.is_active ? "translate-x-5" : "translate-x-0",
                ].join(" ")}
              />
            </button>
          </div>
        </div>

        <p className="text-ink-300 text-sm mt-1">
          {lib.color} · {lib.eco_code ?? "no ECO"} · {lib.difficulty ?? "—"}
        </p>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 flex-wrap">
        <Link to={`/libraries/${id}/teach`} className="btn-primary">Teaching board</Link>
        <button className="btn-ghost" onClick={() => createLine.mutate()}>
          + Add line
        </button>
        <button
          className="btn-ghost"
          onClick={() => exportPgn.mutate()}
          disabled={exportPgn.isPending || !lines?.length}
          title={!lines?.length ? "Add lines to export" : "Export all lines as PGN"}
        >
          {exportPgn.isPending ? "…" : "↓ PGN"}
        </button>
        {!lib.is_public && (
          <button
            className="btn-ghost"
            onClick={() => publishLib.mutate()}
            disabled={publishLib.isPending}
            title="Publish to Public Opening Libraries"
          >
            {publishLib.isPending ? "…" : "📢 Publish"}
          </button>
        )}
        {lib.is_public && (
          <span className="text-sm text-gold-400 flex items-center">
            ✓ Published to Public Opening Libraries
          </span>
        )}
      </div>

      {/* Lines list */}
      <div className="card">
        <h2 className="mb-3">Lines</h2>
        {lines?.length === 0 && <p className="text-ink-300 text-sm">No lines yet.</p>}
        <ul className="flex flex-col divide-y divide-ink-700">
          {lines?.map((line) => (
            <li key={line.id} className="py-3 flex items-center justify-between gap-3">
              {renamingLineId === line.id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (renameValue.trim()) {
                      renameLine.mutate({ lineId: line.id, newName: renameValue.trim() });
                    }
                  }}
                  className="flex-1 flex items-center gap-1"
                >
                  <input
                    autoFocus
                    className="input text-sm py-1 flex-1"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                  />
                  <button
                    type="submit"
                    className="btn-primary text-xs py-1 px-2"
                    disabled={renameLine.isPending}
                  >
                    {renameLine.isPending ? "…" : "Save"}
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1 px-2"
                    onClick={() => {
                      setRenamingLineId(null);
                      setRenameValue("");
                    }}
                  >
                    ✕
                  </button>
                </form>
              ) : (
                <>
                  <div className="flex-1 cursor-pointer" onClick={() => {
                    setRenamingLineId(line.id);
                    setRenameValue(line.name ?? "");
                  }}>
                    <div className="text-ink-100 hover:text-gold-400 transition-colors">{line.name ?? "Untitled line"}</div>
                    <div className="text-xs text-ink-400">{line.moves.length} moves</div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      className="btn-ghost text-xs py-1 px-2"
                      onClick={() => {
                        setRenamingLineId(line.id);
                        setRenameValue(line.name ?? "");
                      }}
                      title="Rename"
                    >
                      ✎
                    </button>
                    {deleteConfirmId === line.id ? (
                      <>
                        <button
                          className="btn-ghost text-xs py-1 px-2 text-red-400 hover:bg-red-600/20"
                          onClick={() => removeLine.mutate(line.id)}
                          disabled={removeLine.isPending}
                        >
                          {removeLine.isPending ? "…" : "Confirm"}
                        </button>
                        <button
                          className="btn-ghost text-xs py-1 px-2"
                          onClick={() => setDeleteConfirmId(null)}
                          disabled={removeLine.isPending}
                        >
                          ✕
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn-ghost text-xs py-1 px-2 text-red-400 hover:text-red-300"
                        onClick={() => setDeleteConfirmId(line.id)}
                        title="Delete"
                      >
                        🗑
                      </button>
                    )}
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
