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
  createUser: (body: { email: string; username: string; password: string; role: string }) =>
    api<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (userId: string, body: { email?: string; username?: string; role?: string; new_password?: string }) =>
    api<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteUser: (userId: string) =>
    api<void>(`/admin/users/${userId}`, { method: "DELETE" }),
  setUserRole: (userId: string, role: string) =>
    api<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }),

  listBackups: () => api<BackupEntry[]>("/admin/backups"),
  createBackup: (name: string, type: string) =>
    api<BackupEntry>("/admin/backups", { method: "POST", body: JSON.stringify({ name, type }) }),
  restoreBackup: (id: string) =>
    api<{ status: string; name: string; message: string }>(`/admin/backups/${id}/restore`, { method: "POST" }),
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

  const restoreMut = useMutation({
    mutationFn: (id: string) => adminApi.restoreBackup(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-backups"] });
      setTimeout(() => window.location.reload(), 1500);
    },
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
                      <button
                        className="btn-ghost text-xs px-2 py-1"
                        onClick={() => {
                          if (window.confirm(`Restore this backup? This will replace ALL current data with the contents of '${b.name}'. This cannot be undone.`)) {
                            restoreMut.mutate(b.id);
                          }
                        }}
                        disabled={restoreMut.isPending}
                        title="Restore from backup"
                      >
                        {restoreMut.isPending ? "Restoring…" : "⟲ Restore"}
                      </button>
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

  // Create user form state
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ username: "", email: "", password: "", role: "user" });
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit user state
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState({ username: "", email: "", role: "", new_password: "" });

  // Delete confirmation state
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Mutations
  const createMut = useMutation({
    mutationFn: () => adminApi.createUser(createForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setShowCreate(false);
      setCreateForm({ username: "", email: "", password: "", role: "user" });
      setCreateError(null);
    },
    onError: (e: any) => setCreateError(e.message ?? "Failed to create user"),
  });

  const updateMut = useMutation({
    mutationFn: () => {
      if (!editingUser) throw new Error("No user selected");
      return adminApi.updateUser(editingUser.id, editForm);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setEditingUser(null);
    },
    onError: (e: any) => setCreateError(e.message ?? "Failed to update user"),
  });

  const deleteMut = useMutation({
    mutationFn: (userId: string) => adminApi.deleteUser(userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setConfirmDeleteId(null);
      setDeleteError(null);
    },
    onError: (e: any) => setDeleteError(e.message ?? "Failed to delete user"),
  });

  const handleEditStart = (user: AdminUser) => {
    setEditingUser(user);
    setEditForm({ username: user.username, email: user.email, role: user.role, new_password: "" });
  };

  const handleEditCancel = () => {
    setEditingUser(null);
  };

  return (
    <div className="card flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2>User management</h2>
        <button
          className="btn-primary text-sm px-3 py-1.5"
          onClick={() => {
            setShowCreate(!showCreate);
            setCreateError(null);
          }}
        >
          {showCreate ? "Cancel" : "+ Create user"}
        </button>
      </div>

      {/* Create user form */}
      {showCreate && (
        <div className="p-3 rounded-md bg-ink-900 border border-ink-700 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label className="label">Username</label>
              <input
                className="input"
                value={createForm.username}
                onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                placeholder="john_doe"
              />
            </div>
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label className="label">Email</label>
              <input
                className="input"
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                placeholder="user@example.com"
              />
            </div>
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                placeholder="••••••••"
              />
            </div>
            <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <label className="label">Role</label>
              <select
                className="input"
                value={createForm.role}
                onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          {createError && <p className="text-red-400 text-sm">{createError}</p>}
          <button
            className="btn-primary text-sm"
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending || !createForm.username.trim() || !createForm.email.trim() || !createForm.password}
          >
            {createMut.isPending ? "Creating…" : "Create user"}
          </button>
        </div>
      )}

      {/* Users list */}
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
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          className="btn-ghost text-xs px-2 py-1"
                          onClick={() => handleEditStart(u)}
                          disabled={editingUser?.id === u.id}
                        >
                          Edit
                        </button>
                        <button
                          className="btn-danger text-xs px-2 py-1"
                          onClick={() => setConfirmDeleteId(u.id)}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit user modal */}
      {editingUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-ink-800 rounded-lg border border-ink-700 p-4 max-w-md w-full">
            <h3 className="text-lg font-medium mb-4">Edit {editingUser.username}</h3>
            <div className="flex flex-col gap-3 mb-4">
              <div className="flex flex-col gap-1">
                <label className="label">Username</label>
                <input
                  className="input"
                  value={editForm.username}
                  onChange={(e) => setEditForm({ ...editForm, username: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="label">Email</label>
                <input
                  className="input"
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="label">Role</label>
                <select
                  className="input"
                  value={editForm.role}
                  onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="label">New Password (optional)</label>
                <input
                  className="input"
                  type="password"
                  value={editForm.new_password}
                  onChange={(e) => setEditForm({ ...editForm, new_password: e.target.value })}
                  placeholder="Leave blank to keep current password"
                />
              </div>
            </div>
            {createError && <p className="text-red-400 text-sm mb-4">{createError}</p>}
            <div className="flex gap-2">
              <button className="btn-primary flex-1" onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
                {updateMut.isPending ? "Saving…" : "Save"}
              </button>
              <button className="btn-ghost flex-1" onClick={handleEditCancel} disabled={updateMut.isPending}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-ink-800 rounded-lg border border-ink-700 p-4 max-w-md w-full">
            <h3 className="text-lg font-medium mb-2">Delete user?</h3>
            <p className="text-sm text-ink-400 mb-4">This will permanently delete the user account and all associated data (libraries, practice history, backups). This cannot be undone.</p>
            {deleteError && <p className="text-red-400 text-sm mb-4">{deleteError}</p>}
            <div className="flex gap-2">
              <button
                className="btn-danger flex-1"
                onClick={() => deleteMut.mutate(confirmDeleteId)}
                disabled={deleteMut.isPending}
              >
                {deleteMut.isPending ? "Deleting…" : "Yes, delete"}
              </button>
              <button
                className="btn-ghost flex-1"
                onClick={() => {
                  setConfirmDeleteId(null);
                  setDeleteError(null);
                }}
                disabled={deleteMut.isPending}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
