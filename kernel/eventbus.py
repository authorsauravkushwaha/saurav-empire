"""Event bus — the nervous system.

Rules:
  * Every meaningful state change is published as an event and appended to `events`.
  * Local subscribers are notified in-process (sync, isolated so one bad handler can't melt the bus).
  * Cross-process consumers (other services, the 3D world) poll `since()` — the event log is the
    contract. Redis is used as a fast path only if the owner installs it.
  * Events are immutable history. They are never edited, only appended.
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from typing import Any, Callable, Iterable

from . import store

MAX_LOCAL_FANOUT = 500


@dataclass
class Event:
    type: str
    source: str = "kernel"
    subject: str | None = None
    severity: str = "info"
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._counts: dict[str, int] = defaultdict(int)
        self._recent: list[dict] = []

    # ---- subscription --------------------------------------------------
    def subscribe(self, pattern: str, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subs[pattern].append(callback)

    def unsubscribe(self, pattern: str, callback: Callable[[Event], None]) -> None:
        with self._lock:
            if callback in self._subs.get(pattern, []):
                self._subs[pattern].remove(callback)

    # ---- publish -------------------------------------------------------
    def publish(self, event: Event | str, **kwargs: Any) -> Event:
        ev = Event(event, **kwargs) if isinstance(event, str) else event
        ev.ts = ev.ts or time.time()

        row = store.insert("events", {
            "ts": ev.ts, "type": ev.type, "source": ev.source, "subject": ev.subject,
            "severity": ev.severity, "payload_json": json.dumps(ev.payload, ensure_ascii=False, default=str),
        })
        # fetch the autoincrement id
        got = store.query_one("SELECT id FROM events ORDER BY id DESC LIMIT 1")
        ev.id = int(got["id"]) if got else None

        with self._lock:
            self._counts[ev.type] += 1
            self._recent.append(ev.to_dict())
            if len(self._recent) > MAX_LOCAL_FANOUT:
                self._recent = self._recent[-MAX_LOCAL_FANOUT:]
            handlers = [h for pat, hs in self._subs.items() if fnmatch(ev.type, pat) for h in hs]

        for handler in handlers:
            try:
                handler(ev)
            except Exception as exc:  # never let a subscriber break the bus
                self._counts["bus.handler_error"] += 1
                store.insert("audit", {
                    "ts": time.time(), "actor": "eventbus", "action": "handler_error",
                    "target": ev.type, "allowed": 1, "reason": f"{type(exc).__name__}: {exc}",
                })
        return ev

    # ---- reads ---------------------------------------------------------
    def since(self, last_id: int = 0, limit: int = 500, types: Iterable[str] | None = None) -> list[dict]:
        rows = store.query(
            "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?", (last_id, limit)
        )
        out = []
        for r in rows:
            r["payload"] = store.jload(r.pop("payload_json", None), {})
            if types and not any(fnmatch(r["type"], t) for t in types):
                continue
            out.append(r)
        return out

    def recent(self, limit: int = 100) -> list[dict]:
        rows = store.query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["payload"] = store.jload(r.pop("payload_json", None), {})
        return list(reversed(rows))

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def tail_metrics(self, window_seconds: int = 300) -> dict:
        cutoff = time.time() - window_seconds
        rows = store.query("SELECT type, COUNT(*) n FROM events WHERE ts > ? GROUP BY type", (cutoff,))
        return {r["type"]: int(r["n"]) for r in rows}


bus = EventBus()

# ---------------------------------------------------------------------------
# Canonical event names (kept in one place so the 3D world can rely on them)
# ---------------------------------------------------------------------------
class E:
    BOOT = "civilization.boot"
    SHUTDOWN = "civilization.shutdown"
    KILLSWITCH = "civilization.killswitch"
    SAFE_MODE = "civilization.safe_mode"

    AGENT_CREATED = "agent.created"
    AGENT_STATUS = "agent.status_changed"
    AGENT_MOVED = "agent.moved"
    AGENT_ASSIGNED = "agent.assigned"
    AGENT_PROMOTED = "agent.promoted"
    AGENT_SUSPENDED = "agent.suspended"
    AGENT_TERMINATED = "agent.terminated"

    DEPT_CREATED = "department.created"
    DEPT_DISSOLVED = "department.dissolved"
    DEPT_BUDGET = "department.budget_changed"

    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_BLOCKED = "task.blocked"
    TASK_VERIFIED = "task.verified"
    TASK_DONE = "task.completed"
    TASK_FAILED = "task.failed"

    MEMORY_WRITTEN = "memory.written"
    MESSAGE_SENT = "message.sent"

    UNIVERSITY_ENROLL = "university.enrolled"
    UNIVERSITY_PROGRESS = "university.progress"
    UNIVERSITY_EXAM = "university.exam"
    UNIVERSITY_CERTIFIED = "university.certified"
    UNIVERSITY_GRADUATED = "university.graduated"
    JOB_MATCHED = "university.job_matched"

    MODEL_CALL = "model.call"
    MODEL_FALLBACK = "model.fallback"
    MODEL_ERROR = "model.error"

    OPPORTUNITY_DISCOVERED = "economy.opportunity_discovered"
    OPPORTUNITY_SCORED = "economy.opportunity_scored"
    OPPORTUNITY_STATUS = "economy.opportunity_status"
    EXPERIMENT_CREATED = "economy.experiment_created"
    EXPERIMENT_MEASURED = "economy.experiment_measured"
    EXPERIMENT_DECIDED = "economy.experiment_decided"
    LEDGER_ENTRY = "economy.ledger_entry"
    LESSON_LEARNED = "economy.lesson"

    APPROVAL_REQUESTED = "governance.approval_requested"
    APPROVAL_DECIDED = "governance.approval_decided"
    POLICY_DENIED = "governance.policy_denied"
    INJECTION_DETECTED = "governance.injection_detected"

    INTEGRATION_STATUS = "integration.status"
    INTEGRATION_CALL = "integration.call"
