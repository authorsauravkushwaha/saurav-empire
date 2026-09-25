"""Canonical filesystem locations for the civilization. No module may hard-code a path."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("EMPIRE_ROOT", Path(__file__).resolve().parents[1])).resolve()

CONFIG_DIR = ROOT / "config"
DOCS_DIR = ROOT / "docs"
SERVICES_DIR = ROOT / "services"
APPS_DIR = ROOT / "apps"
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"

# Runtime state is per-machine and git-ignored.
def _state_dir() -> Path:
    p = Path(os.environ.get("EMPIRE_DATA_DIR", DATA_DIR / "state"))
    if not p.is_absolute():
        p = ROOT / p
    return p

STATE_DIR = _state_dir()
LOG_DIR = DATA_DIR / "logs"
WORKSPACE_DIR = STATE_DIR / "workspace"      # sandboxed agent file area
SECRETS_DIR = STATE_DIR / "secrets"
MEMORY_DIR = STATE_DIR / "memory"
ARTIFACT_DIR = STATE_DIR / "artifacts"

DB_PATH = STATE_DIR / "empire.db"

CONFIG_FILES = {
    "civilization": CONFIG_DIR / "civilization.yaml",
    "departments": CONFIG_DIR / "departments.yaml",
    "models": CONFIG_DIR / "models.yaml",
    "permissions": CONFIG_DIR / "permissions.yaml",
    "governance": CONFIG_DIR / "governance.yaml",
    "university": CONFIG_DIR / "university.yaml",
    "economics": CONFIG_DIR / "economics.yaml",
}

# Filesystem jail: agent code may only read/write inside these (see governance/tools).
JAILED_WRITE_ROOTS = (STATE_DIR, ARTIFACT_DIR, WORKSPACE_DIR)


def ensure_dirs() -> None:
    for p in (STATE_DIR, LOG_DIR, WORKSPACE_DIR, SECRETS_DIR, MEMORY_DIR, ARTIFACT_DIR):
        p.mkdir(parents=True, exist_ok=True)


def in_jail(path: str | Path) -> bool:
    """True if `path` resolves inside an allowed write root."""
    try:
        rp = Path(path).resolve() if Path(path).is_absolute() else (ROOT / path).resolve()
    except OSError:
        return False
    return any(str(rp).startswith(str(r)) for r in JAILED_WRITE_ROOTS)
