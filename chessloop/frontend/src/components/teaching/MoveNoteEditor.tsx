import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { linesApi } from "@/api/lines";
import type { Line, LineMove } from "@/types";

interface Props {
  lineId: string;
  moveIndex: number | null;
  currentMove: LineMove | null;
  libraryId?: string;
  onSaved?: (updatedLine: Line) => void;
  onNoteSaved?: (moveIndex: number, noteText: string) => void;
  readOnly?: boolean;
}

export function MoveNoteEditor({
  lineId,
  moveIndex,
  currentMove,
  libraryId,
  onSaved,
  onNoteSaved,
  readOnly = false,
}: Props) {
  const qc = useQueryClient();
  const [noteText, setNoteText] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (currentMove) {
      setNoteText(currentMove.note || "");
    }
  }, [currentMove?.uci]);

  // Auto-expand textarea as user types
  useEffect(() => {
    if (textareaRef.current && isEditing) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 400)}px`;
    }
  }, [noteText, isEditing]);

  const updateNote = useMutation({
    mutationFn: async (text: string) => {
      if (moveIndex === null) return;
      return linesApi.updateMoveNote(lineId, moveIndex, text);
    },
    onSuccess: (data, savedText) => {
      if (data && moveIndex !== null) {
        qc.setQueryData(["line", lineId], data);
        if (libraryId) {
          qc.invalidateQueries({ queryKey: ["lines", libraryId] });
        }
        onSaved?.(data);
        onNoteSaved?.(moveIndex, savedText);
      }
    },
  });

  const handleSave = useCallback(async () => {
    await updateNote.mutateAsync(noteText);
    setIsEditing(false);
  }, [noteText, updateNote]);

  const handleClear = useCallback(async () => {
    if (confirm("Clear this note?")) {
      await updateNote.mutateAsync("");
      setNoteText("");
    }
  }, [updateNote]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && e.ctrlKey) {
      handleSave();
    }
    if (e.key === "Escape") {
      setIsEditing(false);
      setNoteText(currentMove?.note || "");
    }
  };

  if (!currentMove || moveIndex === null) {
    return (
      <div className="p-4 rounded border border-ink-600 bg-ink-800 text-ink-400 text-sm italic">
        Select a move to add a note
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-semibold text-ink-300">
          Move note: {currentMove.san}
        </label>
        {!isEditing && noteText && (
          <span className="text-xs text-ink-400">
            {noteText.length} chars
          </span>
        )}
      </div>

      {isEditing ? (
        <div className="flex flex-col gap-2">
          <textarea
            ref={textareaRef}
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add notes about this move... (Ctrl+Enter to save, Esc to cancel)"
            className="p-3 rounded bg-ink-700 border border-ink-600 text-ink-100
                       placeholder-ink-500 text-sm focus:outline-none focus:border-gold-500
                       focus:ring-1 focus:ring-gold-400 resize-none overflow-hidden
                       min-h-[100px]"
            autoFocus
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setIsEditing(false);
                setNoteText(currentMove?.note || "");
              }}
              className="px-3 py-1 rounded text-sm bg-ink-700 hover:bg-ink-600
                         text-ink-200 transition-colors"
              disabled={updateNote.isPending}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={updateNote.isPending}
              className="px-3 py-1 rounded text-sm bg-gold-500 hover:bg-gold-400
                         text-ink-900 font-semibold transition-colors disabled:opacity-50"
            >
              {updateNote.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {noteText ? (
            <div className="p-3 rounded bg-ink-700 border border-ink-600 text-ink-100 text-sm whitespace-pre-wrap break-words">
              {noteText}
            </div>
          ) : (
            <div className="p-3 rounded bg-ink-800 border border-dashed border-ink-600 text-ink-500 text-sm italic">
              No note yet
            </div>
          )}
          {!readOnly && (
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setIsEditing(true)}
                className="px-3 py-1.5 rounded text-sm bg-ink-700 hover:bg-ink-600
                           text-gold-300 hover:text-gold-200 transition-colors"
              >
                {noteText ? "Edit" : "Add note"}
              </button>
              {noteText && (
                <button
                  onClick={handleClear}
                  disabled={updateNote.isPending}
                  className="px-2 py-1.5 rounded text-xs bg-ink-700 hover:bg-red-600/30
                             text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                  title="Clear note"
                >
                  ✕ Clear
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
