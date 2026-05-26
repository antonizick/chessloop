import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { librariesApi } from "@/api/libraries";

/** Toggle switch — reused inline for the active/inactive state. */
function ActiveToggle({
  isActive,
  onChange,
  disabled,
}: {
  isActive: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      title={isActive ? "Active — click to deactivate" : "Inactive — click to activate"}
      className={[
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-150",
        isActive
          ? "bg-green-500 border-green-500"
          : "bg-ink-600 border-ink-600",
        disabled ? "opacity-50 cursor-not-allowed" : "",
      ].join(" ")}
    >
      <span
        className={[
          "inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform duration-150",
          isActive ? "translate-x-4" : "translate-x-0",
        ].join(" ")}
      />
    </button>
  );
}

export function Libraries() {
  const qc = useQueryClient();
  const { data: libraries, isLoading } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const [renameModal, setRenameModal] = useState<{
    id: string;
    currentName: string;
  } | null>(null);
  const [newName, setNewName] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      librariesApi.setActive(id, is_active),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["libraries"] });
      // Bust due-count cache so badge refreshes immediately
      qc.invalidateQueries({ queryKey: ["due-count"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => librariesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["libraries"] }),
  });

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      librariesApi.update(id, { name }),
    onSuccess: () => {
      setRenameModal(null);
      setNewName("");
      setRenameError(null);
      qc.invalidateQueries({ queryKey: ["libraries"] });
    },
    onError: (err: any) => {
      setRenameError(
        err.message || "Failed to rename library. This name may already exist."
      );
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1>My Opening Libraries</h1>
        <Link to="/libraries/new" className="btn-primary">+ New library</Link>
      </div>

      <p className="text-sm text-ink-400">
        Only <span className="text-green-400 font-medium">active</span> libraries
        are included in practice sessions. Toggle the switch on each card to
        include or exclude it.
      </p>

      {isLoading && <p className="text-ink-300">Loading…</p>}

      {libraries?.length === 0 && (
        <div className="card text-center text-ink-300">
          No libraries yet. Create your first to start teaching the system an opening.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {libraries?.map((lib) => (
          <div
            key={lib.id}
            className={[
              "card flex flex-col gap-3 transition-colors",
              lib.is_active ? "border-green-500/30" : "border-ink-700",
            ].join(" ")}
          >
            {/* Header row */}
            <div className="flex items-start justify-between gap-2">
              <Link
                to={`/libraries/${lib.id}`}
                className="text-lg font-semibold text-gold-400 hover:text-gold-300 leading-tight"
              >
                {lib.name}
              </Link>

              {/* Active toggle */}
              <div className="flex items-center gap-2 shrink-0 mt-0.5">
                <span
                  className={[
                    "text-xs font-medium",
                    lib.is_active ? "text-green-400" : "text-ink-500",
                  ].join(" ")}
                >
                  {lib.is_active ? "Active" : "Inactive"}
                </span>
                <ActiveToggle
                  isActive={lib.is_active}
                  onChange={() =>
                    toggleActive.mutate({ id: lib.id, is_active: !lib.is_active })
                  }
                  disabled={toggleActive.isPending}
                />
              </div>
            </div>

            {/* Meta pills */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="px-2 py-0.5 rounded bg-ink-700 text-ink-200 capitalize">
                {lib.color}
              </span>
              {lib.eco_code && (
                <span className="px-2 py-0.5 rounded bg-ink-700 text-ink-200">
                  ECO {lib.eco_code}
                </span>
              )}
              {lib.difficulty && (
                <span className="px-2 py-0.5 rounded bg-ink-700 text-ink-200 capitalize">
                  {lib.difficulty}
                </span>
              )}
              {lib.is_public && (
                <span className="px-2 py-0.5 rounded bg-ink-700 text-ink-200">public</span>
              )}
            </div>

            {lib.description && (
              <p className="text-sm text-ink-300">{lib.description}</p>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-1 border-t border-ink-700">
              <Link to={`/libraries/${lib.id}/teach`} className="btn-ghost text-xs">
                ✎ Teach
              </Link>
              <Link to={`/libraries/${lib.id}`} className="btn-ghost text-xs">
                Lines
              </Link>
              <button
                className="btn-ghost text-xs text-ink-300 hover:text-ink-100"
                onClick={() => {
                  setRenameModal({ id: lib.id, currentName: lib.name });
                  setNewName(lib.name);
                  setRenameError(null);
                }}
              >
                Rename
              </button>
              <button
                className="btn-ghost text-xs text-red-400 ml-auto"
                onClick={() => {
                  if (
                    confirm(`Delete library "${lib.name}"? This removes all its lines.`)
                  ) {
                    remove.mutate(lib.id);
                  }
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Rename modal */}
      {renameModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-ink-800 rounded-lg p-6 w-full max-w-sm mx-4 border border-ink-700">
            <h2 className="text-lg font-semibold mb-4">Rename library</h2>
            <div className="mb-4">
              <label className="block text-sm text-ink-300 mb-2">
                New name
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newName.trim() && newName !== renameModal.currentName) {
                    rename.mutate({ id: renameModal.id, name: newName });
                  }
                }}
                placeholder="Library name"
                className="input w-full"
                autoFocus
              />
              {renameError && (
                <p className="text-sm text-red-400 mt-2">{renameError}</p>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setRenameModal(null)}
                className="btn-ghost"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (newName.trim() && newName !== renameModal.currentName) {
                    rename.mutate({ id: renameModal.id, name: newName });
                  }
                }}
                disabled={rename.isPending || !newName.trim() || newName === renameModal.currentName}
                className="btn-primary"
              >
                {rename.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
