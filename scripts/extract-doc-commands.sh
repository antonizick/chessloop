#!/usr/bin/env bash
# Print the fenced ```bash and ```powershell blocks of the user docs, one file per
# block, into a directory, so each can be run on the platform it is for (Phase 10).
# Blocks with placeholders (UPPERCASE words like YOUR-…, VERSION-NAME, FILE) are
# listed but marked "placeholder": they need a human to fill in a value.
# Usage: scripts/extract-doc-commands.sh <out-dir> [doc ...]   (default: README and docs/**/*.md)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="${1:?output directory}"; shift || true
mkdir -p "$out"
files=("$@")
[ "${#files[@]}" -gt 0 ] || mapfile -t files < <(ls README.md; find docs -name '*.md' -not -path 'docs/history/*' | sort)
python3 - "$out" "${files[@]}" <<'PY'
import re, sys
from pathlib import Path
out = Path(sys.argv[1]); n = 0
for f in sys.argv[2:]:
    text = Path(f).read_text(encoding="utf-8")
    for m in re.finditer(r"^([ ]*)```(bash|powershell)\n(.*?)^[ ]*```", text, re.S | re.M):
        n += 1
        indent = len(m.group(1)); body = "".join(l[indent:] for l in m.group(3).splitlines(True))
        ph = bool(re.search(r"\b(YOUR|VERSION-NAME|THE-COMPUTERS|FILE)\b|you@example\.com|/path/to|<[a-z-]+>", body))
        name = f"{n:03d}-{Path(f).stem}-{m.group(2)}{'-placeholder' if ph else ''}.txt"
        (out / name).write_text(body, encoding="utf-8")
        print(f"{name}\t{f}:{text[:m.start()].count(chr(10)) + 2}")
PY
