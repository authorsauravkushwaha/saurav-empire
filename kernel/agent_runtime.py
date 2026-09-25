"""Agent runtime — the loop that makes the civilization behave like an organization.

Agent loop (per the constitution):
    OBSERVE → UNDERSTAND → PLAN → REQUEST TOOLS → EXECUTE → VERIFY → REPORT → LEARN

World tick (drives the 3D visualization, which may never invent activity):
    1. travel      agents move toward their task building
    2. execute     arrive → deliberate (memory) → run tool → verify → report
    3. assign      idle agents claim the highest-priority permitted task
    4. generate    departments refill queues with meaningful work (never busywork)

The runtime is deterministic and cheap: no model is required for the loop to work.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import store, tools, world_layout
from .config import building_index, config, department_seeds
from .eventbus import E, bus
from .governance import approvals, kill_switch_engaged, safe_mode
from .memory import memory
from .model_router import router
from .registry import agents as agent_registry
from .registry import departments as dept_registry
from .tasks import board

MOVE_SPEED = 7.5          # world units per tick
MAX_TRAVELERS_PER_TICK = 40
MAX_WORKERS_PER_TICK = 12
MAX_ASSIGNMENTS_PER_TICK = 8
WORK_RESERVE_PER_DEPARTMENT = 4

TOPICS = [
    "the existing book catalog", "a Writer Nation editing service", "email list reactivation",
    "Instagram carousel series", "YouTube long-form vs Shorts", "a Gumroad template product",
    "author brand positioning across genres", "a poetry collection's reader promise",
    "a ₹0 lead magnet built from an existing chapter", "an author community membership",
    "Hindi-language finance content", "catalogue pricing tiers", "a reader referral loop",
    "a workshop from existing book material", "backlist revival via metadata",
]

MISSION_TEMPLATES: dict[str, list[tuple[str, str, int, dict]]] = {
    "market-intelligence": [
        ("Scan demand signals for {topic}", "market_scan", 3, {"topic": "{topic}"}),
        ("Map the alternatives a buyer already uses for {topic}", "research", 4, {"topic": "{topic}"}),
    ],
    "publishing-operations": [
        ("Audit catalog and rank which titles deserve resources", "catalog_audit", 2, {}),
        ("Assess reader promise for {topic}", "analysis", 4, {"topic": "{topic}"}),
    ],
    "content-creative": [
        ("Draft content with a declared job: {topic}", "content_draft", 4, {"topic": "{topic}", "job": "trust"}),
        ("Write an honest sales page section for {topic}", "copywriting", 5, {"topic": "{topic}", "job": "conversion"}),
    ],
    "growth-distribution": [
        ("Plan a zero-spend distribution test for {topic}", "content_draft", 4, {"topic": "{topic}", "job": "lead"}),
    ],
    "sales-partnerships": [
        ("Draft outreach for {topic}", "outreach_draft", 5, {"topic": "{topic}", "goal": "start a conversation"}),
    ],
    "finance-treasury": [
        ("Recompute unit economics for {topic}", "financial_model", 3, {"topic": "{topic}"}),
        ("Produce the daily honest financial report", "report", 2, {}),
    ],
    "research-lab": [
        ("Design a ₹0 experiment for {topic}", "experiment_design", 3, {"topic": "{topic}"}),
        ("Define the cheapest test for {topic}", "research", 4, {"topic": "{topic}"}),
    ],
    "data-analytics": [
        ("Produce the civilization KPI report", "report", 2, {}),
    ],
    "engineering": [
        ("Write an engineering brief: automate {topic} reporting", "code_task", 5,
         {"goal": "automate reporting for {topic}"}),
    ],
    "product-development": [
        ("Specify the smallest shippable promise for {topic}", "analysis", 3, {"topic": "{topic}"}),
    ],
    "customer-success": [
        ("Review outcome evidence for {topic}", "analysis", 4, {"topic": "{topic}"}),
    ],
    "security-governance": [
        ("Audit recent permission denials and escalation attempts", "analysis", 3, {}),
    ],
    "integration-automation": [
        ("Report connector health and quota status", "analysis", 4, {}),
    ],
    "executive-council": [
        ("Review the pending decision queue and rank by opportunity cost", "analysis", 3, {}),
    ],
    "university": [
        ("Review trainee progress and schedule examinations", "analysis", 5, {}),
    ],
}


# Where a given kind of work actually happens. A task is executed at the building that owns
# the work, so travel in the 3D world is a real consequence of the backend queue — never decoration.
WORK_BUILDINGS: dict[str, str] = {
    "research": "research-lab",
    "market_scan": "market-intelligence",
    "content_draft": "content-lab",
    "copywriting": "copywriting",
    "analysis": "analytics-tower",
    "financial_model": "unit-economics",
    "code_task": "software-hq",
    "verification": "qa-lab",
    "outreach_draft": "sales-floor",
    "catalog_audit": "data-warehouse",
    "experiment_design": "experimental-lab",
    "exam": "ai-university",
    "coursework": "ai-university",
    "report": "analytics-engine",
    "general": "mission-control",
}

# An agent that fails must not rot in ERROR forever, and must not silently retry forever either.
RECOVER_AFTER_SECONDS = 20.0
MAX_RECOVERIES = 3


@dataclass
class TickStats:
    tick: int = 0
    travelers: int = 0
    executed: int = 0
    assigned: int = 0
    generated: int = 0
    denied: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


class AgentRuntime:
    """Runs the agent loop on a background thread. Local-first, cheap, interruptible."""

    def __init__(self, tick_seconds: float | None = None) -> None:
        self.tick_seconds = float(tick_seconds or config().settings.tick_seconds)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.stats = TickStats()
        self.rng = random.Random(int(config().get("civilization.world.seed", 20260925)))
        self._topic_cursor = 0

    # ---- lifecycle -----------------------------------------------------
    def start(self) -> dict:
        if self._thread and self._thread.is_alive():
            return {"status": "already_running"}
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="agent-runtime", daemon=True)
        self._thread.start()
        self._heartbeat()
        bus.publish(E.BOOT, source="agent_runtime", payload={"tick_seconds": self.tick_seconds})
        return {"status": "started", "tick_seconds": self.tick_seconds}

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._heartbeat()
        return {"status": "stopped"}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                self.tick()
            except Exception as exc:  # a bad tick must never kill the civilization
                self.stats.errors.append(f"{type(exc).__name__}: {exc}"[:200])
                bus.publish("runtime.tick_error", source="agent_runtime", severity="error",
                            payload={"error": str(exc)[:300]})
            elapsed = time.time() - started
            self._stop.wait(max(0.2, self.tick_seconds - elapsed))

    # ---- the tick ------------------------------------------------------
    def tick(self) -> TickStats:
        self.stats = TickStats(tick=self.stats.tick + 1)
        started = time.time()
        if kill_switch_engaged():
            self.stats.duration_ms = int((time.time() - started) * 1000)
            return self.stats
        self._recover()
        self._travel()
        self._assign()
        self._work()
        self._generate_work()
        self.stats.duration_ms = int((time.time() - started) * 1000)
        self._heartbeat()
        return self.stats

    def _heartbeat(self) -> None:
        """Publish the runtime's own truth so every service reports the same state.

        The runtime lives in exactly one process (agent-service). Without this, another service
        asking `runtime()` would answer about its own empty instance — which would be a lie the
        3D world could not detect.
        """
        store.set_setting("runtime_heartbeat", {
            "pid": os.getpid(),
            "tick": self.stats.tick,
            "tick_seconds": self.tick_seconds,
            "looping": self.running(),
            "ts": time.time(),
            "last_tick": {"travelers": self.stats.travelers, "executed": self.stats.executed,
                          "assigned": self.stats.assigned, "generated": self.stats.generated,
                          "denied": self.stats.denied, "duration_ms": self.stats.duration_ms},
            "errors": self.stats.errors[-3:],
        })

    # 0. recover ---------------------------------------------------------
    def _recover(self) -> None:
        """ERROR is a rest stop, not a graveyard.

        An agent that failed is retried a bounded number of times (the failure stays in memory and
        in the audit log). After that it is suspended and an owner approval is filed — an agent that
        keeps failing is a decision for the owner, not something the runtime may hide or fake past.
        """
        rows = store.query(
            "SELECT * FROM agents WHERE status='ERROR' AND lifecycle != 'TERMINATED' LIMIT 20")
        for row in rows:
            agent = agent_registry._expand(dict(row))
            stalled_for = time.time() - float(agent.get("updated_at") or 0)
            if stalled_for < RECOVER_AFTER_SECONDS:
                continue
            if agent.get("active_task_id"):
                store.update("agents", agent["id"], {"active_task_id": None})
            recoveries = int((agent.get("meta") or {}).get("recoveries") or 0)
            if recoveries >= MAX_RECOVERIES:
                agent_registry.suspend(
                    agent["id"],
                    f"{recoveries} unrecovered failures — runtime stopped retrying; owner review required.",
                    by="agent_runtime")
                try:
                    approvals.request(
                        action="agent.suspend", risk="HIGH", requester=agent["name"],
                        requester_rank=agent.get("rank", "AGENT"),
                        what=f"Review agent {agent['name']} ({agent['role']})",
                        why=f"{recoveries} consecutive task failures the runtime could not recover from.",
                        expected_result="Owner decides: retrain, reassign or terminate.",
                        risk_notes="A permanently failing agent consumes budget and pollutes reports.",
                        reversibility="Fully reversible — reinstating the agent restores its state.")
                except Exception as exc:  # never let bookkeeping break the tick
                    self.stats.errors.append(f"approvals.request failed: {type(exc).__name__}")
                bus.publish("agent.suspended_for_review", source="agent_runtime", subject=agent["id"],
                            severity="warning",
                            payload={"name": agent["name"], "recoveries": recoveries})
            else:
                meta = dict(agent.get("meta") or {})
                meta["recoveries"] = recoveries + 1
                store.update("agents", agent["id"], {"meta_json": json.dumps(meta, default=str)})
                agent_registry.set_status(agent["id"], "IDLE",
                                          reason=f"recovered_after_error ({recoveries + 1}/{MAX_RECOVERIES})")

    # 1. travel ----------------------------------------------------------
    def _travel(self) -> None:
        rows = store.query(
            "SELECT * FROM agents WHERE status='TRAVELING' AND lifecycle != 'TERMINATED' LIMIT ?",
            (MAX_TRAVELERS_PER_TICK,))
        for row in rows:
            agent = agent_registry._expand(dict(row))
            target_building = agent.get("target_building")
            if not target_building:
                agent_registry.arrive(agent["id"], agent.get("building") or "owner-command-center")
                continue
            building = world_layout.building_world_pos(target_building)
            dest = building["entry"]
            pos = [float(agent.get("pos_x") or 0), float(agent.get("pos_y") or 0)]
            new_pos = world_layout.step_towards(pos, [dest[0], dest[2]], MOVE_SPEED)
            agent_registry.update_position(agent["id"], new_pos[0], new_pos[1])
            arrived = abs(new_pos[0] - dest[0]) < 0.6 and abs(new_pos[1] - dest[2]) < 0.6
            if arrived:
                agent_registry.arrive(agent["id"], target_building)
                task_id = agent.get("active_task_id")
                if task_id:
                    board.start(task_id, agent["id"])
                    agent_registry.set_status(agent["id"], _status_for_task(
                        (board.get(task_id) or {}).get("task_type", "general")), reason="arrived")
                else:
                    agent_registry.set_status(agent["id"], "IDLE", reason="arrived_without_task")
            self.stats.travelers += 1

    @staticmethod
    def _work_building(task: dict, agent: dict, dept_building: str | None) -> str:
        """The building where this task is really done: explicit payload > task type > department."""
        explicit = (task.get("payload") or {}).get("building")
        if explicit:
            return explicit
        by_type = WORK_BUILDINGS.get(task.get("task_type") or "", None)
        if by_type and by_type in building_index():
            return by_type
        return dept_building or "mission-control"

    # 2. assign ----------------------------------------------------------
    def _assign(self) -> None:
        # (a) Tasks already addressed to a specific agent (e.g. university coursework).
        preassigned = store.query(
            "SELECT t.id AS task_id, t.title, t.task_type, t.payload_json, a.id AS agent_id, "
            "a.department_id, a.name "
            "FROM tasks t JOIN agents a ON a.id = t.assignee_id "
            "WHERE t.status='ASSIGNED' AND a.active_task_id IS NULL AND a.status IN ('IDLE','LEARNING') "
            "AND a.lifecycle IN ('TRAINEE','EMPLOYED','GRADUATE') LIMIT ?",
            (MAX_ASSIGNMENTS_PER_TICK,))
        for row in preassigned:
            agent = agent_registry.get(row["agent_id"]) or {}
            dept_building = (dept_registry.get(row["department_id"]) or {}).get("building")
            building = self._work_building(
                {"task_type": row["task_type"], "payload": store.jload(row["payload_json"], {})},
                agent, dept_building)
            store.update("agents", row["agent_id"], {"active_task_id": row["task_id"]})
            agent_registry.move_to(row["agent_id"], building, reason="preassigned_task")
            bus.publish(E.TASK_ASSIGNED, source="agent_runtime", subject=row["task_id"],
                        payload={"agent": row["name"], "agent_id": row["agent_id"],
                                 "title": row["title"], "type": row["task_type"], "preassigned": True})
            self.stats.assigned += 1

        # Departments that actually have work waiting get first call on their own idle people —
        # otherwise a global top-N slice keeps serving the same high performers and the queue stalls.
        waiting = [r["department_id"] for r in store.query(
            "SELECT DISTINCT department_id FROM tasks WHERE status='QUEUED' "
            "AND department_id IS NOT NULL")]
        idle: list[dict] = []
        if waiting:
            marks = ", ".join("?" for _ in waiting)
            idle = store.query(
                f"SELECT * FROM agents WHERE status='IDLE' AND lifecycle IN ('EMPLOYED','GRADUATE') "
                f"AND active_task_id IS NULL AND department_id IN ({marks}) "
                f"ORDER BY performance DESC LIMIT ?",
                (*waiting, MAX_ASSIGNMENTS_PER_TICK * 8))
        assigned = 0
        for row in idle:
            if assigned >= MAX_ASSIGNMENTS_PER_TICK:
                break
            agent = agent_registry._expand(dict(row))
            task = board.claim_next(agent)
            if not task:
                continue
            store.update("agents", agent["id"], {"active_task_id": task["id"]})
            agent_registry.move_to(agent["id"], self._work_building(
                task, agent, (dept_registry.get(agent["department_id"]) or {}).get("building")),
                reason="task")
            bus.publish(E.TASK_ASSIGNED, source="agent_runtime", subject=task["id"],
                        payload={"agent": agent["name"], "agent_id": agent["id"],
                                 "title": task["title"], "type": task["task_type"]})
            assigned += 1
            self.stats.assigned += 1

    # 3. work ------------------------------------------------------------
    def _work(self) -> None:
        rows = store.query(
            "SELECT * FROM agents WHERE status IN ('WORKING','ANALYZING','RESEARCHING','CODING',"
            "'PUBLISHING','SELLING','NEGOTIATING','LEARNING','WAITING') AND active_task_id IS NOT NULL "
            "AND lifecycle != 'TERMINATED' LIMIT ?", (MAX_WORKERS_PER_TICK,))
        for row in rows:
            agent = agent_registry._expand(dict(row))
            task = board.get(agent["active_task_id"])
            if not task:
                store.update("agents", agent["id"], {"active_task_id": None})
                agent_registry.set_status(agent["id"], "IDLE", reason="task_missing")
                continue
            if task["status"] not in ("ASSIGNED", "IN_PROGRESS", "VERIFYING"):
                store.update("agents", agent["id"], {"active_task_id": None})
                agent_registry.set_status(agent["id"], "IDLE", reason=f"task_{task['status'].lower()}")
                continue
            self._execute(agent, task)
            self.stats.executed += 1

    def _execute(self, agent: dict, task: dict) -> None:
        # OBSERVE + UNDERSTAND (memory first — cheap, local, real)
        prior = memory.search(task["title"], agent_id=agent["id"], limit=3)
        context_note = ("; ".join(p["content"][:120] for p in prior)) if prior else "no prior memory"
        memory.working(agent["id"], f"Task {task['id']}: {task['title']} | context: {context_note}",
                       key=task["id"])
        bus.publish(E.TASK_PROGRESS, source="agent_runtime", subject=task["id"],
                    payload={"agent": agent["name"], "phase": "deliberating",
                             "memory_hits": len(prior)})

        # REQUEST TOOLS + EXECUTE
        result = tools.execute(task, agent)

        # VERIFY is inside board.complete(); REPORT follows
        quality_hint = 1.0 if result.get("status") == "ok" else 0.3
        completed = board.complete(task["id"], agent_id=agent["id"], result=result, quality=quality_hint)
        verified = bool((completed or {}).get("verification", {}).get("passed"))

        # LEARN
        agent_registry.record_result(agent["id"], success=verified, quality=float(
            (completed or {}).get("verification", {}).get("score") or 0.0),
            cost_inr=0.0, value_inr=0.0, energy_cost=3.0)
        if verified:
            memory.procedural(agent["id"], f"Playbook for '{task['task_type']}': tool={result.get('tool')}, "
                                           f"verified score={completed['verification']['score']}",
                              key=f"playbook::{task['task_type']}")
        memory.episodic(agent["id"], f"{'Completed' if verified else 'Failed'} task: {task['title']} "
                                     f"(tool={result.get('tool')}, score={completed['verification']['score']})",
                        importance=0.5 if verified else 0.7)
        store.update("agents", agent["id"], {"active_task_id": None})
        agent_registry.set_status(agent["id"], "IDLE" if verified else "ERROR",
                                  reason="task_verified" if verified else "task_failed")
        if not verified and result.get("status") == "denied":
            self.stats.denied += 1

    # 4. generate work ---------------------------------------------------
    def _generate_work(self) -> None:
        # `self.tick` is the method; the counter lives on `self.stats.tick`.
        if self.stats.tick % 3 != 0:
            return
        for seed in department_seeds():
            dept_id = seed["id"]
            open_tasks = store.query_one(
                "SELECT COUNT(*) n FROM tasks WHERE department_id=? AND status IN ('QUEUED','ASSIGNED','IN_PROGRESS')",
                (dept_id,))["n"]
            if open_tasks >= WORK_RESERVE_PER_DEPARTMENT:
                continue
            templates = MISSION_TEMPLATES.get(dept_id)
            if not templates:
                continue
            title, task_type, priority, payload = self.rng.choice(templates)
            topic = self._next_topic()
            title = title.format(topic=topic)
            payload = {k: (v.format(topic=topic) if isinstance(v, str) else v) for k, v in (payload or {}).items()}
            board.create(title=title, description=f"Auto-scheduled for {seed['name']}. "
                                                  f"Declare evidence and label unknowns.",
                         task_type=task_type, department_id=dept_id, created_by="mission_generator",
                         priority=priority, payload=payload)
            self.stats.generated += 1

    def _next_topic(self) -> str:
        topic = TOPICS[self._topic_cursor % len(TOPICS)]
        self._topic_cursor += 1
        return topic

    # ---- introspection -------------------------------------------------
    def status(self) -> dict:
        board_counts = board.metrics()["counts"]
        return {
            "running": self.running(),
            "tick_seconds": self.tick_seconds,
            "ticks": self.stats.tick,
            "last_tick": {"travelers": self.stats.travelers, "executed": self.stats.executed,
                          "assigned": self.stats.assigned, "generated": self.stats.generated,
                          "denied": self.stats.denied, "duration_ms": self.stats.duration_ms},
            "queue": board_counts,
            "safe_mode": safe_mode(),
            "kill_switch": kill_switch_engaged(),
            "errors": self.stats.errors[-5:],
        }


def _status_for_task(task_type: str) -> str:
    return {
        "research": "RESEARCHING", "market_scan": "RESEARCHING", "content_draft": "WORKING",
        "copywriting": "WORKING", "analysis": "ANALYZING", "financial_model": "ANALYZING",
        "code_task": "CODING", "report": "ANALYZING", "outreach_draft": "NEGOTIATING",
        "catalog_audit": "ANALYZING", "experiment_design": "ANALYZING", "exam": "LEARNING",
        "coursework": "LEARNING", "verification": "ANALYZING",
    }.get(task_type, "WORKING")


def runtime_snapshot(*, max_age_seconds: float = 20.0) -> dict:
    """What the *running* runtime is doing, read from its heartbeat (any process may ask)."""
    beat = store.get_setting("runtime_heartbeat", {}) or {}
    if not isinstance(beat, dict) or not beat:
        return {"running": False, "tick": 0, "pid": None, "tick_seconds": None, "last_tick": {},
                "age_seconds": None, "note": "no runtime heartbeat yet — start it from the agent service"}
    age = time.time() - float(beat.get("ts") or 0)
    limit = max(max_age_seconds, float(beat.get("tick_seconds") or 1.5) * 6)
    return {
        "running": bool(beat.get("looping")) and age <= limit,
        "tick": int(beat.get("tick") or 0),
        "pid": beat.get("pid"),
        "tick_seconds": beat.get("tick_seconds"),
        "last_tick": beat.get("last_tick") or {},
        "errors": beat.get("errors") or [],
        "age_seconds": round(age, 2),
        "stale": age > limit,
    }


_runtime: AgentRuntime | None = None


def runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime
