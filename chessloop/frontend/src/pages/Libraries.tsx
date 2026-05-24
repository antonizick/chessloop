import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";

export function Libraries() {
  const qc = useQueryClient();
  const { data: libraries, isLoading } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      librariesApi.setActive(id, is_active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["libraries"] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => librariesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["libraries"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1>Libraries</h1>
        <Link to="/libraries/new" className="btn-primary">+ New library</Link>
      </div>

      {isLoading && <p className="text-ink-300">Loading…</p>}

      {libraries?.length === 0 && (
        <div className="card text-center text-ink-300">
          No libraries yet. Create your first to start teaching the system an opening.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {libraries?.map((lib) => (
          <div key={lib.id} className="card flex flex-col gap-2">
            <div className="flex items-start justify-between">
              <Link to={`/libraries/${lib.id}`} className="text-lg font-semibold text-gold-400">
                {lib.name}
              </Link>
              <span className="text-xs px-2 py-0.5 rounded bg-ink-700 text-ink-200">
                {lib.color}
              </span>
            </div>
            {lib.description && <p className="text-sm text-ink-300">{lib.description}</p>}
            <div className="flex items-center gap-2 text-xs text-ink-400">
              {lib.eco_code && <span>ECO {lib.eco_code}</span>}
              {lib.difficulty && <span>· {lib.difficulty}</span>}
              {lib.is_public && <span>· public</span>}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <Link to={`/libraries/${lib.id}/teach`} className="btn-ghost text-xs">Teach</Link>
              <button
                className="btn-ghost text-xs"
                onClick={() => toggleActive.mutate({ id: lib.id, is_active: !lib.is_active })}
              >
                {lib.is_active ? "Deactivate" : "Activate"}
              </button>
              <button
                className="btn-ghost text-xs text-red-400"
                onClick={() => {
                  if (confirm(`Delete library "${lib.name}"? This removes all its lines.`)) {
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
    </div>
  );
}
