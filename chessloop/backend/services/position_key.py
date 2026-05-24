"""Canonical FEN keying.

Standard FEN has six space-delimited fields:
    <board> <active> <castling> <en passant> <halfmove> <fullmove>

For SRS purposes we keep the first four — they determine legal moves and the
position's strategic identity. Halfmove (50-move counter) and fullmove number
are clock state that we deliberately ignore so transpositions can collide.
"""


def canonical_position_key(fen: str) -> str:
    """Strip half-move and full-move counters from a FEN.

    e.g.  "rnbqkbnr/.../RNBQKBNR w KQkq - 0 1"
       -> "rnbqkbnr/.../RNBQKBNR w KQkq -"
    """
    parts = fen.split()
    return " ".join(parts[:4])


def active_color(fen: str) -> str:
    """Return 'white' or 'black' — the side to move at the given FEN."""
    parts = fen.split()
    if len(parts) < 2:
        return "white"
    return "white" if parts[1].lower() == "w" else "black"
