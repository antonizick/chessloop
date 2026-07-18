import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

export function VerifyEmail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);
  const [status, setStatus] = useState<"verifying" | "error">("verifying");
  const started = useRef(false);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      return;
    }
    if (started.current) return;
    started.current = true;

    (async () => {
      try {
        const res = await authApi.verifyEmail(token);
        setTokens(res.access_token, res.refresh_token);
        const me = await authApi.me();
        setUser(me);
        navigate("/");
      } catch {
        setStatus("error");
      }
    })();
  }, [searchParams, navigate, setTokens, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm card text-center">
        {status === "verifying" ? (
          <p className="text-sm text-ink-200">Verifying your email…</p>
        ) : (
          <>
            <h1 className="mb-4 text-gold-400">Verification failed</h1>
            <p className="text-sm text-ink-200">
              This link is invalid or has expired.
            </p>
            <p className="text-sm text-ink-300 mt-3">
              <Link to="/register">Register again</Link> or{" "}
              <Link to="/login">back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
