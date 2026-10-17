from typing import Literal, Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "chessloop.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    cors_origins: str = "http://localhost:8090,http://localhost:5173"
    # Base of the links in emails. Blank: https://<domain> if a domain is set,
    # else http://localhost:<public_port>.
    frontend_url: str = ""
    domain: str = ""
    public_port: int = 8090
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
    # Blank: the SMTP login if it is an address (what most relays accept), else
    # no-reply@<domain>, else a .local address that real relays may reject.
    smtp_from: str = ""
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

    @model_validator(mode="after")
    def _derive_defaults(self):
        domain = self.domain.strip()
        if not self.frontend_url.strip():
            self.frontend_url = f"https://{domain}" if domain else f"http://localhost:{self.public_port}"
        self.frontend_url = self.frontend_url.strip().rstrip("/")
        if not self.smtp_from.strip():
            if "@" in self.smtp_user:
                self.smtp_from = f"ChessLoop <{self.smtp_user.strip()}>"
            else:
                self.smtp_from = f"ChessLoop <no-reply@{domain or 'chessloop.local'}>"
        return self

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        origins = self.cors_origins.strip()
        if origins == "*":
            return ["*"]
        return [o.strip() for o in origins.split(",") if o.strip()]


# Values that are public (docs, examples, old defaults): anyone could sign tokens with them.
_PUBLIC_JWT_SECRETS = {
    "replace-with-openssl-rand-base64-32",
    "change-me-in-production",
    "dev-secret-change-me",
}
MIN_JWT_SECRET_LENGTH = 32


def jwt_secret_problem(secret: str) -> Optional[str]:
    """Why this JWT secret is unsafe to run with, or None if it is acceptable."""
    s = secret.strip()
    if not s:
        return "JWT_SECRET is empty."
    if "$(" in s or "`" in s:
        return ("JWT_SECRET contains a shell command. A .env file does not run commands: "
                "run the command yourself and paste its output instead.")
    if s in _PUBLIC_JWT_SECRETS:
        return "JWT_SECRET is still the example value, which is public."
    if len(s) < MIN_JWT_SECRET_LENGTH:
        return f"JWT_SECRET is too short ({len(s)} characters; at least {MIN_JWT_SECRET_LENGTH} are needed)."
    return None


settings = Settings()
