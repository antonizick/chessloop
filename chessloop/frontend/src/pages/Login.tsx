import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  const { data: serverConfig } = useQuery({ queryKey: ["auth-config"], queryFn: authApi.config });
  const canEmail = serverConfig?.smtp_configured ?? true;

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
              <label className="label" htmlFor="login-email">Email</label>
              <input className="input" id="login-email" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="label" htmlFor="login-password">Password</label>
                <Link to="/forgot-password" className="text-sm text-ink-300 hover:text-ink-100">
                  Forgot password?
                </Link>
              </div>
              <input className="input" id="login-password" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </div>
            {err && <p className="text-sm text-red-400" role="alert">{err}</p>}
            {unverified && !canEmail && (
              <p className="text-sm text-red-400" role="alert">
                Your account is not verified yet, and this server can't send email.
                Ask your ChessLoop admin to verify it (Admin → Users), then sign in again.
              </p>
            )}
            {unverified && canEmail && (
              <p className="text-sm text-red-400" role="alert">
                Email not verified. Check your inbox for the link, or{" "}
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
                    : "resend the verification email"}
                </button>
              </p>
            )}
            <button className="btn-primary" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
            <p className="text-sm text-ink-300 text-center">
              No account? <Link to="/register" className="underline">Register</Link>
            </p>
          </form>
        ) : (
          <form onSubmit={onSubmitMfa} className="flex flex-col gap-3">
            <p className="text-sm text-ink-200">Enter the 6-digit code from your authenticator app.</p>
            <input className="input tracking-widest text-center" value={totp} aria-label="6-digit code"
              onChange={(e) => setTotp(e.target.value)} placeholder="123456" inputMode="numeric" autoComplete="one-time-code"
              maxLength={6} required />
            {err && <p className="text-sm text-red-400" role="alert">{err}</p>}
            <button className="btn-primary" disabled={loading}>
              {loading ? "Verifying…" : "Verify"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
