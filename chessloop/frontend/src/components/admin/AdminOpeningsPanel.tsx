import { useState, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, type OpeningSearchResult } from "@/api/admin";

// ── Tooltip ───────────────────────────────────────────────────────────────────

function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);
  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-64 rounded bg-ink-700 border border-ink-600 px-3 py-2 text-xs text-ink-100 shadow-lg pointer-events-none leading-relaxed">
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-ink-700" />
        </span>
      )}
    </span>
  );
}

function InfoIcon() {
  return (
    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-ink-600 text-gold-400 text-[10px] font-bold cursor-help ml-1.5 shrink-0">
      ?
    </span>
  );
}

// ── Section: Seed starter libraries ──────────────────────────────────────────

function SeedSection() {
  const qc = useQueryClient();
  const [result, setResult] = useState<{ seeded: number; skipped: number; errors: string[] } | null>(null);

  const seedMut = useMutation({
    mutationFn: adminApi.seedOpenings,
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["public-libraries"] });
    },
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <span className="text-sm font-medium text-ink-200">Seed Starter Libraries</span>
        <Tooltip text="Creates the 16 standard chess opening libraries (Italian Game, Ruy López, Sicilian, etc.) in your account and publishes them to Public Discovery. Already-existing libraries are skipped automatically. Safe to run multiple times.">
          <InfoIcon />
        </Tooltip>
      </div>

      <button
        className="btn-primary w-fit text-sm py-1.5 px-4"
        onClick={() => { setResult(null); seedMut.mutate(); }}
        disabled={seedMut.isPending}
      >
        {seedMut.isPending ? "Seeding…" : "⟳ Seed 16 Openings"}
      </button>

      {seedMut.isError && (
        <p className="text-xs text-red-400">
          Error: {(seedMut.error as Error).message}
        </p>
      )}

      {result && (
        <div className="text-xs text-ink-300 bg-ink-800 border border-ink-700 rounded px-3 py-2 space-y-0.5">
          <p>✓ <span className="text-gold-400">{result.seeded}</span> seeded &nbsp;·&nbsp;
             <span className="text-ink-400">{result.skipped}</span> skipped</p>
          {result.errors.length > 0 && (
            <ul className="mt-1 text-red-400 list-disc list-inside">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Section: Pull variations ──────────────────────────────────────────────────

function PullVariationsSection({ libraryNames }: { libraryNames: string[] }) {
  const [selected, setSelected] = useState("");
  const [count, setCount] = useState(3);
  const [result, setResult] = useState<{ added: number; message: string } | null>(null);

  const pullMut = useMutation({
    mutationFn: () => adminApi.pullVariations(selected, count),
    onSuccess: (data) => setResult(data),
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <span className="text-sm font-medium text-ink-200">Pull Variations</span>
        <Tooltip text="Fetches additional lines from the ECO opening database for an existing library. Related openings (same family, e.g. all Italian Game variants) are added as extra lines. Choose how many variations to add.">
          <InfoIcon />
        </Tooltip>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={selected}
          onChange={(e) => { setSelected(e.target.value); setResult(null); }}
          className="input text-sm py-1 flex-1 min-w-[200px]"
        >
          <option value="">— Select an opening —</option>
          {libraryNames.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>

        <div className="flex items-center gap-1.5">
          <label className="text-xs text-ink-400 whitespace-nowrap">Add up to</label>
          <input
            type="number"
            min={1}
            max={20}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value))))}
            className="input text-sm py-1 w-16 text-center"
          />
          <label className="text-xs text-ink-400">variations</label>
        </div>

        <button
          className="btn-primary text-sm py-1.5 px-4"
          onClick={() => pullMut.mutate()}
          disabled={!selected || pullMut.isPending}
        >
          {pullMut.isPending ? "Pulling…" : "Pull Variations"}
        </button>
      </div>

      {pullMut.isError && (
        <p className="text-xs text-red-400">
          Error: {(pullMut.error as Error).message}
        </p>
      )}

      {result && (
        <p className="text-xs text-ink-300 bg-ink-800 border border-ink-700 rounded px-3 py-2">
          {result.added > 0 ? "✓ " : "ℹ "}
          {result.message}
        </p>
      )}
    </div>
  );
}

// ── Section: Search + import from Lichess ECO database ───────────────────────

function ImportOpeningSection() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [importing, setImporting] = useState<string | null>(null);
  const [importResults, setImportResults] = useState<Record<string, "created" | "exists" | "error">>({});

  function handleQueryChange(val: string) {
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQ(val), 350);
  }

  const { data: results, isFetching } = useQuery({
    queryKey: ["lichess-search", debouncedQ],
    queryFn: () => adminApi.searchOpenings(debouncedQ),
    staleTime: 60_000,
    enabled: true,
  });

  async function handleImport(entry: OpeningSearchResult) {
    setImporting(entry.name);
    try {
      const resp = await adminApi.importOpening({
        eco: entry.eco,
        name: entry.name,
        color: entry.color,
        difficulty: entry.difficulty,
        description: entry.description,
        moves: entry.moves,
        publish: true,
      });
      setImportResults((prev) => ({ ...prev, [entry.name]: resp.status }));
      qc.invalidateQueries({ queryKey: ["public-libraries"] });
    } catch {
      setImportResults((prev) => ({ ...prev, [entry.name]: "error" }));
    } finally {
      setImporting(null);
    }
  }

  const statusLabel: Record<string, { text: string; cls: string }> = {
    created: { text: "Imported ✓", cls: "text-gold-400" },
    exists:  { text: "Already exists", cls: "text-ink-400" },
    error:   { text: "Error", cls: "text-red-400" },
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1">
        <span className="text-sm font-medium text-ink-200">Search & Import Openings</span>
        <Tooltip text="Search the ECO opening database (50+ openings) by name or ECO code. Click 'Import' to add any opening to your library and publish it to Public Discovery. This is not limited to the 16 default openings.">
          <InfoIcon />
        </Tooltip>
      </div>

      <input
        type="text"
        placeholder="Search by name or ECO (e.g. 'Sicilian', 'E62', 'Gambit')…"
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        className="input text-sm"
      />

      {isFetching && (
        <p className="text-xs text-ink-400">Searching…</p>
      )}

      {results && results.length > 0 && (
        <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto pr-1">
          {results.map((entry) => {
            const st = importResults[entry.name];
            const isImporting = importing === entry.name;
            return (
              <div
                key={entry.name}
                className="flex items-start justify-between gap-3 rounded bg-ink-800 border border-ink-700 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-ink-100 truncate">{entry.name}</span>
                    <span className="text-[10px] font-mono text-gold-500 shrink-0">{entry.eco}</span>
                    <span className="text-[10px] text-ink-500 shrink-0 capitalize">{entry.color}</span>
                    <span className="text-[10px] text-ink-500 shrink-0 capitalize">{entry.difficulty}</span>
                  </div>
                  <p className="text-xs text-ink-400 mt-0.5 line-clamp-1">{entry.description}</p>
                  <p className="text-[10px] text-ink-500 mt-0.5">{entry.moves.length} moves</p>
                </div>

                <div className="shrink-0 flex items-center">
                  {st ? (
                    <span className={`text-xs ${statusLabel[st].cls}`}>{statusLabel[st].text}</span>
                  ) : (
                    <button
                      className="btn-ghost text-xs py-1 px-3 border border-ink-600 hover:border-gold-500 hover:text-gold-400"
                      onClick={() => handleImport(entry)}
                      disabled={!!importing}
                    >
                      {isImporting ? "Importing…" : "Import"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {results && results.length === 0 && debouncedQ && !isFetching && (
        <p className="text-xs text-ink-400">No openings found matching "{debouncedQ}".</p>
      )}
    </div>
  );
}

// ── Root panel ────────────────────────────────────────────────────────────────

export function AdminOpeningsPanel({ publicLibraryNames }: { publicLibraryNames: string[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-gold-600/40 rounded-lg bg-ink-800/60">
      {/* Header — always visible */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2">
          <span className="text-gold-500 text-sm">⚙</span>
          <span className="text-sm font-semibold text-gold-400">Admin — Opening Management</span>
        </div>
        <span className="text-ink-400 text-xs">{open ? "▲ Hide" : "▼ Show"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-6 border-t border-ink-700 pt-4">
          <SeedSection />
          <div className="border-t border-ink-700" />
          <PullVariationsSection libraryNames={publicLibraryNames} />
          <div className="border-t border-ink-700" />
          <ImportOpeningSection />
        </div>
      )}
    </div>
  );
}
