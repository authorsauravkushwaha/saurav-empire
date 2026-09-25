"""Owner authentication.

The civilization is local-first, but it can be reached through a tunnel/preview URL. Therefore
the API is not open by default: a single owner token gates every route except health/meta.

The token is generated once, stored 0600 under `data/state/secrets/`, never logged in full, and
never placed in prompts. Rotate it with `python scripts/empire.py rotate-token`.
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from . import paths

TOKEN_FILE = paths.SECRETS_DIR / "owner_token"
PUBLIC_PATHS = {"/api/health", "/api/meta", "/health", "/meta", "/", "/docs", "/openapi.json",
                "/api/auth/status"}


def token_path() -> Path:
    return TOKEN_FILE


def ensure_token() -> str:
    """Return the owner token, creating it on first boot."""
    env_token = os.environ.get("EMPIRE_OWNER_TOKEN", "")
    if env_token:
        return env_token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token


def rotate_token() -> str:
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return token


def masked(token: str | None = None) -> str:
    """Safe-to-print form: never the whole secret."""
    tok = token or ensure_token()
    return f"{tok[:4]}…{tok[-4:]}"


def verify_token(candidate: str | None) -> bool:
    if not candidate:
        return False
    expected = ensure_token()
    return hmac.compare_digest(candidate.strip(), expected)


def verify_internal_key(candidate: str | None) -> bool:
    from .config import config
    if not candidate:
        return False
    return hmac.compare_digest(candidate.strip(), config().settings.internal_key)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.startswith(("/docs", "/redoc", "/openapi", "/assets"))
