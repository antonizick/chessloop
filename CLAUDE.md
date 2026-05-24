# CLAUDE.md — ChessLoop

---

## Project Mode (lightweight Lucent context)

You are working on **ChessLoop**, a project under Nick's `idea/` folder.
Full Lucent identity, LTMemory, and reminders are **not** loaded in this mode —
that context only attaches when Claude is launched from `/home/nick/dev/lucent`.

You still owe Nick the two non-negotiable behaviors:

### 1. Voice box — every response

```
curl -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "your message"}'
```

Send voice **before** text. Brief, conversational. Same message in voice and text.

### 2. Daily note — every response

Append to `/home/nick/dev/lucent/memory/YYYY-MM-DD.md` (today's date).
Log substantive work only: decisions, progress, blockers. Not transcripts.

Format:

```
## [HH:MM] Short headline
- What you did
- Decisions made
- Next step (if any)
```

### 3. Text — respond in Claude Code

Same content as the voice message (or expanded with detail).

---

## Project context

- **Planning doc:** `idea/ChessLoop/planning.md`
- **Working dir:** this directory and below
- **Stay in scope:** do not modify `/home/nick/dev/lucent/memory/` (other than the daily note)
  or other `idea/<project>/` directories unless explicitly asked.

## What's NOT loaded in this mode

- Lucent identity files (`lucentIdent.md`, `userIdent.md`)
- Long-term memory (`LTMemory.md`)
- Active reminders
- Priority email alerts
- Daily note tail (you'll read it directly when needed)

If you need any of the above, switch back: `cd /home/nick/dev/lucent && claude`.
