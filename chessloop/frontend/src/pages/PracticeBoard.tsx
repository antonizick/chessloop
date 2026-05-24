import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function PracticeBoard() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1>Practice</h1>
        <p className="text-ink-300 text-sm">
          Phase 1: static preview. Spaced-repetition session loop arrives in Phase 3.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 items-start">
        <ChessboardWrapper fen={STARTING_FEN} viewOnly />
        <div className="card">
          <h2 className="mb-2">Session</h2>
          <p className="text-ink-300 text-sm">
            No active session. SRS engine, due-position scheduling, and feedback overlay
            will be wired up in Phase 3.
          </p>
        </div>
      </div>
    </div>
  );
}
