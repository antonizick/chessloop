import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { librariesApi, type LichessImportResult } from "@/api/libraries";
import { linesApi } from "@/api/lines";

export function LibraryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [renamingLineId, setRenamingLineId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [lichessResult, setLichessResult] = useState<LichessImportResult | null>(null);
  const [editingLibrary, setEditingLibrary] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", eco_code: "", description: "" });
  const [selectedLines, setSelectedLines] = useState<Set<string>>(new Set());
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);

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

  const bulkDeleteLines = useMutation({
    mutationFn: async (lineIds: string[]) => {
      await Promise.all(lineIds.map((lineId) => linesApi.remove(lineId)));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lines", id] });
      setSelectedLines(new Set());
      setBulkDeleteConfirm(false);
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

  const importFromLichess = useMutation({
    mutationFn: () => librariesApi.importFromLichess(id!),
    onSuccess: (data) => {
      setLichessResult(data);
      qc.invalidateQueries({ queryKey: ["lines", id] });
    },
  });

  const updateLibrary = useMutation({
    mutationFn: (form: { name?: string; eco_code?: string; description?: string }) =>
      librariesApi.update(id!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["library", id] });
      qc.invalidateQueries({ queryKey: ["libraries"] });
      setEditingLibrary(false);
    },
  });

  if (!lib) return <p className="text-ink-300">Loading…</p>;

  const startEdit = () => {
    setEditForm({
      name: lib.name,
      eco_code: lib.eco_code ?? "",
      description: lib.description ?? "",
    });
    setEditingLibrary(true);
  };

  const toggleLineSelection = (lineId: string) => {
    const newSelected = new Set(selectedLines);
    if (newSelected.has(lineId)) {
      newSelected.delete(lineId);
    } else {
      newSelected.add(lineId);
    }
    setSelectedLines(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedLines.size === lines?.length) {
      setSelectedLines(new Set());
    } else {
      setSelectedLines(new Set(lines?.map((l) => l.id) ?? []));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <Link to="/libraries" className="text-sm text-ink-300">← All libraries</Link>

        {editingLibrary ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateLibrary.mutate({
                name: editForm.name.trim() || undefined,
                eco_code: editForm.eco_code.trim() || undefined,
                description: editForm.description.trim() || undefined,
              });
            }}
            className="mt-3 card p-4 flex flex-col gap-3"
          >
            <div>
              <label className="label text-sm">Name</label>
              <input
                className="input text-sm"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                autoFocus
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label text-sm">ECO code</label>
                <input
                  className="input text-sm"
                  value={editForm.eco_code}
                  onChange={(e) => setEditForm({ ...editForm, eco_code: e.target.value })}
                  placeholder="e.g. B90"
                />
              </div>
              <div>
                <label className="label text-sm">Color</label>
                <select className="input text-sm bg-ink-700 text-ink-100" disabled>
                  <option>{lib.color}</option>
                </select>
              </div>
            </div>
            <div>
              <label className="label text-sm">Description</label>
              <textarea
                className="input text-sm"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                className="btn-ghost text-sm py-1 px-2"
                onClick={() => setEditingLibrary(false)}
                disabled={updateLibrary.isPending}
              >
                Cancel
              </button>
              <button className="btn-primary text-sm py-1 px-2" disabled={updateLibrary.isPending}>
                {updateLibrary.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        ) : (
          <>
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

            <div className="flex items-center gap-2">
              <p className="text-ink-300 text-sm">
                {lib.color} · {lib.eco_code ?? "no ECO"} · {lib.difficulty ?? "—"}
              </p>
              <button
                onClick={startEdit}
                className="btn-ghost text-xs py-1 px-2"
                title="Edit library details"
              >
                ✎
              </button>
            </div>
          </>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 flex-wrap">
        <Link to={`/libraries/${id}/unrated`} className="btn-primary">Unrated Learning</Link>
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
        {lib.eco_code && !lib.is_public && (
          <button
            className="btn-ghost"
            onClick={() => { setLichessResult(null); importFromLichess.mutate(); }}
            disabled={importFromLichess.isPending}
            title={`Import all ${lib.eco_code} variations from Lichess`}
          >
            {importFromLichess.isPending ? "…" : "↓ Lichess"}
          </button>
        )}
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

      {lichessResult && (
        <div className="text-xs text-ink-300 bg-ink-800 border border-ink-700 rounded px-3 py-2 flex flex-col gap-0.5">
          <p>✓ <span className="text-gold-400">{lichessResult.imported}</span> lines imported · <span className="text-ink-400">{lichessResult.skipped}</span> skipped from <span className="font-mono text-gold-500">{lichessResult.eco_code}</span></p>
          {lichessResult.errors.length > 0 && (
            <ul className="mt-1 text-red-400 list-disc list-inside">
              {lichessResult.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* Lines list */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h2>Lines</h2>
            {selectedLines.size > 0 && (
              <span className="text-xs text-ink-400">({selectedLines.size} selected)</span>
            )}
          </div>
          {lines && lines.length > 0 && (
            <button
              className="text-xs btn-ghost py-1 px-2"
              onClick={toggleSelectAll}
              title={selectedLines.size === lines.length ? "Deselect all" : "Select all"}
            >
              {selectedLines.size === lines.length ? "Deselect all" : "Select all"}
            </button>
          )}
        </div>

        {lines?.length === 0 && <p className="text-ink-300 text-sm">No lines yet.</p>}

        {selectedLines.size > 0 && (
          <div className="mb-3 p-3 bg-red-900/20 border border-red-700 rounded flex items-center justify-between">
            <span className="text-sm text-red-300">
              {selectedLines.size} line{selectedLines.size === 1 ? "" : "s"} selected for deletion
            </span>
            {bulkDeleteConfirm ? (
              <div className="flex gap-2">
                <button
                  className="btn-ghost text-xs py-1 px-2"
                  onClick={() => setBulkDeleteConfirm(false)}
                  disabled={bulkDeleteLines.isPending}
                >
                  Cancel
                </button>
                <button
                  className="text-xs py-1 px-2 bg-red-600 hover:bg-red-700 text-red-100 rounded transition-colors"
                  onClick={() => bulkDeleteLines.mutate(Array.from(selectedLines))}
                  disabled={bulkDeleteLines.isPending}
                >
                  {bulkDeleteLines.isPending ? "Deleting…" : "Confirm delete"}
                </button>
              </div>
            ) : (
              <button
                className="text-xs py-1 px-2 bg-red-600 hover:bg-red-700 text-red-100 rounded transition-colors"
                onClick={() => setBulkDeleteConfirm(true)}
                title={`Delete ${selectedLines.size} line${selectedLines.size === 1 ? "" : "s"}`}
              >
                Delete selected
              </button>
            )}
          </div>
        )}

        {bulkDeleteConfirm && (
          <div className="mb-3 p-3 bg-red-950 border border-red-600 rounded">
            <p className="text-sm text-red-200 font-medium">
              Are you sure? You are deleting {selectedLines.size} line{selectedLines.size === 1 ? "" : "s"}. This step is permanent and cannot be undone.
            </p>
          </div>
        )}

        <ul className="flex flex-col divide-y divide-ink-700">
          {lines?.map((line) => (
            <li key={line.id} className="py-3 flex items-center gap-3">
              <input
                type="checkbox"
                checked={selectedLines.has(line.id)}
                onChange={() => toggleLineSelection(line.id)}
                className="shrink-0 w-4 h-4 cursor-pointer"
                title="Select for bulk delete"
              />

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
                  <div
                    className="flex-1 cursor-pointer"
                    onClick={() => {
                      navigate(`/libraries/${id}/teach?lineId=${line.id}`);
                    }}
                  >
                    <div className="text-ink-100 hover:text-gold-400 transition-colors">
                      {line.name ?? "Untitled line"}
                    </div>
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
