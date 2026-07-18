import logging
import smtplib
from email.mime.text import MIMEText

from config import settings

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.warning("SMTP not configured — skipping email to %s: %s", to_email, subject)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception:
        # lucent: log-and-continue — a broken SMTP config must never fail registration
        logger.exception("Failed to send email to %s", to_email)


def send_verification_email(to_email: str, token: str) -> None:
    link = f"{settings.frontend_url}/verify-email?token={token}"
    _send(
        to_email,
        "Verify your ChessLoop email",
        f"Welcome to ChessLoop! Confirm your email address by visiting:\n\n{link}\n\n"
        "This link expires in 24 hours.",
    )


def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{settings.frontend_url}/reset-password?token={token}"
    _send(
        to_email,
        "Reset your ChessLoop password",
        f"We received a request to reset your ChessLoop password. Visit this link to choose a new one:\n\n{link}\n\n"
        "This link expires in 1 hour. If you didn't request this, you can safely ignore this email.",
    )
