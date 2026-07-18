import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { ApiError } from "@/api/client";

export function Login() {
  const navigate = useNavigate();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);
  const [totp, setTotp] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");
  const [loading, setLoading] = useState(false);

  async function completeLogin(access: string, refresh: string) {
    setTokens(access, refresh);
    const me = await authApi.me();
    setUser(me);
    navigate("/");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setUnverified(false);
    setResendState("idle");
    setLoading(true);
    try {
      const res = await authApi.login({ email, password });
      if ("mfa_required" in res) {
        setMfaChallenge(res.challenge_token);
      } else {
        await completeLogin(res.access_token, res.refresh_token);
      }
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 403) {
        setUnverified(true);
      } else {
        setErr(e.message ?? "Login failed");
      }
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

  async function onSubmitMfa(e: React.FormEvent) {
    e.preventDefault();
    if (!mfaChallenge) return;
    setErr(null);
    setLoading(true);
    try {
      const res = await authApi.loginMfa({ challenge_token: mfaChallenge, totp_code: totp });
      await completeLogin(res.access_token, res.refresh_token);
    } catch (e: any) {
      setErr(e.message ?? "MFA failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm card">
        <h1 className="mb-4 text-gold-400">♞ ChessLoop</h1>
        {!mfaChallenge ? (
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <div>
              <label className="label">Email</label>
              <input className="input" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </div>
            <div>
              <label className="label">Password</label>
              <input className="input" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </div>
            {err && <p className="text-sm text-red-400">{err}</p>}
            {unverified && (
              <p className="text-sm text-red-400">
                Email not verified.{" "}
                <button
                  type="button"
                  className="underline disabled:opacity-60"
                  disabled={resendState !== "idle"}
                  onClick={onResend}
                >
                  {resendState === "sending"
                    ? "Sending…"
                    : resendState === "sent"
                    ? "Verification email sent"
                    : "Resend verification email"}
                </button>
              </p>
            )}
            <button className="btn-primary" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
            <p className="text-sm text-ink-300 text-center">
              No account? <Link to="/register">Register</Link>
            </p>
          </form>
        ) : (
          <form onSubmit={onSubmitMfa} className="flex flex-col gap-3">
            <p className="text-sm text-ink-200">Enter the 6-digit code from your authenticator app.</p>
            <input className="input tracking-widest text-center" value={totp}
              onChange={(e) => setTotp(e.target.value)} placeholder="123456" maxLength={6} required />
            {err && <p className="text-sm text-red-400">{err}</p>}
            <button className="btn-primary" disabled={loading}>
              {loading ? "Verifying…" : "Verify"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
