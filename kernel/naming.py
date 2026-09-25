"""Naming subsystem — thematic identities with hard de-duplication.

Boss names come from the historically-themed pool in `config/departments.yaml`
(Egyptian rulers/warriors and comparable figures). These are thematic identities only;
they make no historical claim about any AI.

Uniqueness is enforced twice: in-memory (per process) and by a UNIQUE constraint in SQLite
plus the `names_reserved` setting. Two agents can never share a name.
"""
from __future__ import annotations

import random
import threading
import time
from typing import Iterable

from . import store
from .config import config

_lock = threading.RLock()
_reserved_cache: set[str] | None = None


def _load_reserved() -> set[str]:
    global _reserved_cache
    if _reserved_cache is None:
        stored = store.get_setting("names_reserved", []) or []
        rows = store.query("SELECT name FROM agents")
        db_names = {r["name"] for r in rows}
        _reserved_cache = set(stored) | db_names
    return _reserved_cache


def _save_reserved() -> None:
    names = sorted(_load_reserved())
    store.set_setting("names_reserved", names[-4000:])


class NameRegistry:
    def __init__(self) -> None:
        dept_cfg = config().section("departments")
        self.pool: list[str] = list(dept_cfg.get("name_pool", []) or [])
        style = dept_cfg.get("agent_name_style", {}) or {}
        self.prefixes: list[str] = list(style.get("prefix_pool", ["Kemet", "Thebes", "Giza"]))
        self.suffixes: list[str] = list(style.get("suffix_pool", ["Prime", "Nova", "Delta"]))
        self.max_suffix = int(style.get("max_suffix", 99))
        self.rng = random.Random(int(config().get("civilization.world.seed", 20260925)))

    # ---- boss names ----------------------------------------------------
    def next_boss_name(self) -> str:
        with _lock:
            reserved = _load_reserved()
            available = [n for n in self.pool if n not in reserved]
            if not available:
                return self._fallback_name(reserved)
            name = self.rng.choice(available)
            reserved.add(name)
            _save_reserved()
            return name

    def reserve(self, name: str) -> bool:
        """Returns False if the name is already taken (caller must handle it)."""
        with _lock:
            reserved = _load_reserved()
            if name in reserved:
                return False
            reserved.add(name)
            _save_reserved()
            return True

    # ---- ordinary agent names ------------------------------------------
    def next_agent_name(self, department: str | None = None) -> str:
        with _lock:
            reserved = _load_reserved()
            for _ in range(4000):
                prefix = self.rng.choice(self.prefixes)
                suffix = self.rng.choice(self.suffixes)
                num = self.rng.randint(1, self.max_suffix)
                candidate = f"{prefix}-{suffix}-{num:02d}"
                if candidate not in reserved:
                    reserved.add(candidate)
                    _save_reserved()
                    return candidate
            return self._fallback_name(reserved)

    def _fallback_name(self, reserved: set[str]) -> str:
        base = f"Agent-{int(time.time() * 1000) % 10_000_000}"
        candidate = base
        i = 1
        while candidate in reserved:
            candidate = f"{base}-{i}"
            i += 1
        reserved.add(candidate)
        _save_reserved()
        return candidate

    def free_pool(self) -> list[str]:
        reserved = _load_reserved()
        return [n for n in self.pool if n not in reserved]

    def reserved_names(self) -> list[str]:
        return sorted(_load_reserved())


def best_boss_name(used: Iterable[str] | None = None) -> str:
    return NameRegistry().next_boss_name()
