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
import { playMoveSound, playCaptureSound } from "@/utils/sounds";
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
  | "animating"
  | "waiting"
  | "submitting"
  | "feedback_correct"
  | "feedback_wrong"
  | "replaying"
  | "done";

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

  // Stable refs to avoid stale closures in setTimeout callbacks
  const positionRef = useRef<NextPositionResponse | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const modeRef = useRef<UiMode>("weakest");

  positionRef.current = position;
  sessionIdRef.current = sessionId;
  modeRef.current = mode;

  // ── Board helpers ──────────────────────────────────────────────────────────

  const enableBoardForUser = useCallback((pos: NextPositionResponse) => {
    cgRef.current?.set({
      fen: pos.fen_before,
      viewOnly: false,
      turnColor: pos.turn_color,
      movable: {
        free: false,
        color: pos.turn_color,
        dests: legalDests(pos.fen_before),
        showDests: true,
      },
      draggable: { enabled: true },
      drawable: { shapes: [] },
    });
    startedAtRef.current = Date.now();
  }, []);

  // ── Enable board when phase → "waiting" ────────────────────────────────────
  //
  // Run inside useEffect so it fires AFTER React has committed the render and
  // all child effects (ChessboardWrapper's init) have completed.  Since
  // ChessboardWrapper is now always mounted, cgRef.current is guaranteed to be
  // set long before startSession is ever called.
  useEffect(() => {
    if (phase !== "waiting" || !position) return;
    enableBoardForUser(position);
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
      playMoveSound();
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

    if (phase === "replaying") {
      // Forced replay — any move here is the correct one (dests limited to 1 square).
      playMoveSound();
      cgRef.current?.set({
        fen: answer!.fen_after,
        viewOnly: true,
        drawable: { shapes: [] },
      });
      setTimeout(() => advanceToNext(sid), 700);
      return;
    }

    if (phase !== "waiting") return;

    // Check for promotion
    if (isPromotion(pos.fen_before, from, to)) {
      // Snap piece back — wait for promotion modal selection
      cgRef.current?.set({ fen: pos.fen_before });
      setPendingPromotion({ from, to });
      return;
    }

    playMoveSound();
    await submitAnswer(`${from}${to}`, null);
  }

  async function confirmPromotion(piece: "q" | "r" | "b" | "n") {
    if (!pendingPromotion) return;
    const { from, to } = pendingPromotion;
    setPendingPromotion(null);
    await submitAnswer(`${from}${to}${piece}`, null);
  }

  // ── Submit answer to server ────────────────────────────────────────────────

  async function submitAnswer(uci: string, ease: "easy" | "hard" | null) {
    const pos = positionRef.current;
    const sid = sessionIdRef.current;
    if (!pos || !sid) return;

    setPhase("submitting");
    const elapsedMs = Date.now() - startedAtRef.current;

    try {
      const result = await practiceApi.answer(sid, {
        practice_position_id: pos.practice_position_id,
        move_uci: uci,
        ease,
        response_ms: elapsedMs,
      });

      setAnswer(result);
      setRunningStats((prev) => ({
        correct: result.correct ? prev.correct + 1 : prev.correct,
        wrong: result.correct ? prev.wrong : prev.wrong + 1,
        positions_seen: prev.positions_seen + 1,
      }));

      if (result.correct) {
        cgRef.current?.set({
          fen: result.fen_after,
          viewOnly: true,
          drawable: { shapes: [] },
        });
        setPhase("feedback_correct");
      } else {
        showWrongFeedback(pos, result);
      }
    } catch {
      setError("Network error. Try again.");
      setPhase("waiting");
    }
  }

  // ── Wrong answer: red flash → forced replay ────────────────────────────────

  function showWrongFeedback(pos: NextPositionResponse, result: AnswerResponse) {
    const from = result.expected_uci.slice(0, 2) as Key;
    const to = result.expected_uci.slice(2, 4) as Key;
    playCaptureSound(); // distinct "crack" to signal a wrong answer

    // Step 1: show board at the question position with a red arrow
    cgRef.current?.set({
      fen: pos.fen_before,
      viewOnly: true,
      drawable: {
        enabled: true,
        visible: true,
        shapes: [{ orig: from, dest: to, brush: "red" }],
      },
    });
    setPhase("feedback_wrong");

    // Step 2: after 1.6s switch to forced-replay with green guide arrow
    setTimeout(() => {
      if (!cgRef.current) return;
      cgRef.current.set({
        fen: pos.fen_before,
        viewOnly: false,
        turnColor: pos.turn_color,
        movable: {
          free: false,
          color: pos.turn_color,
          // Only allow the one correct square
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
              {phase === "feedback_correct" && answer && (
                <div className="flex-1 flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-green-400 text-xl">✓</span>
                    <span className="font-semibold text-green-400">Correct!</span>
                    <span className="text-ink-300 ml-1">{answer.expected_san}</span>
                  </div>

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
              {phase === "feedback_wrong" && answer && (
                <div className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-red-400 text-xl">✗</span>
                    <span className="font-semibold text-red-400">Wrong</span>
                  </div>
                  <div className="text-sm text-ink-300">
                    Correct move:{" "}
                    <span className="font-semibold text-ink-100">{answer.expected_san}</span>
                  </div>
                  <p className="text-xs text-ink-500 animate-pulse">
                    Study the correct move…
                  </p>
                </div>
              )}

              {/* replaying */}
              {phase === "replaying" && answer && (
                <div className="flex-1 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-red-400 text-xl">✗</span>
                    <span className="font-semibold text-red-400">Wrong</span>
                  </div>
                  <div className="text-sm text-ink-300">
                    Correct move:{" "}
                    <span className="font-semibold text-ink-100">{answer.expected_san}</span>
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
