from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routers import auth, libraries, lines, practice, stats, public


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(libraries.router, prefix="/api")
app.include_router(lines.router, prefix="/api")
app.include_router(practice.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(public.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
