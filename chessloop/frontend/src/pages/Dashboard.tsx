import { useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { librariesApi } from "@/api/libraries";
import { practiceApi } from "@/api/practice";
import { statsApi } from "@/api/stats";
import { useAuthStore } from "@/stores/auth";
import type { MasteryBadge, MasteryEntry } from "@/types";

// ── Badge strip ───────────────────────────────────────────────────────────────

const BADGE_RING: Record<MasteryBadge, string> = {
  not_started: "border-ink-600 text-ink-500",
  learning:    "border-orange-700 text-orange-400",
  developing:  "border-yellow-700 text-yellow-400",
  advanced:    "border-sky-700 text-sky-400",
  mastered:    "border-gold-500 text-gold-400",
};

const BADGE_ICON: Record<MasteryBadge, string> = {
  not_started: "○",
  learning:    "◔",
  developing:  "◑",
  advanced:    "◕",
  mastered:    "●",
};

function MasteryBadgeStrip({ entries }: { entries: MasteryEntry[] }) {
  if (!entries.length) return null;
  const active = entries.filter((e) => e.total_positions > 0).slice(0, 8);
  if (!active.length) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {active.map((e) => (
        <Link
          key={e.library_id}
          to={`/libraries/${e.library_id}`}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-opacity hover:opacity-80 ${BADGE_RING[e.badge]}`}
          title={`${e.library_name} — ${e.mastery_pct}% mastered`}
        >
          <span>{BADGE_ICON[e.badge]}</span>
          <span className="max-w-[120px] truncate">{e.library_name}</span>
        </Link>
      ))}
    </div>
  );
}

// ── Active opening card ───────────────────────────────────────────────────────

const COLOR_DOT: Record<string, string> = {
  white: "bg-white",
  black: "bg-ink-400",
  both:  "bg-gradient-to-r from-white to-ink-400",
};

function ActiveOpeningCards() {
  const { data: libraries } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const { data: mastery } = useQuery({
    queryKey: ["stats-mastery"],
    queryFn: statsApi.mastery,
    staleTime: 60_000,
  });

  const active = libraries?.filter((l) => l.is_active) ?? [];
  if (!active.length) {
    return (
      <p className="text-ink-400 text-sm">
        No active openings.{" "}
        <Link to="/libraries/new" className="text-gold-400 hover:underline">
          Create one
        </Link>.
      </p>
    );
  }

  const masteryMap = new Map(mastery?.libraries.map((m) => [m.library_id, m]));

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {active.slice(0, 6).map((lib) => {
        const m = masteryMap.get(lib.id);
        const pct = m?.mastery_pct ?? 0;
        return (
          <Link
            key={lib.id}
            to={`/libraries/${lib.id}`}
            className="card hover:border-ink-500 transition-colors"
          >
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${COLOR_DOT[lib.color]}`} />
              <span className="font-medium text-ink-100 truncate">{lib.name}</span>
            </div>
            {m && m.total_positions > 0 ? (
              <>
                <div className="w-full bg-ink-700 rounded-full h-1.5 mt-1">
                  <div
                    className="h-1.5 rounded-full bg-gold-500"
                    style={{ width: `${Math.max(pct, 2)}%` }}
                  />
                </div>
                <div className="text-xs text-ink-400 mt-1">{pct}% mastered</div>
              </>
            ) : (
              <div className="text-xs text-ink-500 mt-1">Not started</div>
            )}
          </Link>
        );
      })}
    </div>
  );
}

// ── Weak lines teaser ─────────────────────────────────────────────────────────

function WeakLinesTeaser() {
  const { data: leeches } = useQuery({
    queryKey: ["stats-leeches"],
    queryFn: statsApi.leeches,
    staleTime: 60_000,
  });

  if (!leeches?.length) return null;

  return (
    <div className="card border-red-900/50 bg-red-950/20">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-red-400">
          ⚠ {leeches.length} leech{leeches.length !== 1 ? "es" : ""} need attention
        </h3>
        <Link to="/stats" className="text-xs text-ink-400 hover:text-gold-400">
          See all →
        </Link>
      </div>
      <div className="flex flex-col gap-1">
        {leeches.slice(0, 3).map((l) => (
          <div key={l.practice_position_id} className="text-xs text-ink-400 flex justify-between">
            <span className="truncate max-w-[240px]">
              {l.library_name}
              {l.line_name ? ` · "${l.line_name}"` : ""} — move {l.move_index + 1}
            </span>
            <span className="text-red-500 shrink-0 ml-2">{l.leech_count}✗</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  const { data: libraries } = useQuery({
    queryKey: ["libraries"],
    queryFn: librariesApi.list,
  });

  const { data: dueCount } = useQuery({
    queryKey: ["due-count"],
    queryFn: () => practiceApi.dueCount(),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const { data: mastery } = useQuery({
    queryKey: ["stats-mastery"],
    queryFn: statsApi.mastery,
    staleTime: 60_000,
  });

  function startWeakest() {
    navigate("/practice", { state: { autoMode: "weakest" } });
  }

  const active = libraries?.filter((l) => l.is_active) ?? [];
  const dueTotal = dueCount?.count ?? 0;
  const newCount = dueCount?.new ?? 0;
  const leechCount = dueCount?.leeches ?? 0;

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div>
        <h1>Welcome back{user ? `, ${user.username}` : ""}.</h1>
        <p className="text-ink-300 mt-1 text-sm">Your opening trainer dashboard.</p>
      </div>

      {/* Mastery badge strip */}
      {mastery?.libraries && mastery.libraries.length > 0 && (
        <MasteryBadgeStrip entries={mastery.libraries} />
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="text-xs uppercase text-ink-400 tracking-wide">Active openings</div>
          <div className="text-3xl font-bold text-gold-400 mt-2">{active.length}</div>
          <div className="text-xs text-ink-500 mt-1">{libraries?.length ?? 0} total</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-ink-400 tracking-wide">Due today</div>
          <div className={`text-3xl font-bold mt-2 ${dueTotal > 0 ? "text-gold-400" : "text-ink-500"}`}>
            {dueTotal}
          </div>
          <div className="text-xs text-ink-500 mt-1">{newCount} new · {leechCount} leeches</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-ink-400 tracking-wide">Libraries</div>
          <div className="text-3xl font-bold text-ink-200 mt-2">{libraries?.length ?? 0}</div>
          <div className="text-xs text-ink-500 mt-1">{active.length} active</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-ink-400 tracking-wide">Mastered</div>
          <div className="text-3xl font-bold text-green-400 mt-2">
            {mastery?.libraries.filter((m) => m.badge === "mastered").length ?? 0}
          </div>
          <div className="text-xs text-ink-500 mt-1">of {mastery?.libraries.length ?? 0} libs</div>
        </div>
      </div>

      {/* Practice weakest CTA */}
      {dueTotal > 0 && (
        <div className="card bg-gold-900/20 border-gold-700/40 flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gold-300">
              {dueTotal} position{dueTotal !== 1 ? "s" : ""} ready for review
            </h3>
            <p className="text-sm text-ink-400 mt-0.5">
              Practice your weakest positions across all active libraries.
            </p>
          </div>
          <button
            onClick={startWeakest}
            className="btn-primary shrink-0"
          >
            Practice weakest now →
          </button>
        </div>
      )}

      {/* Active opening cards */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-ink-200">Active openings</h2>
          <Link to="/libraries" className="text-sm text-ink-400 hover:text-gold-400">
            All libraries →
          </Link>
        </div>
        <ActiveOpeningCards />
      </section>

      {/* Weak lines teaser */}
      <WeakLinesTeaser />

      {/* Quick actions */}
      <div className="flex flex-wrap gap-3">
        <Link to="/libraries/new" className="btn-primary">+ New library</Link>
        <Link to="/practice" className="btn-ghost">Practice board</Link>
        <Link to="/stats" className="btn-ghost">View stats</Link>
        <Link to="/public" className="btn-ghost">Public libraries</Link>
      </div>
    </div>
  );
}
