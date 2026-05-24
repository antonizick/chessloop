import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { publicApi } from "@/api/public";
import { api } from "@/api/client";

export function PublicLibraryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [commentText, setCommentText] = useState("");

  const { data: lib, isLoading, error } = useQuery({
    queryKey: ["public-library", id],
    queryFn: () => publicApi.getLibrary(id!),
    enabled: !!id,
  });

  const starMut = useMutation({
    mutationFn: () => publicApi.toggleStar(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["public-library", id] }),
  });

  const forkMut = useMutation({
    mutationFn: () => api<{ id: string }>(`/libraries/${id}/fork`, { method: "POST" }),
    onSuccess: (forked) => {
      qc.invalidateQueries({ queryKey: ["libraries"] });
      navigate(`/libraries/${forked.id}`);
    },
  });

  const commentMut = useMutation({
    mutationFn: () => publicApi.addComment(id!, commentText),
    onSuccess: () => {
      setCommentText("");
      qc.invalidateQueries({ queryKey: ["public-library", id] });
    },
  });

  if (isLoading) {
    return <p className="text-ink-400">Loading…</p>;
  }
  if (error || !lib) {
    return (
      <div className="card text-center py-10">
        <p className="text-ink-400">Library not found or not public.</p>
        <Link to="/public" className="text-gold-400 hover:underline text-sm mt-2 block">
          ← Back to public libraries
        </Link>
      </div>
    );
  }

  const colorLabel: Record<string, string> = { white: "White", black: "Black", both: "Both" };

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      {/* Breadcrumb */}
      <Link to="/public" className="text-ink-400 hover:text-gold-400 text-sm">
        ← Public libraries
      </Link>

      {/* Header */}
      <div className="card flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink-100">{lib.name}</h1>
            <p className="text-ink-400 text-sm mt-1">
              by {lib.owner_username}
              {lib.eco_code && (
                <span className="ml-2 font-mono text-gold-500">{lib.eco_code}</span>
              )}
              <span className="ml-2">· {colorLabel[lib.color]}</span>
              {lib.difficulty && (
                <span className="ml-2 capitalize text-ink-500">· {lib.difficulty}</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => starMut.mutate()}
              disabled={starMut.isPending}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm border transition-colors ${
                lib.user_has_starred
                  ? "border-gold-500 text-gold-400 bg-gold-500/10"
                  : "border-ink-600 text-ink-300 hover:border-gold-500 hover:text-gold-400"
              }`}
            >
              ★ {lib.star_count}
            </button>
            <button
              onClick={() => forkMut.mutate()}
              disabled={forkMut.isPending}
              className="btn-primary text-sm"
            >
              {forkMut.isPending ? "Forking…" : "Fork to my libraries"}
            </button>
          </div>
        </div>

        {lib.description && (
          <p className="text-ink-300 text-sm leading-relaxed">{lib.description}</p>
        )}

        <div className="text-xs text-ink-500">
          {lib.line_count} line{lib.line_count !== 1 ? "s" : ""} ·
          Published {new Date(lib.published_at).toLocaleDateString()}
          {lib.forked_from_id && " · forked"}
        </div>
      </div>

      {/* Comments */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">
          Comments ({lib.comments.length})
        </h2>

        <div className="flex flex-col gap-2 mb-4">
          {lib.comments.length === 0 && (
            <p className="text-ink-400 text-sm">No comments yet. Be the first.</p>
          )}
          {lib.comments.map((c) => (
            <div key={c.id} className="card">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-ink-100">{c.username}</span>
                <span className="text-xs text-ink-500">
                  {new Date(c.created_at).toLocaleDateString()}
                </span>
              </div>
              <p className="text-sm text-ink-300 leading-relaxed">{c.content}</p>
            </div>
          ))}
        </div>

        {/* Add comment */}
        <div className="flex flex-col gap-2">
          <textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder="Add a comment…"
            rows={3}
            className="input resize-none"
          />
          <div className="flex justify-end">
            <button
              onClick={() => commentMut.mutate()}
              disabled={!commentText.trim() || commentMut.isPending}
              className="btn-primary"
            >
              {commentMut.isPending ? "Posting…" : "Post comment"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
