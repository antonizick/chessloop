import { useState } from "react";
import type { PracticeMode } from "@/types";

export type StartPosition = "auto" | "first" | "random" | "mixed";

/**
 * "all_active" is a UI-only mode: it maps to backend mode="weakest" with
 * scope.start_position="random" so every position in every active library
 * gets equal exposure (no SRS weighting bias).
 */
export type UiMode = PracticeMode | "all_active";

export interface PracticeOptions {
  mode: UiMode;
  startPosition: StartPosition;
}

interface Props {
  onStart: (opts: PracticeOptions) => void;
  isLoading: boolean;
  error?: string | null;
}

// ── Data ──────────────────────────────────────────────────────────────────────

const MODES: { id: UiMode; label: string; desc: string; icon: string }[] = [
  {
    id: "weakest",
    label: "Weakest First",
    desc: "Prioritises positions you struggle with most. Balances due items with new material.",
    icon: "⚡",
  },
  {
    id: "leech_drill",
    label: "Leech Drill",
    desc: "Targets positions you've missed 4+ times. Break bad patterns fast.",
    icon: "🎯",
  },
  {
    id: "all_active",
    label: "All Active",
    desc: "Drills every position across all active libraries with equal weight — no SRS bias.",
    icon: "📚",
  },
];

const START_POSITIONS: { id: StartPosition; label: string; desc: string }[] = [
  {
    id: "auto",
    label: "SRS picks",
    desc: "The algorithm selects whichever position you need most.",
  },
  {
    id: "first",
    label: "First move",
    desc: "Always drill from the very first move of each line.",
  },
  {
    id: "random",
    label: "Random",
    desc: "Drop into any position in the dataset at random.",
  },
  {
    id: "mixed",
    label: "Mixed",
    desc: "Each round: 50% chance of first move, 50% SRS-selected.",
  },
];

// ── Segmented control ─────────────────────────────────────────────────────────

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string; desc: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex rounded-lg overflow-hidden border border-ink-700">
        {options.map((opt, i) => (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={[
              "flex-1 py-2 text-sm font-medium transition-colors",
              i > 0 ? "border-l border-ink-700" : "",
              value === opt.id
                ? "bg-gold-500 text-ink-900"
                : "text-ink-300 hover:text-ink-100 hover:bg-ink-700/50",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {options.find((o) => o.id === value) && (
        <p className="text-xs text-ink-400 px-1">
          {options.find((o) => o.id === value)!.desc}
        </p>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function ModeEntry({ onStart, isLoading, error }: Props) {
  const [mode, setMode] = useState<UiMode>("weakest");
  const [startPosition, setStartPosition] = useState<StartPosition>("first");

  // "all_active" overrides start_position to "random" — hide the selector for it
  const showStartPosition = mode !== "all_active" && mode !== "leech_drill";

  return (
    <div className="max-w-lg mx-auto mt-8 flex flex-col gap-6">
      <div>
        <h1>Rated Practice</h1>
        <p className="text-ink-300 text-sm mt-1">
          Choose a session mode and start drilling your openings.
        </p>
      </div>

      {error && (
        <div className="text-red-400 text-sm px-3 py-2 rounded bg-red-500/10 border border-red-500/20">
          {error}
        </div>
      )}

      {/* ── Session mode ── */}
      <div className="flex flex-col gap-2">
        <label className="text-xs font-semibold text-ink-400 uppercase tracking-wide">
          Session Mode
        </label>
        <div className="flex flex-col gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={[
                "card text-left transition-all cursor-pointer",
                mode === m.id ? "!border-gold-500 bg-gold-500/5" : "hover:border-ink-500",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <span className="text-xl w-7 shrink-0">{m.icon}</span>
                <div className="flex-1">
                  <div className="font-semibold text-ink-100 text-sm">{m.label}</div>
                  <div className="text-xs text-ink-400 mt-0.5">{m.desc}</div>
                </div>
                {mode === m.id && <span className="text-gold-400 shrink-0">✓</span>}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Starting position (hidden for leech_drill + all_active) ── */}
      {showStartPosition && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-ink-400 uppercase tracking-wide">
            Where to Start in Each Line
          </label>
          <SegmentedControl
            options={START_POSITIONS}
            value={startPosition}
            onChange={setStartPosition}
          />
        </div>
      )}

      <button
        className="btn-primary w-full py-3 text-base"
        onClick={() => onStart({ mode, startPosition })}
        disabled={isLoading}
      >
        {isLoading ? "Starting…" : "Start Session →"}
      </button>
    </div>
  );
}
