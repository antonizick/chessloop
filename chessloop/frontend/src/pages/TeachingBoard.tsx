import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Api } from "chessground/api";
import { Chess } from "chess.js";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { MoveList, generatePgn, exportPgn } from "@/components/teaching/MoveList";
import { MoveNoteEditor } from "@/components/teaching/MoveNoteEditor";
import { PromotionModal } from "@/components/teaching/PromotionModal";
import { useTeaching } from "@/hooks/useTeaching";
import { librariesApi } from "@/api/libraries";
import { linesApi } from "@/api/lines";
import { useAuthStore } from "@/stores/auth";
import { playMoveSound } from "@/utils/sounds";
import type { Line } from "@/types";

export function TeachingBoard() {
  const { id: libId } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
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

  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [isSaving, setIsSaving] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedMoveForNote, setSelectedMoveForNote] = useState<number | null>(null);

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
    // Update board after reset (cgRef might not be ready on very first render)
    // Chessground sync happens via the teaching-state useEffect below
  }, [selectedLine?.id]);

  // Sync Chessground whenever teaching state changes (fen, dests, turn)
  useEffect(() => {
    if (!cgRef.current) return;
    const atEnd = teaching.isAtEnd;
    cgRef.current.set({
      fen: teaching.boardFen,
      viewOnly: !atEnd,
      turnColor: teaching.liveTurnColor,
      movable: {
        free: false,
        color: atEnd ? teaching.liveTurnColor : undefined,
        dests: atEnd ? teaching.liveDests : new Map(),
        showDests: true,
      },
    });
  }, [teaching.boardFen, teaching.liveDests, teaching.liveTurnColor, teaching.isAtEnd]);

  // ── Mutations ────────────────────────────────────────────────────────────
  const createLine = useMutation({
    mutationFn: (name: string | null) => linesApi.create(libId!, { name: name || undefined }),
    onSuccess: (line) => {
      qc.invalidateQueries({ queryKey: ["lines", libId] });
      setSelectedLineId(line.id);
    },
  });

  const renameLine = useMutation({
    mutationFn: ({ lineId, newName }: { lineId: string; newName: string }) =>
      linesApi.update(lineId, { name: newName }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lines", libId] });
    },
  });

  const deleteLine = useMutation({
    mutationFn: (lineId: string) => linesApi.remove(lineId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lines", libId] });
      if (selectedLineId && selectedLineId === lines[0]?.id) {
        if (lines.length > 1) {
          setSelectedLineId(lines[1].id);
        } else {
          setSelectedLineId(null);
        }
      }
    },
  });

  const importLinesMut = useMutation({
    mutationFn: (body: { moves: string[]; starting_fen?: string }) =>
      linesApi.importMoves(selectedLineId!, body),
    onSuccess: (updatedLine) => {
      qc.invalidateQueries({ queryKey: ["lines", libId] });
      teaching.resetToLine(updatedLine.starting_fen, updatedLine.moves);
      setShowImport(false);
      setImportText("");
      setImportError(null);
    },
    onError: (e: any) => setImportError(e.message ?? "Import failed"),
  });

  // ── Import handler ──────────────────────────────────────────────────────────
  function handleImport() {
    const text = importText.trim();
    if (!text) {
      setImportError("Enter PGN, FEN, or moves to import");
      return;
    }

    const chess = new Chess();
    let moves: string[] = [];
    let starting_fen: string | undefined;

    // Try PGN first (contains move numbers like "1.e4")
    try {
      chess.loadPgn(text);
      moves = chess.history();
      importLinesMut.mutate({ moves, starting_fen });
      return;
    } catch {
      // PGN failed, try other formats
    }

    // Check if it looks like a FEN (has "/" and starts with piece placement)
    const looksLikeFen = /^[rnbqkpRNBQKP1-8\/]+ [wb] /.test(text);
    if (looksLikeFen) {
      try {
        chess.load(text);
        starting_fen = text;
        moves = [];
        importLinesMut.mutate({ moves, starting_fen });
        return;
      } catch {
        setImportError("Invalid FEN string");
        return;
      }
    }

    // Try as plain SAN list (e.g. "e4 c5 Nf3 d6")
    try {
      const sans = text.replace(/\d+\./g, "").trim().split(/\s+/).filter(Boolean);
      chess.reset();
      for (const san of sans) {
        chess.move(san);
      }
      moves = chess.history();
      importLinesMut.mutate({ moves, starting_fen });
      return;
    } catch {
      setImportError("Could not parse as PGN, FEN, or SAN list");
      return;
    }
  }

  // ── Move handler ─────────────────────────────────────────────────────────
  async function onMove({ from, to }: { from: string; to: string }) {
    const result = teaching.tryMove(from as any, to as any);

    if (result === "promotion") {
      // Reset Chessground visually — pawn jumped but we haven't committed
      cgRef.current?.set({ fen: teaching.boardFen });
      return;
    }

    if (!result || !selectedLineId) return;

    playMoveSound(soundsOn);

    // Chessground already shows the moved piece; update legal dests for next move
    cgRef.current?.set({
      turnColor: teaching.liveTurnColor,
      movable: {
        free: false,
        color: teaching.liveTurnColor,
        dests: teaching.liveDests,
        showDests: true,
      },
    });

    // Persist to backend
    setIsSaving(true);
    try {
      await linesApi.appendMove(selectedLineId, result);
      // Refresh the lines query so the move is persisted
      qc.invalidateQueries({ queryKey: ["lines", libId] });
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setIsSaving(false);
    }
  }

  // ── Promotion confirm/cancel ──────────────────────────────────────────────
  async function handlePromotionSelect(piece: "q" | "r" | "b" | "n") {
    const result = teaching.confirmPromotion(piece);
    if (!result || result === "promotion" || !selectedLineId) return;
    setIsSaving(true);
    try {
      await linesApi.appendMove(selectedLineId, result);
      // Refresh the lines query so the move is persisted
      qc.invalidateQueries({ queryKey: ["lines", libId] });
    } finally {
      setIsSaving(false);
    }
  }

  // ── Delete from move index ────────────────────────────────────────────────
  async function handleDeleteFrom(index: number) {
    if (!selectedLineId) return;
    teaching.deleteFrom(index);
    try {
      await linesApi.deleteMove(selectedLineId, index);
      // Refresh lines so move count is accurate in selector
      qc.invalidateQueries({ queryKey: ["lines", libId] });
    } catch (err) {
      console.error("Delete failed:", err);
    }
  }

  // ── Reset to start ───────────────────────────────────────────────────────
  function handleJumpToStart() {
    teaching.jumpTo(-1);
  }

  // ── Navigation and export handlers ────────────────────────────────────────
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
  }

  function handleNextMove() {
    if (teaching.viewIndex === null) {
      return;
    }
    if (teaching.viewIndex < teaching.moves.length - 1) {
      teaching.jumpTo(teaching.viewIndex + 1);
    } else {
      teaching.jumpToEnd();
    }
  }

  function handleExportPgn() {
    const lineName = selectedLine?.name || undefined;
    const pgn = generatePgn(teaching.moves, lineName);
    exportPgn(pgn, lineName);
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
          <h1>Teaching board</h1>
          <div className="flex items-center gap-2 text-sm">
            {isSaving && <span className="text-ink-400 animate-pulse">saving…</span>}
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
              viewOnly={!teaching.isAtEnd}
              onMove={onMove}
              cgRef={cgRef}
              boardTheme={boardTheme}
              pieceSet={pieceSet}
            />
            {/* Viewing-history banner */}
            {!teaching.isAtEnd && (
              <div
                className="absolute inset-0 border-2 border-gold-500/40 rounded pointer-events-none"
              />
            )}
          </div>

          {/* Move note editor - below board, same width */}
          {selectedLine && selectedMoveForNote !== null && (
            <div className="card p-4">
              <MoveNoteEditor
                lineId={selectedLine.id}
                moveIndex={selectedMoveForNote}
                currentMove={teaching.moves[selectedMoveForNote] || null}
                onNoteSaved={(index, noteText) => {
                  teaching.setMoveNote(index, noteText);
                }}
              />
            </div>
          )}
        </div>

        <div className="card min-h-[480px] flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h2>
              {selectedLine?.name ?? "Select a line"}
            </h2>
            <div className="flex items-center gap-2">
              {selectedLine && (
                <span className="text-xs text-ink-400">
                  {teaching.moves.length} move{teaching.moves.length !== 1 ? "s" : ""}
                </span>
              )}
              {selectedLine && (
                <button
                  className="btn-ghost text-xs px-2 py-1"
                  onClick={() => {
                    setShowImport(!showImport);
                    setImportError(null);
                  }}
                >
                  ↓ Import
                </button>
              )}
            </div>
          </div>

          {/* Import panel */}
          {showImport && selectedLine && (
            <div className="mb-3 flex flex-col gap-2 p-3 rounded-md bg-ink-900 border border-ink-700">
              <p className="text-xs text-ink-400">
                Paste PGN notation (e.g. <code>1.e4 c5 2.Nf3</code>) or a FEN string.
                This will <strong>replace</strong> the current line entirely.
              </p>
              <textarea
                className="input font-mono text-xs h-24 resize-none"
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder="1.e4 c5 2.Nf3 d6 3.d4..."
              />
              {importError && <p className="text-red-400 text-xs">{importError}</p>}
              <div className="flex gap-2">
                <button
                  className="btn-primary text-sm flex-1"
                  onClick={handleImport}
                  disabled={!importText.trim() || importLinesMut.isPending}
                >
                  {importLinesMut.isPending ? "Importing…" : "Import"}
                </button>
                <button
                  className="btn-ghost text-sm"
                  onClick={() => {
                    setShowImport(false);
                    setImportError(null);
                    setImportText("");
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {!selectedLine ? (
            <p className="text-ink-300 text-sm italic">
              Create or select a line above to start recording.
            </p>
          ) : (
            <div className="flex-1 overflow-y-auto">
              <MoveList
                moves={teaching.moves}
                viewIndex={teaching.viewIndex}
                isAtEnd={teaching.isAtEnd}
                onJump={(index) => {
                  teaching.jumpTo(index);
                  setSelectedMoveForNote(index);
                }}
                onJumpToEnd={teaching.jumpToEnd}
                onDeleteFrom={handleDeleteFrom}
              />
            </div>
          )}

          {selectedLine && teaching.moves.length > 0 && (
            <div className="mt-3 border-t border-ink-700 pt-3 flex flex-col gap-2">
              <div className="flex items-center gap-1 text-xs">
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleJumpToStart}
                  title="Go to first move"
                >
                  ⟪
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handlePreviousMove}
                  title="Previous move"
                >
                  ‹
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleNextMove}
                  disabled={teaching.isAtEnd}
                  title="Next move"
                >
                  ›
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={teaching.jumpToEnd}
                  title="Go to last move"
                >
                  ⟫
                </button>
                <span className="flex-1" />
                <button
                  className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400"
                  onClick={handleExportPgn}
                  title="Export as PGN"
                >
                  ↓ PGN
                </button>
              </div>
              {teaching.isAtEnd && !teaching.pendingPromotion && (
                <p className="text-xs text-ink-400 mt-3 border-t border-ink-700 pt-3">
                  {teaching.liveTurnColor === "white" ? "♔" : "♚"}{" "}
                  {teaching.liveTurnColor.charAt(0).toUpperCase() + teaching.liveTurnColor.slice(1)} to move
                  {teaching.moves.length === 0 && " · drag a piece to begin"}
                </p>
              )}
            </div>
          )}

          {selectedLine && teaching.isAtEnd && !teaching.pendingPromotion && teaching.moves.length === 0 && (
            <p className="text-xs text-ink-400 mt-3 border-t border-ink-700 pt-3">
              {teaching.liveTurnColor === "white" ? "♔" : "♚"}{" "}
              {teaching.liveTurnColor.charAt(0).toUpperCase() + teaching.liveTurnColor.slice(1)} to move
              {teaching.moves.length === 0 && " · drag a piece to begin"}
            </p>
          )}
        </div>

        {/* Line selector panel */}
        <div className="card flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-ink-200">Lines</h2>
          <div className="flex-1 overflow-y-auto">
            <div className="flex flex-col gap-2">
              {lines.map((line) => (
                <div key={line.id} className="relative flex items-start gap-1 group">
                  {renamingId === line.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (!renameValue.trim()) return;
                        renameLine.mutate({ lineId: line.id, newName: renameValue.trim() }, {
                          onSuccess: () => {
                            setRenamingId(null);
                            setRenameValue("");
                          },
                          onError: () => {
                            setRenamingId(null);
                            setRenameValue("");
                          },
                        });
                      }}
                      className="flex flex-col gap-1 w-full"
                    >
                      <input
                        autoFocus
                        className="input text-xs py-1"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                      />
                      <div className="flex gap-1">
                        <button className="btn-primary py-1 text-xs flex-1" disabled={renameLine.isPending}>
                          {renameLine.isPending ? "…" : "Save"}
                        </button>
                        <button
                          type="button"
                          className="btn-ghost py-1 text-xs"
                          onClick={() => {
                            setRenamingId(null);
                            setRenameValue("");
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <button
                        className={`w-full text-left rounded px-2 py-1.5 text-xs font-medium transition-colors truncate
                          ${selectedLineId === line.id
                            ? "bg-gold-500 text-ink-900"
                            : "bg-ink-700 text-ink-200 hover:bg-ink-600"
                          }`}
                        onClick={() => setSelectedLineId(line.id)}
                        onDoubleClick={() => {
                          setRenamingId(line.id);
                          setRenameValue(line.name || "");
                        }}
                        title={line.name ? `${line.name} (${line.moves.length} moves)` : `${line.moves.length} moves`}
                      >
                        <span>{line.name || "Unnamed"}</span>
                        <span className="text-xs opacity-60"> ({line.moves.length})</span>
                      </button>
                      {deleteConfirmId === line.id ? (
                        <div className="flex gap-0.5">
                          <button
                            type="button"
                            className="btn-ghost py-1 px-1.5 text-xs text-red-400 hover:bg-red-600/20"
                            onClick={() => {
                              setIsDeleting(true);
                              deleteLine.mutate(line.id, {
                                onSuccess: () => {
                                  setIsDeleting(false);
                                  setDeleteConfirmId(null);
                                },
                                onError: () => {
                                  setIsDeleting(false);
                                },
                              });
                            }}
                            disabled={isDeleting}
                            title="Confirm delete"
                          >
                            {isDeleting ? "…" : "✓"}
                          </button>
                          <button
                            type="button"
                            className="btn-ghost py-1 px-1.5 text-xs"
                            onClick={() => setDeleteConfirmId(null)}
                            disabled={isDeleting}
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn-ghost py-1 px-1.5 text-xs text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => setDeleteConfirmId(line.id)}
                          title="Delete line"
                        >
                          🗑
                        </button>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
          <button
            className="rounded px-2 py-1.5 text-xs bg-ink-800 border border-ink-600
                       text-ink-300 hover:border-gold-500 hover:text-gold-400 transition-colors"
            onClick={() => createLine.mutate(null)}
            disabled={createLine.isPending}
          >
            {createLine.isPending ? "Creating…" : "+ New line"}
          </button>
        </div>
      </div>

      {/* Promotion modal */}
      {teaching.pendingPromotion && (
        <PromotionModal
          color={teaching.liveTurnColor}
          onSelect={handlePromotionSelect}
          onCancel={teaching.cancelPromotion}
        />
      )}
    </div>
  );
}
