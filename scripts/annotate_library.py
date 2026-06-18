#!/usr/bin/env python3
"""
Annotate ChessLoop opening libraries with AI-generated educational move notes.

Reads lines from the live Docker DB, calls Claude to generate notes for each
move, then writes them back. Safe to re-run: always overwrites notes.

Usage:
  python3 scripts/annotate_library.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import anthropic


def _load_env_key() -> str | None:
    """Look for ANTHROPIC_API_KEY in environment then in common .env files."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    search = [
        Path.home() / ".env",
        Path(__file__).parent.parent / ".env",
        Path("/home/nick/dev/lucent/ui/.env"),
    ]
    for path in search:
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return None

CONTAINER = "chessloop-backend"
DB_PATH = "/data/chessloop.db"
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert chess coach specializing in opening theory. Your job is to \
annotate chess opening moves with educational notes that guide beginner-to-club \
players through the opening philosophy, key objectives, and tactical ideas.

For each move write 1–4 sentences that:
- Explain WHY this move is played: the purpose, threat it addresses, or idea it sets up
- For the side being trained: highlight the strategic or tactical objective
- For opponent moves: explain what the opponent is trying to achieve so the learner \
understands the correct response
- Tie individual moves back to the overall opening plan where relevant
- Use plain, accessible language — no jargon without a brief explanation

Return ONLY a JSON array of strings, one note per move in input order. \
No move numbers, no labels, no extra text — just the JSON array.\
"""


# ── Docker DB helpers ──────────────────────────────────────────────────────────

def _docker_python(code: str) -> str:
    """Run a Python snippet inside the backend container and return stdout."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python3", "-c", code],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker exec failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def db_query(sql: str, params: list = None) -> list:
    params = params or []
    code = (
        f"import sqlite3,json\n"
        f"c=sqlite3.connect({json.dumps(DB_PATH)}).cursor()\n"
        f"c.execute({json.dumps(sql)},{json.dumps(params)})\n"
        f"print(json.dumps(c.fetchall()))"
    )
    return json.loads(_docker_python(code))


def db_execute(sql: str, params: list) -> None:
    code = (
        f"import sqlite3,json\n"
        f"conn=sqlite3.connect({json.dumps(DB_PATH)})\n"
        f"cursor=conn.cursor()\n"
        f"cursor.execute({json.dumps(sql)},{json.dumps(params)})\n"
        f"conn.commit()"
    )
    _docker_python(code)


# ── Library / line fetching ────────────────────────────────────────────────────

def list_libraries() -> list[dict]:
    rows = db_query(
        "SELECT l.id, l.name, l.color, u.username "
        "FROM library l JOIN user u ON l.owner_user_id = u.id "
        "ORDER BY u.username, l.name"
    )
    return [{"id": r[0], "name": r[1], "color": r[2], "owner": r[3]} for r in rows]


def find_library(name_or_id: str) -> dict:
    libs = list_libraries()
    # Exact ID match first
    for lib in libs:
        if lib["id"] == name_or_id:
            return lib
    # Case-insensitive name match
    needle = name_or_id.lower()
    matches = [lib for lib in libs if needle in lib["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous: {len(matches)} libraries match '{name_or_id}':")
        for lib in matches:
            print(f"  [{lib['id']}]  {lib['owner']} / {lib['name']}  ({lib['color']})")
        sys.exit(1)
    print(f"No library found matching '{name_or_id}'.")
    print("Run with --list to see all libraries.")
    sys.exit(1)


def get_lines(library_id: str) -> list[dict]:
    rows = db_query(
        "SELECT id, name, moves, order_index FROM line "
        "WHERE library_id=? ORDER BY order_index",
        [library_id],
    )
    result = []
    for lid, name, moves_json, order_idx in rows:
        moves = json.loads(moves_json or "[]")
        result.append({"id": lid, "name": name, "moves": moves, "order_index": order_idx})
    return result


# ── Claude annotation ──────────────────────────────────────────────────────────

def build_moves_block(moves: list[dict], color: str) -> str:
    lines = []
    for i, m in enumerate(moves):
        side = "White" if i % 2 == 0 else "Black"
        lines.append(f"{i}. {m['san']} ({side})")
    return "\n".join(lines)


def _parse_notes(raw_text: str) -> list[str]:
    """Strip markdown fences and parse a JSON array of strings."""
    raw = raw_text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    return json.loads(raw)


def annotate_line(
    client: anthropic.Anthropic,
    library_name: str,
    color: str,
    line_name: str,
    moves: list[dict],
    retries: int = 2,
) -> list[str]:
    if not moves:
        return []

    trained_side = color.capitalize() if color in ("white", "black") else color
    moves_block = build_moves_block(moves, color)
    expected = len(moves)

    user_content = (
        f"Opening: {library_name} ({trained_side})\n"
        f"Line: {line_name}\n\n"
        f"Moves:\n{moves_block}\n\n"
        f"Generate educational notes for all {expected} moves. "
        f"Return a JSON array with exactly {expected} strings."
    )

    best: list[str] = []
    last_err: Exception | None = None

    for attempt in range(1, retries + 2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                          "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
            )
            parsed = _parse_notes(response.content[0].text)
            if len(parsed) == expected:
                return parsed
            # Wrong count — save what we got and retry
            best = parsed
            last_err = ValueError(f"got {len(parsed)}, expected {expected}")
            if attempt <= retries:
                print(f"\n      ⚠ attempt {attempt}: {last_err} — retrying…",
                      end="", flush=True)
        except (json.JSONDecodeError, Exception) as e:
            last_err = e
            if attempt <= retries:
                print(f"\n      ⚠ attempt {attempt}: {e} — retrying…",
                      end="", flush=True)

    # All attempts exhausted — pad / trim best partial result and warn
    partial = (best + [""] * expected)[:expected]
    empty_count = partial.count("")
    print(f"\n      ⚠ using partial result after {retries + 1} attempts "
          f"({last_err}); {empty_count} note(s) left blank.")
    return partial


# ── DB write-back ──────────────────────────────────────────────────────────────

def write_notes(line_id: str, moves: list[dict], notes: list[str]) -> None:
    annotated = []
    for move, note in zip(moves, notes):
        m = dict(move)
        m["note"] = note
        annotated.append(m)

    now = datetime.utcnow().isoformat()
    db_execute(
        "UPDATE line SET moves=?, updated_at=? WHERE id=?",
        [json.dumps(annotated), now, line_id],
    )


# ── Interactive selection ──────────────────────────────────────────────────────

_QSTYLE = None


def _qs():
    import questionary
    global _QSTYLE
    if _QSTYLE is None:
        _QSTYLE = questionary.Style([
            ("question",    "bold"),
            ("pointer",     "fg:#FFD700 bold"),
            ("highlighted", "fg:#FFD700"),
            ("selected",    "fg:#00AA00 bold"),
            ("separator",   "fg:#555555"),
        ])
    return questionary, _QSTYLE


def pick_libraries_interactive(libs: list[dict]) -> list[dict]:
    questionary, style = _qs()
    color_icon = {"white": "♔", "black": "♚", "both": "♔♚"}

    choices = [
        questionary.Choice(
            title=f"{color_icon.get(lib['color'], '?')}  {lib['name']}  [{lib['owner']}]",
            value=lib,
        )
        for lib in libs
    ]

    selected = questionary.checkbox(
        "Select libraries to annotate  (↑/↓ move · space select · enter confirm)",
        choices=choices,
        style=style,
    ).ask()

    if not selected:
        print("Nothing selected — exiting.")
        sys.exit(0)

    return selected


def pick_library_single(libs: list[dict]) -> dict:
    questionary, style = _qs()
    color_icon = {"white": "♔", "black": "♚", "both": "♔♚"}

    choices = [
        questionary.Choice(
            title=f"{color_icon.get(lib['color'], '?')}  {lib['name']}  [{lib['owner']}]",
            value=lib,
        )
        for lib in libs
    ]

    selected = questionary.select(
        "Select a library  (↑/↓ move · enter confirm)",
        choices=choices,
        style=style,
    ).ask()

    if not selected:
        print("Nothing selected — exiting.")
        sys.exit(0)

    return selected


def pick_lines_interactive(lib: dict) -> list[dict]:
    questionary, style = _qs()
    lines = get_lines(lib["id"])

    if not lines:
        print(f"No lines in '{lib['name']}' — exiting.")
        sys.exit(0)

    choices = [
        questionary.Choice(
            title=f"[{line['order_index'] + 1}]  {line['name'] or 'Line ' + str(line['order_index'] + 1)}"
                  f"  ({len(line['moves'])} moves)",
            value=line,
        )
        for line in lines
    ]

    selected = questionary.checkbox(
        f"Select lines from '{lib['name']}'  (↑/↓ move · space select · enter confirm)",
        choices=choices,
        style=style,
    ).ask()

    if not selected:
        print("Nothing selected — exiting.")
        sys.exit(0)

    return selected


# ── Run helpers ────────────────────────────────────────────────────────────────

def _annotate_line_entry(client: anthropic.Anthropic, lib: dict, line: dict) -> int:
    """Annotate a single line, write to DB, return move count (0 on skip/error)."""
    move_count = len(line["moves"])
    if move_count == 0:
        print(f"    [{line['order_index'] + 1}] {line['name']} — empty, skipped")
        return 0

    label = line["name"] or f"Line {line['order_index'] + 1}"
    print(f"    [{line['order_index'] + 1}] {label} ({move_count} moves) … ", end="", flush=True)

    try:
        notes = annotate_line(
            client,
            library_name=lib["name"],
            color=lib["color"],
            line_name=label,
            moves=line["moves"],
        )
        write_notes(line["id"], line["moves"], notes)
        print("done")
        return move_count
    except Exception as e:
        print(f"\n      ✕ skipped — {e}")
        return 0


def run_library(client: anthropic.Anthropic, lib: dict) -> None:
    lines = get_lines(lib["id"])
    if not lines:
        print(f"  No lines in '{lib['name']}' — skipping.")
        return

    total_moves = sum(_annotate_line_entry(client, lib, line) for line in lines)
    print(f"  → {total_moves} moves annotated across {len(lines)} lines.")


def run_selected_lines(client: anthropic.Anthropic, lib: dict, lines: list[dict]) -> None:
    total_moves = sum(_annotate_line_entry(client, lib, line) for line in lines)
    print(f"  → {total_moves} moves annotated across {len(lines)} line(s).")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    api_key = _load_env_key()
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY not set.\n"
            "Add it to /home/nick/dev/lucent/ui/.env or export it:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    questionary, style = _qs()

    mode = questionary.select(
        "What would you like to annotate?",
        choices=[
            questionary.Choice("Annotate full libraries",          value="libraries"),
            questionary.Choice("Select specific lines to annotate", value="lines"),
        ],
        style=style,
    ).ask()

    if not mode:
        print("Cancelled.")
        sys.exit(0)

    all_libs = list_libraries()
    print()

    if mode == "libraries":
        selected_libs = pick_libraries_interactive(all_libs)
        print()
        for lib in selected_libs:
            print(f"── {lib['name']}  ({lib['color']}, {lib['owner']}) ──")
            run_library(client, lib)
            print()
    else:
        lib = pick_library_single(all_libs)
        selected_lines = pick_lines_interactive(lib)
        print()
        print(f"── {lib['name']}  ({lib['color']}, {lib['owner']}) ──")
        run_selected_lines(client, lib, selected_lines)
        print()

    print("All done.")


if __name__ == "__main__":
    main()
