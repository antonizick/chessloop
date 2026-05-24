import type { SessionStats } from "@/types";

interface Props {
  stats: SessionStats;
  onRestart: () => void;
}

export function SessionSummary({ stats, onRestart }: Props) {
  const total = stats.correct + stats.wrong;
  const accuracy = total > 0 ? Math.round((stats.correct / total) * 100) : 0;
  const emoji = accuracy >= 85 ? "🏆" : accuracy >= 60 ? "📈" : "💪";

  return (
    <div className="max-w-md mx-auto mt-10 flex flex-col items-center gap-6 text-center">
      <div className="text-5xl">{emoji}</div>

      <div>
        <h1>Session Complete</h1>
        <p className="text-ink-300 text-sm mt-1">Great work. Here's the breakdown:</p>
      </div>

      <div className="card w-full">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-3xl font-bold text-green-400">{stats.correct}</div>
            <div className="text-xs text-ink-400 mt-1">Correct</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-red-400">{stats.wrong}</div>
            <div className="text-xs text-ink-400 mt-1">Wrong</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-gold-400">{accuracy}%</div>
            <div className="text-xs text-ink-400 mt-1">Accuracy</div>
          </div>
        </div>

        {total > 0 && (
          <div className="mt-4 pt-4 border-t border-ink-700">
            {/* Accuracy bar */}
            <div className="h-2 rounded-full bg-ink-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-green-500 transition-all"
                style={{ width: `${accuracy}%` }}
              />
            </div>
          </div>
        )}

        <div className="text-sm text-ink-400 mt-3">
          {stats.positions_seen} position{stats.positions_seen !== 1 ? "s" : ""} reviewed
        </div>
      </div>

      <div className="flex flex-col gap-2 w-full">
        <button className="btn-primary w-full py-3" onClick={onRestart}>
          Practice Again
        </button>
      </div>
    </div>
  );
}
