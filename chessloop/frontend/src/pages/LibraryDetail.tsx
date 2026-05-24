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
      <div>
        <Link to="/libraries" className="text-sm text-ink-300">← All libraries</Link>
        <h1 className="mt-1">{lib.name}</h1>
        <p className="text-ink-300 text-sm">
          {lib.color} · {lib.eco_code ?? "no ECO"} · {lib.difficulty ?? "—"}
        </p>
      </div>

      <div className="flex gap-2">
        <Link to={`/libraries/${id}/teach`} className="btn-primary">Teaching board</Link>
        <button className="btn-ghost" onClick={() => createLine.mutate()}>
          + Add line
        </button>
      </div>

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
