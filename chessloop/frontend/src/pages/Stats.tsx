import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { statsApi } from "@/api/stats";
import type { MasteryBadge, MasteryEntry, HeatmapBucket, LibraryTrendSeries, TrendGranularity, TrendRange } from "@/types";

// ── Badge config ──────────────────────────────────────────────────────────────

const BADGE_CONFIG: Record<MasteryBadge, { label: string; color: string; bg: string }> = {
  not_started: { label: "Not started",  color: "text-ink-400",   bg: "bg-ink-700" },
  learning:    { label: "Learning",     color: "text-orange-400", bg: "bg-orange-900/40" },
  developing:  { label: "Developing",   color: "text-yellow-400", bg: "bg-yellow-900/40" },
  advanced:    { label: "Advanced",     color: "text-sky-400",    bg: "bg-sky-900/40" },
  mastered:    { label: "Mastered",     color: "text-gold-400",   bg: "bg-gold-900/30" },
};

const COLOR_DOT: Record<string, string> = {
  white: "bg-white",
  black: "bg-ink-300",
  both:  "bg-gradient-to-r from-white to-ink-300",
};

// ── Accuracy trend chart ──────────────────────────────────────────────────────

const TREND_PALETTE = [
  "#c79a2d", "#38bdf8", "#a78bfa", "#fb923c",
  "#34d399", "#f472b6", "#a3e635", "#f87171",
];
const SVG_VW = 800, SVG_VH = 200;
const PAD_L = 44, PAD_R = 16, PAD_T = 12, PAD_B = 28;
const PLOT_W = SVG_VW - PAD_L - PAD_R;
const PLOT_H = SVG_VH - PAD_T - PAD_B;

function trendColor(i: number) { return TREND_PALETTE[i % TREND_PALETTE.length]; }

function formatTrendLabel(label: string, granularity: TrendGranularity): string {
  if (granularity === "weekly") {
    const [year, week] = label.split("-W");
    return `W${parseInt(week)} '${year.slice(2)}`;
  }
  const d = new Date(label + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function xStride(n: number, granularity: TrendGranularity): number {
  if (granularity === "weekly") return 1;
  if (n <= 14) return 1;
  if (n <= 31) return 7;
  if (n <= 90) return 14;
  return Math.ceil(n / 10);
}

function buildPolylinePoints(series: LibraryTrendSeries, n: number): string {
  return series.points.map((pt, i) => {
    const x = PAD_L + (i / Math.max(n - 1, 1)) * PLOT_W;
    const y = PAD_T + (1 - pt.accuracy) * PLOT_H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

// ── Accuracy trend graph ─────────────────────────────────────────────────────

function AccuracyTrendGraph() {
  const [range, setRange] = useState<TrendRange>(90);
  const [granularity, setGranularity] = useState<TrendGranularity>("daily");
  const [initialized, setInitialized] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["stats-accuracy-trend", range, granularity],
    queryFn: () => statsApi.accuracyTrend(range, granularity),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!initialized && data && range === 90) {
      const activeDays = data.date_labels.filter((_, i) =>
        data.series.some(s => s.points[i]?.total > 0)
      ).length;
      if (activeDays < 60) setRange(30);
      setInitialized(true);
    }
  }, [data, initialized, range]);

  if (isLoading) {
    return <div className="h-32 flex items-center justify-center text-ink-400 text-sm">Loading…</div>;
  }

  if (!data?.series.length) {
    return (
      <div className="flex items-center justify-center h-40 text-ink-400 text-sm">
        No practice data yet. Start a session to see accuracy trends.
      </div>
    );
  }

  const n = data.date_labels.length;
  const stride = xStride(n, granularity);

  return (
    <div className="flex flex-col gap-4">
      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1">
          {([30, 90, 0] as TrendRange[]).map((d) => (
            <button
              key={d}
              onClick={() => setRange(d)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                range === d
                  ? "bg-gold-500 text-ink-900"
                  : "text-ink-400 hover:bg-ink-700"
              }`}
            >
              {d === 0 ? "All" : `${d}d`}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(["daily", "weekly"] as TrendGranularity[]).map((g) => (
            <button
              key={g}
              onClick={() => setGranularity(g)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                granularity === g
                  ? "bg-ink-600 text-ink-100"
                  : "text-ink-400 hover:bg-ink-700"
              }`}
            >
              {g === "daily" ? "Daily" : "Weekly"}
            </button>
          ))}
        </div>
      </div>

      {/* SVG chart */}
      <svg
        viewBox={`0 0 ${SVG_VW} ${SVG_VH}`}
        width="100%"
        style={{ display: "block" }}
        aria-label="Accuracy over time by library"
      >
        {/* Y-axis gridlines and labels */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((pct) => {
          const y = PAD_T + (1 - pct) * PLOT_H;
          return (
            <g key={pct}>
              <line
                x1={PAD_L}
                y1={y}
                x2={SVG_VW - PAD_R}
                y2={y}
                stroke="#1a1a1f"
                strokeWidth={1}
              />
              <text
                x={PAD_L - 4}
                y={y + 4}
                textAnchor="end"
                fontSize={9}
                fill="#5a5a6b"
              >
                {Math.round(pct * 100)}%
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        {data.date_labels.map((label, i) => {
          if (i % stride !== 0) return null;
          const x = PAD_L + (i / Math.max(n - 1, 1)) * PLOT_W;
          return (
            <text
              key={label}
              x={x}
              y={SVG_VH - 4}
              textAnchor="middle"
              fontSize={8}
              fill="#5a5a6b"
            >
              {formatTrendLabel(label, granularity)}
            </text>
          );
        })}

        {/* Trend lines per library */}
        {data.series.map((series, idx) => {
          const color = trendColor(idx);
          const pts = buildPolylinePoints(series, n);
          return (
            <g key={series.library_id}>
              <polyline
                points={pts}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={0.9}
              />
              {/* Data point circles */}
              {series.points.map((pt, i) => {
                if (pt.total === 0) return null;
                const x = PAD_L + (i / Math.max(n - 1, 1)) * PLOT_W;
                const y = PAD_T + (1 - pt.accuracy) * PLOT_H;
                return (
                  <circle
                    key={i}
                    cx={x}
                    cy={y}
                    r={3}
                    fill={color}
                    stroke="#121215"
                    strokeWidth={1}
                  >
                    <title>
                      {formatTrendLabel(pt.date, granularity)}
                      {"\n"}
                      {series.library_name}: {Math.round(pt.accuracy * 100)}%
                      {"\n"}
                      ({pt.correct}/{pt.total} correct)
                    </title>
                  </circle>
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {data.series.map((series, idx) => (
          <div key={series.library_id} className="flex items-center gap-1.5 text-xs text-ink-300">
            <svg width={16} height={4}>
              <line x1={0} y1={2} x2={16} y2={2}
                    stroke={trendColor(idx)} strokeWidth={2} />
            </svg>
            {series.library_name}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Accuracy heatmap bar (custom SVG) ─────────────────────────────────────────

function HeatmapBar({ buckets }: { buckets: HeatmapBucket[] }) {
  if (buckets.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-ink-400 text-sm">
        No practice data yet. Start a session to see accuracy trends.
      </div>
    );
  }

  const SVG_H = 120;
  const BAR_W = 28;
  const GAP = 6;
  const LABEL_H = 20;
  const totalW = buckets.length * (BAR_W + GAP) - GAP;

  return (
    <div className="overflow-x-auto">
      <svg
        width={totalW}
        height={SVG_H + LABEL_H}
        className="block min-w-full"
        aria-label="Accuracy by move number"
      >
        {buckets.map((b, i) => {
          const x = i * (BAR_W + GAP);
          const barH = Math.max(4, Math.round(b.accuracy * SVG_H));
          const y = SVG_H - barH;
          // Color: green ≥ 0.8, yellow 0.5-0.8, red < 0.5
          const fill =
            b.accuracy >= 0.8
              ? "#a3e635"   // lime-400
              : b.accuracy >= 0.5
              ? "#facc15"   // yellow-400
              : "#f87171";  // red-400

          return (
            <g key={b.move_number}>
              <title>
                Move {b.move_number}: {Math.round(b.accuracy * 100)}% ({b.correct}/{b.total})
              </title>
              {/* Background track */}
              <rect x={x} y={0} width={BAR_W} height={SVG_H} rx={3} fill="#1e293b" />
              {/* Accuracy fill */}
              <rect x={x} y={y} width={BAR_W} height={barH} rx={3} fill={fill} opacity={0.85} />
              {/* Move number label */}
              <text
                x={x + BAR_W / 2}
                y={SVG_H + LABEL_H - 4}
                textAnchor="middle"
                fontSize={9}
                fill="#94a3b8"
              >
                {b.move_number}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Mastery card ──────────────────────────────────────────────────────────────

function MasteryCard({ entry }: { entry: MasteryEntry }) {
  const badge = BADGE_CONFIG[entry.badge];
  const pct = entry.mastery_pct;

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`shrink-0 w-2.5 h-2.5 rounded-full ${COLOR_DOT[entry.color]}`} />
          <span className="font-medium text-ink-100 truncate">{entry.library_name}</span>
        </div>
        <span className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full ${badge.bg} ${badge.color}`}>
          {badge.label}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-ink-700 rounded-full h-2">
        <div
          className="h-2 rounded-full bg-gold-500 transition-all duration-500"
          style={{ width: `${Math.max(pct, entry.total_positions > 0 ? 2 : 0)}%` }}
        />
      </div>

      <div className="flex justify-between text-xs text-ink-400">
        <span>{entry.mastered_positions} / {entry.total_positions} mastered</span>
        <span>{pct > 0 ? `${pct}%` : entry.total_positions === 0 ? "—" : "0%"}</span>
      </div>
    </div>
  );
}

// ── Leech list ────────────────────────────────────────────────────────────────

function LeechSection() {
  const { data: leeches, isLoading } = useQuery({
    queryKey: ["stats-leeches"],
    queryFn: statsApi.leeches,
  });

  if (isLoading) return <p className="text-ink-400 text-sm">Loading…</p>;
  if (!leeches?.length) {
    return (
      <p className="text-ink-400 text-sm">
        No leeches yet. A position becomes a leech after 4 wrong answers.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {leeches.map((l) => (
        <div key={l.practice_position_id} className="card flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink-100 truncate">{l.library_name}</div>
            <div className="text-xs text-ink-400">
              {l.line_name ? `"${l.line_name}" · ` : ""}Move {l.move_index + 1}
            </div>
          </div>
          <div className="shrink-0 flex items-center gap-3 text-xs text-ink-400">
            <span className="text-red-400 font-semibold">{l.leech_count}✗</span>
            <span>ease {l.ease_factor.toFixed(1)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Recent sessions ───────────────────────────────────────────────────────────

function RecentSessions() {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["stats-recent-sessions"],
    queryFn: statsApi.recentSessions,
  });

  if (isLoading) return <p className="text-ink-400 text-sm">Loading…</p>;
  if (!sessions?.length) return <p className="text-ink-400 text-sm">No sessions yet.</p>;

  return (
    <div className="flex flex-col gap-2">
      {sessions.map((s) => {
        const date = new Date(s.started_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        });
        const accuracy =
          s.positions_seen > 0 ? Math.round((s.correct / s.positions_seen) * 100) : 0;
        return (
          <div key={s.id} className="card flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-ink-100 capitalize">{s.mode.replace("_", " ")}</div>
              <div className="text-xs text-ink-400">{date} · {s.positions_seen} positions</div>
            </div>
            <div className="text-right text-xs">
              <div className={accuracy >= 80 ? "text-green-400" : accuracy >= 50 ? "text-yellow-400" : "text-red-400"}>
                {accuracy}%
              </div>
              <div className="text-ink-500">{s.correct}✓ {s.wrong}✗</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main Stats page ───────────────────────────────────────────────────────────

export function Stats() {
  const { data: heatmap, isLoading: loadingHeat } = useQuery({
    queryKey: ["stats-heatmap"],
    queryFn: statsApi.heatmap,
  });

  const { data: mastery, isLoading: loadingMastery } = useQuery({
    queryKey: ["stats-mastery"],
    queryFn: statsApi.mastery,
    staleTime: 60_000,
  });

  return (
    <div className="flex flex-col gap-8">
      <h1>My Stats</h1>

      {/* Accuracy heatmap */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">Accuracy by move</h2>
        <div className="card">
          {loadingHeat ? (
            <div className="h-32 flex items-center justify-center text-ink-400 text-sm">Loading…</div>
          ) : (
            <>
              <HeatmapBar buckets={heatmap?.by_move_number ?? []} />
              <div className="flex gap-4 mt-3 text-xs text-ink-400">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 h-3 rounded bg-lime-400 opacity-85" /> ≥ 80%
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 h-3 rounded bg-yellow-400 opacity-85" /> 50–79%
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 h-3 rounded bg-red-400 opacity-85" /> &lt; 50%
                </span>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Accuracy trend over time */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">Accuracy over time</h2>
        <div className="card">
          <AccuracyTrendGraph />
        </div>
      </section>

      {/* Mastery per library */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">Opening mastery</h2>
        {loadingMastery ? (
          <p className="text-ink-400 text-sm">Loading…</p>
        ) : !mastery?.libraries.length ? (
          <p className="text-ink-400 text-sm">
            No libraries yet. <Link to="/libraries/new" className="text-gold-400 hover:underline">Create one</Link>.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {mastery.libraries.map((e) => <MasteryCard key={e.library_id} entry={e} />)}
          </div>
        )}
      </section>

      {/* Leeches */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">
          Leeches <span className="text-sm text-ink-400 font-normal">(positions you keep missing)</span>
        </h2>
        <LeechSection />
      </section>

      {/* Recent sessions */}
      <section>
        <h2 className="text-lg font-semibold text-ink-200 mb-3">Recent sessions</h2>
        <RecentSessions />
      </section>
    </div>
  );
}
