import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { librariesApi, type EvaluateConflictsResult } from "@/api/libraries";

interface ConflictEvaluatorProps {
  libraryId: string;
}

export function ConflictEvaluator({ libraryId }: ConflictEvaluatorProps) {
  const [showResults, setShowResults] = useState(false);
  const [results, setResults] = useState<EvaluateConflictsResult | null>(null);

  const { mutate: evaluate, isPending } = useMutation({
    mutationFn: async () => {
      return await librariesApi.evaluateConflicts(libraryId);
    },
    onSuccess: (data) => {
      setResults(data);
      setShowResults(true);
    },
  });

  return (
    <div className="w-full">
      <button
        onClick={() => evaluate()}
        disabled={isPending}
        className="px-3 py-1 text-sm bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white rounded transition-colors"
      >
        {isPending ? "Evaluating..." : "Evaluate for Conflicts"}
      </button>

      {showResults && results && (
        <div className="mt-6 bg-slate-800 rounded border border-slate-700 p-4">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-gold-400">
              Conflict Analysis
            </h3>
            <button
              onClick={() => setShowResults(false)}
              className="text-slate-400 hover:text-white text-xl"
            >
              ✕
            </button>
          </div>

          <div className="mb-4 text-slate-300 text-sm">
            <p>
              Positions evaluated: <span className="font-semibold">{results.total_positions}</span>
            </p>
            <p>
              Conflicts found:{" "}
              <span
                className={`font-semibold ${
                  results.conflicts_found > 0 ? "text-yellow-400" : "text-green-400"
                }`}
              >
                {results.conflicts_found}
              </span>
            </p>
          </div>

          {results.conflicts_found > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left px-3 py-2 text-slate-300 font-semibold">
                      Line A
                    </th>
                    <th className="text-left px-3 py-2 text-slate-300 font-semibold">
                      Line B
                    </th>
                    <th className="text-left px-3 py-2 text-slate-300 font-semibold">
                      Position
                    </th>
                    <th className="text-left px-3 py-2 text-slate-300 font-semibold">
                      Move A
                    </th>
                    <th className="text-left px-3 py-2 text-slate-300 font-semibold">
                      Move B
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {results.conflicts.map((conflict, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-slate-700 hover:bg-slate-700 transition-colors"
                    >
                      <td className="px-3 py-2 text-slate-100">{conflict.line_a_name}</td>
                      <td className="px-3 py-2 text-slate-100">{conflict.line_b_name}</td>
                      <td className="px-3 py-2 text-slate-300 text-xs">
                        After move {conflict.move_number}
                      </td>
                      <td className="px-3 py-2 text-amber-400 font-semibold">
                        {conflict.next_move_a}
                      </td>
                      <td className="px-3 py-2 text-amber-400 font-semibold">
                        {conflict.next_move_b}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-center text-slate-400 py-4">
              No conflicts found. All opening lines have unique move sequences.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
