import { useCallback, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";

export interface RecordedMove {
  san: string;
  uci: string;
  fen_after: string;
  note?: string;
}

export function getDests(chess: Chess): Map<Key, Key[]> {
  const dests = new Map<Key, Key[]>();
  for (const m of chess.moves({ verbose: true })) {
    const targets = dests.get(m.from as Key) ?? [];
    targets.push(m.to as Key);
    dests.set(m.from as Key, targets);
  }
  return dests;
}

const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function useTeaching() {
  const startFenRef = useRef(DEFAULT_FEN);
  const chessRef = useRef(new Chess(DEFAULT_FEN));

  const [moves, setMoves] = useState<RecordedMove[]>([]);
  const [viewIndex, setViewIndex] = useState<number | null>(null); // null = live end
  const [pendingPromotion, setPendingPromotion] = useState<{ from: Key; to: Key } | null>(null);

  /** Reset to a fresh line — call whenever the selected line changes. */
  const resetToLine = useCallback((startFen: string, initial: RecordedMove[]) => {
    startFenRef.current = startFen;
    const chess = new Chess(startFen);
    for (const m of initial) chess.move(m.san);
    chessRef.current = chess;
    setMoves(initial);
    setViewIndex(null);
    setPendingPromotion(null);
  }, []);

  /** FEN to display. Determined by viewIndex (null = live position). */
  const boardFen = useMemo(() => {
    if (viewIndex === null) return chessRef.current.fen();
    if (viewIndex < 0) return startFenRef.current;
    const tmp = new Chess(startFenRef.current);
    for (let i = 0; i <= viewIndex; i++) tmp.move(moves[i].san);
    return tmp.fen();
  }, [viewIndex, moves]);

  /** Legal destinations for the live (recording) position. */
  const liveDests = useMemo((): Map<Key, Key[]> => {
    if (viewIndex !== null) return new Map();
    return getDests(chessRef.current);
  }, [viewIndex, moves]); // moves in deps so we recompute after each recorded move

  const liveTurnColor = useMemo(
    (): "white" | "black" => (chessRef.current.turn() === "w" ? "white" : "black"),
    [moves],
  );

  const isAtEnd = viewIndex === null;

  /**
   * Attempt to record a move.
   * Returns the RecordedMove on success, "promotion" if promotion dialog needed, null if illegal/viewing.
   */
  const tryMove = useCallback(
    (from: Key, to: Key, promotion?: "q" | "r" | "b" | "n"): RecordedMove | "promotion" | null => {
      if (viewIndex !== null) return null;

      const chess = chessRef.current;
      const piece = chess.get(from as any);
      const isPromo =
        piece?.type === "p" &&
        ((piece.color === "w" && to[1] === "8") || (piece.color === "b" && to[1] === "1"));

      if (isPromo && !promotion) {
        setPendingPromotion({ from, to });
        return "promotion";
      }

      const result = chess.move({ from: from as any, to: to as any, promotion });
      if (!result) return null;

      setPendingPromotion(null);
      const recorded: RecordedMove = {
        san: result.san,
        uci: `${from}${to}${promotion ?? ""}`,
        fen_after: chess.fen(),
      };
      setMoves((prev) => [...prev, recorded]);
      return recorded;
    },
    [viewIndex],
  );

  const confirmPromotion = useCallback(
    (piece: "q" | "r" | "b" | "n") => {
      if (!pendingPromotion) return null;
      const { from, to } = pendingPromotion;
      setPendingPromotion(null);
      return tryMove(from, to, piece);
    },
    [pendingPromotion, tryMove],
  );

  const cancelPromotion = useCallback(() => setPendingPromotion(null), []);

  /** Delete moves from index onward. Updates chess.js state and jumps back to live end. */
  const deleteFrom = useCallback((index: number) => {
    setMoves((prev) => {
      const kept = prev.slice(0, index);
      const chess = new Chess(startFenRef.current);
      for (const m of kept) chess.move(m.san);
      chessRef.current = chess;
      return kept;
    });
    setViewIndex(null);
  }, []);

  const jumpTo = useCallback((index: number) => setViewIndex(index), []);
  const jumpToEnd = useCallback(() => setViewIndex(null), []);

  /** Update note text for a move at a specific index. */
  const setMoveNote = useCallback((index: number, note: string) => {
    setMoves((prev) => {
      const updated = [...prev];
      if (updated[index]) {
        updated[index] = { ...updated[index], note: note || undefined };
      }
      return updated;
    });
  }, []);

  return {
    moves,
    viewIndex,
    pendingPromotion,
    boardFen,
    liveDests,
    liveTurnColor,
    isAtEnd,
    resetToLine,
    tryMove,
    confirmPromotion,
    cancelPromotion,
    deleteFrom,
    jumpTo,
    jumpToEnd,
    setMoveNote,
    startFenRef,
  };
}
