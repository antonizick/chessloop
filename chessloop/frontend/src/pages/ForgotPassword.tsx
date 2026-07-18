import { useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
    } finally {
      setLoading(false);
      setSent(true);
    }
  }

  if (sent) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-sm card text-center">
          <h1 className="mb-4 text-gold-400">Check your email</h1>
          <p className="text-sm text-ink-200">
            If an account exists for <span className="text-ink-100">{email}</span>, we sent a
            link to reset your password. It expires in 1 hour.
          </p>
          <p className="text-sm text-ink-300 mt-3">
            <Link to="/login">Back to sign in</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm card">
        <h1 className="mb-4 text-gold-400">Reset your password</h1>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus />
          </div>
          <button className="btn-primary" disabled={loading}>
            {loading ? "Sending…" : "Send reset link"}
          </button>
          <p className="text-sm text-ink-300 text-center">
            <Link to="/login">Back to sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
