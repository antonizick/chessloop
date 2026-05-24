# ChessLoop — Design & Implementation Plan

> Last updated: 2026-05-24
> Status: Phase 3 complete — Phase 4 next

---

## 1. Executive Summary

ChessLoop is a self-hosted, move-based spaced-repetition chess opening trainer. Users teach the system by playing moves; the system drills them back with immediate corrective feedback and intelligent weakness-biased scheduling. The target is beginner-to-club players who want opening muscle memory, not flashcard trivia.

---

## 2. Final Technology Stack

### Frontend
| Layer | Choice | Why |
|---|---|---|
| Framework | React 18 + Vite | Fast HMR, excellent ecosystem, chess libs all target React |
| Language | TypeScript | Type safety across board events, SRS data, API contracts |
| Chess UI | Chessground | Best-in-class: drag/drop, touch, keyboard, themes, arrows |
| Chess Logic | chess.js | Move validation, FEN/PGN parsing, legal move generation |
| Styling | TailwindCSS | Utility-first, dark mode trivial, fast to prototype |
| State | Zustand | Lightweight, no boilerplate; board state + session state |
| HTTP | TanStack Query | Caching, loading states, optimistic updates |
| Router | React Router v6 | SPA routing, nested layouts |

### Backend
| Layer | Choice | Why |
|---|---|---|
| Runtime | Python 3.12 | Nick's comfort; FastAPI is the best async REST framework |
| Framework | FastAPI | Auto OpenAPI docs, pydantic validation, async support |
| ORM | SQLModel | Pydantic + SQLAlchemy in one; type-safe models |
| Database | SQLite (WAL mode) | Zero config, file = backup, plenty fast for this scale |
| Auth | python-jose + passlib | JWT sessions, bcrypt hashing, TOTP via pyotp |
| External API | httpx (async) | Lichess Explorer calls, rate-limited + cached |

### Infrastructure
| Layer | Choice |
|---|---|
| Container | Docker Compose (3 services: frontend, backend, nginx) |
| Reverse Proxy | Nginx (SSL termination, static asset serving) |
| Volume | Named Docker volume for `chessloop.db` + backups |

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (SPA)                        │
│  React + Chessground + chess.js + Zustand + TanStack Q  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS (REST JSON)
┌────────────────────────▼────────────────────────────────┐
│                    Nginx Reverse Proxy                   │
│         /api/* → FastAPI    /* → React static           │
└────────────┬───────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│                   FastAPI Backend                        │
│                                                          │
│  Routers:                                                │
│  ├── /auth       (login, register, MFA, sessions)       │
│  ├── /libraries  (CRUD, fork, publish)                   │
│  ├── /lines      (CRUD, teaching, move recording)        │
│  ├── /practice   (session start, answer, SRS scheduler) │
│  ├── /stats      (heatmaps, mastery, leech detection)   │
│  ├── /public     (browse, search, fork, comments)       │
│  ├── /lichess    (proxy + cache Explorer API)            │
│  └── /admin      (backup, restore, user management)     │
│                                                          │
│  Services:                                               │
│  ├── SRSEngine   (SM-2 variant, leech detection)        │
│  ├── PositionKey (Zobrist hash / canonical FEN key)     │
│  ├── LichessCache (TTL cache for Explorer stats)        │
│  └── BackupService (named backups, retention 10)        │
└────────────┬────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│              SQLite (WAL mode, /data/chessloop.db)      │
└─────────────────────────────────────────────────────────┘
             │
             └── External: Lichess Opening Explorer API
```

---

## 4. Complete Data Model

### Users
```sql
User
  id            UUID PK
  email         TEXT UNIQUE NOT NULL
  username      TEXT UNIQUE NOT NULL
  password_hash TEXT NOT NULL
  mfa_secret    TEXT NULL          -- TOTP base32 secret
  mfa_enabled   BOOL DEFAULT FALSE
  role          TEXT DEFAULT 'user' -- 'user' | 'admin'
  theme         TEXT DEFAULT 'dark'
  piece_set     TEXT DEFAULT 'cburnett'
  board_theme   TEXT DEFAULT 'brown'
  sounds_on     BOOL DEFAULT TRUE
  created_at    DATETIME
  last_login    DATETIME NULL
```

### Libraries
```sql
Library
  id              UUID PK
  name            TEXT NOT NULL
  color           TEXT NOT NULL   -- 'white' | 'black' | 'both'
  owner_user_id   UUID FK → User
  is_active       BOOL DEFAULT TRUE
  is_public       BOOL DEFAULT FALSE
  forked_from_id  UUID NULL FK → Library  -- NULL = original
  published_at    DATETIME NULL
  description     TEXT NULL
  eco_code        TEXT NULL       -- e.g. "B90"
  difficulty      TEXT NULL       -- 'beginner'|'intermediate'|'advanced'
  created_at      DATETIME
  updated_at      DATETIME

  INDEX: owner_user_id, is_public, eco_code
```

### Lines
```sql
Line
  id              UUID PK
  library_id      UUID FK → Library
  name            TEXT NULL       -- e.g. "Main Line", "6.Bg5 variation"
  starting_fen    TEXT DEFAULT 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
  moves           TEXT NOT NULL   -- JSON array: [{san, uci, fen_after, note}]
  order_index     INT DEFAULT 0
  created_at      DATETIME
  updated_at      DATETIME

  INDEX: library_id
```

### Move Notes (per-move annotations)
```sql
MoveNote
  id        UUID PK
  line_id   UUID FK → Line
  move_num  INT NOT NULL    -- 0-indexed position in moves array
  text      TEXT NOT NULL
  is_public BOOL DEFAULT FALSE
  author_id UUID FK → User
```

### SRS / Practice
```sql
PracticePosition
  id              UUID PK
  user_id         UUID FK → User
  line_id         UUID FK → Line
  move_index      INT NOT NULL        -- which move in the line is being drilled
  position_key    TEXT NOT NULL       -- canonical FEN key (no clocks)
  ease_factor     FLOAT DEFAULT 2.5   -- SM-2 ease
  interval_days   FLOAT DEFAULT 0
  due_at          DATETIME
  repetitions     INT DEFAULT 0
  leech_count     INT DEFAULT 0       -- wrong answers accumulated
  is_leech        BOOL DEFAULT FALSE
  created_at      DATETIME
  last_reviewed   DATETIME NULL

  UNIQUE: (user_id, line_id, move_index)
  INDEX: (user_id, due_at), (user_id, is_leech)

ReviewLog
  id              UUID PK
  user_id         UUID FK → User
  practice_pos_id UUID FK → PracticePosition
  session_id      UUID NULL FK → PracticeSession
  was_correct     BOOL NOT NULL
  ease_chosen     TEXT NULL     -- 'easy' | 'hard' (only after first correct)
  response_ms     INT NULL      -- response time
  reviewed_at     DATETIME

PracticeSession
  id          UUID PK
  user_id     UUID FK → User
  started_at  DATETIME
  ended_at    DATETIME NULL
  mode        TEXT     -- 'weakest' | 'selected' | 'leech_drill'
  scope       TEXT     -- JSON: library/line ids or 'active'
  stats       TEXT     -- JSON snapshot: {correct, wrong, positions_seen}
```

### Public / Social
```sql
PublicSignal
  id          UUID PK
  user_id     UUID FK → User
  target_type TEXT    -- 'library' | 'line'
  target_id   UUID
  kind        TEXT    -- 'star' | 'comment'
  content     TEXT NULL  -- for comments
  created_at  DATETIME

  INDEX: (target_type, target_id)
```

### Backups
```sql
Backup
  id          UUID PK
  name        TEXT NOT NULL
  type        TEXT NOT NULL  -- 'full' | 'content' | 'progress'
  file_path   TEXT NOT NULL
  size_bytes  INT
  created_by  UUID FK → User
  created_at  DATETIME
```

---

## 5. SRS Engine Design

**Algorithm: Modified SM-2**

```
On correct answer:
  if repetitions == 0:
    interval = 1 day
  elif repetitions == 1:
    interval = 6 days
  else:
    interval = prev_interval * ease_factor
  
  if ease_chosen == 'easy':
    ease_factor = min(ease_factor + 0.15, 2.5)
    interval *= 1.3
  elif ease_chosen == 'hard':
    ease_factor = max(ease_factor - 0.15, 1.3)
    interval *= 0.8
  
  repetitions += 1
  due_at = now + interval

On wrong answer:
  interval = max(1, interval * 0.25)
  repetitions = 0
  leech_count += 1
  due_at = now + 10 minutes  (requeue soon)
  
  if leech_count >= 4:
    is_leech = TRUE  (surfaced in dedicated drill)
```

**Session selection priority:**
1. Overdue items (due_at < now), sorted by most overdue
2. Leeches always included if leech_drill mode
3. New items (never practiced) with 20% weight
4. Weakness bias: positions with ease_factor < 1.8 get 2× weight

---

## 6. API Design

### Auth
```
POST /api/auth/register        { email, username, password }
POST /api/auth/login           { email, password } → JWT
POST /api/auth/login/mfa       { token, totp_code } → JWT (if MFA enabled)
POST /api/auth/logout
GET  /api/auth/me
POST /api/auth/mfa/setup       → { secret, qr_url }
POST /api/auth/mfa/confirm     { totp_code }
```

### Libraries
```
GET    /api/libraries                    → user's libraries
POST   /api/libraries                    { name, color, description }
GET    /api/libraries/{id}
PUT    /api/libraries/{id}
DELETE /api/libraries/{id}
PATCH  /api/libraries/{id}/active        { is_active: bool }
POST   /api/libraries/{id}/publish
POST   /api/libraries/{id}/fork          → new Library (copy)
```

### Lines
```
GET    /api/libraries/{lib_id}/lines
POST   /api/libraries/{lib_id}/lines     { name, starting_fen? }
GET    /api/lines/{id}
PUT    /api/lines/{id}                   { name }
DELETE /api/lines/{id}
POST   /api/lines/{id}/moves             { san, uci } → updated Line
DELETE /api/lines/{id}/moves/{index}     remove move at index
PUT    /api/lines/{id}/moves/{index}/note { text }
```

### Practice
```
POST /api/practice/session/start         { mode, scope }
GET  /api/practice/session/{id}/next     → { line, move_index, fen, ... }
POST /api/practice/session/{id}/answer   { move_uci, correct, ease? }
POST /api/practice/session/{id}/end
GET  /api/practice/due-count             → { count } (for dashboard badge)
```

### Stats
```
GET /api/stats/heatmap              → { by_move_number: [...], by_library: [...] }
GET /api/stats/mastery              → [{ library_id, name, mastery_pct, badge }]
GET /api/stats/leeches              → [PracticePosition]
GET /api/stats/recent-sessions      → [PracticeSession]
```

### Public Discovery
```
GET  /api/public/libraries           ?q=&eco=&color=&difficulty=&sort=
GET  /api/public/libraries/{id}
POST /api/public/libraries/{id}/star
GET  /api/public/libraries/{id}/comments
POST /api/public/libraries/{id}/comments  { text }
```

### Lichess Proxy
```
GET /api/lichess/explorer?fen=&play=   (cached, TTL 24h)
```

### Admin
```
GET    /api/admin/backups
POST   /api/admin/backups              { name, type }
GET    /api/admin/backups/{id}/download
POST   /api/admin/backups/{id}/restore
DELETE /api/admin/backups/{id}
GET    /api/admin/users
PATCH  /api/admin/users/{id}           { role }
```

---

## 7. Frontend Architecture

### Route / View Map
```
/                       → Dashboard
/login                  → Login / Register
/libraries              → Library Browser
/libraries/new          → Create Library
/libraries/{id}         → Library Detail (lines list)
/libraries/{id}/teach   → Teaching Board
/practice               → Practice Entry (mode/scope picker)
/practice/session       → Practice Board (active session)
/stats                  → Stats & Heatmaps
/public                 → Public Library Discovery
/public/{id}            → Public Library Preview
/settings               → User Preferences
/admin                  → Admin Panel (role-gated)
```

### Component Tree (key pieces)
```
App
├── Layout
│   ├── Topbar (nav, user menu, practice badge)
│   └── Sidebar (library tree, quick actions)
├── Dashboard
│   ├── ActiveOpeningCards
│   ├── PracticeWeakestButton
│   ├── RecentSessionSummary
│   └── MasteryBadgeStrip
├── TeachingBoard
│   ├── ChessboardWrapper (Chessground)
│   ├── MoveList (scrollable, editable)
│   ├── LichessStatsPanel
│   └── MoveNoteEditor
├── PracticeBoard
│   ├── ChessboardWrapper (Chessground)
│   ├── FeedbackOverlay (red flash, correct move animation)
│   ├── EasyHardButtons (post-correct)
│   ├── SessionProgressBar
│   └── MoveExplanationDrawer
└── StatsView
    ├── AccuracyHeatmap (move-number chart)
    ├── OpeningMasteryGrid (badges)
    └── LeechDrillList
```

### Chessground Integration Pattern
```typescript
// Core board hook
function useChessboard(config: BoardConfig) {
  const cg = useRef<Api | null>(null);
  const chess = useRef(new Chess());

  const onMove = useCallback((orig: Key, dest: Key) => {
    const move = chess.current.move({ from: orig, to: dest, promotion: 'q' });
    if (!move) return; // illegal, Chessground auto-reverts
    onMoveCallback(move); // teaching: record | practice: evaluate
  }, []);

  return { cg, chess, setPosition, highlightMoves, showArrow };
}
```

### State Management (Zustand stores)
```typescript
// Practice session store
interface PracticeStore {
  sessionId: string | null;
  currentPosition: PositionState | null;
  feedback: FeedbackState | null;
  startSession: (mode, scope) => Promise<void>;
  submitMove: (uci: string) => Promise<void>;
  endSession: () => Promise<void>;
}

// Library store (teaching)
interface TeachingStore {
  lineId: string | null;
  moves: Move[];
  addMove: (move: Move) => Promise<void>;
  deleteMove: (index: number) => Promise<void>;
  updateNote: (index: number, text: string) => Promise<void>;
}
```

---

## 8. Phased Implementation Roadmap

### Phase 1 — Foundation (Sprint 1-2, ~2 weeks) ✅ COMPLETE
**Goal: Auth + Library CRUD working, boards render**

- [x] Project scaffold: Vite+React+TS frontend, FastAPI backend, Docker Compose
- [x] SQLite schema + SQLModel models
- [x] Auth: register, login, JWT middleware, MFA setup
- [x] Library CRUD API + frontend (no board yet)
- [x] Line CRUD API
- [x] Chessground renders in both Teaching and Practice pages (static)
- [x] Basic dark/gold Tailwind theme

### Phase 2 — Teaching Mode (Sprint 3, ~1 week) ✅ COMPLETE
**Goal: Full teaching flow operational**

- [x] Teaching board: play moves → record to Line
- [x] Move list: display, delete individual moves
- [x] Move notes: per-move annotation
- [ ] Lichess Explorer panel (proxy endpoint + frontend panel) ← deferred to Phase 4
- [x] Auto-save on every move

### Phase 3 — Practice Core (Sprint 4-5, ~2 weeks) ✅ COMPLETE
**Goal: Full SRS loop working**

- [x] SRSEngine: SM-2 implementation + leech detection
- [x] PositionKey: canonical FEN hash
- [x] Practice session API (start, next, answer, end)
- [x] Practice board UI: opponent auto-plays, wait for user move
- [x] Feedback overlay: red flash, correct move animation, forced re-play
- [x] Easy/Hard buttons post-correct
- [x] Session summary screen
- [x] Sound effects (move, capture)
- [x] Service manager TUI (manage.sh interactive menu)

**Critical engineering note — Chessground `bindBoard` orientation race:**
Chessground 9.x registers `mousedown`/`touchstart` listeners in `bindBoard()`, which
runs both at init AND whenever `api.set({ orientation })` triggers
`toggleOrientation() → redrawAll() → renderWrap() + bindBoard()`. The problem:
`bindBoard()` reads `state.viewOnly` **before** `configure(state, config)` updates it.
If `state.viewOnly` is `true` at that moment, `bindBoard()` permanently skips listener
registration — `api.set({ viewOnly: false })` later updates state but cannot re-run
`bindBoard()`.

**The fix** (`ChessboardWrapper.tsx` prop-sync effect):
```typescript
// Pre-set viewOnly:false so state is already false when any orientation-triggered
// bindBoard() fires; then apply the final desired values.
api.set({ viewOnly: false });
api.set({ orientation, viewOnly });
```

**Why always-mounted board:** ChessboardWrapper stays in the DOM for the entire page
lifetime (`visibility:hidden` during entry/done phases). This guarantees `cgRef.current`
is set before any network requests resolve, eliminating all timing races between
`useLayoutEffect` init and parent async code.

### Phase 4 — Stats & Discovery (Sprint 6, ~1 week)
**Goal: Progress visible, public content explorable**

- [ ] Heatmap: accuracy by move number (recharts or custom SVG)
- [ ] Mastery %: per-library calculation + badge thresholds
- [ ] Dashboard: active openings, practice badge, weak lines teaser
- [ ] Public library: publish, browse, search, fork
- [ ] "Practice weakest now" button (Active libraries, most overdue)

### Phase 5 — Polish & Admin (Sprint 7, ~1 week)
**Goal: Production-ready self-host**

- [ ] Piece set selector + board color themes (4+ options each)
- [ ] Sound effects (move, capture, correct, wrong)
- [ ] Admin: backup UI (create/download/restore), user management
- [ ] Seed 12+ official starter libraries (PGN import + auto-populate)
- [ ] Docker Compose production config with Nginx + SSL hints
- [ ] README with self-host instructions

---

## 9. Seeded Starter Libraries (Target 16)

| Opening | Color | ECO | Difficulty |
|---|---|---|---|
| Italian Game — Main Line | White | C50 | Beginner |
| Italian Game — Giuoco Piano | White | C54 | Beginner |
| Ruy López — Closed | White | C84 | Intermediate |
| London System | White | D02 | Beginner |
| Queen's Gambit Declined | White | D30 | Intermediate |
| King's Indian Attack | White | A07 | Intermediate |
| Sicilian Defence — Najdorf | Black | B90 | Advanced |
| Sicilian Defence — Dragon | Black | B70 | Advanced |
| French Defence — Classical | Black | C11 | Intermediate |
| Caro-Kann — Classical | Black | B18 | Intermediate |
| King's Indian Defence | Black | E62 | Intermediate |
| Grünfeld Defence | Black | D70 | Advanced |
| Pirc Defence | Black | B07 | Intermediate |
| Queen's Gambit Accepted | Black | D20 | Beginner |
| Dutch Defence | Black | A80 | Intermediate |
| Scandinavian Defence | Black | B01 | Beginner |

Source: Lichess Opening Explorer PGNs + public Chessable-quality annotations.

---

## 10. Key Engineering Decisions & Rationale

### Position Key Design
Store canonical FEN (strip half-move/full-move counters) as position key. This enables:
- SRS deduplication across transpositions (same position reached via different move orders)
- Future transposition detection without refactoring data model
- Zobrist hash as an optional secondary index if performance demands it later

### Teaching Mode: Strict Move Recording
No fuzzy matching. The system records *exactly* the moves played. This enforces repertoire discipline and simplifies the SRS model (one correct response per position-in-line).

### Feedback UX: Forced Correct Move
On wrong answer, the board shows a red highlight + animated arrow showing the correct move. The user *must* play the correct move before continuing. This is the pedagogically critical difference from flashcard systems — motor memory requires physical execution.

### Leech Threshold: 4 Errors
A position becomes a leech after 4 cumulative wrong answers (not consecutive). Leeches surface in a dedicated drill mode and are also shown in the Stats view. This matches Anki's behavioral model.

### Auth: JWT + Refresh Tokens
Access token: 15-minute TTL (stored in memory, never localStorage).
Refresh token: 30-day TTL (httpOnly cookie).
This prevents XSS token theft while keeping UX seamless.

### SQLite WAL Mode
`PRAGMA journal_mode=WAL;` enables concurrent readers with one writer. Adequate for a single self-hosted instance. WAL file = point-in-time-safe for backup copying.

---

## 11. Open Questions (Resolve Before Phase 1)

1. **Move editing in Teaching mode**: Inline board editor for inserting moves mid-sequence, or append-only with delete? **Recommendation: Append + delete for MVP. Insert/reorder in Phase 2.**

2. **Branch support**: Will lines support branching trees (one-to-many from a position), or are they strictly linear sequences? **Recommendation: Linear sequences in MVP. Tree model in Phase 2** — requires more complex UI and SRS position tracking.

3. **Starter library sourcing**: Do you want to manually curate the 16 PGNs, or should I write a scraper against Lichess Explorer to auto-generate them? **Recommendation: Scraper script to pull top lines per ECO, manual QA pass.**

4. **T2.nano performance budget**: SQLite on T2.nano (1 vCPU, 1GB RAM) is fine for <100 concurrent users. The Lichess proxy cache must be in-memory (TTLCache) to avoid hammering the API. No Redis needed at this scale.

---

## 12. File Structure

```
chessloop/
├── docker-compose.yml
├── nginx/
│   └── default.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app factory
│   ├── database.py              # SQLite + SQLModel setup
│   ├── models/
│   │   ├── user.py
│   │   ├── library.py
│   │   ├── line.py
│   │   ├── practice.py
│   │   └── backup.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── libraries.py
│   │   ├── lines.py
│   │   ├── practice.py
│   │   ├── stats.py
│   │   ├── public.py
│   │   ├── lichess.py
│   │   └── admin.py
│   ├── services/
│   │   ├── srs_engine.py
│   │   ├── position_key.py
│   │   ├── lichess_cache.py
│   │   └── backup_service.py
│   ├── auth/
│   │   ├── jwt.py
│   │   └── mfa.py
│   └── seeds/
│       ├── seed.py
│       └── pgns/               # 16 opening PGN files
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes.tsx
│   │   ├── api/               # TanStack Query hooks
│   │   ├── components/
│   │   │   ├── board/         # Chessground wrappers
│   │   │   ├── teaching/
│   │   │   ├── practice/
│   │   │   ├── stats/
│   │   │   └── ui/            # Shared design system
│   │   ├── stores/            # Zustand stores
│   │   ├── pages/             # Route components
│   │   └── types/             # Shared TypeScript types
└── scripts/
    └── generate_seeds.py      # Lichess Explorer → PGN seeds
```

---

## 13. Model Recommendation

**Use Claude Opus for initial creation.**

### Why Opus, not Sonnet or Haiku?

ChessLoop has several intersecting complexity domains that benefit from Opus's deeper reasoning:

| Complexity Factor | Impact |
|---|---|
| **SRS algorithm** | SM-2 with leech detection, weakness bias, session ordering — requires correct mathematical logic on first pass |
| **Chess data model** | FEN normalization, move-sequence storage, position keying, transposition awareness — subtle correctness requirements |
| **Multi-layer auth** | JWT + refresh tokens + TOTP MFA + role gating — security-critical, hard to debug partial implementations |
| **Chessground integration** | Complex stateful board API, event handling, animation callbacks — needs the right patterns up front |
| **Full-stack coherence** | Frontend types must align with backend models; API contracts must match both router and query hook |
| **Phase 1 scaffold quality** | A good scaffold is 10× cheaper to build on than a mediocre one — this is the highest-leverage moment |

**Sonnet** would handle most of this, but tends to produce scaffolds that need significant architectural corrections when multiple complex systems (SRS + chess + auth + real-time board state) interact. The cost of a wrong pattern at Phase 1 compounds across all subsequent phases.

**Haiku** is the wrong tool — great for isolated functions, not for reasoning across a full-stack architecture.

**Practical guidance:**
- Use **Opus** for: Phase 1 scaffold, SRS engine, auth system, Chessground integration hooks
- Switch to **Sonnet** for: routine CRUD endpoints, React page components, styling work, seed data scripting
- Use **Haiku** for: simple utility functions, CSS tweaks, rename/move operations

This hybrid approach keeps costs reasonable while using Opus where architectural correctness matters most.
