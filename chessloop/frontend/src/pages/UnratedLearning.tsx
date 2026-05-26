import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { Api } from "chessground/api";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { MoveList, generatePgn, exportPgn } from "@/components/teaching/MoveList";
import { useTeaching } from "@/hooks/useTeaching";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { librariesApi } from "@/api/libraries";
import { linesApi } from "@/api/lines";
import { useAuthStore } from "@/stores/auth";
import { playNavigationSound } from "@/utils/sounds";
import type { Line } from "@/types";

export function UnratedLearning() {
  const { id: libId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();

  const { data: user = useAuthStore.getState().user } = useCurrentUser();

  const soundsOn = user?.sounds_on ?? true;
  const boardTheme = user?.board_theme ?? "brown";
  const pieceSet = user?.piece_set ?? "cburnett";

  // ── Data ─────────────────────────────────────────────────────────────────
  const { data: lib } = useQuery({
    queryKey: ["library", libId],
    queryFn: () => librariesApi.get(libId!),
    enabled: !!libId,
  });

  const { data: lines = [] } = useQuery({
    queryKey: ["lines", libId],
    queryFn: () => linesApi.listForLibrary(libId!),
    enabled: !!libId,
  });

  const urlLineId = searchParams.get("lineId");
  const [selectedLineId, setSelectedLineId] = useState<string | null>(urlLineId);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // Sync orientation with library color on first load
  useEffect(() => {
    if (lib) setOrientation(lib.color === "black" ? "black" : "white");
  }, [lib?.id]);

  // Auto-select first line when lines load
  useEffect(() => {
    if (lines.length > 0 && !selectedLineId) {
      setSelectedLineId(lines[0].id);
    }
  }, [lines.length]);

  const selectedLine: Line | undefined = lines.find((l) => l.id === selectedLineId);

  // ── Teaching hook ─────────────────────────────────────────────────────────
  const teaching = useTeaching();
  const cgRef = useRef<Api | null>(null);

  // When selected line changes, reset the chess state and update Chessground
  useEffect(() => {
    if (!selectedLine) return;
    teaching.resetToLine(selectedLine.starting_fen, selectedLine.moves);
  }, [selectedLine?.id]);

  // Sync Chessground whenever teaching state changes (fen, dests, turn)
  // Always viewOnly since this is read-only mode
  useEffect(() => {
    if (!cgRef.current) return;
    cgRef.current.set({
      fen: teaching.boardFen,
      viewOnly: true,
      turnColor: teaching.liveTurnColor,
      movable: {
        free: false,
        color: undefined,
        dests: new Map(),
        showDests: true,
      },
    });
  }, [teaching.boardFen, teaching.liveTurnColor]);

  // ── Reset to start ───────────────────────────────────────────────────────
  function handleJumpToStart() {
    teaching.jumpTo(-1);
    playNavigationSound(soundsOn);
  }

  // ── Keyboard navigation ───────────────────────────────────────────────────
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      // Ignore if typing in input or textarea
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          handlePreviousMove();
          break;
        case "ArrowRight":
          e.preventDefault();
          handleNextMove();
          break;
        case "ArrowDown":
          e.preventDefault();
          handleJumpToStart();
          break;
        case "ArrowUp":
          e.preventDefault();
          if (selectedLine) {
            teaching.jumpToEnd();
            playNavigationSound(soundsOn);
          }
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [teaching, selectedLine]);

  // ── Navigation and export handlers ────────────────────────────────────────
  function handlePreviousMove() {
    if (teaching.viewIndex === null) {
      if (teaching.moves.length > 0) {
        const newIndex = teaching.moves.length - 1;
        teaching.jumpTo(newIndex);
      }
    } else if (teaching.viewIndex > 0) {
      const newIndex = teaching.viewIndex - 1;
      teaching.jumpTo(newIndex);
    } else if (teaching.viewIndex === 0) {
      teaching.jumpTo(-1);
    }
    playNavigationSound(soundsOn);
  }

  function handleNextMove() {
    if (teaching.viewIndex === null) {
      return;
    }
    if (teaching.viewIndex < teaching.moves.length - 1) {
      const newIndex = teaching.viewIndex + 1;
      teaching.jumpTo(newIndex);
    } else {
      teaching.jumpToEnd();
    }
    playNavigationSound(soundsOn);
  }

  function handleExportPgn() {
    const lineName = selectedLine?.name || undefined;
    const pgn = generatePgn(teaching.moves, lineName);
    exportPgn(pgn, lineName);
  }

  function handleCopyPgnToClipboard() {
    const lineName = selectedLine?.name || undefined;
    const pgn = generatePgn(teaching.moves, lineName);
    navigator.clipboard.writeText(pgn).then(
      () => {
        setCopyFeedback("✓");
        setTimeout(() => setCopyFeedback(null), 1500);
      },
      () => {
        setCopyFeedback("✕");
        setTimeout(() => setCopyFeedback(null), 1500);
      }
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <Link to={`/libraries/${libId}`} className="text-sm text-ink-300">
          ← {lib?.name ?? "Library"}
        </Link>
        <div className="flex items-center justify-between mt-1">
          <h1>Unrated Learning</h1>
          <div className="flex items-center gap-2 text-sm">
            <button
              className="btn-ghost text-sm"
              onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}
              title="Flip board"
            >
              ⇅ Flip
            </button>
          </div>
        </div>
      </div>

      {/* Board + move list + line selector */}
      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr_280px] gap-6 items-start">
        <div className="flex flex-col gap-4">
          <div className="relative">
            <ChessboardWrapper
              orientation={orientation}
              viewOnly={true}
              onMove={() => {}}
              cgRef={cgRef}
              boardTheme={boardTheme}
              pieceSet={pieceSet}
            />
          </div>
        </div>

        <div className="card min-h-[480px] flex flex-col">
          <div className="flex flex-col gap-2 mb-3">
            <h2>
              {selectedLine?.name ?? "Select a line"}
            </h2>
            {selectedLine && (
              <span className="text-xs text-ink-400">
                {teaching.moves.length} move{teaching.moves.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {!selectedLine ? (
            <p className="text-ink-300 text-sm italic">
              Select a line to start browsing.
            </p>
          ) : (
            <div className="flex-1 overflow-y-auto">
              <MoveList
                moves={teaching.moves}
                viewIndex={teaching.viewIndex}
                isAtEnd={teaching.isAtEnd}
                onJump={(index) => {
                  teaching.jumpTo(index);
                  playNavigationSound(soundsOn);
                }}
                onJumpToEnd={() => {
                  teaching.jumpToEnd();
                  playNavigationSound(soundsOn);
                }}
                onDeleteFrom={() => {}}
              />
            </div>
          )}

          {selectedLine && teaching.moves.length > 0 && (
            <div className="mt-3 border-t border-ink-700 pt-3 flex flex-col gap-2">
              <div className="flex items-center gap-1 text-xs">
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleJumpToStart}
                  title="Go to first move (↓)"
                >
                  ⟪
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handlePreviousMove}
                  title="Previous move (←)"
                >
                  ‹
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleNextMove}
                  disabled={teaching.isAtEnd}
                  title="Next move (→)"
                >
                  ›
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={() => {
                    teaching.jumpToEnd();
                    playNavigationSound(soundsOn);
                  }}
                  title="Go to last move (↑)"
                >
                  ⟫
                </button>
                <span className="flex-1" />
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleCopyPgnToClipboard}
                  title="Copy PGN to clipboard"
                >
                  {copyFeedback || "📋"}
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleExportPgn}
                  title="Export as PGN"
                >
                  ↓ PGN
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Line selector panel */}
        <div className="card flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-ink-200">Lines</h2>
          <div className="flex-1 overflow-y-auto">
            <div className="flex flex-col gap-2">
              {lines.map((line) => (
                <button
                  key={line.id}
                  className={`w-full text-left rounded px-2 py-1.5 text-xs font-medium transition-colors truncate
                    ${selectedLineId === line.id
                      ? "bg-gold-500 text-ink-900"
                      : "bg-ink-700 text-ink-200 hover:bg-ink-600"
                    }`}
                  onClick={() => setSelectedLineId(line.id)}
                  title={line.name ? `${line.name} (${line.moves.length} moves)` : `${line.moves.length} moves`}
                >
                  <span>{line.name || "Unnamed"}</span>
                  <span className="text-xs opacity-60"> ({line.moves.length})</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
