"""Layered configuration: .env -> environment -> YAML config -> defaults.

Precedence (lowest to highest): kernel defaults < config/*.yaml < .env < real environment.
`.env` is parsed here so the civilization needs no python-dotenv, but one is used if present.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import paths

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader. Never overwrites an already-set environment variable."""
    path = path or (paths.ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _expand(value: Any) -> Any:
    """Recursively expand ${VAR} / ${VAR:default} in strings."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


@dataclass
class Settings:
    env: str = "local"
    owner: str = "Owner"
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    log_level: str = "info"
    tick_seconds: float = 1.5
    internal_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_enabled: bool = True
    default_model: str = "qwen2.5:0.5b-instruct"
    postgres_dsn: str = ""
    redis_url: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        def flag(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        known = {
            "EMPIRE_ENV", "EMPIRE_OWNER", "EMPIRE_CURRENCY", "EMPIRE_TIMEZONE", "EMPIRE_LOG_LEVEL",
            "EMPIRE_TICK_SECONDS", "EMPIRE_INTERNAL_KEY", "EMPIRE_OLLAMA_URL", "EMPIRE_OLLAMA_ENABLED",
            "EMPIRE_DEFAULT_MODEL", "EMPIRE_POSTGRES_DSN", "EMPIRE_REDIS_URL", "EMPIRE_DATA_DIR", "EMPIRE_ROOT",
        }
        extra = {k: v for k, v in os.environ.items() if k.startswith("EMPIRE_") and k not in known}
        return cls(
            env=os.environ.get("EMPIRE_ENV", "local"),
            owner=os.environ.get("EMPIRE_OWNER", "Owner"),
            currency=os.environ.get("EMPIRE_CURRENCY", "INR"),
            timezone=os.environ.get("EMPIRE_TIMEZONE", "Asia/Kolkata"),
            log_level=os.environ.get("EMPIRE_LOG_LEVEL", "info"),
            tick_seconds=float(os.environ.get("EMPIRE_TICK_SECONDS", "1.5")),
            internal_key=os.environ.get("EMPIRE_INTERNAL_KEY", ""),
            ollama_url=os.environ.get("EMPIRE_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_enabled=flag("EMPIRE_OLLAMA_ENABLED", True),
            default_model=os.environ.get("EMPIRE_DEFAULT_MODEL", "qwen2.5:0.5b-instruct"),
            postgres_dsn=os.environ.get("EMPIRE_POSTGRES_DSN", ""),
            redis_url=os.environ.get("EMPIRE_REDIS_URL", ""),
            extra=extra,
        )


class Config:
    """Access to every YAML config file plus typed settings."""

    def __init__(self) -> None:
        paths.ensure_dirs()
        load_dotenv()
        self.settings = Settings.from_env()
        self._cache: dict[str, Any] = {}
        self._load_all()
        self._ensure_internal_key()

    # ---- loading -------------------------------------------------------
    def _load_all(self) -> None:
        for name, path in paths.CONFIG_FILES.items():
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                self._cache[name] = _expand(data)
            else:
                self._cache[name] = {}
        self._cache["_resolved_at"] = str(paths.ROOT)

    def _ensure_internal_key(self) -> None:
        """Create a local inter-service key on first boot. Stored 0600 in state dir."""
        if self.settings.internal_key:
            return
        key_file = paths.SECRETS_DIR / "internal.key"
        if key_file.exists():
            self.settings.internal_key = key_file.read_text(encoding="utf-8").strip()
        else:
            import secrets
            key = secrets.token_urlsafe(48)
            key_file.write_text(key, encoding="utf-8")
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
            self.settings.internal_key = key

    def reload(self) -> None:
        self._cache.clear()
        self._load_all()

    # ---- access --------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        """`cfg.get("civilization.world.ground_size")` with a safe default."""
        parts = dotted.split(".")
        node: Any = self._cache.get(parts[0], {})
        for p in parts[1:]:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return default
        return node

    def section(self, name: str) -> dict:
        return dict(self._cache.get(name, {}))

    def boot_summary(self) -> str:
        cities = self.get("civilization.cities", []) or []
        depts = self.get("departments.departments", []) or []
        tracks = self.get("university.tracks", []) or []
        return (
            f"Saurav AI Civilization — {len(cities)} cities, {len(depts)} seeded departments, "
            f"{len(tracks)} university tracks, currency={self.settings.currency}, "
            f"capital={self.get('governance.identity.initial_capital_inr', 0)} {self.settings.currency}, "
            f"models={'ollama@' + self.settings.ollama_url if self.settings.ollama_enabled else 'deterministic-only'}"
        )


_singleton: Config | None = None


def config() -> Config:
    global _singleton
    if _singleton is None:
        _singleton = Config()
    return _singleton


def building_index() -> dict[str, dict]:
    """Flatten the world definition into building_id -> {city, building config}."""
    cfg = config()
    out: dict[str, dict] = {}
    for city in cfg.get("civilization.cities", []) or []:
        for b in city.get("buildings", []) or []:
            out[b["id"]] = {"city": city["id"], "city_name": city["name"], "theme": city.get("theme"),
                            "city_pos": city.get("pos", [0, 0]), **b}
    return out


def city_index() -> dict[str, dict]:
    return {c["id"]: c for c in (config().get("civilization.cities", []) or [])}


def department_seeds() -> Iterable[dict]:
    return config().get("departments.departments", []) or []
