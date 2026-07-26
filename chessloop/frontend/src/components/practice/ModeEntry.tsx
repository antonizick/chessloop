import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import type { PracticeMode } from "@/types";
import { Tooltip } from "@/components/ui/Tooltip";
import { librariesApi } from "@/api/libraries";

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
  // Omitted (not just empty) by callers that bypass this picker — e.g. the
  // dashboard's "practice weakest now" shortcut — so the backend falls back
  // to its default scope (all active libraries, no learned filter) instead
  // of interpreting an empty array as "nothing selected".
  libraryIds?: string[];
  learnedOnly?: boolean;
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

// ── Toggle switch ────────────────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
  disabled,
  title,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      title={title}
      className={[
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-150",
        checked ? "bg-green-500 border-green-500" : "bg-ink-600 border-ink-600",
        disabled ? "opacity-50 cursor-not-allowed" : "",
      ].join(" ")}
    >
      <span
        className={[
          "inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform duration-150",
          checked ? "translate-x-4" : "translate-x-0",
        ].join(" ")}
      />
    </button>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function ModeEntry({ onStart, isLoading, error, isUnrated = false, leechCount = 0 }: Props) {
  const [mode, setMode] = useState<UiMode>("weakest");
  const [startPosition, setStartPosition] = useState<StartPosition>("first");
  const [learnedOnly, setLearnedOnly] = useState(true);
  const [selectedLibraryIds, setSelectedLibraryIds] = useState<Set<string> | null>(null);

  const { data: libraries } = useQuery({
    queryKey: ["libraries"],
    queryFn: () => librariesApi.list(),
  });

  // Default-check every currently-active library, once, when the list loads.
  useEffect(() => {
    if (libraries && selectedLibraryIds === null) {
      setSelectedLibraryIds(new Set(libraries.filter((l) => l.is_active).map((l) => l.id)));
    }
  }, [libraries, selectedLibraryIds]);

  function toggleLibrary(id: string) {
    setSelectedLibraryIds((prev) => {
      const next = new Set(prev ?? []);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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

      {/* ── Libraries ── */}
      {libraries && libraries.length > 0 && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-ink-400 uppercase tracking-wide">
            Libraries
          </label>
          <div className="card flex flex-col gap-1.5 max-h-48 overflow-y-auto">
            {libraries.map((lib) => (
              <label
                key={lib.id}
                className="flex items-center gap-2 text-sm text-ink-200 cursor-pointer py-0.5"
              >
                <input
                  type="checkbox"
                  className="w-4 h-4 cursor-pointer shrink-0"
                  checked={selectedLibraryIds?.has(lib.id) ?? false}
                  onChange={() => toggleLibrary(lib.id)}
                />
                <span className="truncate">{lib.name}</span>
                {!lib.is_active && (
                  <span className="text-xs text-ink-500 shrink-0">(inactive)</span>
                )}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* ── Learned/Active lines only ── */}
      <div className="flex items-center justify-between">
        <Tooltip text="When on, only lines you've marked (or auto-marked) as learned are practiced. Turn off to also get quizzed on lines you haven't fully learned yet.">
          <span className="text-sm text-ink-200 cursor-help">Learned/Active lines only</span>
        </Tooltip>
        <ToggleSwitch checked={learnedOnly} onChange={() => setLearnedOnly((v) => !v)} />
      </div>

      <button
        className="btn-primary w-full py-3 text-base"
        onClick={() =>
          onStart({
            mode,
            startPosition,
            libraryIds: Array.from(selectedLibraryIds ?? []),
            learnedOnly,
          })
        }
        disabled={isLoading || selectedLibraryIds === null}
      >
        {isLoading ? "Starting…" : "Start Session →"}
      </button>
    </div>
  );
}
