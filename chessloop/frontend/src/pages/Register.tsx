import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";

export function Register() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      await authApi.register({ email, username, password });
      navigate("/login");
    } catch (e: any) {
      setErr(e.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm card">
        <h1 className="mb-4 text-gold-400">Create account</h1>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="label">Username</label>
            <input className="input" value={username} minLength={3} maxLength={32}
              onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div>
            <label className="label">Password (min 8)</label>
            <input className="input" type="password" value={password} minLength={8}
              onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {err && <p className="text-sm text-red-400">{err}</p>}
          <button className="btn-primary" disabled={loading}>
            {loading ? "Creating…" : "Create account"}
          </button>
          <p className="text-sm text-ink-300 text-center">
            Have an account? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
