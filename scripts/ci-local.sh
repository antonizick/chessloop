#!/usr/bin/env bash
# Run the same checks as .github/workflows/ci.yml on your own machine.
# Needs Docker (everything runs in containers, so your local Python and Node
# versions don't matter). Usage: scripts/ci-local.sh [step ...]
# Steps: backend frontend shell helpers compose dockerfiles images scan audit docs secrets
#        (default: all; scan needs images first)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$PWD

# Keep these in step with the workflow.
PYTHON_IMAGE=python:3.12.15-slim-trixie  # same as chessloop/backend/Dockerfile
NODE_IMAGE=node:24-alpine
SHELLCHECK_IMAGE=koalaman/shellcheck@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
GITLEAKS_IMAGE=zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
HADOLINT_IMAGE=hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d  # v2.15.1
TRIVY_IMAGE=aquasec/trivy@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa  # v0.75.0
PIP_AUDIT_VERSION=2.10.1

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
  local files=(deploy.sh)
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

step_dockerfiles() {
  local f
  for f in chessloop/backend/Dockerfile chessloop/frontend/Dockerfile chessloop/nginx/Dockerfile; do
    docker run --rm -i "$HADOLINT_IMAGE" hadolint - < "$f" || return 1
  done
}

step_scan() {
  # Trivy's database is cached in a Docker volume between runs.
  local i
  for i in backend frontend nginx; do
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v chessloop-ci-trivy:/root/.cache \
      "$TRIVY_IMAGE" image --quiet --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed \
      --exit-code 1 "chessloop-ci-$i" || return 1
  done
}

step_audit() {
  docker run --rm "${USER_ARGS[@]}" -v "$ROOT/chessloop/backend:/app:ro" -w /app "$PYTHON_IMAGE" \
    sh -c "pip install -q --user --disable-pip-version-check pip-audit==$PIP_AUDIT_VERSION && python -m pip_audit -r requirements.txt --progress-spinner off" \
    || return 1
  # npm audit is advisory (see ci.yml): shown, never fails this step.
  local tmp
  tmp=$(mktemp -d)
  cp "$ROOT/chessloop/frontend/package.json" "$ROOT/chessloop/frontend/package-lock.json" "$tmp/"
  docker run --rm "${USER_ARGS[@]}" -v "$tmp:/app" -w /app "$NODE_IMAGE" npm audit --omit=dev || true
  rm -rf "$tmp"
}

step_docs() {
  python3 scripts/check-doc-links.py
}

step_secrets() {
  # A git worktree's .git is a pointer file, so scan the real repository dir.
  local gitdir src=$ROOT
  gitdir=$(git rev-parse --git-common-dir)
  [[ -d $gitdir/../.git ]] && src=$(cd "$gitdir/.." && pwd)
  docker run --rm -v "$src:/repo" -v "$ROOT/.gitleaks.toml:/gitleaks.toml:ro" "$GITLEAKS_IMAGE" \
    detect --source /repo --config /gitleaks.toml --redact --no-banner
}

ADVISORY=" "   # steps listed here are reported but don't fail the run (none since Phase 12)
steps=("$@")
[[ ${#steps[@]} -gt 0 ]] || steps=(backend frontend shell helpers compose dockerfiles images scan audit docs secrets)

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
