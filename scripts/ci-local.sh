#!/usr/bin/env bash
# Run the same checks as .github/workflows/ci.yml on your own machine.
# Needs Docker (everything runs in containers, so your local Python and Node
# versions don't matter). Usage: scripts/ci-local.sh [step ...]
# Steps: backend frontend shell helpers compose images secrets   (default: all)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$PWD

# Keep these in step with the workflow.
PYTHON_IMAGE=python:3.12.15-slim-trixie  # same as chessloop/backend/Dockerfile
NODE_IMAGE=node:24-alpine
SHELLCHECK_IMAGE=koalaman/shellcheck@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
GITLEAKS_IMAGE=zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

command -v docker >/dev/null 2>&1 || { echo "Docker is required." >&2; exit 1; }

# Containers run as you, so they never leave root-owned files in the repo.
USER_ARGS=(-u "$(id -u):$(id -g)" -e HOME=/tmp)

step_backend() {
  docker run --rm "${USER_ARGS[@]}" \
    -e PYTHONDONTWRITEBYTECODE=1 -e CHESSLOOP_EMAIL_MX_CHECK=false \
    -v "$ROOT/chessloop/backend:/app" -w /app "$PYTHON_IMAGE" \
    sh -c 'pip install -q --user --disable-pip-version-check -r requirements.txt pytest && python -m pytest -q -p no:cacheprovider'
}

step_frontend() {
  # Work on a copy so node_modules and dist don't land in your checkout.
  local tmp
  tmp=$(mktemp -d)
  cp -r "$ROOT/chessloop/frontend/." "$tmp/"
  docker run --rm "${USER_ARGS[@]}" -v "$tmp:/app" -w /app "$NODE_IMAGE" \
    sh -c 'npm ci --no-audit --no-fund && npm run lint && npm run build'
  local rc=$?
  rm -rf "$tmp"
  return "$rc"
}

step_shell() {
  local files=(deploy.sh manage.sh)
  local f
  for f in scripts/*.sh; do [[ -e $f ]] && files+=("$f"); done
  docker run --rm -v "$ROOT:/mnt" -w /mnt "$SHELLCHECK_IMAGE" "${files[@]}"
}

step_helpers() {
  # deploy.sh's helper functions (no Docker needed, except one .env read-back check)
  bash scripts/test-deploy-helpers.sh
}

step_compose() {
  JWT_SECRET=ci-dummy-not-a-secret docker compose -f chessloop/docker-compose.prod.yml config -q
  JWT_SECRET=ci-dummy-not-a-secret docker compose -f chessloop/docker-compose.yml config -q
}

step_images() {
  docker build -q -t chessloop-ci-backend chessloop/backend >/dev/null
  docker build -q -t chessloop-ci-frontend chessloop/frontend >/dev/null
  docker build -q -t chessloop-ci-nginx chessloop/nginx >/dev/null
}

step_secrets() {
  # A git worktree's .git is a pointer file, so scan the real repository dir.
  local gitdir src=$ROOT
  gitdir=$(git rev-parse --git-common-dir)
  [[ -d $gitdir/../.git ]] && src=$(cd "$gitdir/.." && pwd)
  docker run --rm -v "$src:/repo" -v "$ROOT/.gitleaks.toml:/gitleaks.toml:ro" "$GITLEAKS_IMAGE" \
    detect --source /repo --config /gitleaks.toml --redact --no-banner
}

ADVISORY=" shell "   # failing here is reported but doesn't fail the run (see ci.yml)
steps=("$@")
[[ ${#steps[@]} -gt 0 ]] || steps=(backend frontend shell helpers compose images secrets)

failed=()
advisory_failed=()
summary=()
for s in "${steps[@]}"; do
  echo "=== $s ==="
  start=$SECONDS
  if "step_$s"; then
    summary+=("PASS  $s ($((SECONDS - start))s)")
  elif [[ $ADVISORY == *" $s "* ]]; then
    summary+=("WARN  $s (advisory, $((SECONDS - start))s)")
    advisory_failed+=("$s")
  else
    summary+=("FAIL  $s ($((SECONDS - start))s)")
    failed+=("$s")
  fi
done

echo
echo "=== Summary ==="
printf '%s\n' "${summary[@]}"
[[ ${#failed[@]} -eq 0 ]]
