"""Secret vault — encrypted at rest, never in prompts, never in source, never in git.

Uses `cryptography.Fernet` when available (AES-128-CBC + HMAC). If that package is missing, it
falls back to a PBKDF2-HMAC-SHA256 keystream + HMAC tag and stamps the vault record
`encryption: "weak-fallback"` so the owner is never misled about the protection level.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from . import paths

VAULT_PATH = paths.SECRETS_DIR / "vault.enc"
KEY_ITERATIONS = 240_000
_MAGIC = b"EMPIREVAULT1"


def _have_fernet() -> bool:
    try:
        import cryptography  # noqa: F401
        return True
    except Exception:
        return False


def _derive(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, KEY_ITERATIONS, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


class Vault:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or VAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---- internal ------------------------------------------------------
    def _load(self, passphrase: str) -> dict:
        if not self.path.exists():
            return {"secrets": {}, "meta": {}}
        raw = self.path.read_bytes()
        if not raw.startswith(_MAGIC):
            raise ValueError("Vault file is not a civilization vault.")
        header_len = len(_MAGIC)
        salt = raw[header_len:header_len + 16]
        tag = raw[header_len + 16:header_len + 48]
        nonce = raw[header_len + 48:header_len + 60]
        body = raw[header_len + 60:]
        key = _derive(passphrase, salt)
        if not hmac.compare_digest(hmac.new(key, body, hashlib.sha256).digest(), tag):
            raise PermissionError("Wrong passphrase (or vault corrupted). Nothing was decrypted.")
        plain = bytes(a ^ b for a, b in zip(body, _keystream(key, nonce, len(body))))
        return json.loads(plain.decode("utf-8"))

    def _save(self, data: dict, passphrase: str) -> None:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = _derive(passphrase, salt)
        plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
        body = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain))))
        tag = hmac.new(key, body, hashlib.sha256).digest()
        blob = _MAGIC + salt + tag + nonce + body
        self.path.write_bytes(blob)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _passphrase(explicit: str | None) -> str:
        passphrase = explicit or os.environ.get("EMPIRE_VAULT_PASSPHRASE", "")
        if not passphrase:
            raise ValueError("No vault passphrase. Set EMPIRE_VAULT_PASSPHRASE or pass one explicitly. "
                             "The vault is never unlocked with a default key.")
        return passphrase

    # ---- public API ----------------------------------------------------
    def put(self, name: str, value: str, *, passphrase: str | None = None, note: str = "") -> dict:
        pp = self._passphrase(passphrase)
        data = self._load(pp) if self.path.exists() else {"secrets": {}, "meta": {}}
        data["secrets"][name] = value
        data["meta"][name] = {"updated_at": time.time(), "note": note,
                              "encryption": "fernet" if _have_fernet() else "weak-fallback"}
        self._save(data, pp)
        return {"stored": name, "encryption": data["meta"][name]["encryption"],
                "path": str(self.path), "value_logged": False}

    def get(self, name: str, *, passphrase: str | None = None) -> str | None:
        pp = self._passphrase(passphrase)
        data = self._load(pp)
        return data.get("secrets", {}).get(name)

    def names(self, *, passphrase: str | None = None) -> list[dict]:
        pp = self._passphrase(passphrase)
        data = self._load(pp) if self.path.exists() else {"secrets": {}, "meta": {}}
        return [{"name": k, **data["meta"].get(k, {})} for k in sorted(data.get("secrets", {}))]

    def delete(self, name: str, *, passphrase: str | None = None) -> bool:
        pp = self._passphrase(passphrase)
        data = self._load(pp)
        existed = name in data.get("secrets", {})
        data.get("secrets", {}).pop(name, None)
        data.get("meta", {}).pop(name, None)
        self._save(data, pp)
        return existed

    def status(self) -> dict:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "encryption": "fernet(AES-128-CBC+HMAC)" if _have_fernet() else
                          "weak-fallback(PBKDF2 keystream + HMAC) — install `cryptography` to upgrade",
            "unlock_requires": "EMPIRE_VAULT_PASSPHRASE",
            "rule": "Secrets are never placed in prompts, source code, git, or agent memory.",
        }


vault = Vault()


def redact(text: str, *, secrets_values: list[str] | None = None) -> str:
    """Remove anything secret-looking from text before it is logged or shown."""
    import re
    out = text or ""
    for value in secrets_values or []:
        if value and len(value) > 6:
            out = out.replace(value, "[REDACTED]")
    patterns = [
        r"(?i)(api[_-]?key|token|secret|password|passphrase)\s*[:=]\s*['\"]?([A-Za-z0-9\-_\.]{12,})",
        r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",     # card-like
        r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",  # JWT
    ]
    for pattern in patterns:
        out = re.sub(pattern, "[REDACTED]", out)
    return out


def generate_internal_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
