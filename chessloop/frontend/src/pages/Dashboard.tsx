import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { useAuthStore } from "@/stores/auth";

export function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const { data: libraries } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });
  const active = libraries?.filter((l) => l.is_active) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1>Welcome back{user ? `, ${user.username}` : ""}.</h1>
        <p className="text-ink-300 mt-1">Phase 1 scaffold — auth + libraries + boards online.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-xs uppercase text-ink-300">Active openings</div>
          <div className="text-3xl font-semibold text-gold-400 mt-2">{active.length}</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-ink-300">Total libraries</div>
          <div className="text-3xl font-semibold text-gold-400 mt-2">{libraries?.length ?? 0}</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-ink-300">Practice queue</div>
          <div className="text-3xl font-semibold text-ink-400 mt-2">—</div>
          <div className="text-xs text-ink-400 mt-1">(SRS comes in Phase 3)</div>
        </div>
      </div>

      <div className="flex gap-3">
        <Link to="/libraries/new" className="btn-primary">+ New library</Link>
        <Link to="/practice" className="btn-ghost">Practice board (preview)</Link>
      </div>
    </div>
  );
}
