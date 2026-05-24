interface Props {
  color: "white" | "black";
  onSelect: (piece: "q" | "r" | "b" | "n") => void;
  onCancel: () => void;
}

const PIECES: Array<{ piece: "q" | "r" | "b" | "n"; label: string; wSymbol: string; bSymbol: string }> = [
  { piece: "q", label: "Queen",  wSymbol: "♕", bSymbol: "♛" },
  { piece: "r", label: "Rook",   wSymbol: "♖", bSymbol: "♜" },
  { piece: "b", label: "Bishop", wSymbol: "♗", bSymbol: "♝" },
  { piece: "n", label: "Knight", wSymbol: "♘", bSymbol: "♞" },
];

export function PromotionModal({ color, onSelect, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="card flex flex-col items-center gap-4 p-6 min-w-[240px]">
        <h2 className="text-lg font-semibold">Promote pawn</h2>
        <div className="grid grid-cols-4 gap-2">
          {PIECES.map(({ piece, label, wSymbol, bSymbol }) => (
            <button
              key={piece}
              className="flex flex-col items-center gap-1 rounded-lg p-3 text-3xl hover:bg-gold-500
                         hover:text-ink-900 transition-colors bg-ink-700"
              onClick={() => onSelect(piece)}
              title={label}
            >
              {color === "white" ? wSymbol : bSymbol}
              <span className="text-xs font-medium">{label[0]}</span>
            </button>
          ))}
        </div>
        <button className="btn-ghost text-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
