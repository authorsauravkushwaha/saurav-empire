"""Analytics Service (port 8004) — every meaningful event becomes measurable."""
from __future__ import annotations

import os
import time

from fastapi import Depends, Query

from kernel import store
from kernel.economy import economic_summary, ledger
from kernel.model_router import router
from kernel.registry import agents as agent_registry
from kernel.tasks import board
from services.base import ServiceCard, require_owner, service_app

PORT = 8004
CARD = ServiceCard(
    name="analytics-service", port=PORT, layer="B · measurement", domain="analytics",
    description="KPI aggregation, department scorecards, agent productivity, model usage, system health.",
    owns_tables=["events (read)", "tasks (read)", "ledger (read)"],
    produces_events=["analytics.report_generated"],
    consumes_events=["*"],
    endpoints=["GET /analytics/overview", "GET /analytics/tasks", "GET /analytics/agents",
               "GET /analytics/departments", "GET /analytics/timeline", "GET /analytics/models",
               "GET /analytics/system", "GET /analytics/owner-dashboard"],
    dependencies=["kernel.store", "kernel.economy"],
)
application = service_app(CARD)


def _system_metrics() -> dict:
    """Real host metrics from /proc — no dependency, no illusion."""
    out: dict = {"cpu_cores": os.cpu_count(), "load_avg": None, "memory": None, "disk_free_gb": None,
                 "uptime_seconds": None}
    try:
        out["load_avg"] = [round(float(x), 2) for x in open("/proc/loadavg").read().split()[:3]]
        mem = {}
        for line in open("/proc/meminfo").read().splitlines():
            k, _, v = line.partition(":")
            mem[k] = int(v.strip().split()[0]) * 1024
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        out["memory"] = {"total_gb": round(total / 1e9, 2), "available_gb": round(available / 1e9, 2),
                         "used_pct": round((1 - available / total) * 100, 1) if total else None}
        out["uptime_seconds"] = round(float(open("/proc/uptime").read().split()[0]), 0)
    except Exception:
        pass
    try:
        stat = os.statvfs(str(store.paths.STATE_DIR))
        out["disk_free_gb"] = round(stat.f_bavail * stat.f_frsize / 1e9, 2)
    except Exception:
        pass
    out["db_size_mb"] = round(store.db_size_bytes() / 1e6, 3)
    return out


@application.get("/analytics/overview")
def overview(_: str = Depends(require_owner)) -> dict:
    econ = economic_summary()
    tasks = board.metrics()
    agents = agent_registry.counts()
    return {
        "generated_at": time.time(),
        "agents": agents,
        "tasks": tasks,
        "economy": econ,
        "events": {"total": int(store.query_one("SELECT COUNT(*) n FROM events")["n"]),
                   "last_5m": store.query_one("SELECT COUNT(*) n FROM events WHERE ts > ?",
                                              (time.time() - 300,))["n"]},
        "approvals_pending": int(store.query_one(
            "SELECT COUNT(*) n FROM approvals WHERE status='PENDING'")["n"]),
        "table_rows": store.table_counts(),
        "honesty": ("These are internal activity metrics. Revenue is only what the ledger has verified: "
                    f"₹{econ['revenue_inr']:,.2f}."),
    }


@application.get("/analytics/tasks")
def tasks_analytics(_: str = Depends(require_owner)) -> dict:
    return board.metrics()


@application.get("/analytics/agents")
def agent_analytics(_: str = Depends(require_owner)) -> dict:
    by_rank = store.query("SELECT rank, COUNT(*) n, AVG(performance) perf, AVG(reliability) rel "
                          "FROM agents WHERE lifecycle != 'TERMINATED' GROUP BY rank")
    top = agent_registry.top_performers(10)
    idle = int(store.query_one("SELECT COUNT(*) n FROM agents WHERE status='IDLE' AND "
                               "lifecycle != 'TERMINATED'")["n"])
    busy = int(store.query_one("SELECT COUNT(*) n FROM agents WHERE status NOT IN ('IDLE','BLOCKED') "
                               "AND lifecycle != 'TERMINATED'")["n"])
    return {"by_rank": by_rank, "top_performers": top,
            "utilisation": {"idle": idle, "working": busy,
                            "rate": round(busy / max(idle + busy, 1), 3)},
            "certified": int(store.query_one("SELECT COUNT(*) n FROM agents WHERE certs_json != '[]'")["n"])}


@application.get("/analytics/departments")
def department_analytics(_: str = Depends(require_owner)) -> dict:
    rows = store.query(
        "SELECT d.id, d.name, d.city, d.status, "
        "(SELECT COUNT(*) FROM agents a WHERE a.department_id=d.id AND a.lifecycle!='TERMINATED') headcount, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id) tasks, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id AND t.status='DONE') done, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id AND t.status='FAILED') failed, "
        "(SELECT COALESCE(AVG(t.verification_json IS NOT NULL AND t.status='DONE'),0) FROM tasks t "
        " WHERE t.department_id=d.id AND t.status IN ('DONE','FAILED')) success_rate "
        "FROM departments d WHERE d.status='ACTIVE' ORDER BY done DESC")
    return {"departments": rows,
            "note": "Efficiency is measured on verified outcomes, not on volume of activity."}


@application.get("/analytics/timeline")
def timeline(window_hours: int = Query(24, le=720), _: str = Depends(require_owner)) -> dict:
    cutoff = time.time() - window_hours * 3600
    rows = store.query(
        "SELECT CAST(ts/3600 AS INTEGER) AS hour_bucket, type, COUNT(*) n FROM events "
        "WHERE ts > ? GROUP BY hour_bucket, type ORDER BY hour_bucket ASC", (cutoff,))
    tasks = store.query(
        "SELECT CAST(completed_at/3600 AS INTEGER) AS h, status, COUNT(*) n FROM tasks "
        "WHERE completed_at > ? GROUP BY h, status ORDER BY h", (cutoff,))
    return {"window_hours": window_hours, "events": rows, "tasks": tasks}


@application.get("/analytics/models")
def models_analytics(_: str = Depends(require_owner)) -> dict:
    status = router().status()
    return {"router": status, "usage": router().stats(),
            "fallback_events": int(store.query_one(
                "SELECT COUNT(*) n FROM events WHERE type='model.fallback'")["n"]),
            "deterministic_calls": int(store.get_setting("model_calls_deterministic", 0) or 0)}


@application.get("/analytics/system")
def system(_: str = Depends(require_owner)) -> dict:
    return _system_metrics()


@application.get("/analytics/owner-dashboard")
def owner_dashboard(_: str = Depends(require_owner)) -> dict:
    """The single view the owner actually needs: what is working, what is costing, what needs a decision."""
    econ = economic_summary()
    task_metrics = board.metrics()
    pending = store.query("SELECT id, action, risk, what, ts FROM approvals WHERE status='PENDING' "
                          "ORDER BY ts DESC LIMIT 10")
    top_agents = agent_registry.top_performers(5)
    dept_rows = store.query(
        "SELECT d.name, (SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id AND t.status='DONE') done, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.department_id=d.id AND t.status='FAILED') failed "
        "FROM departments d WHERE d.status='ACTIVE' ORDER BY done DESC LIMIT 8")
    return {
        "generated_at": time.time(),
        "money": econ,
        "work": {"completed": task_metrics["completed"], "failed": task_metrics["failed"],
                 "failure_rate": task_metrics["failure_rate"], "queue": task_metrics["counts"]},
        "needs_your_decision": pending,
        "top_agents": [{"name": a["name"], "role": a["role"], "department": a["department_id"],
                        "performance": a["performance"], "tasks_done": a["tasks_done"]} for a in top_agents],
        "departments": dept_rows,
        "model_state": router().status()["note"],
        "kill_switch": bool(store.get_setting("kill_switch", False)),
        "what_to_do_next": [
            "Review anything in 'needs_your_decision' (default is HOLD, never auto-execute).",
            "If the model line says 'deterministic-only', install Ollama to unlock real reasoning.",
            "Connect an account only when you are ready to act on what it reveals.",
        ],
        "honesty": "Activity is not progress. This dashboard separates the two as far as the data allows.",
    }
