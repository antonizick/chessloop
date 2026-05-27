import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { ttsService } from "@/services/textToSpeech";

// ── Option lists ──────────────────────────────────────────────────────────────

const APP_THEMES = [
  { value: "dark",  label: "Dark",  desc: "Deep ink-black with gold accents" },
  { value: "light", label: "Light", desc: "Bright background with dark text" },
] as const;

const BOARD_THEMES = [
  { value: "brown",  label: "Brown",  desc: "Classic walnut — the Lichess default" },
  { value: "blue",   label: "Blue",   desc: "Slate blue-grey — easy on the eyes" },
  { value: "green",  label: "Green",  desc: "Traditional tournament green" },
  { value: "ice",    label: "Ice",    desc: "Cream & gold — retro over-the-board feel" },
  { value: "purple", label: "Purple", desc: "Bold violet contrast" },
] as const;

const PIECE_SETS = [
  { value: "cburnett", label: "CBurnett",  desc: "The Staunton standard — Lichess default" },
  { value: "alpha",    label: "Alpha",     desc: "Flat, high-contrast — clean and minimal" },
  { value: "mono",     label: "Mono",      desc: "Full grayscale — no colour distraction" },
  { value: "shadow",   label: "Shadow",    desc: "Drop-shadow lift — subtle 3-D effect" },
] as const;

const PREVIEW_FEN = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2";

export function Settings() {
  const qc = useQueryClient();
  const setUser = useAuthStore((s) => s.setUser);
  const user = useAuthStore((s) => s.user);

  // ── Account data ──────────────────────────────────────────────────────────

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const u = await authApi.me();
      setUser(u);
      return u;
    },
  });

  // ── MFA state ─────────────────────────────────────────────────────────────

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

  // ── Load available voices ──────────────────────────────────────────────────

  useEffect(() => {
    const loadVoices = () => {
      const voices = ttsService.getAvailableVoices();
      setAvailableVoices(voices);
    };

    loadVoices();
    // Some browsers load voices asynchronously
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);

    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, []);

  // ── Preferences ────────────────────────────────────────────────────────────

  // Local optimistic state for instant preview
  const [localTheme,         setLocalTheme]         = useState<string>(user?.theme              ?? "dark");
  const [localBoardTheme,    setLocalBoardTheme]    = useState<string>(user?.board_theme        ?? "brown");
  const [localPieceSet,      setLocalPieceSet]      = useState<string>(user?.piece_set          ?? "cburnett");
  const [localSoundsOn,      setLocalSoundsOn]      = useState<boolean>(user?.sounds_on         ?? true);
  const [localTtsEnabled,    setLocalTtsEnabled]    = useState<boolean>(user?.tts_enabled       ?? true);
  const [localTtsVoice,      setLocalTtsVoice]      = useState<string>(user?.tts_voice          ?? "Microsoft Zira");
  const [localBoostVisibility, setLocalBoostVisibility] = useState<boolean>(user?.boost_visibility ?? false);
  const [prefSaved, setPrefSaved] = useState(false);
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);

  const updatePrefs = useMutation({
    mutationFn: authApi.updatePreferences,
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      qc.invalidateQueries({ queryKey: ["me"] });
      setPrefSaved(true);
      setTimeout(() => setPrefSaved(false), 2000);
    },
  });

  function savePreferences() {
    updatePrefs.mutate({
      theme: localTheme,
      board_theme: localBoardTheme,
      piece_set: localPieceSet,
      sounds_on: localSoundsOn,
      tts_enabled: localTtsEnabled,
      tts_voice: localTtsVoice,
      boost_visibility: localBoostVisibility,
    });
    // Apply theme immediately to root element
    applyTheme(localTheme);
    // Update TTS service settings
    ttsService.setEnabled(localTtsEnabled);
    ttsService.setDefaultVoice(localTtsVoice);
    // Apply boost visibility immediately
    applyBoostVisibility(localBoostVisibility);
  }

  function applyTheme(themeName: string) {
    const html = document.documentElement;
    if (themeName === "light") {
      html.classList.add("light-theme");
    } else {
      html.classList.remove("light-theme");
    }
  }

  function applyBoostVisibility(on: boolean) {
    document.documentElement.classList.toggle("boost-visibility", on);
  }

  function toggleBoostVisibility(newValue: boolean) {
    setLocalBoostVisibility(newValue);
    updatePrefs.mutate({ boost_visibility: newValue });
    applyBoostVisibility(newValue);
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <h1>Settings</h1>

      {/* ── Account info ─────────────────────────────────────────────────── */}
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

      {/* ── App theme ─────────────────────────────────────────────────────── */}
      <div className="card flex flex-col gap-5">
        <h2>App theme</h2>
        <div>
          <label className="label">Theme</label>
          <div className="grid grid-cols-2 gap-2 mt-1">
            {APP_THEMES.map((t) => (
              <button
                key={t.value}
                onClick={() => setLocalTheme(t.value)}
                className={`rounded-md border p-2.5 text-left text-sm transition-colors ${
                  localTheme === t.value
                    ? "border-gold-500 bg-gold-500/10 text-gold-300"
                    : "border-ink-600 text-ink-300 hover:border-ink-400"
                }`}
              >
                <div className="font-medium">{t.label}</div>
                <div className="text-xs text-ink-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Boost Visibility */}
        <div className="flex items-center justify-between py-1">
          <div>
            <div className="text-sm font-medium text-ink-100">Boost visibility</div>
            <div className="text-xs text-ink-400 mt-0.5">Larger text, high-contrast labels on dark theme</div>
          </div>
          <button
            onClick={() => toggleBoostVisibility(!localBoostVisibility)}
            className={`relative w-11 h-6 rounded-full transition-colors ${
              localBoostVisibility ? "bg-gold-500" : "bg-ink-600"
            }`}
            role="switch"
            aria-checked={localBoostVisibility}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                localBoostVisibility ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>

      {/* ── Board appearance ──────────────────────────────────────────────── */}
      <div className="card flex flex-col gap-5">
        <h2>Board appearance</h2>

        {/* Live preview */}
        <div className="flex justify-center">
          <ChessboardWrapper
            fen={PREVIEW_FEN}
            orientation="white"
            viewOnly
            size={240}
            boardTheme={localBoardTheme}
            pieceSet={localPieceSet}
          />
        </div>

        {/* Board theme */}
        <div>
          <label className="label">Board theme</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-1">
            {BOARD_THEMES.map((t) => (
              <button
                key={t.value}
                onClick={() => setLocalBoardTheme(t.value)}
                className={`rounded-md border p-2.5 text-left text-sm transition-colors ${
                  localBoardTheme === t.value
                    ? "border-gold-500 bg-gold-500/10 text-gold-300"
                    : "border-ink-600 text-ink-300 hover:border-ink-400"
                }`}
              >
                <div className="font-medium">{t.label}</div>
                <div className="text-xs text-ink-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Piece set */}
        <div>
          <label className="label">Piece set</label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-1">
            {PIECE_SETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setLocalPieceSet(p.value)}
                className={`rounded-md border p-2.5 text-left text-sm transition-colors ${
                  localPieceSet === p.value
                    ? "border-gold-500 bg-gold-500/10 text-gold-300"
                    : "border-ink-600 text-ink-300 hover:border-ink-400"
                }`}
              >
                <div className="font-medium">{p.label}</div>
                <div className="text-xs text-ink-500 mt-0.5">{p.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Sounds */}
        <div className="flex items-center justify-between py-1">
          <div>
            <div className="text-sm font-medium text-ink-100">Sound effects</div>
            <div className="text-xs text-ink-400 mt-0.5">Move clicks, correct chime, wrong buzz</div>
          </div>
          <button
            onClick={() => setLocalSoundsOn((v) => !v)}
            className={`relative w-11 h-6 rounded-full transition-colors ${
              localSoundsOn ? "bg-gold-500" : "bg-ink-600"
            }`}
            role="switch"
            aria-checked={localSoundsOn}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                localSoundsOn ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>

      {/* ── Audio Settings ────────────────────────────────────────────────── */}
      <div className="card flex flex-col gap-5">
        <h2>Audio</h2>

        {/* Text-to-speech toggle */}
        <div className="flex items-center justify-between py-1">
          <div>
            <div className="text-sm font-medium text-ink-100">Read move notes aloud</div>
            <div className="text-xs text-ink-400 mt-0.5">Speak move instructions during practice</div>
          </div>
          <button
            onClick={() => setLocalTtsEnabled((v) => !v)}
            className={`relative w-11 h-6 rounded-full transition-colors ${
              localTtsEnabled ? "bg-gold-500" : "bg-ink-600"
            }`}
            role="switch"
            aria-checked={localTtsEnabled}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                localTtsEnabled ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Voice selector */}
        {localTtsEnabled && (
          <div>
            <label className="label">Voice</label>
            <select
              value={localTtsVoice}
              onChange={(e) => setLocalTtsVoice(e.target.value)}
              className="w-full px-3 py-2 rounded bg-ink-700 border border-ink-600 text-ink-100 text-sm focus:outline-none focus:border-gold-500 focus:ring-1 focus:ring-gold-400"
            >
              {availableVoices.length === 0 ? (
                <option>Microsoft Zira (default)</option>
              ) : (
                availableVoices.map((voice) => (
                  <option key={voice.name} value={voice.name}>
                    {voice.name}
                  </option>
                ))
              )}
            </select>
            <p className="text-xs text-ink-400 mt-2">Default voice: Microsoft Zira (rate 1.0, pitch 1.0)</p>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1 border-t border-ink-700">
          <button
            className="btn-primary"
            onClick={savePreferences}
            disabled={updatePrefs.isPending}
          >
            {updatePrefs.isPending ? "Saving…" : "Save preferences"}
          </button>
          {prefSaved && (
            <span className="text-sm text-green-400">✓ Saved</span>
          )}
        </div>
      </div>

      {/* ── Two-factor auth ───────────────────────────────────────────────── */}
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
