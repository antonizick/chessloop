import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from database import init_db
from routers import auth, libraries, lines, games, practice, stats, public, admin


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

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)

    # Also write uvicorn access logs to the same file
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvlog = logging.getLogger(name)
        uvlog.addHandler(file_handler)


_setup_logging()

_FRONTEND_LOG_PATH = Path(settings.db_path).parent / "logs" / "frontend.log"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
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
    try:
        _FRONTEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.utcnow().isoformat()} [{entry.level.upper()}] {entry.message}"
        if entry.url:
            line += f" | url={entry.url}"
        if entry.stack:
            line += f"\n  {entry.stack}"
        with _FRONTEND_LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass
