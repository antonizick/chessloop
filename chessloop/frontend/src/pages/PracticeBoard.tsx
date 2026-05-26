/**
 * PracticeBoard — Phase 3 spaced-repetition drill loop.
 *
 * ── Why ChessboardWrapper is always mounted ────────────────────────────────
 * Chessground registers its mousedown/touchstart listeners in bindBoard(),
 * which runs once — at Chessground initialisation.  Chessground's api.set()
 * does NOT re-run bindBoard; it only re-renders pieces.  When orientation
 * changes, api.set() internally calls toggleOrientation() → redrawAll() →
 * renderWrap() + bindBoard(), but at that point state.viewOnly still has its
 * OLD value (configure() hasn't run yet), so if it's true, bindBoard() skips
 * listener registration permanently.
 *
 * The root fix is to keep ChessboardWrapper in the DOM at all times so that
 * Chessground is initialised once at page load (with viewOnly:false, so
 * bindBoard registers listeners correctly) and never destroyed until the user
 * navigates away.  During "entry" and "done" phases the board wrapper is
 * hidden with CSS (visibility:hidden preserves layout & dimensions so
 * getBoundingClientRect() stays correct for hit-testing).
 *
 * State machine phases:
 *   entry          → mode picker shown, board invisible
 *   loading        → fetching next position / starting session
 *   animating      → auto-playing preceding moves on board
 *   waiting        → user's turn to drag a move
 *   submitting     → POST /answer in flight
 *   feedback_correct → correct! show SRS info + Easy/OK/Hard buttons
 *   feedback_wrong   → wrong! red arrow shown, delay before forced replay
 *   replaying      → user must drag the correct move to continue
 *   done           → session summary shown, board invisible
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Chess } from "chess.js";
import type { Api } from "chessground/api";
import type { Key } from "chessground/types";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { PromotionModal } from "@/components/teaching/PromotionModal";
import { ModeEntry } from "@/components/practice/ModeEntry";
import type { PracticeOptions, UiMode } from "@/components/practice/ModeEntry";
import { SessionSummary } from "@/components/practice/SessionSummary";
import { practiceApi } from "@/api/practice";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useAuthStore } from "@/stores/auth";
import { playMoveSound, playCorrectSound, playWrongSound } from "@/utils/sounds";
import type {
  PracticeMode,
  NextPositionResponse,
  AnswerResponse,
  SessionStats,
} from "@/types";

// ── Types ─────────────────────────────────────────────────────────────────────

type Phase =
  | "entry"
  | "loading"
  | "animating"        // auto-playing preceding moves before the challenge
  | "waiting"          // user's turn to drag a move
  | "computer_move"    // computer auto-playing its mainline reply
  | "submitting"       // POST /answer in flight
  | "feedback_correct" // line complete — show SRS info + Easy/OK/Hard
  | "feedback_wrong"   // wrong move — red arrow shown, delay before forced replay
  | "replaying"        // user must drag the correct move to continue
  | "done";            // session summary shown, board invisible

// Per-move context stored when the user gets a move wrong so the replaying
// phase (and its UI copy) can show the correct move without hitting the server.
type WrongMoveCtx = {
  from: string;
  to: string;
  san: string;
  fenAfter: string;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function legalDests(fen: string): Map<Key, Key[]> {
  const chess = new Chess(fen);
  const dests = new Map<Key, Key[]>();
  for (const m of chess.moves({ verbose: true })) {
    const targets = dests.get(m.from as Key) ?? [];
    targets.push(m.to as Key);
    dests.set(m.from as Key, targets);
  }
  return dests;
}

function intervalLabel(days: number): string {
  if (days < 1) return `${Math.round(days * 24)}h`;
  if (days <= 1) return "1 day";
  if (days < 30) return `${Math.round(days)} days`;
  const months = Math.round(days / 30);
  return `${months} month${months > 1 ? "s" : ""}`;
}

/** Extract whose turn it is directly from the FEN string ("w"→white, "b"→black). */
function turnFromFen(fen: string): "white" | "black" {
  return fen.split(" ")[1] === "w" ? "white" : "black";
}

function isPromotion(fen: string, from: string, to: string): boolean {
  const chess = new Chess(fen);
  const piece = chess.get(from as any);
  return (
    piece?.type === "p" &&
    ((piece.color === "w" && to[1] === "8") || (piece.color === "b" && to[1] === "1"))
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PracticeBoard() {
  const location = useLocation();

  const { data: user = useAuthStore.getState().user } = useCurrentUser();

  const soundsOn = user?.sounds_on ?? true;
  const boardTheme = user?.board_theme ?? "brown";
  const pieceSet = user?.piece_set ?? "cburnett";

  // cgRef is set once when ChessboardWrapper mounts (at page load, not on Start).
  // It stays valid for the entire session — no timing race with network requests.
  const cgRef = useRef<Api | null>(null);

  // Core session state
  const [phase, setPhase] = useState<Phase>("entry");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<UiMode>("weakest");
  const [position, setPosition] = useState<NextPositionResponse | null>(null);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [doneStats, setDoneStats] = useState<SessionStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Board UI
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [pendingPromotion, setPendingPromotion] = useState<{
    from: string;
    to: string;
  } | null>(null);

  // Running tally (shown in header during session)
  const [runningStats, setRunningStats] = useState<SessionStats>({
    correct: 0,
    wrong: 0,
    positions_seen: 0,
  });

  // Animation
  const [animStep, setAnimStep] = useState(0);

  // Response timing
  const startedAtRef = useRef(0);

  // ── Line-traversal state ───────────────────────────────────────────────────
  //
  // remaining_moves[lineStep] is always the NEXT move to be played.
  // Even lineStep values (0, 2, 4, …) are the user's moves.
  // Odd values (1, 3, 5, …) are the computer's auto-replies.
  //
  // currentFen tracks the live board FEN as moves are played so mid-line
  // board setup is independent of position.fen_before (which only describes
  // the start of the challenge).
  const [lineStep, setLineStep] = useState(0);
  const [currentFen, setCurrentFen] = useState("");
  const [wrongMoveCtx, setWrongMoveCtx] = useState<WrongMoveCtx | null>(null);

  // Stable refs to avoid stale closures in setTimeout callbacks
  const positionRef = useRef<NextPositionResponse | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const modeRef = useRef<UiMode>("weakest");
  const lineStepRef = useRef(0);
  const currentFenRef = useRef("");
  const wrongMoveCtxRef = useRef<WrongMoveCtx | null>(null);

  positionRef.current = position;
  sessionIdRef.current = sessionId;
  modeRef.current = mode;
  lineStepRef.current = lineStep;
  currentFenRef.current = currentFen;
  wrongMoveCtxRef.current = wrongMoveCtx;

  // ── Board helpers ──────────────────────────────────────────────────────────

  // fenOverride is used for mid-line "waiting" states where the board is
  // already past position.fen_before (i.e. lineStep > 0).
  const enableBoardForUser = useCallback(
    (pos: NextPositionResponse, fenOverride?: string) => {
      const fen = fenOverride ?? pos.fen_before;
      const color = turnFromFen(fen);
      cgRef.current?.set({
        fen,
        viewOnly: false,
        turnColor: color,
        movable: {
          free: false,
          color,
          dests: legalDests(fen),
          showDests: true,
        },
        draggable: { enabled: true },
        drawable: { shapes: [] },
      });
      startedAtRef.current = Date.now();
    },
    [],
  );

  // ── Enable board when phase → "waiting" ────────────────────────────────────
  //
  // Fires after React commits the render.  currentFenRef always holds the
  // latest live FEN — for the initial waiting state (lineStep === 0) that is
  // position.fen_before; for mid-line waiting states it is the FEN after the
  // computer's last reply.
  useEffect(() => {
    if (phase !== "waiting" || !position) return;
    enableBoardForUser(position, currentFenRef.current || undefined);
  }, [phase, position, enableBoardForUser]);

  // ── Auto-start from Dashboard "Practice weakest now" ──────────────────────
  // When navigated here with state.autoMode, skip the ModeEntry screen.
  const autoStartedRef = useRef(false);
  useEffect(() => {
    const autoMode = (location.state as { autoMode?: string } | null)?.autoMode;
    if (autoMode && phase === "entry" && !autoStartedRef.current) {
      autoStartedRef.current = true;
      startSession({ mode: autoMode as UiMode, startPosition: "auto" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Start session ──────────────────────────────────────────────────────────

  async function startSession({ mode: uiMode, startPosition }: PracticeOptions) {
    setMode(uiMode);
    setError(null);
    setRunningStats({ correct: 0, wrong: 0, positions_seen: 0 });
    setPhase("loading");
    try {
      // Translate UI mode → backend mode + scope.
      // "all_active" = backend "weakest" with uniform-random start so every position
      // in every active library gets equal exposure (no SRS weakness bias).
      let backendMode: PracticeMode;
      const scope: Record<string, unknown> = {};

      if (uiMode === "all_active") {
        backendMode = "weakest";
        scope.start_position = "random";
      } else {
        backendMode = uiMode as PracticeMode;
        if (startPosition !== "auto") scope.start_position = startPosition;
      }

      const sess = await practiceApi.start(backendMode, scope);
      setSessionId(sess.id);
      sessionIdRef.current = sess.id;
      await advanceToNext(sess.id);
    } catch {
      setError("Could not start session. Is the server running?");
      setPhase("entry");
    }
  }

  // ── Load next position ─────────────────────────────────────────────────────

  const advanceToNext = useCallback(
    async (sid: string) => {
      setPhase("loading");
      setAnswer(null);
      setPendingPromotion(null);
      try {
        const resp = await practiceApi.next(sid);

        if (resp.done) {
          const ended = await practiceApi.end(sid);
          const stats = ended.stats;

          // Nothing was practiced — the session was empty (no leeches, no active
          // libraries, or no seeded positions yet). Go back to entry with a clear
          // error message rather than showing a meaningless "0 positions reviewed" screen.
          if ((stats.positions_seen ?? 0) === 0) {
            setPhase("entry");
            const modeNow = modeRef.current;
            if (modeNow === "leech_drill") {
              setError(
                "No leeches yet! Miss a position 4 times to promote it to leech status, then come back.",
              );
            } else {
              setError(
                "No practice positions found. Make sure you have at least one active library with lines recorded in the Teaching Board.",
              );
            }
            return;
          }

          setDoneStats(stats);
          setPhase("done");
          return;
        }

        setPosition(resp);
        positionRef.current = resp;
        setOrientation(resp.turn_color);

        // Reset line-traversal state for the new challenge.
        setLineStep(0);
        lineStepRef.current = 0;
        setCurrentFen(resp.fen_before);
        currentFenRef.current = resp.fen_before;
        setWrongMoveCtx(null);
        wrongMoveCtxRef.current = null;

        if (resp.preceding_moves.length === 0) {
          // No animation needed — go straight to waiting.
          // The useEffect above will call enableBoardForUser after React commits.
          setPhase("waiting");
        } else {
          // Start animation from the line's starting FEN
          cgRef.current?.set({
            fen: resp.starting_fen,
            viewOnly: true,
            movable: { free: false, color: undefined, dests: new Map() },
            drawable: { shapes: [] },
          });
          setAnimStep(0);
          setPhase("animating");
        }
      } catch {
        setError("Failed to load next position.");
      }
    },
    [enableBoardForUser],
  );

  // ── Preceding-move animation ───────────────────────────────────────────────

  useEffect(() => {
    if (phase !== "animating" || !position) return;

    const moves = position.preceding_moves;

    if (animStep >= moves.length) {
      // Animation complete — transition to waiting.
      // The [phase, position] useEffect will call enableBoardForUser.
      setPhase("waiting");
      return;
    }

    const fenAfter = moves[animStep].fen_after;
    const timer = setTimeout(() => {
      playMoveSound(soundsOn);
      cgRef.current?.set({ fen: fenAfter, viewOnly: true });
      setAnimStep((s) => s + 1);
    }, 450);

    return () => clearTimeout(timer);
  }, [phase, animStep, position, enableBoardForUser]);

  // ── User move handler ──────────────────────────────────────────────────────

  async function onMove({ from, to }: { from: string; to: string }) {
    const pos = positionRef.current;
    const sid = sessionIdRef.current;
    if (!pos || !sid) return;

    // ── Replaying phase: forced-replay of the correct move ──────────────────
    if (phase === "replaying") {
      const ctx = wrongMoveCtxRef.current;
      if (!ctx) return;
      playMoveSound(soundsOn);
      cgRef.current?.set({
        fen: ctx.fenAfter,
        viewOnly: true,
        drawable: { shapes: [] },
      });

      // Submit the wrong-round result to the server, then advance.
      setPhase("submitting");
      const elapsedMs = Date.now() - startedAtRef.current;
      try {
        const result = await practiceApi.answer(sid, {
          practice_position_id: pos.practice_position_id,
          // Send the first expected move for the audit log; line_correct
          // overrides the correctness decision on the server.
          move_uci: pos.remaining_moves[0]?.uci ?? `${from}${to}`,
          ease: null,
          response_ms: elapsedMs,
          line_correct: false,
        });
        setAnswer(result);
        setRunningStats((prev) => ({
          correct: prev.correct,
          wrong: prev.wrong + 1,
          positions_seen: prev.positions_seen + 1,
        }));
      } catch {
        setError("Network error.");
      }

      await new Promise((r) => setTimeout(r, 500));
      advanceToNext(sid);
      return;
    }

    if (phase !== "waiting") return;

    // ── Promotion check ─────────────────────────────────────────────────────
    const activeFen = currentFenRef.current || pos.fen_before;
    if (isPromotion(activeFen, from, to)) {
      // Snap piece back — wait for promotion modal selection.
      cgRef.current?.set({ fen: activeFen });
      setPendingPromotion({ from, to });
      return;
    }

    handleUserMove(`${from}${to}`, null);
  }

  async function confirmPromotion(piece: "q" | "r" | "b" | "n") {
    if (!pendingPromotion) return;
    const { from, to } = pendingPromotion;
    setPendingPromotion(null);
    handleUserMove(`${from}${to}${piece}`, null);
  }

  // ── Core line-progression logic ────────────────────────────────────────────
  //
  // Called whenever the user drags a move in the "waiting" phase.
  // Validates locally against remaining_moves[lineStep], then either
  // advances the line (computer replies) or ends the round.

  function handleUserMove(uci: string, _unused: null) {
    const pos = positionRef.current;
    if (!pos) return;

    const moves = pos.remaining_moves;
    // Guard: remaining_moves is missing if the backend is running old code.
    if (!moves || moves.length === 0) {
      console.error("[ChessLoop] remaining_moves is missing — restart the backend.");
      setError("Server response is stale. Please restart the backend and refresh.");
      return;
    }

    const step = lineStepRef.current;
    if (step >= moves.length) return;

    const expected = moves[step];
    const match = uci.toLowerCase() === expected.uci.toLowerCase();

    if (match) {
      // ── Correct move ──────────────────────────────────────────────────────
      playMoveSound(soundsOn);
      cgRef.current?.set({
        fen: expected.fen_after,
        viewOnly: true,
        drawable: { shapes: [] },
      });

      const newStep = step + 1;
      setLineStep(newStep);
      lineStepRef.current = newStep;
      setCurrentFen(expected.fen_after);
      currentFenRef.current = expected.fen_after;

      if (newStep >= moves.length) {
        // Line exhausted after user's move — round complete.
        finishRound(pos);
      } else {
        // Computer responds next.
        setPhase("computer_move");
        playComputerMove();
      }
    } else {
      // ── Wrong move ────────────────────────────────────────────────────────
      showWrongFeedback(expected);
    }
  }

  // ── Computer auto-reply ────────────────────────────────────────────────────
  //
  // Reads lineStepRef (post-user-move increment) to find the computer's move,
  // animates it after a short pause, then either enables the board for the
  // user's next move or calls finishRound if the line is now exhausted.

  function playComputerMove() {
    setTimeout(() => {
      const pos = positionRef.current;
      if (!pos) return;

      const step = lineStepRef.current; // odd index = computer's turn
      const moves = pos.remaining_moves;
      if (step >= moves.length) {
        finishRound(pos);
        return;
      }

      const computerMove = moves[step];
      playMoveSound(soundsOn);
      cgRef.current?.set({
        fen: computerMove.fen_after,
        viewOnly: true,
        drawable: { shapes: [] },
      });

      const newStep = step + 1;
      setLineStep(newStep);
      lineStepRef.current = newStep;
      setCurrentFen(computerMove.fen_after);
      currentFenRef.current = computerMove.fen_after;

      if (newStep >= moves.length) {
        // Line ends on the computer's move (e.g. opponent plays the last book
        // move) — the round is complete after this reply.
        finishRound(pos);
      } else {
        // User's next move — the "waiting" useEffect will call enableBoardForUser
        // with currentFenRef after React commits the phase change.
        setPhase("waiting");
      }
    }, 600);
  }

  // ── Round completion: submit result and show SRS feedback ─────────────────

  async function finishRound(pos: NextPositionResponse) {
    const sid = sessionIdRef.current;
    if (!sid) return;

    setPhase("submitting");
    const elapsedMs = Date.now() - startedAtRef.current;

    try {
      const result = await practiceApi.answer(sid, {
        practice_position_id: pos.practice_position_id,
        move_uci: pos.remaining_moves[0]?.uci ?? "",
        ease: null,
        response_ms: elapsedMs,
        line_correct: true,
      });
      setAnswer(result);
      setRunningStats((prev) => ({
        correct: prev.correct + 1,
        wrong: prev.wrong,
        positions_seen: prev.positions_seen + 1,
      }));
      playCorrectSound(soundsOn);
      setPhase("feedback_correct");
    } catch {
      setError("Network error. Try again.");
      setPhase("waiting");
    }
  }

  // ── Wrong move: red-arrow flash → forced replay ────────────────────────────

  function showWrongFeedback(expected: { uci: string; san: string; fen_after: string }) {
    const from = expected.uci.slice(0, 2) as Key;
    const to   = expected.uci.slice(2, 4) as Key;
    playWrongSound(soundsOn);

    const fen = currentFenRef.current;
    const ctx: WrongMoveCtx = { from, to, san: expected.san, fenAfter: expected.fen_after };
    setWrongMoveCtx(ctx);
    wrongMoveCtxRef.current = ctx;

    // Step 1: freeze the board and show a red arrow on the correct move.
    cgRef.current?.set({
      fen,
      viewOnly: true,
      drawable: {
        enabled: true,
        visible: true,
        shapes: [{ orig: from, dest: to, brush: "red" }],
      },
    });
    setPhase("feedback_wrong");

    // Step 2: after 1.6 s, switch to green-guided forced replay.
    setTimeout(() => {
      if (!cgRef.current) return;
      const color = turnFromFen(fen);
      cgRef.current.set({
        fen,
        viewOnly: false,
        turnColor: color,
        movable: {
          free: false,
          color,
          dests: new Map([[from, [to]]]),
          showDests: true,
        },
        draggable: { enabled: true },
        drawable: {
          enabled: true,
          visible: true,
          shapes: [{ orig: from, dest: to, brush: "green" }],
        },
      });
      setPhase("replaying");
    }, 1600);
  }

  // ── End session early ──────────────────────────────────────────────────────

  async function endSessionEarly() {
    const sid = sessionIdRef.current;
    if (sid) {
      try { await practiceApi.end(sid); } catch { /* swallow */ }
    }
    restart();
  }

  // ── Restart ────────────────────────────────────────────────────────────────

  function restart() {
    setPhase("entry");
    setSessionId(null);
    setPosition(null);
    setAnswer(null);
    setDoneStats(null);
    setError(null);
    setPendingPromotion(null);
    setRunningStats({ correct: 0, wrong: 0, positions_seen: 0 });
    setLineStep(0);
    lineStepRef.current = 0;
    setCurrentFen("");
    currentFenRef.current = "";
    setWrongMoveCtx(null);
    wrongMoveCtxRef.current = null;
    // Reset board to default starting position, view-only
    cgRef.current?.set({
      fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      viewOnly: true,
      movable: { free: false, color: undefined, dests: new Map() },
      drawable: { shapes: [] },
    });
  }

  // ── Computed ───────────────────────────────────────────────────────────────

  const isActive = phase !== "entry" && phase !== "done";
  const isViewOnly = phase !== "waiting" && phase !== "replaying";
  // "computer_move" is intentionally view-only (included by the line above).

  // ── Render ─────────────────────────────────────────────────────────────────
  //
  // ChessboardWrapper is ALWAYS in the JSX tree — it never unmounts.
  // During "entry" and "done" phases the board grid is hidden via
  // visibility:hidden (which preserves layout dimensions so Chessground's
  // getBoundingClientRect() keeps returning correct values).

  return (
    <div className="flex flex-col gap-4">

      {/* ── Mode entry (shown when phase === "entry") ── */}
      {phase === "entry" && (
        <ModeEntry onStart={startSession} isLoading={false} error={error} />
      )}

      {/* ── Session summary (shown when phase === "done") ── */}
      {phase === "done" && doneStats && (
        <SessionSummary stats={doneStats} onRestart={restart} />
      )}

      {/* ── Active session layout — ALWAYS MOUNTED ──────────────────────────
          visibility:hidden keeps the ChessboardWrapper in the DOM with correct
          dimensions during entry/done so Chessground is ready the instant
          the user clicks Start (cgRef.current is already set).              */}
      <div style={{ visibility: isActive ? "visible" : "hidden" }}>

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1>Practice</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink-400 mt-0.5">
              {position && (
                <>
                  <span>{position.library_name}</span>
                  <span className="text-ink-600">·</span>
                  <span>{position.line_name ?? "Line"}</span>
                  {position.is_new && (
                    <span className="px-1.5 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30">
                      New
                    </span>
                  )}
                  {position.is_leech && (
                    <span className="px-1.5 py-0.5 rounded text-xs bg-red-500/20 text-red-400 border border-red-500/30">
                      Leech
                    </span>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm">
            {/* Running score */}
            <div className="flex items-center gap-2">
              <span className="text-green-400 font-medium">{runningStats.correct}✓</span>
              <span className="text-red-400 font-medium">{runningStats.wrong}✗</span>
            </div>
            <button
              className="btn-ghost text-xs"
              onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}
              title="Flip board"
            >
              ⇅
            </button>
            <button className="btn-ghost text-xs text-ink-500" onClick={endSessionEarly}>
              End
            </button>
          </div>
        </div>

        {/* Board + panel */}
        <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 items-start">

          {/* Board */}
          <div className="relative">
            <ChessboardWrapper
              size={480}
              orientation={orientation}
              viewOnly={isViewOnly}
              onMove={onMove}
              cgRef={cgRef}
              boardTheme={boardTheme}
              pieceSet={pieceSet}
            />

            {/* Phase border overlays */}
            {(phase === "feedback_wrong" || phase === "replaying") && (
              <div className="absolute inset-0 border-2 border-red-500/50 rounded pointer-events-none" />
            )}
            {phase === "feedback_correct" && (
              <div className="absolute inset-0 border-2 border-green-500/50 rounded pointer-events-none" />
            )}

            {/* Loading veil */}
            {(phase === "loading" || phase === "submitting") && (
              <div className="absolute inset-0 bg-ink-900/60 flex items-center justify-center rounded">
                <div className="w-6 h-6 border-2 border-gold-400 border-t-transparent rounded-full animate-spin" />
              </div>
            )}
          </div>

          {/* Side panel */}
          <div className="card flex flex-col gap-4" style={{ minHeight: 480 }}>

            {/* Position context */}
            {position && (
              <div className="border-b border-ink-700 pb-3">
                <div className="text-sm font-medium text-ink-100 mb-1">
                  {position.turn_color === "white" ? "♔" : "♚"}{" "}
                  {position.turn_color === "white" ? "White" : "Black"} to move
                </div>
                {position.preceding_moves.length > 0 && (
                  <div className="text-xs text-ink-500">
                    After{" "}
                    <span className="text-ink-300">
                      {position.preceding_moves.map((m) => m.san).join(" ")}
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-2 mt-1.5 text-xs text-ink-500">
                  <span>
                    Rep {position.repetitions} · EF {position.ease_factor.toFixed(2)}
                  </span>
                </div>
              </div>
            )}

            {/* Phase-specific content */}
            <div className="flex-1 flex flex-col">

              {/* loading */}
              {phase === "loading" && (
                <div className="flex-1 flex items-center justify-center text-ink-500 text-sm">
                  Loading…
                </div>
              )}

              {/* animating */}
              {phase === "animating" && (
                <div className="flex-1 flex items-center justify-center">
                  <p className="text-ink-400 text-sm animate-pulse text-center">
                    Replaying preceding moves…
                  </p>
                </div>
              )}

              {/* computer_move */}
              {phase === "computer_move" && (
                <div className="flex-1 flex items-center justify-center">
                  <p className="text-ink-400 text-sm animate-pulse text-center">
                    Opponent replies…
                  </p>
                </div>
              )}

              {/* waiting */}
              {phase === "waiting" && (
                <div className="flex-1 flex flex-col items-center justify-center gap-2">
                  <p className="text-ink-400 text-sm text-center">
                    Make your move on the board
                  </p>
                  <div className="text-3xl opacity-30">♟</div>
                </div>
              )}

              {/* submitting */}
              {phase === "submitting" && (
                <div className="flex-1 flex items-center justify-center text-ink-500 text-sm animate-pulse">
                  Checking…
                </div>
              )}

              {/* feedback_correct */}
              {phase === "feedback_correct" && answer && position && (
                <div className="flex-1 flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-green-400 text-xl">✓</span>
                    <span className="font-semibold text-green-400">Line complete!</span>
                  </div>

                  {/* Show how many moves the user played through */}
                  {position.remaining_moves.length > 1 && (
                    <div className="text-xs text-ink-400">
                      Played{" "}
                      <span className="text-ink-200">
                        {Math.ceil(position.remaining_moves.length / 2)}
                      </span>{" "}
                      move{Math.ceil(position.remaining_moves.length / 2) !== 1 ? "s" : ""} ·{" "}
                      <span className="text-ink-300">
                        {position.remaining_moves.map((m) => m.san).join(" ")}
                      </span>
                    </div>
                  )}

                  {answer.note && (
                    <blockquote className="text-xs text-ink-300 italic border-l-2 border-gold-500/40 pl-3">
                      {answer.note}
                    </blockquote>
                  )}

                  <div className="text-xs text-ink-400 space-y-0.5">
                    <div>
                      Next review:{" "}
                      <span className="text-ink-200">
                        {intervalLabel(answer.srs.interval_days)}
                      </span>
                    </div>
                    <div>
                      Streak:{" "}
                      <span className="text-ink-200">{answer.srs.repetitions}</span>
                      {answer.srs.is_leech && (
                        <span className="ml-2 text-red-400">⚠ leech</span>
                      )}
                    </div>
                  </div>

                  <div className="mt-auto flex gap-2">
                    <button
                      className="flex-1 py-2 rounded text-sm border border-ink-700 text-ink-400 hover:border-red-500/60 hover:text-red-400 transition-colors"
                      onClick={() => advanceToNext(sessionId!)}
                    >
                      Hard
                    </button>
                    <button
                      className="flex-1 py-2 rounded text-sm border border-ink-600 text-ink-200 hover:border-ink-400 transition-colors font-medium"
                      onClick={() => advanceToNext(sessionId!)}
                    >
                      OK
                    </button>
                    <button
                      className="flex-1 py-2 rounded text-sm border border-ink-700 text-ink-400 hover:border-green-500/60 hover:text-green-400 transition-colors"
                      onClick={() => advanceToNext(sessionId!)}
                    >
                      Easy
                    </button>
                  </div>
                </div>
              )}

              {/* feedback_wrong */}
              {phase === "feedback_wrong" && wrongMoveCtx && (
                <div className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-red-400 text-xl">✗</span>
                    <span className="font-semibold text-red-400">Wrong</span>
                  </div>
                  <div className="text-sm text-ink-300">
                    Correct move:{" "}
                    <span className="font-semibold text-ink-100">{wrongMoveCtx.san}</span>
                  </div>
                  <p className="text-xs text-ink-500 animate-pulse">
                    Study the correct move…
                  </p>
                </div>
              )}

              {/* replaying */}
              {phase === "replaying" && wrongMoveCtx && (
                <div className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-red-400 text-xl">✗</span>
                    <span className="font-semibold text-red-400">Wrong</span>
                  </div>
                  <div className="text-sm text-ink-300">
                    Correct move:{" "}
                    <span className="font-semibold text-ink-100">{wrongMoveCtx.san}</span>
                  </div>
                  <p className="text-xs text-gold-400 animate-pulse">
                    ↑ Play the correct move to continue
                  </p>
                </div>
              )}

            </div>

            {/* Error banner */}
            {error && isActive && (
              <div className="text-red-400 text-xs px-2 py-1.5 rounded bg-red-500/10 border border-red-500/20">
                {error}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Promotion modal */}
      {pendingPromotion && (
        <PromotionModal
          color={position?.turn_color ?? "white"}
          onSelect={confirmPromotion}
          onCancel={() => setPendingPromotion(null)}
        />
      )}
    </div>
  );
}
