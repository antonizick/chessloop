import { useState, useEffect } from "react";
import type { PracticeMode } from "@/types";
import { Tooltip } from "@/components/ui/Tooltip";

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
  isUnrated?: boolean;
  leechCount?: number;
}

// ── Data ──────────────────────────────────────────────────────────────────────

const MODES: { id: UiMode; label: string; desc: string; tooltip: string; icon: string }[] = [
  {
    id: "weakest",
    label: "Weakest First",
    desc: "Prioritises positions you struggle with most. Balances due items with new material.",
    tooltip: "This mode helps you focus on your weakest areas. It uses a smart system to show you the positions where you're most likely to make mistakes, mixed with new positions you haven't seen before. Think of it as a personalized practice plan that adapts to what you need to work on most.",
    icon: "⚡",
  },
  {
    id: "leech_drill",
    label: "Leech Drill",
    desc: "Targets positions you've missed 4+ times. Break bad patterns fast.",
    tooltip: "A 'leech' is a position you keep getting wrong — you've missed it at least 4 times. This mode shows only those tough positions so you can intensely focus on fixing your mistakes. It's perfect when you want to break a bad habit and master a position that's been giving you trouble.",
    icon: "🎯",
  },
  {
    id: "all_active",
    label: "All Active",
    desc: "Drills every position across all active libraries with equal weight — no SRS bias.",
    tooltip: "This mode treats all your positions equally, without favoring harder or easier ones. Every position you've saved gets equal attention. It's great for a broad review of everything you know, or if you just want to practice all your lines without any particular focus.",
    icon: "📚",
  },
];

const START_POSITIONS: { id: StartPosition; label: string; desc: string }[] = [
  {
    id: "auto",
    label: "SRS picks",
    desc: "The smart system chooses which position to show you based on what you need to practice most. It learns from your mistakes and adjusts to focus on your weak spots.",
  },
  {
    id: "first",
    label: "First move",
    desc: "Always start from the very beginning of each line. This helps you get comfortable with the opening moves and builds your understanding from the ground up.",
  },
  {
    id: "random",
    label: "Random",
    desc: "The system picks a random position from anywhere in your lines. This is unpredictable and can help you practice flexibility when you don't know where you'll be playing.",
  },
  {
    id: "mixed",
    label: "Mixed",
    desc: "A balanced approach: half the time you'll start from the first move, and half the time the smart system will choose. Best of both worlds.",
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
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <Tooltip key={opt.id} text={opt.desc} wide>
            <button
              onClick={() => onChange(opt.id)}
              className={value === opt.id ? "btn-primary" : "btn-ghost"}
            >
              {opt.label}
            </button>
          </Tooltip>
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

export function ModeEntry({ onStart, isLoading, error, isUnrated = false, leechCount = 0 }: Props) {
  const [mode, setMode] = useState<UiMode>("weakest");
  const [startPosition, setStartPosition] = useState<StartPosition>("first");

  // "all_active" overrides start_position to "random" — hide the selector for it
  const showStartPosition = mode !== "all_active" && mode !== "leech_drill";
  const hasNoLeeches = leechCount === 0;

  // Reset mode to "weakest" if leech_drill is selected but no leeches are available
  useEffect(() => {
    if (mode === "leech_drill" && hasNoLeeches) {
      setMode("weakest");
    }
  }, [mode, hasNoLeeches]);

  return (
    <div className="max-w-lg mx-auto mt-8 flex flex-col gap-6">
      <div>
        <h1>{isUnrated ? "Unrated Practice" : "Rated Practice"}</h1>
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
          {MODES.map((m) => {
            const isDisabled = m.id === "leech_drill" && hasNoLeeches;
            const tooltipText = isDisabled
              ? "You don't have any leeches yet in your active libraries. A 'leech' is a position you've missed 4 or more times—it's a position that keeps giving you trouble. As you practice and miss positions, they'll automatically be promoted to leech status when they reach 4 misses. Then you can come back and use this mode to focus intensely on breaking those bad patterns."
              : m.tooltip;
            return (
              <Tooltip key={m.id} text={tooltipText} disabled={isDisabled}>
                <button
                  onClick={() => !isDisabled && setMode(m.id)}
                  className={[
                    "card text-left transition-all min-h-24 w-full flex flex-col",
                    isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
                    mode === m.id ? "!border-gold-500 bg-gold-500/5" : !isDisabled ? "hover:border-ink-500" : "",
                  ].join(" ")}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-xl w-7 shrink-0 pt-0.5">{m.icon}</span>
                    <div className="flex-1">
                      <div className="font-semibold text-ink-100 text-sm">{m.label}</div>
                      <div className="text-xs text-ink-400 mt-0.5">{m.desc}</div>
                    </div>
                    {mode === m.id && <span className="text-gold-400 shrink-0 pt-0.5">✓</span>}
                  </div>
                </button>
              </Tooltip>
            );
          })}
        </div>
      </div>

      {/* ── Starting position (hidden for leech_drill + all_active) ── */}
      {showStartPosition && (
        <div className="flex flex-col gap-2">
          <Tooltip text="Choose where you want to start practicing each line: from the opening moves, a random position mid-line, or a mix of both.">
            <label className="text-xs font-semibold text-ink-400 uppercase tracking-wide cursor-help">
              Where to Start in Each Line
            </label>
          </Tooltip>
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
