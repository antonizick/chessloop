import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Api } from "chessground/api";

import { ChessboardWrapper } from "@/components/board/ChessboardWrapper";
import { MoveList, generatePgn, exportPgn } from "@/components/teaching/MoveList";
import { MoveNoteEditor } from "@/components/teaching/MoveNoteEditor";
import { GameStats } from "@/components/games/GameStats";
import { useTeaching } from "@/hooks/useTeaching";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useAuthStore } from "@/stores/auth";
import { gamesApi, type GameCreate } from "@/api/games";
import { parsePgnToSans } from "@/utils/pgn";
import { playNavigationSound } from "@/utils/sounds";
import type { Game, GameColor, GameResult } from "@/types";

const PAGE_SIZE = 10;

const RESULT_STYLES: Record<GameResult, string> = {
  win: "text-emerald-400",
  loss: "text-red-400",
  draw: "text-ink-300",
};
const RESULT_LABEL: Record<GameResult, string> = { win: "Win", loss: "Loss", draw: "Draw" };

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function formatShort(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MyGames() {
  const qc = useQueryClient();
  const { data: user = useAuthStore.getState().user } = useCurrentUser();
  const soundsOn = user?.sounds_on ?? true;
  const boardTheme = user?.board_theme ?? "brown";
  const pieceSet = user?.piece_set ?? "cburnett";

  const { data: games = [] } = useQuery({ queryKey: ["games"], queryFn: gamesApi.list });

  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selectedMoveForNote, setSelectedMoveForNote] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingGame, setEditingGame] = useState<Game | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // Auto-select first game once loaded
  useEffect(() => {
    if (games.length > 0 && !selectedGameId) setSelectedGameId(games[0].id);
  }, [games.length]);

  const selectedGame: Game | undefined = games.find((g) => g.id === selectedGameId);

  const teaching = useTeaching();
  const cgRef = useRef<Api | null>(null);
  // Auto-orient to the colour the player played; the flip button is a manual override.
  const baseOrientation: GameColor = selectedGame?.played_color ?? "white";
  const orientation: GameColor = flipped
    ? baseOrientation === "white" ? "black" : "white"
    : baseOrientation;

  // Reset board state when the selected game changes (re-apply auto orientation)
  useEffect(() => {
    if (!selectedGame) return;
    teaching.resetToLine(selectedGame.starting_fen, selectedGame.moves);
    setSelectedMoveForNote(null);
    setFlipped(false);
  }, [selectedGame?.id]);

  // Keep the selected note in sync with the freshest move data after a note save
  const noteMove =
    selectedMoveForNote !== null ? teaching.moves[selectedMoveForNote] ?? null : null;

  // Sync Chessground (view-only — games are navigated, not edited on the board)
  useEffect(() => {
    if (!cgRef.current) return;
    cgRef.current.set({
      fen: teaching.boardFen,
      viewOnly: true,
      movable: { free: false, dests: new Map() },
    });
  }, [teaching.boardFen]);

  // ── Navigation ─────────────────────────────────────────────────────────────
  function gotoStart() {
    teaching.jumpTo(-1);
    setSelectedMoveForNote(null);
    playNavigationSound(soundsOn);
  }
  function gotoEnd() {
    teaching.jumpToEnd();
    setSelectedMoveForNote(null);
    playNavigationSound(soundsOn);
  }
  function gotoPrev() {
    if (teaching.viewIndex === null) {
      if (teaching.moves.length > 0) {
        const i = teaching.moves.length - 1;
        teaching.jumpTo(i);
        setSelectedMoveForNote(i);
      }
    } else if (teaching.viewIndex > 0) {
      const i = teaching.viewIndex - 1;
      teaching.jumpTo(i);
      setSelectedMoveForNote(i);
    } else {
      teaching.jumpTo(-1);
      setSelectedMoveForNote(null);
    }
    playNavigationSound(soundsOn);
  }
  function gotoNext() {
    if (teaching.viewIndex === null) return;
    if (teaching.viewIndex < teaching.moves.length - 1) {
      const i = teaching.viewIndex + 1;
      teaching.jumpTo(i);
      setSelectedMoveForNote(i);
    } else {
      teaching.jumpToEnd();
      setSelectedMoveForNote(null);
    }
    playNavigationSound(soundsOn);
  }

  function handleExportPgn() {
    if (!selectedGame) return;
    const pgn = generatePgn(teaching.moves, selectedGame.name);
    exportPgn(pgn, selectedGame.name);
  }

  function handleCopyPgn() {
    if (!selectedGame) return;
    const pgn = generatePgn(teaching.moves, selectedGame.name);
    navigator.clipboard.writeText(pgn).then(
      () => { setCopyFeedback("✓"); setTimeout(() => setCopyFeedback(null), 1500); },
      () => { setCopyFeedback("✕"); setTimeout(() => setCopyFeedback(null), 1500); },
    );
  }

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || formOpen) return;
      if (!selectedGame) return;
      switch (e.key) {
        case "ArrowLeft": e.preventDefault(); gotoPrev(); break;
        case "ArrowRight": e.preventDefault(); gotoNext(); break;
        case "ArrowDown": e.preventDefault(); gotoStart(); break;
        case "ArrowUp": e.preventDefault(); gotoEnd(); break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [teaching, selectedGame, formOpen]);

  // ── Mutations ────────────────────────────────────────────────────────────
  const deleteGame = useMutation({
    mutationFn: (id: string) => gamesApi.remove(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["games"] });
      if (id === selectedGameId) setSelectedGameId(null);
      setDeleteConfirmId(null);
    },
  });

  async function saveNote(moveIndex: number, text: string) {
    if (!selectedGameId) return;
    const updated = await gamesApi.updateMoveNote(selectedGameId, moveIndex, text);
    qc.setQueryData<Game[]>(["games"], (prev) =>
      prev?.map((g) => (g.id === updated.id ? updated : g)),
    );
    return updated;
  }

  // ── Pagination ─────────────────────────────────────────────────────────────
  const pageCount = Math.max(1, Math.ceil(games.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pagedGames = useMemo(
    () => games.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE),
    [games, safePage],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1>My Games</h1>
        <button className="btn-primary text-sm" onClick={() => { setEditingGame(null); setFormOpen(true); }}>
          + New Game
        </button>
      </div>

      {games.length === 0 ? (
        <div className="card p-8 text-center text-ink-300">
          <p className="mb-3">You haven't uploaded any games yet.</p>
          <button className="btn-primary text-sm" onClick={() => { setEditingGame(null); setFormOpen(true); }}>
            Upload your first game
          </button>
        </div>
      ) : (
        <>
          {/* Metadata header bar */}
          {selectedGame && (
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-ink-700">
                <span className="text-lg font-semibold text-ink-100">{formatDate(selectedGame.played_date)}</span>
                <div className="flex gap-2">
                  <button className="btn-ghost text-xs" onClick={() => { setEditingGame(selectedGame); setFormOpen(true); }}>
                    ✎ Edit
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-ink-700 border-b border-ink-700">
                <MetaCell label="Playing" value={selectedGame.played_color === "white" ? "White" : "Black"} />
                <MetaCell label="Opponent Level" value={selectedGame.opponent_level?.toString() ?? "—"} />
                <MetaCell label="Result" value={RESULT_LABEL[selectedGame.result]} valueClass={RESULT_STYLES[selectedGame.result]} />
                <MetaCell label="Repeat Offense?" value={selectedGame.repeat_offense ? "Yes" : "No"}
                  valueClass={selectedGame.repeat_offense ? "text-red-400" : "text-emerald-400"} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-ink-700">
                <MemoCell label="What happened:" value={selectedGame.what_happened} />
                <MemoCell label="Lesson Learned:" value={selectedGame.lesson_learned} />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr_280px] gap-6 items-start">
            {/* Board + note editor */}
            <div className="flex flex-col gap-4">
              <ChessboardWrapper
                orientation={orientation}
                viewOnly
                cgRef={cgRef}
                boardTheme={boardTheme}
                pieceSet={pieceSet}
              />
              {selectedGame && (
                <div className="flex justify-center">
                  <button
                    className="btn-ghost text-sm"
                    onClick={() => setFlipped((f) => !f)}
                    title="Flip board"
                  >
                    ⇅ Flip board
                  </button>
                </div>
              )}
              {selectedGame && selectedMoveForNote !== null && (
                <div className="card p-4">
                  <MoveNoteEditor
                    lineId={selectedGame.id}
                    moveIndex={selectedMoveForNote}
                    currentMove={noteMove}
                    saveNote={saveNote}
                    onNoteSaved={(index, text) => teaching.setMoveNote(index, text)}
                  />
                </div>
              )}
            </div>

            {/* Move list + nav */}
            <div className="card min-h-[480px] flex flex-col">
              <div className="mb-3">
                <h2>{selectedGame?.name ?? "Select a game"}</h2>
                {selectedGame && (
                  <span className="text-xs text-ink-400">
                    {teaching.moves.length} move{teaching.moves.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              {selectedGame && teaching.moves.length > 0 ? (
                <div className="flex-1 overflow-y-auto">
                  <MoveList
                    moves={teaching.moves}
                    viewIndex={teaching.viewIndex}
                    isAtEnd={teaching.isAtEnd}
                    onJump={(i) => { teaching.jumpTo(i); setSelectedMoveForNote(i); playNavigationSound(soundsOn); }}
                    onJumpToEnd={gotoEnd}
                    readOnly
                  />
                </div>
              ) : (
                <p className="text-ink-300 text-sm italic flex-1">
                  {selectedGame ? "This game has no recorded moves." : "Select a game from the list."}
                </p>
              )}

              {selectedGame && teaching.moves.length > 0 && (
                <div className="mt-3 border-t border-ink-700 pt-3 flex items-center gap-1 text-xs">
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={gotoStart} title="First move (↓)">⟪</button>
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={gotoPrev} title="Previous (←)">‹</button>
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={gotoNext} disabled={teaching.isAtEnd} title="Next (→)">›</button>
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={gotoEnd} title="Last move (↑)">⟫</button>
                  <span className="flex-1" />
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleCopyPgn} title="Copy PGN to clipboard">
                    {copyFeedback || "📋"}
                  </button>
                  <button className="btn-ghost px-2 py-1 text-ink-400 hover:text-gold-400" onClick={handleExportPgn} title="Download PGN">
                    ↓ PGN
                  </button>
                </div>
              )}
            </div>

            {/* Games list + pagination */}
            <div className="card flex flex-col gap-3">
              <h2 className="text-sm font-semibold text-ink-200">My Games</h2>
              <div className="flex-1 overflow-y-auto">
                <div className="flex flex-col gap-1.5">
                  {pagedGames.map((g) => (
                    <div key={g.id} className="relative flex items-center gap-1 group">
                      <button
                        className={`w-full text-left rounded px-2 py-1.5 text-xs font-medium transition-colors truncate
                          ${selectedGameId === g.id ? "bg-gold-500 text-ink-900" : "bg-ink-700 text-ink-200 hover:bg-ink-600"}`}
                        onClick={() => setSelectedGameId(g.id)}
                        title={g.name}
                      >
                        <span className={`mr-1.5 ${selectedGameId === g.id ? "text-ink-900" : RESULT_STYLES[g.result]}`}>●</span>
                        {formatShort(g.played_date)} · {g.name}
                      </button>
                      {deleteConfirmId === g.id ? (
                        <div className="flex gap-0.5">
                          <button className="btn-ghost py-1 px-1.5 text-xs text-red-400" disabled={deleteGame.isPending}
                            onClick={() => deleteGame.mutate(g.id)} title="Confirm delete">
                            {deleteGame.isPending ? "…" : "✓"}
                          </button>
                          <button className="btn-ghost py-1 px-1.5 text-xs" onClick={() => setDeleteConfirmId(null)}>✕</button>
                        </div>
                      ) : (
                        <button
                          className="btn-ghost py-1 px-1.5 text-xs text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => setDeleteConfirmId(g.id)} title="Delete game">🗑</button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {pageCount > 1 && (
                <div className="flex items-center justify-between text-xs text-ink-400 border-t border-ink-700 pt-2">
                  <button className="btn-ghost px-2 py-1 disabled:opacity-40" disabled={safePage === 0}
                    onClick={() => setPage(safePage - 1)}>‹ Prev</button>
                  <span>{safePage + 1} / {pageCount}</span>
                  <button className="btn-ghost px-2 py-1 disabled:opacity-40" disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(safePage + 1)}>Next ›</button>
                </div>
              )}

              <button
                className="rounded px-2 py-1.5 text-xs bg-ink-800 border border-ink-600 text-ink-300 hover:border-gold-500 hover:text-gold-400 transition-colors"
                onClick={() => { setEditingGame(null); setFormOpen(true); }}>
                + New Game
              </button>
            </div>
          </div>

          {/* Statistics & timelines across all uploaded games */}
          <GameStats games={games} />
        </>
      )}

      {formOpen && (
        <GameFormModal
          game={editingGame}
          onClose={() => setFormOpen(false)}
          onSaved={(g) => {
            qc.invalidateQueries({ queryKey: ["games"] });
            setSelectedGameId(g.id);
            setFormOpen(false);
          }}
        />
      )}
    </div>
  );
}

function MetaCell({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="px-4 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-400">{label}</div>
      <div className={`text-sm font-semibold ${valueClass ?? "text-ink-100"}`}>{value}</div>
    </div>
  );
}

function MemoCell({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="px-4 py-2">
      <div className="text-[11px] uppercase tracking-wide text-ink-400 mb-1">{label}</div>
      <div className="text-sm text-ink-200 whitespace-pre-wrap break-words min-h-[1.5rem]">
        {value || <span className="text-ink-500 italic">—</span>}
      </div>
    </div>
  );
}

// ── Create / edit form ─────────────────────────────────────────────────────

interface FormProps {
  game: Game | null;
  onClose: () => void;
  onSaved: (g: Game) => void;
}

function GameFormModal({ game, onClose, onSaved }: FormProps) {
  const isEdit = !!game;
  const [name, setName] = useState(game?.name ?? "");
  const [playedDate, setPlayedDate] = useState(game?.played_date ?? "");
  const [color, setColor] = useState<GameColor>(game?.played_color ?? "white");
  const [opponentLevel, setOpponentLevel] = useState(game?.opponent_level?.toString() ?? "");
  const [result, setResult] = useState<GameResult>(game?.result ?? "win");
  const [whatHappened, setWhatHappened] = useState(game?.what_happened ?? "");
  const [lesson, setLesson] = useState(game?.lesson_learned ?? "");
  const [repeatOffense, setRepeatOffense] = useState(game?.repeat_offense ?? false);
  const [pgnText, setPgnText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const metadata = {
        name: name.trim(),
        played_date: playedDate || null,
        played_color: color,
        opponent_level: opponentLevel ? parseInt(opponentLevel, 10) : null,
        result,
        what_happened: whatHappened.trim() || null,
        lesson_learned: lesson.trim() || null,
        repeat_offense: repeatOffense,
      };
      if (isEdit) {
        return gamesApi.update(game!.id, metadata);
      }
      const { moves, startingFen } = parsePgnToSans(pgnText);
      const body: GameCreate = { ...metadata, moves, starting_fen: startingFen };
      return gamesApi.create(body);
    },
    onSuccess: (g) => onSaved(g),
    onError: (e: any) => setError(e?.message ?? "Save failed"),
  });

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    file.text().then((txt) => {
      setPgnText(txt);
      if (!name.trim()) setName(file.name.replace(/\.pgn$/i, ""));
    });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return setError("Please give the game a name.");
    if (!isEdit && !pgnText.trim()) return setError("Please upload or paste a PGN.");
    if (!isEdit) {
      try {
        parsePgnToSans(pgnText);
      } catch (err: any) {
        return setError(err?.message ?? "Could not parse the PGN.");
      }
    }
    save.mutate();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4">{isEdit ? "Edit game" : "New game"}</h2>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 col-span-2">
              <span className="text-xs text-ink-400">Name</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="2 May afternoon game" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-400">Date</span>
              <input type="date" className="input" value={playedDate ?? ""} onChange={(e) => setPlayedDate(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-400">Playing as</span>
              <select className="input" value={color} onChange={(e) => setColor(e.target.value as GameColor)}>
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-400">Opponent level</span>
              <input type="number" className="input" value={opponentLevel} onChange={(e) => setOpponentLevel(e.target.value)} placeholder="1100" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-400">Result</span>
              <select className="input" value={result} onChange={(e) => setResult(e.target.value as GameResult)}>
                <option value="win">Win</option>
                <option value="loss">Loss</option>
                <option value="draw">Draw</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 col-span-2">
              <span className="text-xs text-ink-400">What happened</span>
              <textarea className="input h-20 resize-none" value={whatHappened} onChange={(e) => setWhatHappened(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 col-span-2">
              <span className="text-xs text-ink-400">Lesson learned</span>
              <textarea className="input h-20 resize-none" value={lesson} onChange={(e) => setLesson(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink-400">Repeat offense?</span>
              <select className="input" value={repeatOffense ? "yes" : "no"} onChange={(e) => setRepeatOffense(e.target.value === "yes")}>
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </label>
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-2 border-t border-ink-700 pt-3">
              <span className="text-xs text-ink-400">PGN</span>
              <input type="file" accept=".pgn,.txt" onChange={handleFile} className="text-xs text-ink-300" />
              {fileName && <span className="text-xs text-gold-400">Loaded: {fileName}</span>}
              <textarea
                className="input font-mono text-xs h-24 resize-none"
                value={pgnText}
                onChange={(e) => setPgnText(e.target.value)}
                placeholder="…or paste PGN here — 1. e4 e5 2. Nf3 Nc6 …"
              />
            </div>
          )}

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <div className="flex gap-2 justify-end pt-1">
            <button type="button" className="btn-ghost text-sm" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary text-sm" disabled={save.isPending}>
              {save.isPending ? "Saving…" : isEdit ? "Save changes" : "Create game"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
