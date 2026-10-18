#!/usr/bin/env python3
"""
build-starter-lines.py: DEV-ONLY. Builds chessloop/backend/services/starter_data.json,
the bundled lines of the 16 starter libraries. It is NOT run at install or at run time:
the product ships the JSON and needs no network and no Lichess token.

How it works
  1. Each opening below has hand-chosen branch points (named, from standard theory).
  2. Each branch is extended with the most popular continuation from the Lichess
     Opening Explorer (lichess database, rated 1800+, blitz/rapid/classical) until the
     line is at least MIN_PLIES long (never more than MAX_PLIES).
  3. Every line is replayed with python-chess; the file is only written if all are legal,
     unique within the opening and start with the opening's base moves.

Usage (token only through the environment; never put it in a file in the repo):
  LICHESS_API_TOKEN=$(cat ~/.config/chessloop-build-token) \
    uv run --with chess==1.10.0 --with httpx python scripts/build-starter-lines.py
  Add --offline to skip Lichess and keep each branch exactly as written below.

Data source: Lichess Opening Explorer, https://lichess.org/api (the Lichess game database is
CC0, https://database.lichess.org). Only move popularity is used; no text is copied.
"""
import json
import os
import sys
import time
from pathlib import Path

import chess

MIN_PLIES, MAX_PLIES = 14, 24
MIN_SHARE, MIN_GAMES = 0.12, 300
OUT = Path(__file__).resolve().parent.parent / "chessloop/backend/services/starter_data.json"
CACHE = Path(os.environ.get("EXPLORER_CACHE", "/tmp/chessloop-explorer-cache.json"))

# name -> (base moves every line must start with, [(line name, prefix)])
# The FIRST branch of each opening is the line older versions seeded (the "legacy" line).
# Names must match services/starter_libraries.py.
OPENINGS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "Italian Game — Main Line": ("e4 e5 Nf3 Nc6 Bc4", [
        ("Main line: 3...Bc5 4.c3 Nf6 5.d4", "e4 e5 Nf3 Nc6 Bc4"),
        ("Two Knights: 4.Ng5 d5 5.exd5 Na5", "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Na5"),
        ("Two Knights: Fried Liver Attack", "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7"),
        ("Two Knights: 4.d4 exd4 5.e5", "e4 e5 Nf3 Nc6 Bc4 Nf6 d4 exd4 e5 d5 Bb5 Ne4 Nxd4 Bd7"),
        ("Giuoco Pianissimo", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6"),
        ("Italian: 4.O-O (Giuoco Piano, slow)", "e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3"),
        ("Evans Gambit", "e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4"),
        ("Hungarian Defence", "e4 e5 Nf3 Nc6 Bc4 Be7 d4 exd4"),
    ]),
    "Italian Game — Giuoco Piano": ("e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6", [
        ("Main line: 5.d4 Bb4+ 7.Nc3", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+ Nc3"),
        ("Moeller Attack", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+ Nc3 Nxe4 O-O Bxc3 d5"),
        ("6.Bd2 Bxd2+ exchange", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+ Bd2 Bxd2+ Nbxd2 d5"),
        ("Centre attack 6.e5", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 e5 d5 Bb5 Ne4 cxd4 Bb6"),
        ("Giuoco Pianissimo 5.d3 d6", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O"),
        ("5.d3 a6", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 a6"),
        ("5.d3 d6 6.Nbd2", "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 Nbd2"),
    ]),
    "Ruy López — Closed": ("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O", [
        ("Closed main line: 9.h3", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3"),
        ("Chigorin: 9...Na5", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7"),
        ("Chigorin: 11...Qd7", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qd7"),
        ("Breyer: 9...Nb8", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Nb8 d4 Nbd7"),
        ("Zaitsev: 9...Bb7", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Bb7 d4 Re8 Nbd2 Bf8"),
        ("Smyslov: 9...h6", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 h6 d4 Re8 Nbd2 Bf8"),
        ("Karpov: 9...Nd7", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Nd7 d4 Bf6"),
        ("9.d4 Bg4 (pin)", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O d4 Bg4"),
        ("9.d3 slow plan", "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O d3 Na5 Bc2 c5"),
    ]),
    "London System": ("d4 d5 Nf3 Nf6 Bf4", [
        ("Main line: ...e6 and ...Bd6", "d4 d5 Nf3 Nf6 Bf4 e6 e3 Bd6 Bg3 O-O Nbd2"),
        ("vs ...c5 with ...Nc6", "d4 d5 Nf3 Nf6 Bf4 e6 e3 c5 c3 Nc6 Nbd2"),
        ("vs ...c5 and ...Qb6", "d4 d5 Nf3 Nf6 Bf4 c5 e3 Nc6 c3 Qb6 Qb3 c4 Qc2 Bf5"),
        ("vs ...Bf5 (mirror)", "d4 d5 Nf3 Nf6 Bf4 Bf5 e3 e6 Nbd2 Nbd7"),
        ("vs ...g6 (Pirc style)", "d4 d5 Nf3 Nf6 Bf4 g6 e3 Bg7 h3 O-O Nbd2"),
        ("vs ...Bd6 with Bd3", "d4 d5 Nf3 Nf6 Bf4 e6 e3 Bd6 Bg3 O-O Bd3 b6"),
        ("vs ...c5 and ...cxd4", "d4 d5 Nf3 Nf6 Bf4 e6 e3 c5 Nbd2 cxd4 exd4 Bd6"),
    ]),
    "Queen's Gambit Declined": ("d4 d5 c4 e6", [
        ("Orthodox main line: Bh4", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4"),
        ("Tartakower: ...b6", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4 b6 Bd3 Bb7"),
        ("Lasker: ...Ne4", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4 Ne4 Bxe7 Qxe7"),
        ("Manhattan: ...dxc4", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4 dxc4 Bxc4 Nbd7"),
        ("Exchange Variation", "d4 d5 c4 e6 Nc3 Nf6 cxd5 exd5 Bg5 Be7 e3 c6 Bd3"),
        ("Exchange: Nf3, Bg5 and Qc2", "d4 d5 c4 e6 cxd5 exd5 Nc3 Nf6 Nf3 Be7 Bg5 O-O e3 Nbd7 Bd3 Re8 Qc2 c6"),
        ("Ragozin: ...Bb4", "d4 d5 c4 e6 Nc3 Nf6 Nf3 Bb4 Bg5 h6 Bh4"),
        ("Cambridge Springs", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 e3 c6 Nf3 Qa5"),
        ("Orthodox: Rc1 and ...c6", "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7 Rc1 c6 Bd3 dxc4 Bxc4 Nd5"),
    ]),
    "King's Indian Attack": ("Nf3 d5 g3", [
        ("Main line vs ...c5 and ...e5", "Nf3 d5 g3 Nf6 Bg2 c5 O-O Nc6 d3 e5 Nbd2"),
        ("vs ...e6 (French set-up)", "Nf3 d5 g3 Nf6 Bg2 e6 O-O Be7 d3 O-O Nbd2 c5 e4 Nc6"),
        ("vs ...c5 and ...e6", "Nf3 d5 g3 Nf6 Bg2 c5 O-O Nc6 d3 e6 Nbd2 Be7 e4"),
        ("vs ...c5 and ...Nc6 early", "Nf3 d5 g3 c5 Bg2 Nc6 O-O e5 d3 Nf6 Nbd2 Be7"),
        ("vs ...g6", "Nf3 d5 g3 g6 Bg2 Bg7 O-O Nf6 d3 O-O Nbd2 Nc6 e4"),
        ("vs ...Bg4", "Nf3 d5 g3 Bg4 Bg2 Nd7 O-O e6 d3 Ngf6 Nbd2"),
        ("vs ...c6 and ...Bg4", "Nf3 d5 g3 c6 Bg2 Bg4 O-O Nd7 d3 e6 Nbd2 Ngf6"),
        ("vs ...e6 and ...c5", "Nf3 d5 g3 Nf6 Bg2 e6 O-O c5 d3 Nc6 Nbd2 Be7 e4 O-O"),
    ]),
    "Sicilian Defence — Najdorf": ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6", [
        ("English Attack: 6.Be3 e5", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e5"),
        ("English Attack: 6.Be3 e6", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e6 f3 b5 g4 h6 Qd2 Nbd7"),
        ("6.Bg5 e6 7.f4 Be7", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bg5 e6 f4 Be7 Qf3 Qc7"),
        ("Poisoned Pawn: 7...Qb6", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bg5 e6 f4 Qb6 Qd2 Qxb2 Rb1 Qa3"),
        ("6.Be2 e5 (Scheveningen-style)", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be2 e5 Nb3 Be7 O-O O-O"),
        ("6.Be2 e6", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be2 e6 O-O Be7 f4 O-O Be3 Qc7"),
        ("6.Bc4 e6 7.Bb3 b5", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bc4 e6 Bb3 b5 O-O Bb7"),
        ("6.f3 e5 7.Nb3", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 f3 e5 Nb3 Be6 Be3 Nbd7"),
        ("6.Bg5 Nbd7 7.Bc4", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Bg5 Nbd7 Bc4 Qa5 Qd2 h6"),
    ]),
    "Sicilian Defence — Dragon": ("e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6", [
        ("Yugoslav: 9.Qd2 Nc6", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6"),
        ("Yugoslav: 9.Bc4 Bd7", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6 Bc4 Bd7 O-O-O Rc8 Bb3 Ne5"),
        ("Yugoslav: 9.O-O-O d5", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6 O-O-O d5 Kb1 Nxd4"),
        ("Yugoslav: Soltis h4 attack", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 Nc6 Qd2 O-O Bc4 Bd7 O-O-O Rc8 Bb3 Ne5 h4 h5"),
        ("Classical: 7.Be2", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be2 Bg7 O-O O-O Nb3 Be6 f4 Nc6"),
        ("Classical: 7.Bc4 ", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Bc4 Bg7 Be3 O-O Bb3 Nc6 f3"),
        ("Levenfish-style: 7.f4", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 f4 Bg7 Nf3 O-O Bd3 Nc6"),
    ]),
    "French Defence — Classical": ("e4 e6 d4 d5 Nc3 Nf6", [
        ("Classical: 4.Bg5 Be7 5.e5", "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 Bxe7 Qxe7 f4"),
        ("Steinitz: 4.e5 Nfd7", "e4 e6 d4 d5 Nc3 Nf6 e5 Nfd7 f4 c5 Nf3 Nc6 Be3 cxd4 Nxd4 Bc5"),
        ("Burn: 4.Bg5 dxe4", "e4 e6 d4 d5 Nc3 Nf6 Bg5 dxe4 Nxe4 Be7 Bxf6 Bxf6 Nf3 O-O"),
        ("MacCutcheon: 4...Bb4", "e4 e6 d4 d5 Nc3 Nf6 Bg5 Bb4 e5 h6 Bd2 Bxc3 bxc3 Ne4 Qg4 Kf8"),
        ("Classical: 6.h4 attack", "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 h4"),
        ("Classical: 7.Qd2 O-O 8.f4", "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 Bxe7 Qxe7 Qd2 O-O f4 c5"),
        ("Steinitz: 5...c5 6.Nf3 Nc6", "e4 e6 d4 d5 Nc3 Nf6 e5 Nfd7 Nce2 c5 c3 Nc6 f4 Qb6"),
    ]),
    "Caro-Kann — Classical": ("e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6", [
        ("Main line: h4 and h5", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3"),
        ("7.h4 h6 8.Nf3 Nd7 9.Bd3", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6"),
        ("7.h4 h6 8.h5", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6"),
        ("7.Nf3 Nd7 8.Bd3", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 Nf3 Nd7 Bd3 Bxd3 Qxd3 e6 Bf4 Ngf6"),
        ("7.Bc4 e6", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 Bc4 e6 Nf3 Nf6 Qe2 Nbd7"),
        ("7.f4 h6", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 f4 h6 Nf3 Nd7 Bd3 Bxd3 Qxd3 e6"),
        ("9.h5 Bh7 10.Bd3 Bxd3 11.Qxd3 e6 12.Bf4 Qa5+", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bf4 Qa5+"),
    ]),
    "King's Indian Defence": ("d4 Nf6 c4 g6 Nc3 Bg7", [
        ("Fianchetto: 4.Nf3 and g3", "d4 Nf6 c4 g6 Nc3 Bg7 Nf3 O-O g3 d6 Bg2 Nc6"),
        ("Classical: ...e5 and d5", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7"),
        ("Mar del Plata: Ne1 and ...f5", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7 Ne1 Nd7 Be3 f5 f3 f4"),
        ("Sämisch: 5.f3", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 f3 O-O Be3 e5 Nge2 c6"),
        ("Four Pawns Attack", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 f4 O-O Nf3 c5 d5 e6"),
        ("Averbakh: 5.Be2 and Bg5", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Be2 O-O Bg5 c5 d5 e6"),
        ("Petrosian: 7.d5 a5", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 d5 a5 Bg5 h6"),
        ("Exchange: 7.dxe5", "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 dxe5 dxe5 Qxd8 Rxd8 Bg5"),
    ]),
    "Grünfeld Defence": ("d4 Nf6 c4 g6 Nc3 d5", [
        ("Exchange main line: ...c5", "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Nf3 c5"),
        ("Exchange: 7.Bc4 and Ne2", "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Bc4 c5 Ne2 Nc6 Be3 O-O O-O"),
        ("Exchange: Rb1 line", "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Nf3 c5 Rb1 O-O Be2 cxd4 cxd4 Qa5+"),
        ("Exchange: Be3 and Qa5", "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Nf3 c5 Be3 Qa5 Qd2 Bg4"),
        ("Russian System: Qb3", "d4 Nf6 c4 g6 Nc3 d5 Nf3 Bg7 Qb3 dxc4 Qxc4 O-O e4 Bg4 Be3 Nfd7"),
        ("Bf4 System", "d4 Nf6 c4 g6 Nc3 d5 Bf4 Bg7 e3 O-O Rc1 c5 dxc5 Be6"),
        ("Bg5 and ...Ne4", "d4 Nf6 c4 g6 Nc3 d5 Bg5 Ne4 Bh4 Nxc3 bxc3 dxc4"),
        ("3.f3 and Qb3 systems", "d4 Nf6 c4 g6 Nc3 d5 e3 Bg7 Qb3 c6 Nf3 O-O Bd2 e6"),
    ]),
    "Pirc Defence": ("e4 d6 d4 Nf6 Nc3 g6", [
        ("Classical: Nf3 and Be2", "e4 d6 d4 Nf6 Nc3 g6 Nf3 Bg7 Be2 O-O O-O"),
        ("Classical: ...c6 and a4", "e4 d6 d4 Nf6 Nc3 g6 Nf3 Bg7 Be2 O-O O-O c6 a4 Nbd7"),
        ("Classical: ...Bg4", "e4 d6 d4 Nf6 Nc3 g6 Nf3 Bg7 Be2 O-O O-O Bg4 Be3 Nc6 Qd3 e5"),
        ("Austrian Attack: 4.f4", "e4 d6 d4 Nf6 Nc3 g6 f4 Bg7 Nf3 O-O Bd3 Na6 O-O c5"),
        ("150 Attack: Be3 and Qd2", "e4 d6 d4 Nf6 Nc3 g6 Be3 c6 Qd2 b5 f3 Nbd7"),
        ("Bc4 system", "e4 d6 d4 Nf6 Nc3 g6 Bc4 Bg7 Qe2 O-O Bb3 c6"),
        ("Bg5 system", "e4 d6 d4 Nf6 Nc3 g6 Bg5 Bg7 Qd2 h6 Bh4 c5"),
        ("Be3 and f3", "e4 d6 d4 Nf6 Nc3 g6 f3 Bg7 Be3 O-O Qd2 c6"),
    ]),
    "Queen's Gambit Accepted": ("d4 d5 c4 dxc4", [
        ("Main line: 3.Nf3 Nf6 4.e3 e6", "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6"),
        ("3.e3 Nf6 4.Bxc4 e6", "d4 d5 c4 dxc4 e3 Nf6 Bxc4 e6 Nf3 c5 O-O a6 Qe2 b5 Bb3 Bb7"),
        ("Central: 3.e4 Nf6 4.e5", "d4 d5 c4 dxc4 e4 Nf6 e5 Nd5 Bxc4 Nb6 Bb3 Nc6"),
        ("Central: 3.e4 e5", "d4 d5 c4 dxc4 e4 e5 Nf3 exd4 Bxc4 Nc6 O-O Be6"),
        ("3.Nf3 a6 4.e3 Bg4", "d4 d5 c4 dxc4 Nf3 a6 e3 Bg4 Bxc4 e6 h3 Bh5"),
        ("3.Nf3 Nf6 4.Nc3 a6 5.e4 b5", "d4 d5 c4 dxc4 Nf3 Nf6 Nc3 a6 e4 b5 e5 Nd5"),
        ("3.Nf3 Nf6 4.e3 Bg4", "d4 d5 c4 dxc4 Nf3 Nf6 e3 Bg4 Bxc4 e6 h3 Bh5 Nc3 Nc6"),
        ("3.e3 e5", "d4 d5 c4 dxc4 e3 e5 Bxc4 exd4 exd4 Nf6 Nc3 Be7"),
        ("3.Nf3 Nf6 4.e3 e6 5.Bxc4 c5 6.O-O a6 7.Bb3", "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6 Bb3 cxd4 exd4 Nc6"),
    ]),
    "Dutch Defence": ("d4 f5", [
        ("Classical: ...e6, ...Be7, ...d6", "d4 f5 Nf3 Nf6 g3 e6 Bg2 Be7 O-O O-O c4 d6"),
        ("Stonewall: ...d5", "d4 f5 g3 Nf6 Bg2 e6 Nf3 d5 O-O Bd6 c4 c6 Nc3 O-O"),
        ("Leningrad: ...g6", "d4 f5 g3 Nf6 Bg2 g6 Nf3 Bg7 O-O O-O c4 d6 Nc3 Qe8"),
        ("Leningrad: ...Nc6 and d5", "d4 f5 g3 Nf6 Bg2 g6 Nf3 Bg7 O-O O-O c4 d6 Nc3 Nc6 d5 Na5"),
        ("Staunton Gambit", "d4 f5 e4 fxe4 Nc3 Nf6 Bg5 e6 Nxe4 Be7"),
        ("vs the London: Bf4", "d4 f5 Bf4 Nf6 e3 e6 Nf3 Be7 h3 O-O Bd3 b6"),
        ("2.Bg5 line", "d4 f5 Bg5 Nf6 Bxf6 exf6 e3 d5 Nd2 c6"),
        ("Classical: Qc2 and Nc3", "d4 f5 Nf3 Nf6 g3 e6 Bg2 Be7 O-O O-O c4 d6 Nc3 Qe8 Qc2 Qh5"),
    ]),
    "Scandinavian Defence": ("e4 d5 exd5", [
        ("Main line: 3.Nc3 Qa5", "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 Bf5 Bc4 e6"),
        ("3...Qa5 with ...c6", "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 c6 Nf3 Nf6 Bc4 Bf5 Bd2 e6"),
        ("3...Qd6", "e4 d5 exd5 Qxd5 Nc3 Qd6 d4 Nf6 Nf3 a6 g3 Bg4"),
        ("3...Qd8", "e4 d5 exd5 Qxd5 Nc3 Qd8 d4 Nf6 Nf3 Bg4 h3 Bxf3 Qxf3 e6"),
        ("Modern: 2...Nf6 3.Bb5+", "e4 d5 exd5 Nf6 Bb5+ Bd7 Bc4 b5 Bb3 Nxd5"),
        ("Modern: 3.d4 Nxd5", "e4 d5 exd5 Nf6 d4 Nxd5 c4 Nb6 Nf3 g6 Nc3 Bg7"),
        ("Icelandic Gambit: 3.c4 e6", "e4 d5 exd5 Nf6 c4 e6 dxe6 Bxe6 Nf3 Nc6"),
        ("2...Qxd5 3.Nf3", "e4 d5 exd5 Qxd5 Nf3 Nf6 d4 Bg4 Be2 e6 h3 Bh5"),
    ]),
}


def explorer(session, fen_cache, play: list[str]) -> list[dict]:
    """Moves from the Lichess explorer after `play` (UCI list), cached on disk."""
    key = " ".join(play)
    if key in fen_cache:
        return fen_cache[key]
    url = "https://explorer.lichess.org/lichess"
    params = {"play": ",".join(play), "moves": 4, "topGames": 0, "recentGames": 0,
              "ratings": "1800,2000,2200,2500", "speeds": "blitz,rapid,classical"}
    for attempt in range(6):
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 429:
            print(f"  429 from Lichess, waiting {60 * (attempt + 1)} s", flush=True)
            time.sleep(60 * (attempt + 1))  # Lichess asks for a minute after a 429
            continue
        r.raise_for_status()
        data = r.json()
        total = data["white"] + data["draws"] + data["black"]
        moves = [
            {"uci": m["uci"], "san": m["san"], "n": m["white"] + m["draws"] + m["black"], "total": total}
            for m in data["moves"]
        ]
        fen_cache[key] = moves
        time.sleep(2.5)  # one request every few seconds: the explorer rate limit is strict
        return moves
    raise SystemExit("Lichess kept answering 429; try again later")


def extend(session, cache, sans: list[str], target: int, offline: bool) -> list[str]:
    board = chess.Board()
    uci = []
    for s in sans:
        mv = board.parse_san(s)  # raises on an illegal move
        uci.append(mv.uci())
        board.push(mv)
    out = list(sans)
    while not offline and len(out) < target and len(out) < MAX_PLIES:
        moves = explorer(session, cache, uci)
        if not moves:
            break
        top = moves[0]
        if top["n"] < MIN_GAMES or top["n"] / max(top["total"], 1) < MIN_SHARE:
            break
        mv = board.parse_san(top["san"])
        out.append(board.san(mv))
        uci.append(mv.uci())
        board.push(mv)
    return out


def main() -> int:
    offline = "--offline" in sys.argv
    session = cache = None
    if not offline:
        import httpx
        token = os.environ.get("LICHESS_API_TOKEN", "")
        if not token:
            print("LICHESS_API_TOKEN is not set (or pass --offline)", file=sys.stderr)
            return 2
        session = httpx.Client(headers={"Authorization": f"Bearer {token}"})
        cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    result, problems = {}, []
    for name, (base, branches) in OPENINGS.items():
        base_l = base.split()
        lines, seen = [], set()
        for i, (label, prefix) in enumerate(branches):
            sans = prefix.split()
            if sans[: len(base_l)] != base_l:
                problems.append(f"{name} / {label}: does not start with the base moves")
                continue
            try:
                # first branch = legacy line: keep it exactly, then extend below the minimum only if short
                full = extend(session, cache, sans, MIN_PLIES, offline)
            except ValueError as e:
                problems.append(f"{name} / {label}: illegal move ({e})")
                continue
            key = tuple(full)
            if key in seen:
                problems.append(f"{name} / {label}: duplicate of an earlier line")
                continue
            seen.add(key)
            lines.append({"name": label.strip(), "moves": full})
        if not 6 <= len(lines) <= 10:
            problems.append(f"{name}: {len(lines)} lines (need 6 to 10)")
        result[name] = {"base": base_l, "lines": lines}
        if cache is not None:
            CACHE.write_text(json.dumps(cache))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    OUT.write_text(json.dumps({"openings": result}, ensure_ascii=False, indent=1) + "\n")
    total = sum(len(v["lines"]) for v in result.values())
    print(f"wrote {OUT} ({len(result)} openings, {total} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
