import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

export function Settings() {
  const qc = useQueryClient();
  const setUser = useAuthStore((s) => s.setUser);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const u = await authApi.me();
      setUser(u);
      return u;
    },
  });

  const [setupResult, setSetupResult] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [totp, setTotp] = useState("");
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);

  const beginMfa = useMutation({
    mutationFn: authApi.mfaSetup,
    onSuccess: (r) => setSetupResult(r),
  });
  const confirmMfa = useMutation({
    mutationFn: (code: string) => authApi.mfaConfirm(code),
    onSuccess: () => {
      setConfirmMsg("MFA enabled.");
      setSetupResult(null);
      setTotp("");
      qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e: any) => setConfirmMsg(e.message ?? "Failed"),
  });

  return (
    <div className="flex flex-col gap-6 max-w-xl">
      <h1>Settings</h1>

      <div className="card">
        <h2>Account</h2>
        <dl className="mt-2 grid grid-cols-[120px_1fr] gap-y-1 text-sm">
          <dt className="text-ink-300">Username</dt><dd>{me?.username}</dd>
          <dt className="text-ink-300">Email</dt><dd>{me?.email}</dd>
          <dt className="text-ink-300">Role</dt><dd>{me?.role}</dd>
          <dt className="text-ink-300">MFA</dt>
          <dd>{me?.mfa_enabled ? "Enabled" : "Disabled"}</dd>
        </dl>
      </div>

      <div className="card">
        <h2>Two-factor auth</h2>
        {me?.mfa_enabled ? (
          <p className="text-sm text-ink-300 mt-2">TOTP MFA is active on your account.</p>
        ) : !setupResult ? (
          <>
            <p className="text-sm text-ink-300 mt-2">
              Add a TOTP authenticator (Authy, 1Password, Google Authenticator).
            </p>
            <button className="btn-primary mt-3" onClick={() => beginMfa.mutate()}>
              Set up MFA
            </button>
          </>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-sm">
              Scan or paste this URI into your authenticator, then enter the 6-digit code.
            </p>
            <code className="text-xs break-all bg-ink-900 p-2 rounded border border-ink-700">
              {setupResult.otpauth_url}
            </code>
            <p className="text-xs text-ink-400">Secret: <span className="font-mono">{setupResult.secret}</span></p>
            <input
              className="input tracking-widest text-center mt-2"
              value={totp}
              onChange={(e) => setTotp(e.target.value)}
              placeholder="123456"
              maxLength={6}
            />
            <button className="btn-primary" onClick={() => confirmMfa.mutate(totp)}>
              Confirm
            </button>
            {confirmMsg && <p className="text-sm text-ink-300">{confirmMsg}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
