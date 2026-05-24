import { useEffect, useRef } from "react";
import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Config } from "chessground/config";
import type { Key } from "chessground/types";

export interface BoardChange {
  from: Key;
  to: Key;
}

interface Props {
  fen?: string;
  orientation?: "white" | "black";
  viewOnly?: boolean;
  turnColor?: "white" | "black";
  size?: number;
  onMove?: (change: BoardChange) => void;
  /** Expose the Chessground Api so parents can call .set() imperatively */
  cgRef?: React.MutableRefObject<Api | null>;
  className?: string;
}

export function ChessboardWrapper({
  fen,
  orientation = "white",
  viewOnly = false,
  turnColor,
  size = 480,
  onMove,
  cgRef,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const apiRef = useRef<Api | null>(null);
  const onMoveRef = useRef(onMove);
  onMoveRef.current = onMove;

  useEffect(() => {
    if (!containerRef.current || apiRef.current) return;
    const config: Config = {
      fen,
      orientation,
      viewOnly,
      turnColor,
      movable: {
        free: false,
        color: viewOnly ? undefined : (turnColor ?? orientation),
        showDests: true,
      },
      draggable: { enabled: !viewOnly },
      events: {
        move: (from, to) => onMoveRef.current?.({ from, to }),
      },
    };
    const api = Chessground(containerRef.current, config);
    apiRef.current = api;
    if (cgRef) cgRef.current = api;
    return () => {
      api.destroy();
      apiRef.current = null;
      if (cgRef) cgRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep orientation + viewOnly in sync via props (fen/dests handled imperatively by parent)
  useEffect(() => {
    apiRef.current?.set({ orientation, viewOnly });
  }, [orientation, viewOnly]);

  return (
    <div
      ref={containerRef}
      style={{ width: size, height: size }}
      className={className}
    />
  );
}
