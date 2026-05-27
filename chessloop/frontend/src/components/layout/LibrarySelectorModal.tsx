import { useNavigate } from "react-router-dom";
import type { Library } from "@/types";

interface LibrarySelectorModalProps {
  libraries: Library[];
  onClose: () => void;
  mode: "learn" | "teach";
}

export function LibrarySelectorModal({ libraries, onClose, mode }: LibrarySelectorModalProps) {
  const navigate = useNavigate();

  const handleSelectLibrary = (libraryId: string) => {
    const path = mode === "learn" ? `/libraries/${libraryId}/unrated` : `/libraries/${libraryId}/teach`;
    navigate(path);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-ink-900/80 flex items-center justify-center z-50">
      <div className="bg-ink-800 border border-ink-700 rounded-lg p-6 max-w-md w-full mx-4">
        <h2 className="text-lg font-semibold mb-4">
          {mode === "learn" ? "Select a library to learn" : "Select a library to teach"}
        </h2>

        {libraries.length === 0 ? (
          <p className="text-ink-400 text-sm">No libraries yet. Create one to get started.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {libraries.map((lib) => (
              <button
                key={lib.id}
                onClick={() => handleSelectLibrary(lib.id)}
                className="text-left px-4 py-3 rounded hover:bg-ink-700 transition-colors border border-ink-700 hover:border-ink-600"
              >
                <span className="mr-2 text-gold-400">
                  {lib.color === "white" ? "♔" : lib.color === "black" ? "♚" : "⚭"}
                </span>
                <span className="text-ink-200">{lib.name}</span>
              </button>
            ))}
          </ul>
        )}

        <button
          onClick={onClose}
          className="w-full mt-4 px-4 py-2 rounded text-sm bg-ink-700 hover:bg-ink-600 transition-colors text-ink-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
