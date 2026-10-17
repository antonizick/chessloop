# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from its first release.

History before this changelog: see `git log`.

## [Unreleased]

### Added
- `LICENSE` (GNU AGPL-3.0-or-later), `NOTICE` and `THIRD_PARTY_NOTICES.md`.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) and this changelog.
- GitHub issue templates (install problem, bug report, feature request), a pull request template and Dependabot configuration.
- `.editorconfig` and `.gitattributes` (LF line endings, so scripts work when cloned on Windows for WSL).
- GitHub Actions CI (`.github/workflows/ci.yml`) on pushes to `main` and pull requests: backend tests, frontend type check and build, ShellCheck (advisory for now), Compose file validation, Docker image builds and a gitleaks secret scan. Actions and scanner images are pinned by SHA or digest.
- `scripts/ci-local.sh` runs the same checks locally in Docker, and `.gitleaks.toml` configures the secret scan.
- CI status badge in the README.
- `VITE_ALLOWED_HOSTS` environment variable for the Vite dev server's allowed hostnames.

### Changed
- Vite dev server no longer has a hard-coded personal hostname; it accepts `localhost,127.0.0.1` unless `VITE_ALLOWED_HOSTS` is set.
- `planning.md` moved to `docs/history/planning.md`.
- `.gitignore` now also ignores `*.db*`, `*.tsbuildinfo`, `passdata/`, `backups/`, `runs/` and `*.tar.gz`.

### Removed
- Developer-only and personal files: root `CLAUDE.md`, the committed `chessloop.db`, `passdata/`, `scripts/` (one-off maintenance scripts with personal paths and a compiled `__pycache__`), and `chessloop/frontend/tsconfig.tsbuildinfo`.
