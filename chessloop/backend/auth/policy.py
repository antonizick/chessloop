"""Account policy shared by the API routes and the seed scripts: when email
verification is required, what counts as an acceptable password, and a small
in-memory rate limiter for sensitive endpoints."""
import re
import threading
import time
from collections import deque

from sqlmodel import Session, select

from config import settings
from models.system_settings import SystemSettings

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

# Words that make a password guessable no matter what is appended to them
# ("password2026!", "chessloop123"). Compared after stripping digits/symbols.
_DENYLIST_BASES = {
    "admin", "administrator", "password", "chessloop", "chess",
    "changeme", "letmein", "welcome", "qwerty", "qwertyuiop", "iloveyou",
    "secret", "default", "root", "user", "login",
}


def password_problem(password: str) -> str | None:
    """Return a human-readable reason the password is unacceptable, or None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
    lowered = password.lower()
    # "P@ssw0rd2026!" → "password": drop leading/trailing digits and symbols,
    # undo common letter substitutions, then drop whatever else isn't a letter.
    core = re.sub(r"^[^a-z@$]+|[^a-z]+$", "", lowered).translate(_LEET)
    base = re.sub(r"[^a-z]", "", core)
    if (
        base in _DENYLIST_BASES
        or len(set(lowered)) <= 2  # "aaaaaaaaaaaa", "abababababab"
        or (lowered.isdigit() and (lowered in _ASCENDING or lowered in _DESCENDING))
    ):
        return "That password is too easy to guess. Choose something less common."
    return None


_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_ASCENDING = "0123456789" * 13
_DESCENDING = "9876543210" * 13


def verification_source(session: Session) -> str:
    """'admin' when an admin has set the toggle, else 'config'."""
    return "admin" if session.exec(select(SystemSettings)).first() else "config"


def verification_required(session: Session) -> bool:
    """Whether new registrations must verify their email before logging in.

    An admin's explicit choice (a system_settings row) wins; otherwise
    CHESSLOOP_EMAIL_VERIFICATION decides, where 'auto' means "only if SMTP is
    configured", so a self-host without email never locks new users out.
    """
    row = session.exec(select(SystemSettings)).first()
    if row is not None:
        return row.enforce_email_verification
    mode = settings.email_verification
    if mode == "on":
        return True
    if mode == "off":
        return False
    return settings.smtp_configured


class RateLimiter:
    """Sliding-window counter keyed by an arbitrary string (user id, IP).

    lucent: in-process memory only — limits reset on restart and are per worker.
    ChessLoop runs one uvicorn worker, so that is enough to stop online guessing.
    """

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._events.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_events

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
