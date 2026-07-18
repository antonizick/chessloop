import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import { api } from "@/api/client";
import { adminApi } from "@/api/admin";
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

const backupApi = {
  listUsers: () => api<AdminUser[]>("/admin/users"),
  createUser: (body: { email: string; username: string; password: string; role: string }) =>
    api<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (userId: string, body: { email?: string; username?: string; role?: string; new_password?: string }) =>
    api<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteUser: (userId: string) =>
    api<void>(`/admin/users/${userId}`, { method: "DELETE" }),

  listBackups: () => api<BackupEntry[]>("/admin/backups"),
  createBackup: (name: string, type: string) =>
    api<BackupEntry>("/admin/backups", { method: "POST", body: JSON.stringify({ name, type }) }),
  uploadBackup: async (file: File, name: string, type: string) => {
    const { accessToken, refreshToken, setTokens, logout } = useAuthStore.getState();

    const makeFormData = () => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", name);
      fd.append("type", type);
      return fd;
    };

    const headers: Record<string, string> = {};
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

    let res = await fetch("/api/admin/backups/upload", {
      method: "POST",
      headers,
      body: makeFormData(),
    });

    if (res.status === 401 && refreshToken) {
      const refreshRes = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        setTokens(data.access_token, data.refresh_token);
        res = await fetch("/api/admin/backups/upload", {
          method: "POST",
          headers: { Authorization: `Bearer ${data.access_token}` },
          body: makeFormData(),
        });
      } else {
        logout();
        throw new Error("Session expired — please log in again");
      }
    }

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `Upload failed (${res.status})`);
    }
    return res.json() as Promise<BackupEntry>;
  },
  restoreBackup: (id: string) =>
    api<{ status: string; name: string; message: string }>(`/admin/backups/${id}/restore`, { method: "POST" }),
  deleteBackup: (id: string) =>
    api<void>(`/admin/backups/${id}`, { method: "DELETE" }),
};

function fmt(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

type Tab = "users" | "backups" | "backend-logs" | "frontend-logs" | "activity" | "new-user-popup";

const TABS: { id: Tab; label: string }[] = [
  { id: "users", label: "Users" },
  { id: "backups", label: "Backups" },
  { id: "backend-logs", label: "Backend Logs" },
  { id: "frontend-logs", label: "Frontend Logs" },
  { id: "activity", label: "Activity" },
  { id: "new-user-popup", label: "New User Popup" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function Admin() {
  const user = useAuthStore((s) => s.user);
  const [activeTab, setActiveTab] = useState<Tab>("users");

  if (user?.role !== "admin") return <Navigate to="/" replace />;

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <h1>Admin panel</h1>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-ink-700 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === t.id
                ? "border-gold-400 text-gold-400"
                : "border-transparent text-ink-400 hover:text-ink-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "users" && <UsersSection />}
      {activeTab === "backups" && <BackupsSection />}
      {activeTab === "backend-logs" && <LogSection title="Backend Logs" fetchLines={(n) => adminApi.getBackendLogs(n).then(r => r.lines)} queryKey="backend-logs" />}
      {activeTab === "frontend-logs" && <LogSection title="Frontend Logs" fetchLines={(n) => adminApi.getFrontendLogs(n).then(r => r.lines)} queryKey="frontend-logs" />}
      {activeTab === "activity" && <ActivitySection />}
      {activeTab === "new-user-popup" && <NewUserPopupSection />}
    </div>
  );
}

// ── Log viewer ────────────────────────────────────────────────────────────────

function LogSection({
  title,
  fetchLines,
  queryKey,
}: {
  title: string;
  fetchLines: (n: number) => Promise<string[]>;
  queryKey: string;
}) {
  const [lineCount, setLineCount] = useState(300);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: lines = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: [queryKey, lineCount],
    queryFn: () => fetchLines(lineCount),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2>{title}</h2>
        <div className="flex items-center gap-2">
          <select
            className="input text-xs py-1"
            value={lineCount}
            onChange={(e) => setLineCount(Number(e.target.value))}
          >
            <option value={100}>Last 100 lines</option>
            <option value={300}>Last 300 lines</option>
            <option value={500}>Last 500 lines</option>
            <option value={1000}>Last 1000 lines</option>
          </select>
          <button
            className="btn-ghost text-xs px-3 py-1.5"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? "Refreshing…" : "↺ Refresh"}
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-ink-500 text-sm">Loading…</p>
      ) : lines.length === 0 ? (
        <p className="text-ink-500 text-sm">No log entries found. Logs appear here once the server writes them.</p>
      ) : (
        <div className="bg-ink-950 rounded-md border border-ink-700 p-3 overflow-auto max-h-[600px] font-mono text-xs leading-relaxed">
          {lines.map((line, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap break-all ${
                line.includes("ERROR") || line.includes("[ERROR]")
                  ? "text-red-400"
                  : line.includes("WARNING") || line.includes("WARN")
                  ? "text-yellow-400"
                  : line.includes("INFO")
                  ? "text-ink-300"
                  : "text-ink-400"
              }`}
            >
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
      <p className="text-xs text-ink-500">Auto-refreshes every 30 seconds.</p>
    </div>
  );
}

// ── Activity log ──────────────────────────────────────────────────────────────

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  login:           { label: "Login",            color: "text-blue-400" },
  register:        { label: "Register",         color: "text-green-400" },
  create_library:  { label: "Create library",   color: "text-gold-400" },
  delete_library:  { label: "Delete library",   color: "text-red-400" },
  fork_library:    { label: "Fork library",     color: "text-purple-400" },
  publish_library: { label: "Publish library",  color: "text-emerald-400" },
  create_line:     { label: "Create line",      color: "text-teal-400" },
  delete_line:     { label: "Delete line",      color: "text-orange-400" },
};

function ActivitySection() {
  const [limit, setLimit] = useState(200);
  const [filterUser, setFilterUser] = useState("");
  const [filterAction, setFilterAction] = useState("");

  const { data: logs = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["activity-logs", limit],
    queryFn: () => adminApi.getActivityLogs(limit),
    refetchInterval: 30_000,
  });

  const filtered = logs.filter((e) => {
    if (filterUser && !e.username.toLowerCase().includes(filterUser.toLowerCase())) return false;
    if (filterAction && e.action !== filterAction) return false;
    return true;
  });

  return (
    <div className="card flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2>User activity</h2>
        <div className="flex items-center gap-2">
          <select
            className="input text-xs py-1"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            <option value={100}>Last 100</option>
            <option value={200}>Last 200</option>
            <option value={500}>Last 500</option>
            <option value={1000}>Last 1000</option>
          </select>
          <button
            className="btn-ghost text-xs px-3 py-1.5"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? "Refreshing…" : "↺ Refresh"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          className="input text-xs py-1 w-40"
          placeholder="Filter by user…"
          value={filterUser}
          onChange={(e) => setFilterUser(e.target.value)}
        />
        <select
          className="input text-xs py-1"
          value={filterAction}
          onChange={(e) => setFilterAction(e.target.value)}
        >
          <option value="">All actions</option>
          {Object.entries(ACTION_LABELS).map(([key, { label }]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        {(filterUser || filterAction) && (
          <button
            className="btn-ghost text-xs px-2 py-1"
            onClick={() => { setFilterUser(""); setFilterAction(""); }}
          >
            Clear
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="text-ink-500 text-sm">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="text-ink-500 text-sm">{logs.length === 0 ? "No activity recorded yet." : "No entries match the filter."}</p>
      ) : (
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink-800">
              <tr className="text-left text-ink-400 border-b border-ink-700">
                <th className="pb-2 pr-4 font-medium text-xs">Time</th>
                <th className="pb-2 pr-4 font-medium text-xs">User</th>
                <th className="pb-2 pr-4 font-medium text-xs">Action</th>
                <th className="pb-2 pr-4 font-medium text-xs">Target</th>
                <th className="pb-2 font-medium text-xs">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {filtered.map((entry) => {
                const meta = ACTION_LABELS[entry.action];
                return (
                  <tr key={entry.id} className="hover:bg-ink-700/30 transition-colors">
                    <td className="py-1.5 pr-4 text-ink-500 text-xs whitespace-nowrap font-mono">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="py-1.5 pr-4 text-ink-200 text-xs font-medium">
                      {entry.username}
                    </td>
                    <td className="py-1.5 pr-4 text-xs">
                      <span className={`font-medium ${meta?.color ?? "text-ink-300"}`}>
                        {meta?.label ?? entry.action}
                      </span>
                    </td>
                    <td className="py-1.5 pr-4 text-ink-300 text-xs max-w-[200px] truncate">
                      {entry.target ?? "—"}
                    </td>
                    <td className="py-1.5 text-ink-500 text-xs max-w-[200px] truncate">
                      {entry.detail ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-ink-500">
        Showing {filtered.length} of {logs.length} entries. Auto-refreshes every 30 seconds.
      </p>
    </div>
  );
}

// ── Backups ───────────────────────────────────────────────────────────────────

async function downloadBackup(id: string, filename: string) {
  const { accessToken, refreshToken, setTokens, logout } = useAuthStore.getState();
  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  let res = await fetch(`/api/admin/backups/${id}/download`, { headers });

  if (res.status === 401 && refreshToken) {
    const refreshRes = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (refreshRes.ok) {
      const data = await refreshRes.json();
      setTokens(data.access_token, data.refresh_token);
      res = await fetch(`/api/admin/backups/${id}/download`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
    } else {
      logout();
      throw new Error("Session expired — please log in again");
    }
  }

  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function BackupsSection() {
  const qc = useQueryClient();
  const [newName, setNewName] = useState("manual-backup");
  const [newType, setNewType] = useState<"full" | "content" | "progress">("full");
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadType, setUploadType] = useState<"full" | "content" | "progress">("full");
  const [uploadErr, setUploadErr] = useState<string | null>(null);

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["admin-backups"],
    queryFn: backupApi.listBackups,
  });

  const createMut = useMutation({
    mutationFn: () => backupApi.createBackup(newName, newType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-backups"] });
      setCreateErr(null);
    },
    onError: (e: any) => setCreateErr(e.message ?? "Failed to create backup"),
  });

  const restoreMut = useMutation({
    mutationFn: (id: string) => backupApi.restoreBackup(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-backups"] });
      setTimeout(() => window.location.reload(), 1500);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => backupApi.deleteBackup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-backups"] }),
  });

  const uploadMut = useMutation({
    mutationFn: () => {
      if (!uploadFile) throw new Error("No file selected");
      return backupApi.uploadBackup(uploadFile, uploadName || uploadFile.name, uploadType);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-backups"] });
      setShowUpload(false);
      setUploadFile(null);
      setUploadName("");
      setUploadType("full");
      setUploadErr(null);
    },
    onError: (e: any) => setUploadErr(e.message ?? "Upload failed"),
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

      {/* Upload backup */}
      <button
        className="btn-ghost text-sm px-3 py-1.5 w-fit"
        onClick={() => {
          setShowUpload(!showUpload);
          setUploadErr(null);
        }}
      >
        {showUpload ? "▼ Hide upload" : "▶ Upload backup file"}
      </button>
      {showUpload && (
        <div className="flex flex-col gap-3 p-3 rounded-md bg-ink-900 border border-ink-700">
          <div className="flex flex-col gap-2">
            <label className="label">Select backup file (.db)</label>
            <input
              type="file"
              accept=".db"
              onChange={(e) => {
                setUploadFile(e.target.files?.[0] || null);
                setUploadErr(null);
              }}
              className="input text-sm"
            />
            {uploadFile && (
              <p className="text-xs text-ink-400">
                Selected: {uploadFile.name} ({(uploadFile.size / 1024 / 1024).toFixed(1)} MB)
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="label">Display name</label>
              <input
                className="input"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder={uploadFile?.name || "backup-name"}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="label">Type</label>
              <select
                className="input"
                value={uploadType}
                onChange={(e) => setUploadType(e.target.value as typeof uploadType)}
              >
                <option value="full">Full</option>
                <option value="content">Content only</option>
                <option value="progress">Progress only</option>
              </select>
            </div>
          </div>
          {uploadErr && <p className="text-red-400 text-sm">{uploadErr}</p>}
          <button
            className="btn-primary"
            onClick={() => uploadMut.mutate()}
            disabled={uploadMut.isPending || !uploadFile}
          >
            {uploadMut.isPending ? "Uploading…" : "Upload & Register"}
          </button>
        </div>
      )}

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
                      <button
                        className="btn-ghost text-xs px-2 py-1"
                        disabled={downloading === b.id}
                        onClick={async () => {
                          setDownloading(b.id);
                          try {
                            await downloadBackup(b.id, `${b.name}.db`);
                          } finally {
                            setDownloading(null);
                          }
                        }}
                      >
                        {downloading === b.id ? "Downloading…" : "↓ Download"}
                      </button>
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
    queryFn: backupApi.listUsers,
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
    mutationFn: () => backupApi.createUser(createForm),
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
      return backupApi.updateUser(editingUser.id, editForm);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setEditingUser(null);
    },
    onError: (e: any) => setCreateError(e.message ?? "Failed to update user"),
  });

  const deleteMut = useMutation({
    mutationFn: (userId: string) => backupApi.deleteUser(userId),
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

// ── New user popup ────────────────────────────────────────────────────────────

function NewUserPopupSection() {
  const qc = useQueryClient();
  const [htmlContent, setHtmlContent] = useState("");
  const [isEnabled, setIsEnabled] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-new-user-popup"],
    queryFn: adminApi.getNewUserPopup,
  });

  useEffect(() => {
    if (data) {
      setHtmlContent(data.html_content);
      setIsEnabled(data.is_enabled);
    }
  }, [data]);

  const saveMut = useMutation({
    mutationFn: () => adminApi.updateNewUserPopup({ html_content: htmlContent, is_enabled: isEnabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-new-user-popup"] });
      setSaveErr(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e: any) => setSaveErr(e.message ?? "Failed to save"),
  });

  if (isLoading) return <div className="card">Loading…</div>;

  return (
    <div className="card flex flex-col gap-4">
      <h2>New user popup</h2>
      <p className="text-xs text-ink-400">
        Shown once on the dashboard to accounts that just registered. Content is raw HTML,
        sanitized before rendering to users.
      </p>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isEnabled}
          onChange={(e) => setIsEnabled(e.target.checked)}
        />
        Enabled
      </label>

      <div className="flex flex-col gap-1">
        <label className="label">HTML content</label>
        <textarea
          className="input h-40 resize-none font-mono text-xs"
          value={htmlContent}
          onChange={(e) => setHtmlContent(e.target.value)}
          placeholder="<h2>Welcome!</h2><p>Thanks for joining.</p>"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="label">Preview</label>
        <div
          className="p-3 rounded-md bg-ink-900 border border-ink-700 min-h-[80px]"
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(htmlContent) }}
        />
      </div>

      {saveErr && <p className="text-red-400 text-sm">{saveErr}</p>}

      <button className="btn-primary w-fit" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
        {saveMut.isPending ? "Saving…" : saved ? "Saved ✓" : "Save"}
      </button>
    </div>
  );
}
