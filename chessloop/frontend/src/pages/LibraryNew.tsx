import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { librariesApi, type LibraryCreate } from "@/api/libraries";

export function LibraryNew() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<LibraryCreate>({ name: "", color: "white" });
  const [err, setErr] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => librariesApi.create(form),
    onSuccess: (lib) => {
      qc.invalidateQueries({ queryKey: ["libraries"] });
      navigate(`/libraries/${lib.id}`);
    },
    onError: (e: any) => setErr(e.message ?? "Create failed"),
  });

  return (
    <div className="max-w-md">
      <h1 className="mb-4">New library</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          create.mutate();
        }}
        className="flex flex-col gap-3 card"
      >
        <div>
          <label className="label">Name</label>
          <input
            className="input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="label">Color</label>
          <select
            className="input"
            value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value as LibraryCreate["color"] })}
          >
            <option value="white">White</option>
            <option value="black">Black</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div>
          <label className="label">Description (optional, Markdown supported)</label>
          <textarea
            className="input font-mono"
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">ECO code</label>
            <input
              className="input"
              value={form.eco_code ?? ""}
              onChange={(e) => setForm({ ...form, eco_code: e.target.value })}
              placeholder="e.g. B90"
            />
          </div>
          <div>
            <label className="label">Difficulty</label>
            <select
              className="input"
              value={form.difficulty ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  difficulty: (e.target.value || undefined) as LibraryCreate["difficulty"],
                })
              }
            >
              <option value="">—</option>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex gap-2 justify-end">
          <button type="button" className="btn-ghost" onClick={() => navigate(-1)}>Cancel</button>
          <button className="btn-primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
