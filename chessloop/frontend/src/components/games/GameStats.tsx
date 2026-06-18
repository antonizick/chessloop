import { useMemo } from "react";
import type { Game, GameColor, GameResult } from "@/types";

// Shared palette — consistent with the My Stats page.
const WIN = "#34d399"; // emerald-400
const DRAW = "#94a3b8"; // slate-400
const LOSS = "#f87171"; // red-400

interface Tally {
  total: number;
  win: number;
  loss: number;
  draw: number;
}

function emptyTally(): Tally {
  return { total: 0, win: 0, loss: 0, draw: 0 };
}

function add(t: Tally, r: GameResult) {
  t.total += 1;
  t[r] += 1;
}

function winRate(t: Tally): number {
  return t.total > 0 ? t.win / t.total : 0;
}

/** Score = points per game (win 1, draw 0.5). 0–1. */
function score(t: Tally): number {
  return t.total > 0 ? (t.win + 0.5 * t.draw) / t.total : 0;
}

function rateColor(rate: number): string {
  if (rate >= 0.6) return WIN;
  if (rate >= 0.4) return "#facc15"; // yellow-400
  return LOSS;
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// ── Summary tile ─────────────────────────────────────────────────────────────

function Tile({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="card flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-ink-400">{label}</span>
      <span className={`text-2xl font-bold ${valueClass ?? "text-ink-100"}`}>{value}</span>
      {sub && <span className="text-xs text-ink-400">{sub}</span>}
    </div>
  );
}

// ── Stacked results bar ──────────────────────────────────────────────────────

function ResultsBar({ t }: { t: Tally }) {
  const seg = (n: number) => (t.total > 0 ? (n / t.total) * 100 : 0);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-6 w-full overflow-hidden rounded-md bg-ink-700">
        {t.win > 0 && (
          <div className="h-full flex items-center justify-center text-[10px] font-semibold text-ink-900"
            style={{ width: `${seg(t.win)}%`, background: WIN }} title={`${t.win} wins`}>
            {seg(t.win) > 8 ? t.win : ""}
          </div>
        )}
        {t.draw > 0 && (
          <div className="h-full flex items-center justify-center text-[10px] font-semibold text-ink-900"
            style={{ width: `${seg(t.draw)}%`, background: DRAW }} title={`${t.draw} draws`}>
            {seg(t.draw) > 8 ? t.draw : ""}
          </div>
        )}
        {t.loss > 0 && (
          <div className="h-full flex items-center justify-center text-[10px] font-semibold text-ink-900"
            style={{ width: `${seg(t.loss)}%`, background: LOSS }} title={`${t.loss} losses`}>
            {seg(t.loss) > 8 ? t.loss : ""}
          </div>
        )}
      </div>
      <div className="flex gap-4 text-xs text-ink-400">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: WIN }} /> {t.win} W</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: DRAW }} /> {t.draw} D</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: LOSS }} /> {t.loss} L</span>
      </div>
    </div>
  );
}

// ── Per-colour card ──────────────────────────────────────────────────────────

function ColorCard({ color, t }: { color: GameColor; t: Tally }) {
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${color === "white" ? "bg-white" : "bg-ink-300"}`} />
          <span className="font-medium text-ink-100 capitalize">{color}</span>
        </div>
        <span className="text-xs text-ink-400">{t.total} game{t.total !== 1 ? "s" : ""}</span>
      </div>
      <div className="w-full bg-ink-700 rounded-full h-2">
        <div className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(winRate(t) * 100, t.total > 0 ? 2 : 0)}%`, background: rateColor(winRate(t)) }} />
      </div>
      <div className="flex justify-between text-xs text-ink-400">
        <span>{t.win}W · {t.draw}D · {t.loss}L</span>
        <span>{t.total > 0 ? `${pct(winRate(t))} win` : "—"}</span>
      </div>
    </div>
  );
}

// ── Win rate by opponent level (SVG bars) ──────────────────────────────────────

const BAND = 200;

function OpponentLevelChart({ games }: { games: Game[] }) {
  const buckets = useMemo(() => {
    const map = new Map<number, Tally>();
    for (const g of games) {
      if (g.opponent_level == null) continue;
      const band = Math.floor(g.opponent_level / BAND) * BAND;
      if (!map.has(band)) map.set(band, emptyTally());
      add(map.get(band)!, g.result);
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([band, t]) => ({ band, t }));
  }, [games]);

  if (buckets.length === 0) {
    return <div className="flex items-center justify-center h-32 text-ink-400 text-sm">No opponent ratings recorded yet.</div>;
  }

  const SVG_H = 120, BAR_W = 44, GAP = 14, LABEL_H = 30;
  const totalW = buckets.length * (BAR_W + GAP) - GAP;

  return (
    <div className="overflow-x-auto">
      <svg width={Math.max(totalW, 1)} height={SVG_H + LABEL_H} className="block" aria-label="Win rate by opponent level">
        {buckets.map((b, i) => {
          const x = i * (BAR_W + GAP);
          const rate = winRate(b.t);
          const barH = Math.max(4, Math.round(rate * SVG_H));
          const y = SVG_H - barH;
          return (
            <g key={b.band}>
              <title>{b.band}–{b.band + BAND - 1}: {pct(rate)} win ({b.t.win}/{b.t.total})</title>
              <rect x={x} y={0} width={BAR_W} height={SVG_H} rx={3} fill="#1e293b" />
              <rect x={x} y={y} width={BAR_W} height={barH} rx={3} fill={rateColor(rate)} opacity={0.85} />
              <text x={x + BAR_W / 2} y={SVG_H - barH - 4} textAnchor="middle" fontSize={9} fill="#cbd5e1">
                {pct(rate)}
              </text>
              <text x={x + BAR_W / 2} y={SVG_H + 13} textAnchor="middle" fontSize={9} fill="#94a3b8">
                {b.band}+
              </text>
              <text x={x + BAR_W / 2} y={SVG_H + 25} textAnchor="middle" fontSize={8} fill="#5a5a6b">
                {b.t.total}g
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Games over time (monthly stacked bars) ──────────────────────────────────────

function monthLabel(key: string): string {
  const [y, m] = key.split("-");
  const d = new Date(parseInt(y), parseInt(m) - 1, 1);
  return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

function TimelineChart({ games }: { games: Game[] }) {
  const months = useMemo(() => {
    const map = new Map<string, Tally>();
    for (const g of games) {
      if (!g.played_date) continue;
      const key = g.played_date.slice(0, 7); // YYYY-MM
      if (!map.has(key)) map.set(key, emptyTally());
      add(map.get(key)!, g.result);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([key, t]) => ({ key, t }));
  }, [games]);

  if (months.length === 0) {
    return <div className="flex items-center justify-center h-32 text-ink-400 text-sm">Add dates to your games to see a timeline.</div>;
  }

  const maxTotal = Math.max(...months.map((m) => m.t.total), 1);
  const SVG_H = 140, BAR_W = 40, GAP = 16, LABEL_H = 22, TOP = 8;
  const totalW = months.length * (BAR_W + GAP) - GAP;
  const plotH = SVG_H - TOP;

  return (
    <div className="overflow-x-auto">
      <svg width={Math.max(totalW, 1)} height={SVG_H + LABEL_H} className="block" aria-label="Games played over time">
        {months.map((m, i) => {
          const x = i * (BAR_W + GAP);
          const h = (n: number) => Math.round((n / maxTotal) * plotH);
          const winH = h(m.t.win), drawH = h(m.t.draw), lossH = h(m.t.loss);
          const total = winH + drawH + lossH;
          let yCursor = SVG_H - total;
          const segs: Array<{ height: number; fill: string }> = [
            { height: winH, fill: WIN },
            { height: drawH, fill: DRAW },
            { height: lossH, fill: LOSS },
          ];
          return (
            <g key={m.key}>
              <title>{monthLabel(m.key)}: {m.t.win}W {m.t.draw}D {m.t.loss}L ({pct(score(m.t))} score)</title>
              {segs.map((s, si) => {
                if (s.height <= 0) return null;
                const rect = <rect key={si} x={x} y={yCursor} width={BAR_W} height={s.height} fill={s.fill} opacity={0.88} />;
                yCursor += s.height;
                return rect;
              })}
              <text x={x + BAR_W / 2} y={SVG_H - total - 4} textAnchor="middle" fontSize={9} fill="#cbd5e1">
                {m.t.total}
              </text>
              <text x={x + BAR_W / 2} y={SVG_H + 14} textAnchor="middle" fontSize={8} fill="#94a3b8">
                {monthLabel(m.key)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="flex gap-4 mt-2 text-xs text-ink-400">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: WIN }} /> Wins</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: DRAW }} /> Draws</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded" style={{ background: LOSS }} /> Losses</span>
      </div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export function GameStats({ games }: { games: Game[] }) {
  const { overall, white, black, repeats } = useMemo(() => {
    const overall = emptyTally();
    const white = emptyTally();
    const black = emptyTally();
    let repeats = 0;
    for (const g of games) {
      add(overall, g.result);
      add(g.played_color === "white" ? white : black, g.result);
      if (g.repeat_offense) repeats += 1;
    }
    return { overall, white, black, repeats };
  }, [games]);

  if (games.length === 0) return null;

  return (
    <div className="flex flex-col gap-8 mt-4 border-t border-ink-700 pt-8">
      <h2 className="text-lg font-semibold text-ink-200">Game statistics</h2>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile label="Total games" value={overall.total.toString()} />
        <Tile label="Win rate" value={pct(winRate(overall))} valueClass={rateColor(winRate(overall)) === WIN ? "text-emerald-400" : rateColor(winRate(overall)) === LOSS ? "text-red-400" : "text-yellow-400"}
          sub={`${pct(score(overall))} score`} />
        <Tile label="Record" value={`${overall.win}–${overall.loss}–${overall.draw}`} sub="W–L–D" />
        <Tile label="Repeat offenses" value={repeats.toString()} valueClass={repeats > 0 ? "text-red-400" : "text-emerald-400"}
          sub={overall.total > 0 ? `${pct(repeats / overall.total)} of games` : undefined} />
      </div>

      {/* Results breakdown */}
      <section>
        <h3 className="text-sm font-semibold text-ink-300 mb-3">Results</h3>
        <div className="card"><ResultsBar t={overall} /></div>
      </section>

      {/* By colour */}
      <section>
        <h3 className="text-sm font-semibold text-ink-300 mb-3">Performance by colour</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ColorCard color="white" t={white} />
          <ColorCard color="black" t={black} />
        </div>
      </section>

      {/* By opponent level */}
      <section>
        <h3 className="text-sm font-semibold text-ink-300 mb-3">Win rate by opponent level</h3>
        <div className="card"><OpponentLevelChart games={games} /></div>
      </section>

      {/* Timeline */}
      <section>
        <h3 className="text-sm font-semibold text-ink-300 mb-3">Games over time</h3>
        <div className="card"><TimelineChart games={games} /></div>
      </section>
    </div>
  );
}
