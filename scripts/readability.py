#!/usr/bin/env python3
"""Flesch-Kincaid grade level of the user docs (prose only: code blocks, tables, links
and inline code are removed). Aim: about grade 8. Usage: scripts/readability.py [file ...]"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(n, 1)


def prose(text: str) -> str:
    text = re.sub(r"^\s*```.*?^\s*```", "", text, flags=re.S | re.M)
    text = re.sub(r"`[^`]*`", "x", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    lines = [re.sub(r"^\s*([#>*-]|\d+\.)\s*", "", l) for l in text.splitlines() if not l.strip().startswith("|")]
    return "\n".join(lines)


def grade(text: str):
    sentences = [s for s in re.split(r"[.!?:]+\s+|\n\s*\n|\n", prose(text)) if re.search(r"[A-Za-z]{2}", s)]
    words = [w for s in sentences for w in re.findall(r"[A-Za-z']+", s)]
    if not sentences or not words:
        return 0.0, 0
    syl = sum(syllables(w) for w in words)
    return 0.39 * len(words) / len(sentences) + 11.8 * syl / len(words) - 15.59, len(words)


files = [Path(a) for a in sys.argv[1:]] or [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
for f in files:
    if "history" in f.parts:
        continue
    g, n = grade(f.read_text(encoding="utf-8"))
    print(f"{g:5.1f}  {n:5d} words  {f.relative_to(ROOT) if f.is_absolute() else f}")
