import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { Api } from "chessground/api";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { ConflictEvaluator } from "@/components/board/ConflictEvaluator";
import { MoveList, generatePgn, exportPgn } from "@/components/teaching/MoveList";
import { MoveNoteEditor } from "@/components/teaching/MoveNoteEditor";
import { useTeaching } from "@/hooks/useTeaching";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { publicApi } from "@/api/public";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { playNavigationSound } from "@/utils/sounds";
import { ttsService } from "@/services/textToSpeech";
import type { Line } from "@/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function PublicLearn() {
  const { id: libId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const setUser = useAuthStore((s) => s.setUser);

  const { data: user = useAuthStore.getState().user } = useCurrentUser();

  const soundsOn = user?.sounds_on ?? true;
  const boardTheme = user?.board_theme ?? "brown";
  const pieceSet = user?.piece_set ?? "cburnett";
  const ttsEnabled = user?.tts_enabled ?? true;
  const ttsVoice = user?.tts_voice ?? "Microsoft Zira";

  useEffect(() => {
    ttsService.setEnabled(ttsEnabled);
    ttsService.setDefaultVoice(ttsVoice);
  }, [ttsEnabled, ttsVoice]);

  // Mutation for toggling TTS preference
  const updateTtsEnabled = useMutation({
    mutationFn: (enabled: boolean) =>
      authApi.updatePreferences({ tts_enabled: enabled }),
    onSuccess: (updatedUser) => {
      setUser(updatedUser);
      qc.invalidateQueries({ queryKey: ["me"] });
      ttsService.setEnabled(updatedUser.tts_enabled);
    },
  });

  const { data: lib } = useQuery({
    queryKey: ["public-library", libId],
    queryFn: () => publicApi.getLibrary(libId!),
    enabled: !!libId,
  });

  const { data: lines = [] } = useQuery({
    queryKey: ["public-library-lines", libId],
    queryFn: () => publicApi.getLines(libId!),
    enabled: !!libId,
  });

  const urlLineId = searchParams.get("lineId");
  const [selectedLineId, setSelectedLineId] = useState<string | null>(urlLineId);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (lib) setOrientation(lib.color === "black" ? "black" : "white");
  }, [lib?.id]);

  useEffect(() => {
    if (lines.length > 0 && !selectedLineId) {
      setSelectedLineId(lines[0].id);
    }
  }, [lines.length]);

  const selectedLine: Line | undefined = lines.find((l) => l.id === selectedLineId);

  const teaching = useTeaching();
  const cgRef = useRef<Api | null>(null);

  useEffect(() => {
    if (!selectedLine) return;
    teaching.resetToLine(selectedLine.starting_fen, selectedLine.moves);
  }, [selectedLine?.id]);

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

  useEffect(() => {
    if (ttsEnabled && teaching.viewIndex !== null && teaching.viewIndex >= 0) {
      const currentMove = teaching.moves[teaching.viewIndex];
      if (currentMove?.note) {
        ttsService.speak(currentMove.note);
      }
    }
  }, [teaching.viewIndex, ttsEnabled, teaching.moves]);

  function handleJumpToStart() {
    teaching.jumpTo(-1);
    playNavigationSound(soundsOn);
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
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

  function handlePreviousMove() {
    if (teaching.viewIndex === null) {
      if (teaching.moves.length > 0) {
        teaching.jumpTo(teaching.moves.length - 1);
      }
    } else if (teaching.viewIndex > 0) {
      teaching.jumpTo(teaching.viewIndex - 1);
    } else if (teaching.viewIndex === 0) {
      teaching.jumpTo(-1);
    }
    playNavigationSound(soundsOn);
  }

  function handleNextMove() {
    if (teaching.viewIndex === null) return;
    if (teaching.viewIndex < teaching.moves.length - 1) {
      teaching.jumpTo(teaching.viewIndex + 1);
    } else {
      teaching.jumpToEnd();
    }
    playNavigationSound(soundsOn);
  }

  function handleExportPgn() {
    const lineName = selectedLine?.name || undefined;
    exportPgn(generatePgn(teaching.moves, lineName), lineName);
  }

  function handleCopyPgn() {
    const pgn = generatePgn(teaching.moves, selectedLine?.name || undefined);
    navigator.clipboard.writeText(pgn).then(
      () => { setCopyFeedback("✓"); setTimeout(() => setCopyFeedback(null), 1500); },
      () => { setCopyFeedback("✕"); setTimeout(() => setCopyFeedback(null), 1500); },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <Link to={`/public/${libId}`} className="text-sm text-ink-300 hover:text-gold-400">
          ← {lib?.name ?? "Library"}
        </Link>
        <div className="flex items-center justify-between mt-1">
          <div className="flex items-center gap-2">
            <h1>Learn / View</h1>
            <span className="text-xs px-2 py-1 bg-ink-700 text-ink-400 rounded">Read-only</span>
          </div>
          <button
            className="btn-ghost text-sm"
            onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}
            title="Flip board"
          >
            ⇅ Flip
          </button>
        </div>
      </div>

      {/* Board + move list + line selector */}
      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr_280px] gap-6 items-start">
        <div className="flex flex-col gap-4">
          <ChessboardWrapper
            orientation={orientation}
            viewOnly={true}
            onMove={() => {}}
            cgRef={cgRef}
            boardTheme={boardTheme}
            pieceSet={pieceSet}
          />

          {selectedLine && teaching.viewIndex !== null && (
            <div className="card p-4 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink-300">Move Notes</h3>
                <div className="flex items-center gap-3">
                  <label className="text-xs text-ink-400">Read aloud</label>
                  <button
                    onClick={() => updateTtsEnabled.mutate(!ttsEnabled)}
                    disabled={updateTtsEnabled.isPending}
                    className={`relative w-10 h-6 rounded-full transition-colors ${
                      ttsEnabled ? "bg-gold-500" : "bg-ink-600"
                    } disabled:opacity-50`}
                    role="switch"
                    aria-checked={ttsEnabled}
                    title={ttsEnabled ? "Disable reading notes aloud" : "Enable reading notes aloud"}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                        ttsEnabled ? "translate-x-4" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>
              </div>
              <MoveNoteEditor
                lineId={selectedLine.id}
                moveIndex={teaching.viewIndex}
                currentMove={teaching.moves[teaching.viewIndex] || null}
                libraryId={libId}
                readOnly={true}
              />
            </div>
          )}

          {libId && selectedLineId && (
            <div className="card p-4">
              <ConflictEvaluator libraryId={libId} currentFen={teaching.boardFen} currentLineId={selectedLineId} />
            </div>
          )}
        </div>

        <div className="card min-h-[480px] flex flex-col">
          <div className="flex flex-col gap-2 mb-3">
            <h2>{selectedLine?.name ?? "Select a line"}</h2>
            {selectedLine && (
              <span className="text-xs text-ink-400">
                {teaching.moves.length} move{teaching.moves.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {!selectedLine ? (
            <p className="text-ink-300 text-sm italic">Select a line to start browsing.</p>
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
            <div className="mt-3 border-t border-ink-700 pt-3">
              <div className="flex items-center gap-1 text-xs">
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleJumpToStart} title="First move (↓)">⟪</button>
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handlePreviousMove} title="Previous (←)">‹</button>
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleNextMove} disabled={teaching.isAtEnd} title="Next (→)">›</button>
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={() => { teaching.jumpToEnd(); playNavigationSound(soundsOn); }} title="Last move (↑)">⟫</button>
                <span className="flex-1" />
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleCopyPgn} title="Copy PGN">{copyFeedback || "📋"}</button>
                <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleExportPgn} title="Export PGN">↓ PGN</button>
              </div>
            </div>
          )}
        </div>

        {/* Line selector */}
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
