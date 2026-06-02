import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { publicApi } from "@/api/public";
import { useAuthStore } from "@/stores/auth";
import { AdminOpeningsPanel } from "@/components/admin/AdminOpeningsPanel";
import type { PublicLibraryEntry, VideoLink } from "@/types";

const COLOR_LABEL: Record<string, string> = {
  white: "White",
  black: "Black",
  both: "Both",
};

const DIFF_LABEL: Record<string, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

function LibraryCard({ lib, isAdmin }: { lib: PublicLibraryEntry; isAdmin: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const starMut = useMutation({
    mutationFn: () => publicApi.toggleStar(lib.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["public-libraries"], exact: false }),
  });

  const forkMut = useMutation({
    mutationFn: async () => {
      // Fork via the libraries router
      const { api } = await import("@/api/client");
      return api(`/public/libraries/${lib.id}/fork`, { method: "POST" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["libraries"] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: async () => {
      const { adminApi } = await import("@/api/admin");
      return adminApi.deleteOpening(lib.name);
    },
    onSuccess: () => {
      setShowDeleteConfirm(false);
      // Invalidate all public-libraries queries with different filters
      qc.invalidateQueries({ queryKey: ["public-libraries"], exact: false, refetchType: "all" });
    },
  });

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={`/public/${lib.id}`}
            className="font-semibold text-ink-100 hover:text-gold-400 truncate block"
          >
            {lib.name}
          </Link>
          <div className="text-xs text-ink-400 mt-0.5">
            by {lib.owner_username}
            {lib.eco_code && <span className="ml-2 font-mono text-gold-500">{lib.eco_code}</span>}
            {lib.forked_from_id && <span className="ml-2 text-ink-500">· fork</span>}
          </div>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1 text-xs">
          <span className="text-ink-400">{COLOR_LABEL[lib.color]}</span>
          {lib.difficulty && (
            <span className="text-ink-500 capitalize">{DIFF_LABEL[lib.difficulty] ?? lib.difficulty}</span>
          )}
        </div>
      </div>

      {lib.description && (
        <p className="text-sm text-ink-300 line-clamp-2">{lib.description}</p>
      )}

      {lib.video_links.length > 0 && (
        <div className="flex flex-col gap-1 pt-2 border-t border-ink-700">
          {lib.video_links.map((link: VideoLink) => (
            <a
              key={link.id}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-2 px-3 py-1.5 rounded bg-ink-800 border border-ink-700 hover:border-gold-500/50 text-xs text-ink-200 hover:text-gold-300 transition-colors"
            >
              <span className="text-gold-500 shrink-0">▶</span>
              <span className="truncate">{link.title}</span>
            </a>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-ink-400 pt-1 border-t border-ink-700">
        <span>{lib.line_count} line{lib.line_count !== 1 ? "s" : ""}</span>
        <div className="flex items-center gap-3">
          <button
            onClick={() => starMut.mutate()}
            disabled={starMut.isPending}
            className="flex items-center gap-1 hover:text-gold-400 transition-colors"
            title="Star"
          >
            ★ {lib.star_count}
          </button>
          <button
            onClick={() => navigate(`/public/${lib.id}/learn`)}
            className="btn-ghost text-xs py-0.5"
            title="Browse this library in read-only mode"
          >
            Learn / View
          </button>
          <button
            onClick={() => forkMut.mutate()}
            disabled={forkMut.isPending}
            className="btn-ghost text-xs py-0.5"
            title="Fork to your libraries"
          >
            {forkMut.isSuccess ? "Forked ✓" : "Fork / Add to My Library"}
          </button>
          {isAdmin && (
            <>
              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={deleteMut.isPending}
                  className="btn-ghost text-xs py-0.5 text-red-400 hover:text-red-300"
                  title="Delete this opening"
                >
                  🗑
                </button>
              ) : (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => deleteMut.mutate()}
                    disabled={deleteMut.isPending}
                    className="btn-ghost text-xs py-0.5 text-red-400 hover:bg-red-600/20"
                  >
                    {deleteMut.isPending ? "…" : "Confirm"}
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleteMut.isPending}
                    className="btn-ghost text-xs py-0.5"
                  >
                    ✕
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function Public() {
  const [q, setQ] = useState("");
  const [color, setColor] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [sort, setSort] = useState<"stars" | "newest" | "name" | "lines">("stars");
  const user = useAuthStore((s) => s.user);

  const { data: libraries, isLoading } = useQuery({
    queryKey: ["public-libraries", q, color, difficulty, sort],
    queryFn: () => publicApi.browse({ q, color, difficulty, sort }),
    staleTime: 30_000,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1>Public Opening Libraries</h1>
        <p className="text-ink-300 mt-1 text-sm">Browse and fork community opening repertoires.</p>
      </div>

      {/* Admin opening management panel — admins only */}
      {user?.role === "admin" && (
        <AdminOpeningsPanel publicLibraries={libraries ?? []} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="input flex-1 min-w-[180px]"
        />
        <select
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className="input w-[130px]"
        >
          <option value="">All colors</option>
          <option value="white">White</option>
          <option value="black">Black</option>
          <option value="both">Both</option>
        </select>
        <select
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
          className="input w-[150px]"
        >
          <option value="">All levels</option>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </select>
        <div className="flex items-center gap-2">
          <label className="text-xs text-ink-400 whitespace-nowrap">Sort by:</label>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as "stars" | "newest" | "name" | "lines")}
            className="input w-[130px]"
          >
            <option value="stars">Most starred</option>
            <option value="newest">Newest</option>
            <option value="lines">Most lines</option>
            <option value="name">Name (A-Z)</option>
          </select>
        </div>
      </div>

      {/* Results */}
      {isLoading ? (
        <p className="text-ink-400 text-sm">Loading…</p>
      ) : !libraries?.length ? (
        <div className="card text-center py-10 text-ink-400">
          <p>No public libraries found.</p>
          <p className="text-sm mt-1">
            Publish one of your own from{" "}
            <Link to="/libraries" className="text-gold-400 hover:underline">Libraries</Link>.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {libraries.map((lib) => (
            <LibraryCard key={lib.id} lib={lib} isAdmin={user?.role === "admin"} />
          ))}
        </div>
      )}
    </div>
  );
}
