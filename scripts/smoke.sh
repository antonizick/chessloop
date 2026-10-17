#!/usr/bin/env bash
# ChessLoop API smoke test. Run from the host against the VM IP, or inside the
# VM against localhost. Needs bash, curl and python3.
# Copy of lab/smoke.sh from the ChessLoop deployment-validation lab, used by
# the CI install smoke job (.github/workflows/ci.yml). Keep the two in step.
#
# Usage: lab/smoke.sh <base-url>        e.g. http://10.77.0.90:8080
# Env:
#   SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD  admin login      [none: step skipped unless both are set]
#   SMOKE_USER_PASSWORD   password for the throwaway user      [random]
#   MAILPIT_API           Mailpit base URL                     [http://10.77.0.2:8025]
#   SMOKE_RESTART_CMD     command that restarts the containers (enables the persistence step)
#
# Output: one line per step ("PASS", "FAIL", "SKIP" or "FAIL (expected: Hn)"),
# then a JSON summary on the last line. A step that fails for a reason already in
# docs/FINDINGS.md is labelled with that H-number and does NOT abort the run.
# Exit: 0 = no unexpected failures, 1 = at least one unexpected FAIL,
#       2 = bad usage, 3 = only expected failures.
set -uo pipefail

BASE="${1:-}"; BASE="${BASE%/}"
[[ -n "$BASE" ]] || { echo "usage: smoke.sh <base-url>" >&2; exit 2; }
MAILPIT_API="${MAILPIT_API:-http://10.77.0.2:8025}"
ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-}"
ADMIN_PW="${SMOKE_ADMIN_PASSWORD:-}"
RAND="$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
USER_EMAIL="smoke-${RAND}@example.com"
USER_NAME="smoke${RAND}"
USER_PW="${SMOKE_USER_PASSWORD:-Smoke-${RAND}-pw}"

BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
CODE=0
RESULTS=()      # "name|status|note"
UNEXPECTED=0; EXPECTED=0
TOKEN=""        # token used for the library/practice steps
USER_TOKEN=""; ADMIN_TOKEN=""
LIB_ID=""; LINE_ID=""; SESSION_ID=""

# req METHOD PATH [JSON] [TOKEN] : sets CODE and BODY
req() {
  local m="$1" p="$2" d="${3:-}" t="${4:-}"
  local args=(-s -o "$BODY" -w '%{http_code}' -m 30 -X "$m")
  [[ -n "$d" ]] && args+=(-H 'Content-Type: application/json' -d "$d")
  [[ -n "$t" ]] && args+=(-H "Authorization: Bearer $t")
  CODE="$(curl "${args[@]}" "$BASE$p" 2>/dev/null)" || CODE=000
}
# jget EXPR : evaluate a Python expression against the parsed response (d)
jget() { python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$BODY" "$1" 2>/dev/null; }
detail() { head -c 160 "$BODY" | tr '\n' ' '; }

# record NAME STATUS [EXPECTED-H] [NOTE]
record() {
  local name="$1" st="$2" h="${3:-}" note="${4:-}" label="$2"
  if [[ "$st" == FAIL ]]; then
    if [[ -n "$h" ]]; then label="FAIL (expected: $h)"; EXPECTED=$((EXPECTED + 1)); else UNEXPECTED=$((UNEXPECTED + 1)); fi
  fi
  printf '%-22s %s%s\n' "$name" "$label" "${note:+  # $note}"
  RESULTS+=("$name|$label|$note")
}

# ── steps ────────────────────────────────────────────────────────────────────
step_health() {
  req GET /api/health
  if [[ "$CODE" == 200 && "$(jget "d.get('status')")" == ok ]]; then record health PASS
  else record health FAIL "" "HTTP $CODE $(detail)"; fi
}

step_admin_login() {
  if [[ -z "$ADMIN_PW" || -z "$ADMIN_EMAIL" ]]; then record admin_login SKIP "" "SMOKE_ADMIN_EMAIL/PASSWORD not set"; return; fi
  req POST /api/auth/login "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PW\"}"
  if [[ "$CODE" == 200 ]]; then
    ADMIN_TOKEN="$(jget "d['access_token']")"
    req GET /api/auth/me "" "$ADMIN_TOKEN"
    if [[ "$(jget "d.get('role')")" == admin ]]; then record admin_login PASS; else record admin_login FAIL "" "logged in but role is not admin"; fi
  elif [[ "$CODE" == 403 ]]; then record admin_login FAIL H1 "HTTP 403 $(detail)"
  else record admin_login FAIL "" "HTTP $CODE $(detail)"; fi
}

step_register() {
  req POST /api/auth/register "{\"email\":\"$USER_EMAIL\",\"username\":\"$USER_NAME\",\"password\":\"$USER_PW\"}"
  if [[ "$CODE" == 201 ]]; then record register PASS
  elif [[ "$CODE" == 422 ]]; then record register FAIL H9 "HTTP 422 $(detail)"; REGISTERED=0
  else record register FAIL "" "HTTP $CODE $(detail)"; REGISTERED=0; fi
}

step_verify_email() {
  [[ "${REGISTERED:-1}" == 0 ]] && { record verify_email SKIP "" "registration failed"; return; }
  # Try a login first: if verification is not enforced the user can log in at once.
  req POST /api/auth/login "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PW\"}"
  if [[ "$CODE" == 200 ]]; then record verify_email PASS "" "verification not enforced"; USER_TOKEN="$(jget "d['access_token']")"; return; fi
  local msg_id="" tok=""
  for _ in 1 2 3 4 5 6; do
    msg_id="$(curl -s -m 10 "$MAILPIT_API/api/v1/search?query=to:${USER_EMAIL}" | python3 -I -c 'import json,sys; m=json.load(sys.stdin).get("messages") or []; print(m[0]["ID"] if m else "")' 2>/dev/null)"
    [[ -n "$msg_id" ]] && break
    sleep 2
  done
  if [[ -z "$msg_id" ]]; then record verify_email FAIL H3 "no verification email reached Mailpit; login was HTTP $CODE"; return; fi
  tok="$(curl -s -m 10 "$MAILPIT_API/api/v1/message/$msg_id" | python3 -I -c 'import json,re,sys; t=json.load(sys.stdin).get("Text",""); m=re.search(r"token=([^\s]+)", t); print(m.group(1) if m else "")')"
  [[ -n "$tok" ]] || { record verify_email FAIL "" "email has no token link"; return; }
  req POST /api/auth/verify-email "{\"token\":\"$tok\"}"
  if [[ "$CODE" == 200 ]]; then USER_TOKEN="$(jget "d['access_token']")"; record verify_email PASS
  else record verify_email FAIL "" "HTTP $CODE $(detail)"; fi
}

step_user_login() {
  [[ "${REGISTERED:-1}" == 0 ]] && { record user_login SKIP "" "registration failed"; return; }
  req POST /api/auth/login "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PW\"}"
  if [[ "$CODE" == 200 ]]; then USER_TOKEN="$(jget "d['access_token']")"; record user_login PASS
  elif [[ "$CODE" == 403 ]]; then record user_login FAIL H3 "HTTP 403 $(detail)"
  else record user_login FAIL "" "HTTP $CODE $(detail)"; fi
}

# Change the throwaway user's password, then check that the old refresh token
# and the old password stop working and the new password works (Phase 06).
step_change_password() {
  [[ -n "$USER_TOKEN" ]] || { record change_password SKIP "" "no user login"; return; }
  local new_pw="Changed-${RAND}-pw" old_refresh
  req POST /api/auth/login "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PW\"}"
  old_refresh="$(jget "d['refresh_token']")"
  req POST /api/auth/change-password "{\"current_password\":\"$USER_PW\",\"new_password\":\"$new_pw\"}" "$USER_TOKEN"
  if [[ "$CODE" == 404 ]]; then record change_password FAIL H2 "no change-password endpoint"; return; fi
  [[ "$CODE" == 200 ]] || { record change_password FAIL "" "HTTP $CODE $(detail)"; return; }
  USER_TOKEN="$(jget "d['access_token']")"
  req POST /api/auth/refresh "{\"refresh_token\":\"$old_refresh\"}"; local refresh_code="$CODE"
  req POST /api/auth/login "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PW\"}"; local old_code="$CODE"
  req POST /api/auth/login "{\"email\":\"$USER_EMAIL\",\"password\":\"$new_pw\"}"; local new_code="$CODE"
  if [[ "$refresh_code" == 401 && "$old_code" == 401 && "$new_code" == 200 ]]; then
    USER_PW="$new_pw"; USER_TOKEN="$(jget "d['access_token']")"
    record change_password PASS "" "old refresh token and old password rejected"
  else
    record change_password FAIL "" "old refresh $refresh_code (want 401), old pw $old_code (401), new pw $new_code (200)"
  fi
}

pick_token() {
  TOKEN="${USER_TOKEN:-$ADMIN_TOKEN}"
  [[ -n "$TOKEN" ]] || return 1
  [[ -z "$USER_TOKEN" ]] && echo "note: using the admin token for library/practice steps" >&2
  return 0
}

step_create_library() {
  req POST /api/libraries '{"name":"Smoke Test Library","color":"white","description":"created by lab/smoke.sh"}' "$TOKEN"
  if [[ "$CODE" == 201 ]]; then LIB_ID="$(jget "d['id']")"; record create_library PASS
  else record create_library FAIL "" "HTTP $CODE $(detail)"; fi
}

step_add_line() {
  [[ -n "$LIB_ID" ]] || { record add_line SKIP "" "no library"; return; }
  req POST "/api/libraries/$LIB_ID/lines" '{"name":"Smoke line"}' "$TOKEN"
  [[ "$CODE" == 201 ]] || { record add_line FAIL "" "create line HTTP $CODE $(detail)"; return; }
  LINE_ID="$(jget "d['id']")"
  local san
  for san in e4 e5 Nf3 Nc6; do
    req POST "/api/lines/$LINE_ID/moves" "{\"san\":\"$san\"}" "$TOKEN"
    [[ "$CODE" == 200 ]] || { record add_line FAIL "" "move $san HTTP $CODE $(detail)"; LINE_ID=""; return; }
  done
  if [[ "$(jget "len(d['moves'])")" == 4 ]]; then record add_line PASS "" "4 moves"
  else record add_line FAIL "" "expected 4 moves"; LINE_ID=""; fi
}

step_practice() {
  [[ -n "$LINE_ID" ]] || { record practice SKIP "" "no line"; return; }
  req POST /api/practice/session/start "{\"mode\":\"selected\",\"scope\":{\"library_ids\":[\"$LIB_ID\"]},\"is_rated\":true}" "$TOKEN"
  [[ "$CODE" == 200 ]] || { record practice FAIL "" "start HTTP $CODE $(detail)"; return; }
  SESSION_ID="$(jget "d['id']")"
  req GET "/api/practice/session/$SESSION_ID/next" "" "$TOKEN"
  [[ "$CODE" == 200 ]] || { record practice FAIL "" "next HTTP $CODE $(detail)"; return; }
  local pos uci
  pos="$(jget "d.get('practice_position_id','')")"; uci="$(jget "d['remaining_moves'][0]['uci'] if d.get('remaining_moves') else ''")"
  [[ -n "$pos" && -n "$uci" ]] || { record practice FAIL "" "no position returned: $(detail)"; return; }
  req POST "/api/practice/session/$SESSION_ID/answer" "{\"practice_position_id\":\"$pos\",\"move_uci\":\"$uci\"}" "$TOKEN"
  if [[ "$CODE" == 200 && "$(jget "d.get('correct')")" == True ]]; then record practice PASS "" "answered $uci"
  else record practice FAIL "" "answer HTTP $CODE $(detail)"; fi
  req POST "/api/practice/session/$SESSION_ID/end" "" "$TOKEN"
}

step_stats() {
  [[ -n "$SESSION_ID" ]] || { record stats SKIP "" "no session"; return; }
  req GET /api/stats/mastery "" "$TOKEN"; local a="$CODE"
  req GET /api/practice/due-count "" "$TOKEN"
  if [[ "$a" == 200 && "$CODE" == 200 ]]; then record stats PASS; else record stats FAIL "" "mastery $a, due-count $CODE"; fi
}

step_persist() {
  if [[ -z "${SMOKE_RESTART_CMD:-}" ]]; then record persistence SKIP "" "SMOKE_RESTART_CMD not set"; return; fi
  [[ -n "$LIB_ID" ]] || { record persistence SKIP "" "no library"; return; }
  if ! bash -c "$SMOKE_RESTART_CMD" >/dev/null 2>&1; then record persistence FAIL "" "restart command failed"; return; fi
  for _ in $(seq 1 30); do req GET /api/health; [[ "$CODE" == 200 ]] && break; sleep 2; done
  req GET /api/libraries "" "$TOKEN"
  if [[ "$CODE" == 200 && "$(jget "any(x['id']=='$LIB_ID' for x in d)")" == True ]]; then record persistence PASS
  else record persistence FAIL "" "library missing after restart: HTTP $CODE $(detail)"; fi
}

# ── run ──────────────────────────────────────────────────────────────────────
step_health
step_admin_login
step_register
step_verify_email
step_user_login
step_change_password
if pick_token; then
  step_create_library; step_add_line; step_practice; step_stats; step_persist
else
  for s in create_library add_line practice stats persistence; do record "$s" SKIP "" "no usable login"; done
fi

python3 -I - "$BASE" "$UNEXPECTED" "$EXPECTED" "${RESULTS[@]}" <<'PY'
import json, sys
base, unexpected, expected, *rows = sys.argv[1:]
steps = [dict(zip(("step", "result", "note"), r.split("|", 2))) for r in rows]
print(json.dumps({"base_url": base, "unexpected_failures": int(unexpected),
                  "expected_failures": int(expected), "steps": steps}))
PY

if ((UNEXPECTED > 0)); then exit 1; fi
if ((EXPECTED > 0)); then exit 3; fi
exit 0
