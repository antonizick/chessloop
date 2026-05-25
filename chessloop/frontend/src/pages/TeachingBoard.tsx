import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Api } from "chessground/api";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { MoveList } from "@/components/teaching/MoveList";
import { PromotionModal } from "@/components/teaching/PromotionModal";
import { LineSelector } from "@/components/teaching/LineSelector";
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

      {/* Line selector */}
      <LineSelector
        lines={lines}
        selectedId={selectedLineId}
        onSelect={setSelectedLineId}
        onCreateNew={(name) => createLine.mutate(name)}
        onRename={(lineId, newName) => renameLine.mutateAsync({ lineId, newName })}
        isCreating={createLine.isPending}
      />

      {/* Board + move list */}
      <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 items-start">
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

        <div className="card min-h-[480px] flex flex-col">
          <div className="flex items-center justify-between mb-3">
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
              Create or select a line above to start recording.
            </p>
          ) : (
            <div className="flex-1 overflow-y-auto">
              <MoveList
                moves={teaching.moves}
                viewIndex={teaching.viewIndex}
                isAtEnd={teaching.isAtEnd}
                onJump={teaching.jumpTo}
                onJumpToStart={handleJumpToStart}
                onJumpToEnd={teaching.jumpToEnd}
                onDeleteFrom={handleDeleteFrom}
              />
            </div>
          )}

          {selectedLine && teaching.isAtEnd && !teaching.pendingPromotion && (
            <p className="text-xs text-ink-400 mt-3 border-t border-ink-700 pt-3">
              {teaching.liveTurnColor === "white" ? "♔" : "♚"}{" "}
              {teaching.liveTurnColor.charAt(0).toUpperCase() + teaching.liveTurnColor.slice(1)} to move
              {teaching.moves.length === 0 && " · drag a piece to begin"}
            </p>
          )}
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
