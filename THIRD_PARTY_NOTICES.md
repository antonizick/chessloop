# Third-Party Notices

ChessLoop is licensed under AGPL-3.0-or-later (see `LICENSE`). It depends on the open-source components below. This file lists **direct** dependencies; each component keeps its own licence and copyright. Licence names come from package metadata (`pip-licenses` 3.12 environment, and the `license` fields in `chessloop/frontend/package-lock.json`) and were checked on 2026-10-16. Regenerate it when dependencies change.

## Compatibility summary

- Every direct dependency is under a licence that is compatible with AGPL-3.0-or-later (MIT, BSD, Apache-2.0, ISC, MPL-2.0, Unlicense, GPL-3.0-or-later). No incompatible licence was found.
- **GPL-3.0-or-later components:** `chess` (python-chess, backend) and `chessground` (frontend, whose `chessground.cburnett.css` embeds the default "cburnett" piece artwork by Colin M.L. Burnett, which the Lichess project lists as GPL-2.0-or-later; see <https://github.com/lichess-org/lila/blob/master/COPYING.md>). GPL-3.0 can be combined with AGPL-3.0 (GPLv3 section 13); the combined work is distributed under the AGPL terms.
- **MPL-2.0:** `certifi` (transitive) and `dompurify` (dual-licensed MPL-2.0 OR Apache-2.0; ChessLoop uses it under Apache-2.0). MPL obligations apply only to modified MPL files, which ChessLoop does not modify.
- Build-time only: the `caniuse-lite` data package (CC-BY-4.0, pulled in by autoprefixer) is not shipped in the runtime image.

## Backend (Python): `chessloop/backend/requirements.txt`

| Package | Version | Licence | Use |
|---|---|---|---|
| fastapi | 0.142.2 | MIT | Web framework |
| starlette | 1.7.0 | BSD-3-Clause | ASGI toolkit under FastAPI (pinned for security fixes) |
| uvicorn | 0.32.1 | BSD | ASGI server |
| sqlmodel | 0.0.22 | MIT | ORM / models |
| pydantic | 2.10.3 | MIT | Data validation |
| pydantic-settings | 2.7.0 | MIT | Settings loading |
| email_validator | 2.2.0 | Unlicense | Email address validation |
| PyJWT | 2.15.1 | MIT | JWT signing |
| passlib | 1.7.4 | BSD | Password hashing API |
| bcrypt | 4.0.1 | Apache-2.0 | Password hashing |
| pyotp | 2.9.0 | MIT | TOTP two-factor codes |
| qrcode | 8.0 | BSD-3-Clause | QR codes for MFA setup |
| httpx | 0.28.1 | BSD | HTTP client (Lichess, email) |
| chess | 1.10.0 | GPL-3.0-or-later | Move validation, PGN/FEN (python-chess) |
| python-multipart | 0.0.32 | Apache-2.0 | Form/file uploads |
| python-dotenv | 1.2.2 | BSD-3-Clause | `.env` loading |

Transitive Python packages installed with them (version resolved 2026-10-18, licence from metadata) are: annotated-doc (MIT), annotated-types (MIT), anyio (MIT), certifi (Mozilla Public License 2.0 (MPL 2.0)), click (BSD-3-Clause), dnspython (ISC), greenlet (MIT AND PSF-2.0), h11 (MIT), httpcore (BSD-3-Clause), httptools (MIT), idna (BSD-3-Clause), opentelemetry-api (Apache-2.0), pillow (MIT-CMU), pydantic_core (MIT), PyYAML (MIT), SQLAlchemy (MIT), typing-inspection (MIT), typing_extensions (PSF-2.0), uvloop (Apache Software License; MIT), watchfiles (MIT), websockets (BSD-3-Clause).

Note: `qrcode` metadata also carries a stray "Other/Proprietary" classifier; its `LICENSE` file is the 3-clause BSD text (checked 2026-10-16), so it is listed as BSD-3-Clause. Where this table says plain `BSD`, the package metadata does not name the clause count.

## Frontend (npm): `chessloop/frontend/package-lock.json`

### Runtime dependencies

| Package | Version | Licence | Use |
|---|---|---|---|
| @tanstack/react-query | 5.100.14 | MIT | Server-state fetching/cache |
| chess.js | 1.4.0 | BSD-2-Clause | Client-side move logic |
| chessground | 9.2.1 | GPL-3.0-or-later | Chess board UI (and the cburnett piece artwork) |
| dompurify | 3.4.17 | (MPL-2.0 OR Apache-2.0) | HTML sanitising |
| marked | 18.0.7 | MIT | Markdown rendering |
| react | 18.3.1 | MIT | UI library |
| react-dom | 18.3.1 | MIT | UI library |
| react-router-dom | 6.30.6 | MIT | Routing |
| zustand | 5.0.13 | MIT | State store |

### Build-time development dependencies (not shipped in the runtime image)

| Package | Version | Licence |
|---|---|---|
| @types/dompurify | 3.0.5 | MIT |
| @types/react | 18.3.29 | MIT |
| @types/react-dom | 18.3.7 | MIT |
| @vitejs/plugin-react | 4.7.0 | MIT |
| autoprefixer | 10.5.0 | MIT |
| postcss | 8.5.15 | MIT |
| tailwindcss | 3.4.19 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| vite | 6.4.2 | MIT |

The remaining ~170 transitive npm packages are listed with their licences in `package-lock.json` (MIT, ISC, Apache-2.0, BSD and CC-BY-4.0 data only).

## Data

- **Lichess chess-openings** (<https://github.com/lichess-org/chess-openings>): opening names/moves fetched at runtime by the admin import. Released under CC0 1.0 (public domain dedication) per the repository README. Not bundled.
- **Lichess Explorer API** (<https://explorer.lichess.org>): queried by the optional seed script, and by the development-only `scripts/build-starter-lines.py`, which uses move popularity from the Lichess game database (CC0 1.0, <https://database.lichess.org>) to choose how each hand-written starter line continues. The result is bundled as `chessloop/backend/services/starter_data.json` (move lists and line names written for ChessLoop; no Lichess text or dataset is copied). The product itself never calls Lichess for this. Explorer use is subject to Lichess terms of use.

## Container base images

| Image | Used in | Licence (summary) |
|---|---|---|
| `python:3.12.15-slim-trixie` | backend Dockerfile | Debian packages (various, mostly GPL/LGPL/BSD) and Python (PSF-2.0) |
| `node:24-alpine` | frontend build stage (not shipped) | Node.js (MIT) on Alpine Linux (various) |
| `nginx:1.30-alpine` | frontend and reverse proxy (`nginx/Dockerfile`) | nginx (BSD-2-Clause) on Alpine Linux (various) |

Base images contain many packages under their own licences; see each image's documentation on Docker Hub.
