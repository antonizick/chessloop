from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "chessloop.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_prefix = "CHESSLOOP_"
        env_file = ".env"
        extra = "ignore"  # ignore unknown env vars (e.g. LICHESS_API_TOKEN)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
