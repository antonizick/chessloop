# ChessLoop — Design & Implementation Plan

> Last updated: 2026-05-28
> Status: Phase 5+ complete — Backup upload & recovery feature added

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

### Phase 4 — Stats & Discovery (Sprint 6, ~1 week) ✅ COMPLETE
**Goal: Progress visible, public content explorable**

- [x] Heatmap: accuracy by move number (custom SVG bar chart, color-coded)
- [x] Mastery %: per-library calculation + badge thresholds (not_started/learning/developing/advanced/mastered)
- [x] Dashboard: active openings, practice badge, weak lines teaser, mastery badge strip
- [x] Public library: publish (already in Phase 2), browse, search, fork, star, comment
- [x] "Practice weakest now" button (CTA card, auto-starts weakest session)

**Phase 4 notes:**
- Stats backend: `/api/stats/heatmap`, `/api/stats/mastery`, `/api/stats/leeches`, `/api/stats/recent-sessions`
- Public backend: `/api/public/libraries` (browse/filter/sort), detail, star toggle, comments
- `PublicSignal` model added for stars + comments
- Heatmap uses pure SVG (no recharts dep) — green ≥80%, yellow 50-79%, red <50%
- "Practice weakest now" navigates to `/practice` with `state.autoMode="weakest"` for auto-start

### Phase 5 — Polish & Admin (Sprint 7, ~1 week) ✅ COMPLETE
**Goal: Production-ready self-host**

- [x] Piece set selector + board color themes (5 themes: brown/blue/green/ice/purple; 4 piece sets: cburnett/alpha/mono/shadow)
- [x] Sound effects (move, capture, correct chime, wrong buzz; sounds_on toggle per user)
- [x] Admin: backup UI (create/download/delete, 10-backup retention), user management (promote/demote)
- [x] Seed 16 official starter libraries (seed_libraries.py — SAN-only API, python-chess on backend)
- [x] Docker Compose production config (docker-compose.prod.yml — 127.0.0.1 binding, health checks, SSL notes)
- [x] README with full self-host guide (admin setup, seed script, SSL options A/B/C, backup instructions)
- [x] Boost Visibility: larger fonts, high-contrast labels, auto-save on toggle
- [x] Rated/Unrated practice indicators: distinct visual badges on practice screens
- [x] Learning/Teaching quick-access menu: library selector modal for rapid access to learning and teaching screens

**Phase 5 notes:**
- Board themes: CSS classes on ChessboardWrapper container — `board-theme-{name}` overrides `cg-board` background
- Piece sets: CSS `filter` variants applied to `.cg-wrap piece` elements (no extra SVG files needed)
- Preferences: `PATCH /api/auth/preferences` endpoint; live board preview in Settings before saving
- Admin: role-gated (`role='admin'`); Admin panel linked in Sidebar for admin users only
- Backend: `LineMoveAppend` now accepts SAN-only — backend computes UCI + FEN via python-chess
- Seed: creates `seedbot` account, adds 16 openings, publishes them; skips existing libraries

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

## 12. Post-Phase 5 Fixes & Refinements

### Backup Directory Fix (2026-05-24)

**Issue:** Backup creation returned 500 error due to permission denied on `/data/backups`.

**Root cause:** Default backup path was `/data/backups` (system-owned directory), but users lack write permission.

**Fix:** Changed default backup directory to `./backups` (relative path, user-owned).
- `backend/services/backup_service.py` line 25
- Environment variable override still available: `CHESSLOOP_BACKUP_DIR`

**Result:** Backups now work out-of-the-box; portable across dev and Docker deployments.

### Move Navigation & PGN Export Enhancement (2026-05-25)

**Feature:** Added move navigation controls and PGN export to Teaching Board

**Implementation:**
- Navigation buttons at bottom of move list card: ⟪ (first) · ‹ (previous) · › (next) · ⟫ (last)
- Export button: ↓ PGN (downloads moves as valid PGN file with [Event] header using line name)
- Smart navigation: Previous from end jumps to last move; next from last jumps to live position
- Controls positioned with "White to move" / "Black to move" indicator for clear UX

**Files modified:**
- `frontend/src/components/teaching/MoveList.tsx` — exported PGN generation functions
- `frontend/src/pages/TeachingBoard.tsx` — navigation handlers and control UI

**Result:** Users can easily navigate through recorded moves and export openings in standard PGN format for use in other tools.

### Navigation Refactor & Teaching Board Layout (2026-05-25)

**Feature:** Moved main navigation to collapsible left sidebar; reorganized Teaching Board layout

**Implementation:**
- **Topbar:** Removed Libraries, Practice, Stats, Discover nav items; kept Settings and Logout
- **Sidebar:** Added collapsible Menu section with all 4 main navigation items + Practice due-count badge
- **Teaching Board:** Changed from 2-column (board | movelist) to 3-column (board | movelist | lines panel) grid layout
- **Line Management:** Inlined LineSelector component into right panel; full create/rename/delete in right sidebar

**Files modified:**
- `frontend/src/components/layout/Topbar.tsx` — removed nav items and unused dueCount query
- `frontend/src/components/layout/Sidebar.tsx` — added Menu toggle and main navigation items
- `frontend/src/pages/TeachingBoard.tsx` — changed grid layout and inlined line management UI

**Result:** Navigation consolidated in sidebar for cleaner topbar; Teaching Board now has dedicated panel for line management, reducing visual clutter and improving usability.

### Practice Screen Default & Library Deletion Bug Fix (2026-05-25)

**Changes:**
1. **Practice Default:** Changed default "where to start in each line" option from "SRS picks" to "First move"
   - File: `frontend/src/components/practice/ModeEntry.tsx` line 113
   
2. **Library Deletion Bug:** Fixed 500 error when deleting libraries due to unhandled foreign key constraints
   - Issue: ReviewLog and PracticePosition records were referencing deleted lines
   - Fix: Updated `delete_library` endpoint in `backend/routers/libraries.py` to properly cascade deletes
     - Delete ReviewLog entries → PracticePosition entries → Line entries → Library (in order)
     - Added explicit `session.flush()` calls between each deletion level to respect FK constraints

**Files modified:**
- `frontend/src/components/practice/ModeEntry.tsx` — changed default startPosition to "first"
- `backend/routers/libraries.py` — added PracticePosition and ReviewLog imports; fixed deletion cascade logic

**Result:** Practice users start from the beginning of lines by default; library deletion now works properly with no orphaned database records.

### Line Duplication Feature (2026-05-26)

**Feature:** Added duplicate line button to Teaching Board line management panel

**Implementation:**
- **Button:** Duplicate button (⧭) appears on hover next to delete button in line list
- **Behavior:** Creates a new line with "{name} copy" and duplicates all moves from original line
- **UX:** Auto-selects new duplicated line; shows loading state ("…") during operation; disabled while copying
- **API:** Single mutation combining `linesApi.create()` + `linesApi.importMoves()` for efficient duplication

**Files modified:**
- `frontend/src/pages/TeachingBoard.tsx` — added duplicateLine mutation and button UI
- `chessloop/README.md` — updated Teaching Board Controls section with duplicate button documentation

**Result:** Users can quickly create variations of existing lines without re-playing all moves.

### Unrated Learning Feature (2026-05-26)

**Feature:** Added read-only "Unrated Learning" mode for browsing opening libraries without any editing capabilities

**Implementation:**
- **New Component:** `frontend/src/pages/UnratedLearning.tsx` (330 lines)
  - Copied from TeachingBoard.tsx and stripped all write operations
  - Board always `viewOnly={true}` — pieces cannot be moved under any circumstances
  - No mutations: no create/rename/delete/duplicate lines, no move recording, no imports

**Removed from Teaching Board:**
- All 5 mutations: createLine, renameLine, deleteLine, duplicateLine, importLinesMut
- All write UI: import panel, rename form, duplicate button (⧭), delete button (🗑), "+ New line" button
- All edit state: isSaving, showImport, importText, importError, renamingId, renameValue, deleteConfirmId, isDeleting
- PromotionModal and handlePromotionSelect (no new moves possible)
- Note editor (kept simple for read-only mode)

**Preserved Features:**
- Full navigation: arrow keys (← → ↑ ↓), navigation buttons (⟪ ‹ › ⟫)
- PGN export and clipboard copy
- Flip board button
- Clean read-only line selector
- User preferences: sounds, board theme, piece set

**Entry Points (2 locations):**
1. **Libraries.tsx:** Added "Unrated Learning" button left of "✎ Teach" in library grid cards
2. **LibraryDetail.tsx:** Added "Unrated Learning" button left of "Teaching Board" in detail page

**Route Configuration:**
- Added to App.tsx: `<Route path="/libraries/:id/unrated" element={<UnratedLearning />} />`

**Files modified:**
- `frontend/src/pages/UnratedLearning.tsx` — NEW (330 lines)
- `frontend/src/App.tsx` — added import and route
- `frontend/src/pages/Libraries.tsx` — added entry point button
- `frontend/src/pages/LibraryDetail.tsx` — added entry point button

**Result:** Users can now browse and study opening lines in a distraction-free, read-only mode with full navigation and export capabilities but no ability to modify content.

### Automatic Lichess GitHub Line Loading (2026-05-26)

**Feature:** Automatic loading of opening lines from Lichess GitHub repository when a new opening library is imported

**Implementation:**
- Modified `import_opening()` function in `backend/services/opening_import.py` to automatically call `import_lichess_lines_into_library()` after library creation
- The GitHub import happens silently after the main library is created; if it fails for any reason, the library is still successfully created

**Behavior:**
1. When admin imports an opening (via `/admin/openings/import` endpoint), the library is created with its ECO code
2. Immediately after, the system automatically fetches all matching opening lines from the Lichess GitHub chess-openings repository
3. These lines are loaded directly into the library based on ECO code matching
4. This mirrors the previously added functionality but now happens automatically without manual triggering

**Why automatic:**
- Users no longer need to manually call `/admin/openings/import-lichess-lines` after importing
- New openings are instantly populated with comprehensive line data from the chess-openings repository
- Simplified workflow: import once, get complete library with variations

**Files modified:**
- `backend/services/opening_import.py` — modified `import_opening()` function to auto-load GitHub lines

**Result:** Opening imports are now fully automated — when a library is created, all available opening lines from the Lichess GitHub repository are loaded immediately.

### Practice Mode UI Enhancement & Leech Count Fix (2026-05-27)

**Feature:** Improved practice mode entry screen with better UX for disabled states and hover tooltips

**Implementation:**

1. **Shared Tooltip Component** — `frontend/src/components/ui/Tooltip.tsx` (NEW)
   - Reusable hover tooltip that displays absolutely-positioned bubble above element
   - Styled with dark ink palette and CSS triangle caret pointing downward
   - Supports disabled state (greyed out with reduced opacity)
   - Allows tooltips to show even on disabled elements for contextual explanations

2. **Mode Entry Improvements** — `frontend/src/components/practice/ModeEntry.tsx`
   - Added `leechCount` prop from parent to enable conditional disabling
   - Wrapped all session mode cards in `<Tooltip>` components with detailed descriptions
   - Wrapped all "where to start" segment buttons in `<Tooltip>` components
   - Added `disabled` prop to mode cards when `leechCount === 0` for Leech Drill
   - Greyed out disabled cards with `opacity-50 cursor-not-allowed` styling
   - Disabled Leech Drill card shows tooltip: "You don't have any leeches yet. A 'leech' is a position you've missed 4+ times. When you reach 4 misses on any position, it will be marked as a leech and you can come back to drill it here."

3. **Practice Board Integration** — `frontend/src/pages/PracticeBoard.tsx`
   - Added `useQuery` hook to fetch due-count data (with `refetchOnMount: true`)
   - Passes `leechCount={dueCount?.leeches ?? 0}` prop to `<ModeEntry>`
   - Added validation in `startSession()` to prevent starting leech_drill mode with zero leeches
   - Shows user-friendly error message if attempt is made

4. **Backend Leech Count Fix** — `backend/routers/practice.py` (lines 298-324)
   - **Root issue:** `/due-count` endpoint was counting leeches from ALL libraries, not respecting active-library filter
   - **Fix:** Updated query to only count `PracticePosition` records from active libraries via chain: `PracticePosition` → `Line.library_id` → filter by `Library.is_active == True`
   - **Impact:** Now correctly reflects leech count visible to user in their active practice set

**Files modified:**
- `frontend/src/components/ui/Tooltip.tsx` — NEW shared component
- `frontend/src/components/practice/ModeEntry.tsx` — added leechCount prop, tooltip wrappers, disabled state logic
- `frontend/src/pages/PracticeBoard.tsx` — added due-count query, validation, leechCount prop pass-through
- `backend/routers/practice.py` — fixed active-library filtering in due-count endpoint

**Result:** Users now see clear visual feedback (greyed-out with explanatory tooltip) when Leech Drill is unavailable, reducing confusion. All practice modes and start-position options have hover tooltips for discoverability. Backend now correctly counts only leeches from active libraries.

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

---

## 14. Infrastructure & Networking Fixes (2026-05-26)

### Tailscale VPN & HMR Support

**Problem:** 
- Intermittent 502 errors when accessing the frontend through Tailscale VPN (https://bld2.taild1bb43.ts.net:8443)
- Mixed content warnings: HTTPS pages trying to connect to insecure WebSocket (ws://)
- Vite dev server HMR not auto-detecting host from browser requests

**Solution:**
1. **HMR Protocol Auto-Detection** (vite.config.ts):
   - Changed `hmr.protocol` from `'ws'` to `'auto'`
   - Vite now auto-detects based on page protocol:
     - HTTPS (Tailscale) → `wss://` (secure WebSocket)
     - HTTP (localhost) → `ws://` (regular WebSocket)
   - Eliminates mixed content errors and 502 gateway failures

2. **React Warning Fix** (PracticeBoard.tsx):
   - Removed `flushSync` calls from useEffect (React 19 compatibility)
   - Replaced with `Promise.resolve().then()` microtask for deferred state updates
   - Maintains minimal flickering while respecting React's rendering constraints
   - Removed unused `flushSync` import from react-dom

**Files Modified:**
- `chessloop/frontend/vite.config.ts` — HMR protocol config
- `chessloop/frontend/src/pages/PracticeBoard.tsx` — board initialization workaround

**Testing & Verification:**
- ✅ Localhost access (http://localhost:8090) — fully functional
- ✅ Tailscale access (https://bld2.taild1bb43.ts.net:8443) — fully functional, no 502 errors
- ✅ Practice boards — pieces draggable, no console warnings
- ✅ HMR — hot reloads work transparently over both connections

**Impact:**
This enables the development environment to work seamlessly over VPN, allowing Nick to:
- Access ChessLoop through Tailscale from anywhere
- Use full development server with HMR across different network interfaces
- Work with localhost and production-like HTTPS configurations simultaneously

---

## 15. Dark/Light Theme System (2026-05-27)

### Overview
Implemented a user-selectable theme system with two modes (dark and light) that persist to each user's account and sync across all devices and sessions. The dark theme is the default for new accounts.

### Design Goals
- **Default to dark:** New accounts start with dark theme (matches existing design)
- **Persistent:** Theme preference stored in database, applies across all logins
- **Pervasive:** Affects all UI elements (fonts, backgrounds, buttons, cards, borders)
- **Quick toggle:** Theme toggle icon (🌙/☀️) in topbar for friction-free switching
- **Maintainable:** CSS custom properties system for easy future color adjustments

### Architecture

**Database Layer:**
- User model already had `theme: str = Field(default="dark")` field
- No schema migration needed; field always existed

**Backend (API):**
- `PreferencesRequest` schema updated to include optional `theme` field
- `auth.py` validates theme ∈ {dark, light}, rejects invalid values with clear error
- `PATCH /auth/preferences` endpoint now handles theme updates alongside piece_set, board_theme, sounds_on
- Theme change returns full user object with updated theme

**Frontend (Styling):**
- `index.css` defines CSS custom properties:
  - `:root` (dark theme defaults): `--color-ink-900` through `--color-ink-100`, `--color-gold-*`
  - `html.light-theme` (light overrides): invert ink colors, adjust gold palette for light backgrounds
- `tailwind.config.ts` switched from hardcoded hex colors to `rgb(var(--color-ink-900))` pattern
- All color utilities now dynamically resolve at runtime

**Frontend (UI):**
- `App.tsx` exports `applyTheme(themeName)` function that toggles `light-theme` class on `<html>`
- RequireAuth hook watches `user.theme` and applies theme on login
- Theme class applied immediately on preference update

**Settings Page:**
- New "App theme" section above "Board appearance"
- Two buttons: Dark (ink background, gold accents) and Light (cream background, darker accents)
- Clicking a theme button updates local state, live-previews the theme
- "Save preferences" button sends theme to API
- Success message confirms save

**Topbar Enhancement:**
- Theme toggle button added between username and logout
- Icon displays 🌙 (moon) when dark, ☀️ (sun) when light
- Clicking toggles theme immediately and persists to database
- Button disabled during API call to prevent double-clicks
- Tooltip on hover shows which theme will be activated

### Implementation Details

**Color Palette (CSS Variables):**

**Dark Theme (default):**
```
--color-ink-900: 10 10 11    (near black)
--color-ink-800: 18 18 21    (dark charcoal)
--color-ink-700: 26 26 31    (charcoal)
--color-ink-600: 38 38 48    (dark grey)
--color-ink-500: 58 58 71    (grey)
--color-ink-400: 90 90 107   (medium grey)
--color-ink-300: 139 139 156 (light grey)
--color-ink-200: 196 196 208 (lighter grey)
--color-ink-100: 232 232 238 (off-white)

--color-gold-900: 58 44 8    (dark gold)
--color-gold-700: 122 91 20  (medium gold)
--color-gold-500: 199 154 45 (gold)
--color-gold-400: 212 175 68 (bright gold)
--color-gold-300: 229 196 102 (light gold)
--color-gold-200: 240 217 154 (very light gold)
```

**Light Theme:**
```
--color-ink-900: 245 245 247 (off-white background)
--color-ink-800: 255 255 255 (white)
--color-ink-700: 242 242 247 (very light grey)
--color-ink-600: 230 230 240 (light grey)
--color-ink-500: 200 200 215 (medium grey)
--color-ink-400: 120 120 140 (darker grey)
--color-ink-300: 100 100 120 (dark grey)
--color-ink-200: 60 60 80    (darker grey)
--color-ink-100: 20 20 30    (near black text)

--color-gold-900: 255 250 220 (light gold bg)
--color-gold-700: 220 180 80  (medium-dark gold)
--color-gold-500: 199 154 45  (standard gold)
--color-gold-400: 180 140 30  (darker gold)
--color-gold-300: 160 120 20  (dark gold)
--color-gold-200: 140 100 10  (very dark gold)
```

### Files Modified

1. **backend/routers/auth.py**
   - Added `_VALID_THEMES = {"dark", "light"}`
   - Updated `update_preferences()` to handle theme parameter and validation

2. **backend/schemas/auth.py**
   - Added `theme: Optional[str] = None` to PreferencesRequest

3. **frontend/src/index.css**
   - Added CSS custom property definitions for both dark and light themes
   - `:root` sets dark theme defaults
   - `html.light-theme` overrides for light mode

4. **frontend/tailwind.config.ts**
   - Changed all hardcoded colors to use `rgb(var(--color-*))`
   - Box shadow glow also uses CSS variables

5. **frontend/src/App.tsx**
   - Added `applyTheme()` function to toggle light-theme class
   - RequireAuth hook calls applyTheme on user load
   - useEffect watches user.theme and reapplies on change

6. **frontend/src/api/auth.ts**
   - Updated updatePreferences() signature to include theme parameter

7. **frontend/src/pages/Settings.tsx**
   - Added APP_THEMES constant with Dark/Light options
   - Added theme selector UI in "App theme" card
   - Integrated theme into savePreferences() mutation
   - Calls applyTheme() immediately on theme change

8. **frontend/src/components/layout/Topbar.tsx**
   - Imported useMutation, useQueryClient, authApi
   - Added applyTheme() function
   - Created updateTheme mutation for theme changes
   - Added theme toggle button with moon/sun icons
   - Button disabled during API call

### User Flow

1. **New User:** Registers → defaults to dark theme
2. **Switch to Light (Settings):**
   - Navigate to Settings
   - Click "Light" button in "App theme" section
   - See live preview of light theme
   - Click "Save preferences"
   - Success confirmation appears
   - Theme persists across refresh/logout/login
3. **Switch to Dark (Topbar):**
   - Click ☀️ icon in topbar (when in light mode)
   - Theme toggles to dark immediately
   - Preference saved automatically to database
4. **Cross-Device:** Log in on another device → theme automatically applies

### Testing & Verification

**API Tests:**
- ✅ New users default to dark theme
- ✅ Theme update via PATCH /auth/preferences
- ✅ Theme persists in database
- ✅ Invalid theme rejected with validation error

**Frontend Tests:**
- ✅ CSS variables properly defined
- ✅ Theme class applied to HTML element
- ✅ Settings UI with theme selector
- ✅ Topbar toggle icon (🌙/☀️) displays correctly
- ✅ Theme persists across page refreshes
- ✅ Theme applies on login via App.tsx

### Future Enhancements
- Auto-detect system theme preference (prefers-color-scheme) on first login
- Per-board theme override for color-blind accessibility
- More theme variants (sepia, high-contrast, etc.)
- Theme transition animations (smooth color fade)

### Commit
```
135644f feat: Add dark/light theme system with persistent user preferences
```

---

## 16. Docker Network Reliability Fix (2026-05-28)

### Problem

After running for ~15 hours on WSL2, all API calls began returning 504 Gateway Timeout. The app
showed a connectivity error that resembled a database failure. `manage.sh` reported all three
containers as running.

**Root cause:** NOT a database issue. Docker's iptables FORWARD rule for the `chessloop-net` bridge
network went missing. This rule (`-A FORWARD -i br-X -o br-X -j ACCEPT`) is added when the network
is created and is required for containers on the same bridge to communicate. It can be lost when:

- The Docker daemon restarts (WSL2 sleep/hibernate)
- WSL2's virtual network adapter resets
- The Docker service is cycled while containers remain "up" in the daemon state

**Diagnostic fingerprint:**
- `docker ps` shows all containers "Up" ✓
- Host can ping containers directly ✓
- Containers cannot ping each other — 100% packet loss ✗
- Nginx error logs: `upstream timed out (110: Operation timed out)` to correct backend IP
- Backend logs: no requests logged in 30+ minutes despite appearing "Up"

### Fix Applied

1. Stopped and removed all containers
2. Removed the stale `chessloop-net` network
3. Recreated network + containers — Docker re-adds the FORWARD rule on network creation
4. Database was safe throughout — stored in `chessloop-data` Docker volume, untouched

### Prevention

Added `--restart always` to all three `docker run` commands in `manage.sh`:
- When the Docker daemon restarts, it automatically restarts containers
- Container restart triggers Docker to re-add all iptables rules, self-healing the network
- Applied live to running containers via `docker update --restart always`

### Commit
```
fix: add --restart always to manage.sh to survive Docker daemon restarts on WSL2
```

---

## 18. Backup Upload & Recovery Feature (2026-05-28)

### Overview
Added the ability for admins to upload previously-downloaded backup files and restore the system from them. This completes the disaster recovery workflow: users can download backups for safekeeping and re-upload them to recover if needed.

### Implementation

**Backend — `chessloop/backend/routers/admin.py`**
- New endpoint: `POST /api/admin/backups/upload`
  - Accepts multipart form-data: `file` (SQLite .db), `name` (optional), `type` (full/content/progress)
  - Validates SQLite database magic bytes: `"SQLite format 3\x00"`
  - Saves uploaded file to backup directory with timestamped filename
  - Creates `Backup` record in database
  - Enforces 10-backup retention limit via `_prune()`
  - Returns 201 Created with full backup metadata
- **Critical fix**: Placed `/backups/upload` route BEFORE parameterized `/{backup_id}` routes
  - FastAPI matches routes in definition order
  - Without this ordering, `/backups/upload` matched `/{backup_id}` and returned 405 Method Not Allowed

**Frontend — `chessloop/frontend/src/pages/Admin.tsx`**
- New `adminApi.uploadBackup()` method
  - Builds FormData with file, name, type fields
  - Uses authenticated fetch with Bearer token + automatic refresh on 401
  - Reconstructs FormData on token refresh (FormData can't be reused)
- New UI in `BackupsSection`:
  - Collapsible "Upload backup file" panel below create backup
  - File input (accept=".db"), name/type fields, "Upload & Register" button
  - Shows file size preview
  - Error display and loading state
  - On success, invalidates backup list query to refresh display
- Newly uploaded backup appears in list and can be restored with existing ⟲ Restore button

### Testing & Verification
- ✅ Endpoint routing verified (returns 403 for non-admin, not 405)
- ✅ Multipart form-data parsing works correctly
- ✅ SQLite validation (magic bytes check) implemented
- ✅ Frontend UI renders and collects form data
- ✅ API method handles auth token refresh for uploads
- ✅ Integration with existing backup list and restore workflows

### Files Modified
- `backend/routers/admin.py` — 88-line endpoint + imports
- `frontend/src/pages/Admin.tsx` — upload UI + API method

---

## 17. Backup Download Authentication Fix (2026-05-28)

### Problem

Backup downloads silently failed. The browser opened the Save As dialog, then immediately showed
"File wasn't available on the site." The backup files existed on disk and the API was healthy.

**Root cause:** The download button was a plain `<a href="/api/admin/backups/{id}/download" download>`
anchor tag. Browser-native navigation to a URL never sends the `Authorization` header — only cookies
travel automatically. ChessLoop uses JWT bearer tokens (not cookies), so every download request
arrived at the backend unauthenticated. `require_admin` rejected it with 401, which the browser
surfaced as the "file unavailable" error after already opening the dialog.

### Fix

Replaced the anchor with a `<button>` that performs a programmatic `fetch()` with the full auth
flow (`frontend/src/pages/Admin.tsx`):

1. Reads the current access token from the Zustand auth store
2. `fetch()`es the download endpoint with `Authorization: Bearer <token>`
3. If the response is 401 (expired token), calls `/api/auth/refresh`, updates the store, and
   retries the download once with the new token
4. On success, reads the response as a `Blob`, creates a temporary object URL, programmatically
   clicks a hidden `<a download>` to trigger the browser Save As dialog, then revokes the URL
5. Shows "Downloading…" on the button while in-flight; disables it to prevent double-clicks

No backend changes were required — the endpoint already served the file correctly for authenticated
requests.

### Removed
- `downloadUrl` helper in `adminApi` (dead code — was only used as the `href` on the removed anchor)

### Commit
```
fix: use authenticated fetch for backup downloads instead of plain href
```

