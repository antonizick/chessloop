import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/api/auth";

interface MfaSetupProps {
  onComplete: () => void;
  onSkip?: () => void;
  compact?: boolean;
}

export function MfaSetup({ onComplete, onSkip, compact }: MfaSetupProps) {
  const qc = useQueryClient();

  const [setupResult, setSetupResult] = useState<{ secret: string; otpauth_url: string; qr_code_b64: string } | null>(null);
  const [totp, setTotp] = useState("");
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);
  const [showManualEntry, setShowManualEntry] = useState(false);

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
      onComplete();
    },
    onError: (e: any) => setConfirmMsg(e.message ?? "Failed"),
  });

  if (!setupResult) {
    return (
      <div>
        <p className="text-sm text-ink-300 mt-2">
          Add a TOTP authenticator (Authy, 1Password, Google Authenticator).
        </p>
        <div className="flex items-center gap-3 mt-3">
          <button className="btn-primary" onClick={() => beginMfa.mutate()} disabled={beginMfa.isPending}>
            {beginMfa.isPending ? "Starting…" : "Set up MFA"}
          </button>
          {onSkip && (
            <button className="btn-secondary" onClick={onSkip}>
              Skip for now
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-3">
      <p className="text-sm">
        Scan this QR code with your authenticator app, then enter the 6-digit code.
      </p>
      <div className="flex justify-center">
        <img
          src={`data:image/png;base64,${setupResult.qr_code_b64}`}
          alt="Scan with your authenticator app"
          className={`rounded border border-ink-600 bg-white p-2 ${compact ? "w-40 h-40" : "w-48 h-48"}`}
        />
      </div>
      {!showManualEntry ? (
        <button
          className="text-sm text-gold-400 hover:text-gold-300 transition-colors text-center"
          onClick={() => setShowManualEntry(true)}
        >
          Can't scan? Enter manually
        </button>
      ) : (
        <div className="p-2 rounded border border-ink-600 bg-ink-900/50">
          <p className="text-xs text-ink-400 mb-1">Secret key:</p>
          <code className="text-xs break-all font-mono text-ink-200">{setupResult.secret}</code>
        </div>
      )}
      <input
        className="input tracking-widest text-center"
        value={totp}
        onChange={(e) => setTotp(e.target.value)}
        placeholder="123456"
        maxLength={6}
        autoFocus
      />
      <div className="flex items-center gap-3">
        <button
          className="btn-primary flex-1"
          onClick={() => confirmMfa.mutate(totp)}
          disabled={confirmMfa.isPending}
        >
          {confirmMfa.isPending ? "Confirming…" : "Confirm & enable MFA"}
        </button>
        {onSkip && (
          <button className="btn-secondary" onClick={onSkip}>
            Skip for now
          </button>
        )}
      </div>
      {confirmMsg && <p className="text-sm text-ink-300">{confirmMsg}</p>}
    </div>
  );
}
