"""World Service (port 8013) — the 3D world's only source of truth.

Everything the React Three Fiber client renders comes from here: buildings, agent positions,
statuses, occupancy and the visual-analytics mapping of business metrics onto the environment.
"""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Query

from kernel import store, world_layout
from kernel.agent_runtime import runtime, runtime_snapshot
from kernel.config import building_index, city_index, config
from kernel.registry import agents as agent_registry
from kernel.registry import departments as dept_registry
from kernel.tasks import board
from services.base import ServiceCard, require_owner, service_app

PORT = 8013
CARD = ServiceCard(
    name="world-service", port=PORT, layer="A · 3D civilization", domain="world",
    description="World layout, live agent positions, occupancy and visual analytics for the 3D client.",
    owns_tables=["agents (positions only)"],
    produces_events=["world.snapshot"],
    consumes_events=["agent.*", "task.*"],
    endpoints=["GET /world/layout", "GET /world/state", "GET /world/agent/{id}",
               "GET /world/analytics", "GET /world/buildings", "POST /world/tick"],
    dependencies=["kernel.world_layout", "kernel.registry"],
)
application = service_app(CARD)

STATUS_COLORS = {
    "IDLE": "#8b93a7", "TRAVELING": "#60a5fa", "WORKING": "#22d3ee", "ANALYZING": "#a78bfa",
    "RESEARCHING": "#34d399", "CODING": "#fbbf24", "LEARNING": "#38bdf8", "WAITING": "#94a3b8",
    "NEGOTIATING": "#f472b6", "PUBLISHING": "#fb923c", "SELLING": "#4ade80", "ERROR": "#ef4444",
    "BLOCKED": "#f97316", "ESCALATED": "#dc2626", "COMPLETED": "#10b981",
}


@application.get("/world/layout")
def layout(_: str = Depends(require_owner)) -> dict:
    data = world_layout.layout()
    data["status_colors"] = STATUS_COLORS
    data["generated_at"] = time.time()
    return data


@application.get("/world/state")
def state(limit: int = Query(2000, le=4000), _: str = Depends(require_owner)) -> dict:
    """Snapshot for the 3D client. Positions come from the backend, never from the renderer."""
    rows = agent_registry.list(limit=limit)
    depts = {d["id"]: d for d in dept_registry.list()}
    counts: dict[str, int] = {}
    for a in rows:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    return {
        "generated_at": time.time(),
        "agents": [{
            "id": a["id"], "name": a["name"], "role": a["role"], "rank": a["rank"],
            "department": a["department_id"],
            "department_name": (depts.get(a["department_id"]) or {}).get("name"),
            "status": a["status"], "color": STATUS_COLORS.get(a["status"], "#8b93a7"),
            "position": a["position"], "building": a["building"], "target_building": a["target_building"],
            "active_task": a["active_task_id"], "energy": a["energy"],
            "performance": a["performance"], "reliability": a["reliability"],
            "certs": a["certs"][:3], "model_tier": a["model_tier"],
        } for a in rows],
        "status_counts": counts,
        **{k: v for k, v in runtime_snapshot().items() if k in ("running", "tick", "age_seconds")},
    }


@application.get("/world/agent/{agent_id}")
def inspect(agent_id: str, _: str = Depends(require_owner)) -> dict:
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(404, {"error": "not_found", "detail": f"No agent {agent_id}"})
    dept = dept_registry.get(agent.get("department_id") or "") if agent.get("department_id") else None
    tasks = board.list(assignee_id=agent_id, limit=20)
    audit_rows = store.query("SELECT ts, action, tool, risk, allowed, reason FROM audit WHERE actor=? "
                             "ORDER BY id DESC LIMIT 20", (agent["name"],))
    memory_rows = store.query("SELECT ts, layer, key, substr(content,1,240) AS content, evidence_kind, "
                              "confidence, importance FROM memory WHERE agent_id=? "
                              "ORDER BY ts DESC LIMIT 15", (agent_id,))
    return {
        "agent": agent,
        "department": dept,
        "tasks": [{k: t[k] for k in ("id", "title", "status", "task_type", "priority",
                                     "created_at", "completed_at")} for t in tasks],
        "recent_actions": audit_rows,
        "recent_memory": memory_rows,
        "location": world_layout.building_world_pos(agent.get("building") or "owner-command-center"),
        "manager": agent_registry.get(agent["manager_id"]) if agent.get("manager_id") else None,
        "reports": agent_registry.list(limit=50).__len__() and [a["name"] for a in agent_registry.list(limit=200)
                                                               if a["manager_id"] == agent_id][:20],
    }


@application.get("/world/buildings")
def buildings(_: str = Depends(require_owner)) -> dict:
    idx = building_index()
    occupancy: dict[str, int] = {}
    for row in store.query("SELECT building, COUNT(*) n FROM agents WHERE lifecycle != 'TERMINATED' "
                           "GROUP BY building"):
        if row["building"]:
            occupancy[row["building"]] = row["n"]
    depts_by_building: dict[str, list] = {}
    for d in dept_registry.list():
        depts_by_building.setdefault(d["building"], []).append({"id": d["id"], "name": d["name"],
                                                                "headcount": d["headcount"]})
    return {"count": len(idx), "buildings": [
        {**world_layout.building_world_pos(bid), "occupancy": occupancy.get(bid, 0),
         "departments": depts_by_building.get(bid, [])} for bid in idx]}


@application.get("/world/analytics")
def visual_analytics(_: str = Depends(require_owner)) -> dict:
    """Business metrics expressed as environment: activity intensity, revenue state, warnings."""
    dept_rows = dept_registry.list()
    tasks_by_dept = {r["department_id"]: r for r in store.query(
        "SELECT department_id, COUNT(*) n, SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) done, "
        "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) failed FROM tasks "
        "WHERE department_id IS NOT NULL GROUP BY department_id")}
    agents_by_dept = {r["department_id"]: r["n"] for r in store.query(
        "SELECT department_id, COUNT(*) n FROM agents WHERE lifecycle != 'TERMINATED' "
        "AND department_id IS NOT NULL GROUP BY department_id")}
    revenue = float(store.query_one(
        "SELECT COALESCE(SUM(amount_inr),0) s FROM ledger WHERE direction='IN' AND verified=1")["s"] or 0)
    approvals_pending = int(store.query_one(
        "SELECT COUNT(*) n FROM approvals WHERE status='PENDING'")["n"])
    errors = int(store.query_one(
        "SELECT COUNT(*) n FROM events WHERE severity IN ('error','critical') AND ts > ?",
        (time.time() - 3600,))["n"])

    city_activity: dict[str, dict] = {}
    buildings_out = []
    for dept in dept_rows:
        t = tasks_by_dept.get(dept["id"], {})
        done = int(t.get("done") or 0)
        total = int(t.get("n") or 0)
        intensity = round(min(1.0, (done * 2 + total) / 40), 3)
        city = dept["city"]
        city_activity.setdefault(city, {"intensity": 0.0, "departments": 0, "agents": 0, "tasks": 0})
        c = city_activity[city]
        c["intensity"] = round(min(1.0, c["intensity"] + intensity / 3), 3)
        c["departments"] += 1
        c["agents"] += int(agents_by_dept.get(dept["id"], 0))
        c["tasks"] += total
        buildings_out.append({
            "building": dept["building"], "department": dept["id"], "city": city,
            "activity_intensity": intensity,
            "health": ("warning" if int(t.get("failed") or 0) > int(done) else
                       "active" if done else "quiet"),
            "tasks_open": total - done, "tasks_done": done,
            "headcount": int(agents_by_dept.get(dept["id"], 0)),
        })
    return {
        "revenue_state": {"verified_revenue_inr": revenue,
                          "visual": "dormant" if revenue <= 0 else "growing",
                          "honesty": "₹0 revenue renders as a dormant economy — not as growth."},
        "system_warnings": {"pending_approvals": approvals_pending, "recent_errors_1h": errors,
                            "kill_switch": bool(store.get_setting("kill_switch", False)),
                            "safe_mode": bool(store.get_setting("safe_mode", False))},
        "cities": city_activity,
        "buildings": buildings_out,
        "generated_at": time.time(),
    }


@application.post("/world/tick")
def tick(_: str = Depends(require_owner)) -> dict:
    stats = runtime().tick()
    return {"tick": stats.tick, "travelers": stats.travelers, "assigned": stats.assigned,
            "executed": stats.executed, "generated": stats.generated, "duration_ms": stats.duration_ms}
