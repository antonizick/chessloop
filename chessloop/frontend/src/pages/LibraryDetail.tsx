import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { linesApi } from "@/api/lines";

export function LibraryDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

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
    mutationFn: () => linesApi.create(id!, { name: "New line" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lines", id] }),
  });

  const removeLine = useMutation({
    mutationFn: (lineId: string) => linesApi.remove(lineId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lines", id] }),
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
      <div className="flex gap-2">
        <Link to={`/libraries/${id}/teach`} className="btn-primary">Teaching board</Link>
        <button className="btn-ghost" onClick={() => createLine.mutate()}>
          + Add line
        </button>
      </div>

      {/* Lines list */}
      <div className="card">
        <h2 className="mb-3">Lines</h2>
        {lines?.length === 0 && <p className="text-ink-300 text-sm">No lines yet.</p>}
        <ul className="flex flex-col divide-y divide-ink-700">
          {lines?.map((line) => (
            <li key={line.id} className="py-3 flex items-center justify-between">
              <div>
                <div className="text-ink-100">{line.name ?? "Untitled line"}</div>
                <div className="text-xs text-ink-400">{line.moves.length} moves</div>
              </div>
              <button
                className="btn-ghost text-xs text-red-400"
                onClick={() => {
                  if (confirm(`Delete "${line.name ?? "Untitled line"}"?`)) {
                    removeLine.mutate(line.id);
                  }
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
