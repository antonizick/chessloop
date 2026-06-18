import type { RecordedMove } from "@/hooks/useTeaching";

interface Props {
  moves: RecordedMove[];
  viewIndex: number | null;
  isAtEnd: boolean;
  onJump: (index: number) => void;
  onJumpToEnd: () => void;
  onDeleteFrom?: (index: number) => void;
  /** Hide the per-move delete affordance (e.g. read-only game review). */
  readOnly?: boolean;
}

export function generatePgn(moves: RecordedMove[], lineName?: string): string {
  let pgn = '';
  if (lineName) {
    pgn += `[Event "${lineName}"]\n`;
  }
  pgn += '\n';

  for (let i = 0; i < moves.length; i++) {
    if (i % 2 === 0) {
      pgn += `${Math.floor(i / 2) + 1}. `;
    }
    pgn += moves[i].san;
    if (i < moves.length - 1) {
      pgn += ' ';
    }
  }

  return pgn;
}

export function exportPgn(pgn: string, lineName?: string) {
  const element = document.createElement('a');
  element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(pgn));
  element.setAttribute('download', `${lineName || 'opening'}.pgn`);
  element.style.display = 'none';
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
}

export function MoveList({
  moves,
  viewIndex,
  isAtEnd,
  onJump,
  onJumpToEnd,
  onDeleteFrom,
  readOnly = false,
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
      {pairs.map(({ num, white, wi, black, bi }) => (
        <div key={wi} className="flex items-center gap-0.5 text-sm">
          <span className="text-ink-500 w-6 text-right shrink-0 select-none">{num}.</span>
          <MoveChip
            move={white}
            index={wi}
            active={viewIndex === wi}
            onJump={onJump}
            onDeleteFrom={onDeleteFrom}
            readOnly={readOnly}
          />
          {black !== undefined && bi !== undefined && (
            <MoveChip
              move={black}
              index={bi}
              active={viewIndex === bi}
              onJump={onJump}
              onDeleteFrom={onDeleteFrom}
              readOnly={readOnly}
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
  onDeleteFrom?: (i: number) => void;
  readOnly?: boolean;
}

function MoveChip({ move, index, active, onJump, onDeleteFrom, readOnly = false }: ChipProps) {
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
      {move.note && (
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            active ? "bg-ink-900" : "bg-gold-300"
          }`}
          title={move.note}
        />
      )}
      {!readOnly && onDeleteFrom && (
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
      )}
    </div>
  );
}
