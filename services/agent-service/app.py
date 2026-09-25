"""Agent Service (port 8001) — identity, hierarchy, lifecycle, and the Department Factory."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Query

from kernel import store
from kernel.eventbus import E, bus
from kernel.governance import audit, permissions
from kernel.registry import agents as agent_registry
from kernel.registry import bootstrap_organization
from kernel.registry import departments as dept_registry
from kernel.tasks import board
from kernel.university import university
from services.base import ServiceCard, require_owner, service_app

PORT = 8001
RUNTIME_AUTOSTART = os.environ.get("EMPIRE_RUNTIME_AUTOSTART", "true").strip().lower() in ("1", "true", "yes", "on")
CARD = ServiceCard(
    name="agent-service", port=PORT, layer="C · agent organization", domain="agents & departments",
    description="Agent registry (identity, hierarchy, status, metrics) and the dynamic Department Factory.",
    owns_tables=["agents", "departments"],
    produces_events=["agent.*", "department.*"],
    consumes_events=["task.*", "university.*"],
    endpoints=["GET /agents", "GET /agents/{id}", "POST /agents/hire", "POST /agents/{id}/promote",
               "POST /agents/{id}/suspend", "POST /agents/{id}/assign", "POST /agents/{id}/retrain",
               "GET /departments", "POST /departments", "GET /departments/tree",
               "POST /departments/{id}/hire", "POST /departments/{id}/dissolve",
               "GET /runtime", "POST /runtime/start", "POST /runtime/stop", "POST /bootstrap"],
    dependencies=["kernel.registry", "kernel.agent_runtime"],
)
application = service_app(CARD)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
@application.get("/agents")
def list_agents(department_id: str | None = None, rank: str | None = None, status: str | None = None,
                lifecycle: str | None = None, limit: int = Query(200, le=2000),
                _: str = Depends(require_owner)) -> dict:
    rows = agent_registry.list(department_id=department_id, rank=rank, status=status,
                               lifecycle=lifecycle, limit=limit)
    return {"count": len(rows), "agents": rows, "summary": agent_registry.counts()}


@application.get("/agents/counts")
def counts(_: str = Depends(require_owner)) -> dict:
    return agent_registry.counts()


@application.get("/agents/summary")
def summary(_: str = Depends(require_owner)) -> dict:
    return agent_registry.counts()


@application.get("/agents/org-chart")
def org_chart(_: str = Depends(require_owner)) -> dict:
    return agent_registry.org_chart()


@application.get("/agents/top")
def top(limit: int = Query(10, le=50), _: str = Depends(require_owner)) -> dict:
    return {"top": agent_registry.top_performers(limit)}


@application.get("/agents/{agent_id}")
def get_agent(agent_id: str, _: str = Depends(require_owner)) -> dict:
    agent = agent_registry.get(agent_id) or agent_registry.by_name(agent_id)
    if not agent:
        raise HTTPException(404, {"error": "not_found", "detail": f"No agent '{agent_id}'"})
    return agent


@application.post("/agents/hire")
def hire(body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        agent = agent_registry.hire(
            role=body.get("role", "Operator"), rank=body.get("rank", "AGENT"),
            department_id=body.get("department_id"),
            name=body.get("name") or None,           # None → naming subsystem picks a unique name
            manager_id=body.get("manager_id"), model_tier=body.get("model_tier", "nano"),
            skills=body.get("skills") or {}, building=body.get("building"),
        )
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc
    return {"agent": agent, "note": "Hiring is free — the cost is local compute and attention."}


@application.post("/agents/{agent_id}/assign")
def assign_task(agent_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(404, {"error": "not_found", "detail": "Unknown agent"})
    task = board.create(title=body.get("title", "Untitled task"),
                        description=body.get("description", ""),
                        task_type=body.get("task_type", "general"),
                        department_id=agent.get("department_id"),
                        created_by="OWNER", priority=int(body.get("priority", 3)),
                        assignee_id=agent_id, payload=body.get("payload") or {})
    return {"task": task, "agent": agent["name"],
            "note": "The agent will travel to its building, work, verify, and report."}


@application.post("/agents/{agent_id}/promote")
def promote(agent_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        return {"agent": agent_registry.promote(agent_id, body.get("rank", "MANAGER"),
                                                reason=body.get("reason", "owner decision"))}
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc


@application.post("/agents/{agent_id}/suspend")
def suspend(agent_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    return {"agent": agent_registry.suspend(agent_id, (body or {}).get("reason", "owner decision"))}


@application.post("/agents/{agent_id}/reinstate")
def reinstate(agent_id: str, _: str = Depends(require_owner)) -> dict:
    return {"agent": agent_registry.reinstate(agent_id)}


@application.post("/agents/{agent_id}/terminate")
def terminate(agent_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    return {"agent": agent_registry.terminate(agent_id, (body or {}).get("reason", "owner decision"))}


@application.post("/agents/{agent_id}/retrain")
def retrain(agent_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    track = (body or {}).get("track")
    return {"enrolment": university.enroll(agent_id, track),
            "coursework": len(university.start_coursework(agent_id))}


@application.post("/agents/{agent_id}/pause")
def pause(agent_id: str, _: str = Depends(require_owner)) -> dict:
    return {"agent": agent_registry.suspend(agent_id, "paused by owner (memory and rank retained)")}


# ---------------------------------------------------------------------------
# Departments (dynamic factory — no hard-coded maximum)
# ---------------------------------------------------------------------------
@application.get("/departments")
def list_departments(status: str | None = None, _: str = Depends(require_owner)) -> dict:
    return {"departments": dept_registry.list(status=status)}


@application.get("/departments/tree")
def tree(_: str = Depends(require_owner)) -> dict:
    return {"tree": dept_registry.tree()}


@application.get("/departments/{dept_id}")
def get_department(dept_id: str, _: str = Depends(require_owner)) -> dict:
    dept = dept_registry.get(dept_id)
    if not dept:
        raise HTTPException(404, {"error": "not_found", "detail": f"No department '{dept_id}'"})
    dept["staff"] = [{"id": a["id"], "name": a["name"], "role": a["role"], "rank": a["rank"],
                      "status": a["status"], "performance": a["performance"]}
                     for a in agent_registry.list(department_id=dept_id, limit=200)]
    dept["open_tasks"] = len(board.list(status="QUEUED", department_id=dept_id, limit=100))
    return dept


@application.post("/departments")
def create_department(body: dict, _: str = Depends(require_owner)) -> dict:
    """CREATE_DEPARTMENT(name, objective, boss, budget, permissions, tools, KPIs, parent)."""
    try:
        dept = dept_registry.create(
            name=body.get("name", "Unnamed Department"),
            objective=body.get("objective", ""),
            kpis=body.get("kpis") or [],
            city=body.get("city", "command"),
            building=body.get("building", "mission-control"),
            parent_id=body.get("parent_department"),
            kind=body.get("kind", "department"),
            boss_name=body.get("boss"),
            budget_inr=float(body.get("budget", 0) or 0),
            permissions=body.get("permissions") or [],
            tools=body.get("tools") or [],
            consumer_of=body.get("consumer_of", "internal"),
            producer_for=body.get("producer_for", "internal"),
            kill_criteria=body.get("kill_criteria"),
            created_by="OWNER",
            requested_id=body.get("id"),
            meta={"created_via": "api"},
        )
    except ValueError as exc:
        raise HTTPException(400, {"error": "department_rejected", "detail": str(exc)}) from exc
    return {"department": dept,
            "provisioned": ["workspace", "db namespace", "analytics namespace", "task queue",
                            "memory namespace", "comms channel", "KPI dashboard", "security policy",
                            "budget", "boss", "reporting line"]}


@application.post("/departments/{dept_id}/hire")
def hire_into(dept_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    body = body or {}
    try:
        out = dept_registry.hire_workforce(dept_id, int(body.get("specialists", 2)),
                                          int(body.get("trainees", 1)), body.get("roles"))
    except ValueError as exc:
        raise HTTPException(404, {"error": "not_found", "detail": str(exc)}) from exc
    return {"hired": len(out["specialists"]), "trainees": len(out["trainees"]),
            "specialists": [a["name"] for a in out["specialists"]],
            "trainees": [a["name"] for a in out["trainees"]]}


@application.post("/departments/{dept_id}/dissolve")
def dissolve(dept_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    try:
        return {"department": dept_registry.dissolve(dept_id, (body or {}).get("reason", "owner decision"))}
    except ValueError as exc:
        raise HTTPException(404, {"error": "not_found", "detail": str(exc)}) from exc


# ---------------------------------------------------------------------------
# Runtime control
# ---------------------------------------------------------------------------
@application.get("/runtime")
def runtime_status(_: str = Depends(require_owner)) -> dict:
    from kernel.agent_runtime import runtime as rt
    return rt().status()


@application.post("/runtime/start")
def runtime_start(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    from kernel.agent_runtime import AgentRuntime
    from kernel import agent_runtime as mod
    tick = (body or {}).get("tick_seconds")
    if mod._runtime is None:
        mod._runtime = AgentRuntime(tick_seconds=tick)
    return mod._runtime.start()


@application.post("/runtime/stop")
def runtime_stop(_: str = Depends(require_owner)) -> dict:
    from kernel.agent_runtime import runtime as rt
    return rt().stop()


@application.post("/bootstrap")
def bootstrap(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    force = bool((body or {}).get("force"))
    return bootstrap_organization(force=force)


@application.get("/permissions/check")
def permission_check(rank: str, tool: str, _: str = Depends(require_owner)) -> dict:
    return permissions.check(actor="owner-check", rank=rank, tool=tool).as_dict()


@application.get("/audit/denials")
def denials(limit: int = Query(50, le=500), _: str = Depends(require_owner)) -> dict:
    rows = store.query("SELECT ts, actor, actor_rank, tool, risk, target, reason FROM audit "
                       "WHERE allowed=0 ORDER BY id DESC LIMIT ?", (limit,))
    return {"count": len(rows), "denials": rows}


@application.post("/events/test")
def emit_test_event(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    """Diagnostic: proves the event → WebSocket → 3D path is alive."""
    ev = bus.publish(E.AGENT_STATUS, source="agent-service",
                     subject=(body or {}).get("agent_id", "diagnostic"),
                     payload={"to": "WORKING", "reason": "owner connectivity test"})
    audit("OWNER", "events.test", target=str(ev.id), allowed=True, actor_rank="OWNER")
    return {"published": True, "event_id": ev.id}


# ---------------------------------------------------------------------------
# The agent runtime lives in exactly one process: this one.
# It drives the loop the 3D world visualises (travel → work → verify → report → learn).
# ---------------------------------------------------------------------------
@application.on_event("startup")
def _start_runtime() -> None:
    if not RUNTIME_AUTOSTART:
        return
    from kernel import store
    from kernel.agent_runtime import runtime as rt
    if store.get_setting("kill_switch", False):
        bus.publish("runtime.blocked", source="agent-service", severity="warning",
                    payload={"reason": "Kill switch is engaged — runtime will not autostart."})
        return
    result = rt().start()
    bus.publish("runtime.autostart", source="agent-service", severity="notice",
                payload={"result": result, "note": "Agents will now travel, work, verify and learn."})


@application.on_event("shutdown")
def _stop_runtime() -> None:
    from kernel.agent_runtime import runtime as rt
    try:
        rt().stop()
    except Exception:
        pass
