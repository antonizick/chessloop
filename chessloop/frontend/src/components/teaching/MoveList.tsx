import type { RecordedMove } from "@/hooks/useTeaching";

interface Props {
  moves: RecordedMove[];
  viewIndex: number | null;
  isAtEnd: boolean;
  onJump: (index: number) => void;
  onJumpToStart: () => void;
  onJumpToEnd: () => void;
  onDeleteFrom: (index: number) => void;
}

export function MoveList({
  moves,
  viewIndex,
  isAtEnd,
  onJump,
  onJumpToStart,
  onJumpToEnd,
  onDeleteFrom,
}: Props) {
  if (moves.length === 0) {
    return (
      <p className="text-ink-300 text-sm italic mt-2">
        Drag pieces on the board to record moves.
      </p>
    );
  }

  // Group into pairs: [{num, white, wi, black?, bi?}]
  const pairs: Array<{
    num: number;
    white: RecordedMove;
    wi: number;
    black?: RecordedMove;
    bi?: number;
  }> = [];
  for (let i = 0; i < moves.length; i += 2) {
    pairs.push({
      num: Math.floor(i / 2) + 1,
      white: moves[i],
      wi: i,
      black: moves[i + 1],
      bi: i + 1,
    });
  }

  return (
    <div className="flex flex-col gap-0.5">
      {/* Jump to start */}
      <button
        className="text-xs text-ink-400 hover:text-gold-400 text-left mb-1"
        onClick={onJumpToStart}
      >
        ⟪ start
      </button>

      {pairs.map(({ num, white, wi, black, bi }) => (
        <div key={wi} className="flex items-center gap-0.5 text-sm">
          <span className="text-ink-500 w-6 text-right shrink-0 select-none">{num}.</span>
          <MoveChip
            move={white}
            index={wi}
            active={viewIndex === wi}
            onJump={onJump}
            onDeleteFrom={onDeleteFrom}
          />
          {black !== undefined && bi !== undefined && (
            <MoveChip
              move={black}
              index={bi}
              active={viewIndex === bi}
              onJump={onJump}
              onDeleteFrom={onDeleteFrom}
            />
          )}
        </div>
      ))}

      {!isAtEnd && (
        <button
          className="mt-2 text-xs text-gold-400 hover:text-gold-300 text-left"
          onClick={onJumpToEnd}
        >
          → live position
        </button>
      )}
    </div>
  );
}

interface ChipProps {
  move: RecordedMove;
  index: number;
  active: boolean;
  onJump: (i: number) => void;
  onDeleteFrom: (i: number) => void;
}

function MoveChip({ move, index, active, onJump, onDeleteFrom }: ChipProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      className={`group flex items-center gap-0.5 rounded px-2 py-0.5 cursor-pointer select-none
        ${active ? "bg-gold-500 text-ink-900 font-semibold" : "hover:bg-ink-700 text-ink-100"}`}
      onClick={() => onJump(index)}
      onKeyDown={(e) => e.key === "Enter" && onJump(index)}
    >
      <span>{move.san}</span>
      <button
        className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300
                   text-xs leading-none ml-1 transition-opacity"
        onClick={(e) => {
          e.stopPropagation();
          if (confirm(`Delete "${move.san}" and all moves after it?`)) {
            onDeleteFrom(index);
          }
        }}
        title="Delete from here"
        aria-label={`Delete ${move.san} and after`}
      >
        ×
      </button>
    </div>
  );
}
