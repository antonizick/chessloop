import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { Navigate } from "react-router-dom";

// ── API helpers ───────────────────────────────────────────────────────────────

interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  mfa_enabled: boolean;
  created_at: string;
  last_login: string | null;
}

interface BackupEntry {
  id: string;
  name: string;
  type: string;
  size_bytes: number;
  created_by: string;
  created_at: string;
}

const adminApi = {
  listUsers: () => api<AdminUser[]>("/admin/users"),
  setUserRole: (userId: string, role: string) =>
    api<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }),

  listBackups: () => api<BackupEntry[]>("/admin/backups"),
  createBackup: (name: string, type: string) =>
    api<BackupEntry>("/admin/backups", { method: "POST", body: JSON.stringify({ name, type }) }),
  deleteBackup: (id: string) =>
    api<void>(`/admin/backups/${id}`, { method: "DELETE" }),
  downloadUrl: (id: string) => `/api/admin/backups/${id}/download`,
};

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

// ── Component ─────────────────────────────────────────────────────────────────

export function Admin() {
  const user = useAuthStore((s) => s.user);
  if (user?.role !== "admin") return <Navigate to="/" replace />;

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <h1>Admin panel</h1>
      <BackupsSection />
      <UsersSection />
    </div>
  );
}

// ── Backups ───────────────────────────────────────────────────────────────────

function BackupsSection() {
  const qc = useQueryClient();
  const [newName, setNewName] = useState("manual-backup");
  const [newType, setNewType] = useState<"full" | "content" | "progress">("full");
  const [createErr, setCreateErr] = useState<string | null>(null);

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["admin-backups"],
    queryFn: adminApi.listBackups,
  });

  const createMut = useMutation({
    mutationFn: () => adminApi.createBackup(newName, newType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-backups"] });
      setCreateErr(null);
    },
    onError: (e: any) => setCreateErr(e.message ?? "Failed to create backup"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => adminApi.deleteBackup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-backups"] }),
  });

  return (
    <div className="card flex flex-col gap-4">
      <h2>Database backups</h2>
      <p className="text-xs text-ink-400">
        Full backups copy the entire SQLite file. Up to 10 backups are retained; oldest is
        pruned automatically when the limit is reached.
      </p>

      {/* Create backup */}
      <div className="flex flex-wrap items-end gap-3 p-3 rounded-md bg-ink-900 border border-ink-700">
        <div className="flex flex-col gap-1 flex-1 min-w-[160px]">
          <label className="label">Backup name</label>
          <input
            className="input"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="manual-backup"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="label">Type</label>
          <select
            className="input"
            value={newType}
            onChange={(e) => setNewType(e.target.value as typeof newType)}
          >
            <option value="full">Full</option>
            <option value="content">Content only</option>
            <option value="progress">Progress only</option>
          </select>
        </div>
        <button
          className="btn-primary"
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending || !newName.trim()}
        >
          {createMut.isPending ? "Creating…" : "Create backup"}
        </button>
      </div>
      {createErr && <p className="text-red-400 text-sm">{createErr}</p>}

      {/* Backup list */}
      {isLoading ? (
        <p className="text-ink-500 text-sm">Loading…</p>
      ) : backups.length === 0 ? (
        <p className="text-ink-500 text-sm">No backups yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-700">
                <th className="pb-2 font-medium">Name</th>
                <th className="pb-2 font-medium">Type</th>
                <th className="pb-2 font-medium">Size</th>
                <th className="pb-2 font-medium">Created</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {backups.map((b) => (
                <tr key={b.id} className="hover:bg-ink-700/30 transition-colors">
                  <td className="py-2 pr-4 font-mono text-xs text-ink-200">{b.name}</td>
                  <td className="py-2 pr-4 text-ink-400">{b.type}</td>
                  <td className="py-2 pr-4 text-ink-400">{fmt(b.size_bytes)}</td>
                  <td className="py-2 pr-4 text-ink-400 text-xs">{fmtDate(b.created_at)}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2 justify-end">
                      <a
                        href={adminApi.downloadUrl(b.id)}
                        className="btn-ghost text-xs px-2 py-1"
                        download
                      >
                        ↓ Download
                      </a>
                      <button
                        className="btn-danger text-xs px-2 py-1"
                        onClick={() => deleteMut.mutate(b.id)}
                        disabled={deleteMut.isPending}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Users ────────────────────────────────────────────────────────────────────

function UsersSection() {
  const qc = useQueryClient();
  const currentUserId = useAuthStore((s) => s.user?.id);

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.listUsers,
  });

  const roleMut = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) => adminApi.setUserRole(id, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  return (
    <div className="card flex flex-col gap-4">
      <h2>User management</h2>

      {isLoading ? (
        <p className="text-ink-500 text-sm">Loading…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-400 border-b border-ink-700">
                <th className="pb-2 font-medium">Username</th>
                <th className="pb-2 font-medium">Email</th>
                <th className="pb-2 font-medium">Role</th>
                <th className="pb-2 font-medium">MFA</th>
                <th className="pb-2 font-medium">Joined</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-ink-700/30 transition-colors">
                  <td className="py-2 pr-4 font-medium text-ink-100">{u.username}</td>
                  <td className="py-2 pr-4 text-ink-400 text-xs">{u.email}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        u.role === "admin"
                          ? "bg-gold-500/20 text-gold-400 border border-gold-500/30"
                          : "bg-ink-700 text-ink-400 border border-ink-600"
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-xs text-ink-400">
                    {u.mfa_enabled ? "✓" : "—"}
                  </td>
                  <td className="py-2 pr-4 text-xs text-ink-500">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-2">
                    {u.id !== currentUserId && (
                      <button
                        className={`text-xs px-2 py-1 rounded border transition-colors ${
                          u.role === "admin"
                            ? "border-ink-600 text-ink-400 hover:border-red-500/60 hover:text-red-400"
                            : "border-ink-600 text-ink-400 hover:border-gold-500/60 hover:text-gold-400"
                        }`}
                        onClick={() =>
                          roleMut.mutate({
                            id: u.id,
                            role: u.role === "admin" ? "user" : "admin",
                          })
                        }
                        disabled={roleMut.isPending}
                      >
                        {u.role === "admin" ? "Revoke admin" : "Make admin"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
