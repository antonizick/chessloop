import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { MfaSetup } from "@/components/auth/MfaSetup";

export function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);

  const [status, setStatus] = useState<"checking" | "form" | "submitting" | "mfa" | "error">(
    token ? "checking" : "error",
  );
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [disableMfa, setDisableMfa] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const checked = useRef(false);

  useEffect(() => {
    if (!token || checked.current) return;
    checked.current = true;
    authApi
      .validateResetToken(token)
      .then(() => setStatus("form"))
      .catch(() => setStatus("error"));
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (password !== confirmPassword) {
      setErr("Passwords don't match");
      return;
    }
    setErr(null);
    setStatus("submitting");
    try {
      const res = await authApi.resetPassword({ token, new_password: password, disable_mfa: disableMfa });
      setTokens(res.access_token, res.refresh_token);
      const me = await authApi.me();
      setUser(me);
      if (me.mfa_enabled) {
        navigate("/");
      } else {
        setStatus("mfa");
      }
    } catch (e: any) {
      setErr(e.message ?? "This link is invalid or has expired.");
      setStatus("form");
    }
  }

  function goToDashboard() {
    navigate("/");
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm card">
        {status === "checking" ? (
          <p className="text-sm text-ink-200 text-center">Checking your link…</p>
        ) : status === "error" ? (
          <div className="text-center">
            <h1 className="mb-4 text-gold-400">Link invalid or expired</h1>
            <p className="text-sm text-ink-200">
              This password reset link is no longer valid — it may have already been used or
              expired.
            </p>
            <p className="text-sm text-ink-300 mt-3">
              <Link to="/forgot-password">Request a new link</Link> or{" "}
              <Link to="/login">back to sign in</Link>
            </p>
          </div>
        ) : status === "mfa" ? (
          <div className="text-left">
            <h1 className="mb-2 text-gold-400 text-center">Secure your account</h1>
            <p className="text-sm text-ink-300 text-center">
              Password reset. Optionally add two-factor authentication now.
            </p>
            <MfaSetup onComplete={goToDashboard} onSkip={goToDashboard} compact />
          </div>
        ) : (
          <>
            <h1 className="mb-4 text-gold-400 text-center">Choose a new password</h1>
            <form onSubmit={onSubmit} className="flex flex-col gap-3">
              <div>
                <label className="label">New password (min 8)</label>
                <input className="input" type="password" value={password} minLength={8}
                  onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required autoFocus />
              </div>
              <div>
                <label className="label">Confirm new password</label>
                <input className="input" type="password" value={confirmPassword} minLength={8}
                  onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password" required />
              </div>
              <label className="flex items-center gap-2 text-sm text-ink-300">
                <input type="checkbox" checked={disableMfa}
                  onChange={(e) => setDisableMfa(e.target.checked)} />
                Remove two-factor authentication (if you no longer have access to it)
              </label>
              {err && <p className="text-sm text-red-400">{err}</p>}
              <button className="btn-primary" disabled={status === "submitting"}>
                {status === "submitting" ? "Resetting…" : "Reset password"}
              </button>
              <p className="text-sm text-ink-300 text-center">
                <Link to="/login">Back to sign in</Link>
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
