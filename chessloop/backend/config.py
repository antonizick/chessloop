from typing import Literal, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "chessloop.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    cors_origins: str = "http://localhost:8090,http://localhost:5173"
    frontend_url: str = "http://localhost:8090"
    # auto: verification is required only when SMTP is configured (there is a way
    # to deliver the link); on/off force it. An admin's choice in Admin → System
    # settings (a system_settings row) overrides this.
    email_verification: Literal["auto", "on", "off"] = "auto"
    # Live MX lookup at registration. Off by default: it fails on offline/LAN-only
    # hosts and adds nothing when nobody is going to be emailed.
    email_mx_check: bool = False

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "ChessLoop <no-reply@chessloop.local>"
    smtp_use_tls: bool = True

    class Config:
        env_prefix = "CHESSLOOP_"
        env_file = ".env"
        extra = "ignore"

    @field_validator("email_verification", mode="before")
    @classmethod
    def _normalise_mode(cls, v):
        # "EMAIL_VERIFICATION=" (blank in .env) means the default, not a crash
        return (v.strip().lower() or "auto") if isinstance(v, str) else v

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        origins = self.cors_origins.strip()
        if origins == "*":
            return ["*"]
        return [o.strip() for o in origins.split(",") if o.strip()]


settings = Settings()
