from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "chessloop.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    cors_origins: str = "http://localhost:8090,http://localhost:5173"
    frontend_url: str = "http://localhost:8090"
    email_mx_check: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "ChessLoop <no-reply@chessloop.local>"
    smtp_use_tls: bool = True

    class Config:
        env_prefix = "CHESSLOOP_"
        env_file = ".env"
        extra = "ignore"  # ignore unknown env vars (e.g. LICHESS_API_TOKEN)

    @property
    def cors_origin_list(self) -> list[str]:
        origins = self.cors_origins.strip()
        if origins == "*":
            return ["*"]
        return [o.strip() for o in origins.split(",") if o.strip()]


settings = Settings()
