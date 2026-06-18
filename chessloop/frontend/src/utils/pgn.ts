import { Chess } from "chess.js";

/** Strip `{...}` comments and `(...)` variations from a PGN string. */
function stripCommentsAndVariations(pgn: string): string {
  const noComments = pgn.replace(/\{[^}]*\}/g, " ");
  let depth = 0;
  let out = "";
  for (const ch of noComments) {
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (depth === 0) out += ch;
  }
  return out;
}

export interface ParsedGame {
  moves: string[];
  startingFen?: string;
}

/**
 * Parse PGN/SAN text into an ordered SAN list, tolerant of headers, comments,
 * variations, NAGs, and a trailing illegal token. Honours a `[FEN "..."]`
 * header if present. Throws if no legal moves can be read.
 */
export function parsePgnToSans(text: string): ParsedGame {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("Empty PGN");

  // Respect an explicit starting position from a [FEN "..."] header.
  const fenMatch = trimmed.match(/\[FEN\s+"([^"]+)"\]/i);
  const startingFen = fenMatch?.[1];

  // Strict parse first — handles well-formed PGNs cleanly.
  try {
    const chess = new Chess();
    chess.loadPgn(stripCommentsAndVariations(trimmed));
    const moves = chess.history();
    if (moves.length > 0) return { moves, startingFen };
  } catch {
    /* fall through to lenient parse */
  }

  // Lenient parse: strip headers/result/move-numbers/NAGs, replay until the
  // first illegal token.
  const tokens = stripCommentsAndVariations(trimmed)
    .replace(/^\s*\[.*?\]\s*$/gm, " ")
    .replace(/\b(1-0|0-1|1\/2-1\/2|\*)\b/g, " ")
    .replace(/\$\d+/g, " ")
    .replace(/\d+\.(\.\.)?/g, " ")
    .split(/\s+/)
    .filter(Boolean);

  const chess = startingFen ? new Chess(startingFen) : new Chess();
  for (const san of tokens) {
    try {
      chess.move(san);
    } catch {
      break;
    }
  }
  const moves = chess.history();
  if (moves.length === 0) throw new Error("Could not parse any legal moves from PGN");
  return { moves, startingFen };
}
