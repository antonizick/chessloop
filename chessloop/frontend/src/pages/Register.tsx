import { useState } from "react";
import { Link } from "react-router-dom";
import { authApi, type RegisterResult } from "@/api/auth";

export function Register() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState<RegisterResult | null>(null);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      setRegistered(await authApi.register({ email, username, password }));
    } catch (e: any) {
      setErr(e.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function onResend() {
    setResendState("sending");
    try {
      await authApi.resendVerification(email);
    } finally {
      setResendState("sent");
    }
  }

  if (registered && registered.next_step !== "check_email") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-sm card">
          <h1 className="mb-4 text-gold-400">Account created</h1>
          <p className="text-sm text-ink-200">{registered.message}</p>
          <Link to="/login" className="btn-primary mt-4 block text-center">Go to sign in</Link>
        </div>
      </div>
    );
  }

  if (registered) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-sm card">
          <h1 className="mb-4 text-gold-400">Check your email</h1>
          <p className="text-sm text-ink-200">
            We sent a verification link to <span className="text-ink-100">{email}</span>.
            Click it to activate your account.
          </p>
          <button
            className="btn-primary mt-4"
            disabled={resendState !== "idle"}
            onClick={onResend}
          >
            {resendState === "sending" ? "Sending…" : resendState === "sent" ? "Email sent" : "Resend email"}
          </button>
          <p className="text-sm text-ink-300 text-center mt-3">
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </div>
    );
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
            <label className="label">Password (at least 12 characters)</label>
            <input className="input" type="password" value={password} minLength={12} maxLength={128}
              onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
            <p className="text-xs text-ink-400 mt-1">A few unrelated words make a strong, memorable password.</p>
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
