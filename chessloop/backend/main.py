import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from auth.policy import RateLimiter, client_ip
from database import init_db
from services import backup_service
from routers import auth, libraries, lines, games, practice, stats, public, admin, new_user_popup, banner


def _setup_logging() -> None:
    log_dir = Path(settings.db_path).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "backend.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    # stderr too, so app warnings (e.g. "SMTP not configured") reach `docker compose logs`.
    # uvicorn's own loggers don't propagate to root, so nothing is printed twice.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Also write uvicorn access logs to the same file
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvlog = logging.getLogger(name)
        uvlog.addHandler(file_handler)


_setup_logging()

_FRONTEND_LOG_PATH = Path(settings.db_path).parent / "logs" / "frontend.log"

# POST /api/logs/client needs no sign-in (errors happen before it too), so
# whatever reaches the file is capped: field lengths, entries per browser
# address per minute, and the file size (rotated, 2 old files kept).
_CLIENT_LOG_LIMITS = {"level": 16, "message": 2000, "stack": 8000, "url": 500}
CLIENT_LOG_RATE = RateLimiter(max_events=30, window_seconds=60)
_frontend_log: logging.Logger | None = None


def _frontend_logger() -> logging.Logger:
    global _frontend_log
    if _frontend_log is None:
        _FRONTEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            _FRONTEND_LOG_PATH, maxBytes=1024 * 1024, backupCount=2
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        log = logging.getLogger("chessloop.frontend")
        log.propagate = False
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        _frontend_log = log
    return _frontend_log


def _one_line(value: str, limit: int) -> str:
    # A browser could send newlines to forge extra log lines; keep one line each.
    text = "".join(ch if ch.isprintable() else " " for ch in value)
    return text[:limit] + ("…" if len(text) > limit else "")


def _log_email_setup() -> None:
    log = logging.getLogger("chessloop.startup")
    if settings.smtp_configured:
        log.info("Email: SMTP server %s:%s configured", settings.smtp_host, settings.smtp_port)
    else:
        log.info("Email: SMTP not configured; ChessLoop will not send any email")
    if settings.email_verification == "on" and not settings.smtp_configured:
        log.warning(
            "EMAIL_VERIFICATION=on but SMTP is not configured: new accounts cannot verify "
            "and must be verified by an admin (Admin → Users)"
        )


def _log_cors_setup() -> None:
    if settings.cors_wildcard_ignored:
        logging.getLogger("chessloop.startup").warning(
            "CORS_ORIGINS=* is ignored: the web UI does not need it. "
            "List exact origins (https://example.org) only if another site must call the API"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    backup_service.secure_backup_dir()
    _log_email_setup()
    _log_cors_setup()
    yield


app = FastAPI(
    title="ChessLoop API",
    version="0.1.0",
    description="Self-hosted, move-based spaced-repetition chess opening trainer.",
    lifespan=lifespan,
)

cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(libraries.router, prefix="/api")
app.include_router(lines.router, prefix="/api")
app.include_router(games.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(public.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(new_user_popup.router, prefix="/api")
app.include_router(banner.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


class ClientLogEntry(BaseModel):
    level: str = "error"
    message: str
    stack: str | None = None
    url: str | None = None


@app.post("/api/logs/client", status_code=204)
async def receive_client_log(entry: ClientLogEntry, request: Request):
    ip = client_ip(request)
    if CLIENT_LOG_RATE.blocked(ip):
        return
    CLIENT_LOG_RATE.hit(ip)
    try:
        lim = _CLIENT_LOG_LIMITS
        line = (
            f"{datetime.utcnow().isoformat()} [{_one_line(entry.level, lim['level']).upper()}] "
            f"{_one_line(entry.message, lim['message'])}"
        )
        if entry.url:
            line += f" | url={_one_line(entry.url, lim['url'])}"
        if entry.stack:
            stack = entry.stack[: lim["stack"]]
            line += "".join(f"\n  {_one_line(s, lim['stack'])}" for s in stack.splitlines())
        _frontend_logger().info(line)
    except Exception:
        pass
