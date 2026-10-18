#!/usr/bin/env python3
"""Offline check of the user docs: every relative link points at a file that exists,
every #anchor exists in its target, every image exists, and no doc mentions
removed things. Usage: scripts/check-doc-links.py   (exit 1 on any problem)."""
import re
import sys
from urllib.parse import unquote
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "chessloop" / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
DOCS = [d for d in DOCS if "history" not in d.parts]
FORBIDDEN = ["manage.sh", "caddyserver.com/get", "admin@example.com / admin", "simply ", "just "]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    h = re.sub(r"[`*]", "", heading.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path: Path) -> set:
    out, fence = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fence = not fence
        elif not fence and line.startswith("#"):
            out.add(slug(line.lstrip("#")))
    return out


problems = []
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    for word in FORBIDDEN:
        if word in body and doc.name != "CHANGELOG.md":
            problems.append(f"{doc.relative_to(ROOT)}: contains '{word.strip()}'")
    for target in LINK.findall(body):
        if re.match(r"(https?:|mailto:)", target):
            continue
        file_part, _, frag = target.partition("#")
        dest = doc if not file_part else (doc.parent / unquote(file_part)).resolve()
        if not dest.exists():
            problems.append(f"{doc.relative_to(ROOT)}: broken link {target}")
        elif frag and dest.suffix == ".md" and frag not in anchors(dest):
            problems.append(f"{doc.relative_to(ROOT)}: no heading for #{frag} in {dest.relative_to(ROOT)}")
print(f"checked {len(DOCS)} files")
for p in problems:
    print("PROBLEM:", p)
sys.exit(1 if problems else 0)
