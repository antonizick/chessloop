import { useEffect, useLayoutEffect, useRef } from "react";
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

  /**
   * WHY useLayoutEffect (not useEffect) for init:
   *
   * useEffect fires AFTER browser paint — but fetch() Promises (used by the
   * parent to load practice positions) resolve as microtasks, which run BEFORE
   * paint.  That means when the parent's async code calls enableBoardForUser()
   * (via cgRef.current?.set(...)), the board has not been initialised yet and
   * cgRef.current is still null.  The optional-chain silently swallows the
   * call, leaving the board forever unresponsive.
   *
   * useLayoutEffect fires SYNCHRONOUSLY after DOM commit, before paint and
   * before any pending microtasks can execute.  So cgRef.current is guaranteed
   * to be set by the time any awaited network responses land in the parent.
   */
  useLayoutEffect(() => {
    if (!containerRef.current || apiRef.current) return;

    /**
     * CRITICAL: Always init with viewOnly=false so that Chessground's
     * events.bindBoard() attaches mousedown/touchstart listeners to the DOM.
     * bindBoard() returns early (skips all listeners) when viewOnly=true, and
     * that skip is permanent — calling set({ viewOnly: false }) later updates
     * the state object but does NOT re-run bindBoard, leaving the board
     * permanently unresponsive to mouse/touch events.
     *
     * The parent's viewOnly prop is applied immediately after init via the
     * sync effect below. Transitioning false→true via set() works fine because
     * the event handlers check !s.viewOnly before acting.
     *
     * movable.color starts as undefined so nothing is draggable by default;
     * the parent sets it imperatively via cgRef when it wants interaction.
     */
    const config: Config = {
      fen,
      orientation,
      viewOnly: false,
      turnColor,
      movable: {
        free: false,
        color: undefined,
        showDests: true,
      },
      draggable: { enabled: true },
      events: {
        move: (from, to) => onMoveRef.current?.({ from, to }),
      },
    };

    const api = Chessground(containerRef.current, config);
    apiRef.current = api;
    if (cgRef) cgRef.current = api;

    // Apply the actual viewOnly prop now that listeners are bound
    if (viewOnly) {
      api.set({ viewOnly: true });
    }

    return () => {
      api.destroy();
      apiRef.current = null;
      if (cgRef) cgRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync orientation and viewOnly when props change.
  //
  // CRITICAL ORDER: set viewOnly:false BEFORE changing orientation.
  //
  // When orientation changes, api.set() calls toggleOrientation() → redrawAll()
  // → renderWrap() (DOM wiped) → bindBoard().  bindBoard() reads state.viewOnly
  // at that exact moment — BEFORE configure(state, config) has run — so it sees
  // the OLD (possibly true) value and permanently skips listener registration.
  //
  // By issuing api.set({ viewOnly: false }) first, state.viewOnly is already
  // false when the orientation-change triggers bindBoard().  The second call
  // then sets the final desired viewOnly value (which may be true for view-only
  // phases; that's fine because the runtime !s.viewOnly check in startDragOrDraw
  // will block interaction without touching listener registration).
  useEffect(() => {
    const api = apiRef.current;
    if (!api) return;
    api.set({ viewOnly: false });            // ensure bindBoard sees false
    api.set({ orientation, viewOnly });      // apply final state (may trigger toggleOrientation)
  }, [orientation, viewOnly]);

  return (
    <div
      ref={containerRef}
      style={{ width: size, height: size }}
      className={className}
    />
  );
}
