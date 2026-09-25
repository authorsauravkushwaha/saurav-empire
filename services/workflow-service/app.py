"""Workflow Service (port 8005) — task queues, verification, scheduled missions and automations."""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Query

from kernel import store
from kernel.eventbus import E, bus
from kernel.tasks import board
from services.base import ServiceCard, require_owner, service_app

PORT = 8005
CARD = ServiceCard(
    name="workflow-service", port=PORT, layer="B · event-driven core", domain="tasks & workflows",
    description="Task lifecycle, verification rubrics, mission generation and repeatable automations.",
    owns_tables=["tasks"],
    produces_events=["task.*"],
    consumes_events=["agent.*", "economy.*"],
    endpoints=["GET /tasks", "POST /tasks", "POST /tasks/{id}/assign", "POST /tasks/{id}/cancel",
               "POST /tasks/{id}/verify", "GET /tasks/metrics", "GET /missions/templates",
               "GET /automations", "POST /automations/{name}/run"],
    dependencies=["kernel.tasks", "kernel.tools"],
)
application = service_app(CARD)


@application.get("/tasks")
def list_tasks(status: str | None = None, department_id: str | None = None,
               assignee_id: str | None = None, limit: int = Query(100, le=500),
               _: str = Depends(require_owner)) -> dict:
    rows = board.list(status=status, department_id=department_id, assignee_id=assignee_id, limit=limit)
    return {"count": len(rows), "tasks": rows}


@application.get("/tasks/{task_id}")
def get_task(task_id: str, _: str = Depends(require_owner)) -> dict:
    task = board.get(task_id)
    if not task:
        raise HTTPException(404, {"error": "not_found", "detail": f"No task {task_id}"})
    return task


@application.get("/tasks/metrics/summary")
def metrics(_: str = Depends(require_owner)) -> dict:
    return board.metrics()


@application.get("/tasks/metrics")
def metrics_alias(_: str = Depends(require_owner)) -> dict:
    return board.metrics()


@application.post("/tasks")
def create_task(body: dict, _: str = Depends(require_owner)) -> dict:
    return {"task": board.create(title=body.get("title", "Untitled"), description=body.get("description", ""),
                                 task_type=body.get("task_type", "general"),
                                 department_id=body.get("department_id"), created_by="OWNER",
                                 priority=int(body.get("priority", 3)),
                                 payload=body.get("payload") or {},
                                 assignee_id=body.get("assignee_id"))}


@application.post("/tasks/{task_id}/assign")
def assign(task_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        return {"task": board.assign(task_id, body.get("agent_id", ""), by="OWNER")}
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc


@application.post("/tasks/{task_id}/cancel")
def cancel(task_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    task = board.get(task_id)
    if not task:
        raise HTTPException(404, {"error": "not_found", "detail": "Unknown task"})
    store.update("tasks", task_id, {"status": "CANCELLED", "error": (body or {}).get("reason", "cancelled by owner")})
    bus.publish(E.TASK_FAILED, source="workflow-service", subject=task_id, severity="notice",
                payload={"reason": (body or {}).get("reason", "cancelled by owner"), "cancelled": True})
    return {"task": board.get(task_id)}


@application.post("/tasks/{task_id}/verify")
def verify(task_id: str, _: str = Depends(require_owner)) -> dict:
    """Re-run verification on any task. Verification is deterministic first, model second."""
    return {"verification": board.verify(task_id)}


@application.get("/missions/templates")
def templates(_: str = Depends(require_owner)) -> dict:
    from kernel.agent_runtime import MISSION_TEMPLATES
    return {"templates": {dept: [{"title": t, "task_type": tt, "priority": p} for t, tt, p, _ in rows]
                          for dept, rows in MISSION_TEMPLATES.items()}}


@application.get("/automations")
def automations(_: str = Depends(require_owner)) -> dict:
    return {"automations": [
        {"name": "daily-report", "description": "KPI report task to Data & Analytics", "cost_inr": 0},
        {"name": "catalog-audit", "description": "Rank catalog titles by resource-worthiness", "cost_inr": 0},
        {"name": "discovery-scan", "description": "Find zero-capital opportunity candidates", "cost_inr": 0},
        {"name": "university-batch", "description": "Induct trainees and examine those ready", "cost_inr": 0},
        {"name": "free-resource-scan", "description": "Enumerate legal free capability available now", "cost_inr": 0},
        {"name": "memory-maintenance", "description": "Purge expired low-importance memory", "cost_inr": 0},
    ]}


@application.post("/automations/{name}/run")
def run_automation(name: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    started = time.time()
    result: dict
    if name == "daily-report":
        result = {"task": board.create(title="Daily honest KPI report", task_type="report",
                                       department_id="data-analytics", created_by="automation", priority=2)}
    elif name == "catalog-audit":
        result = {"task": board.create(title="Catalog audit: rank titles deserving resources",
                                       task_type="catalog_audit", department_id="publishing-operations",
                                       created_by="automation", priority=2)}
    elif name == "discovery-scan":
        from kernel.economy import opportunities
        opps = opportunities.discover_zero_capital()
        result = {"opportunities_created": len(opps),
                  "titles": [o["title"] for o in opps]}
    elif name == "university-batch":
        from kernel.university import university
        result = {"inducted": university.induct_trainees(limit=6),
                  "graduated": university.graduate_batch(limit=3)}
    elif name == "free-resource-scan":
        from kernel.economy import free_resources
        result = free_resources.scan()
    elif name == "memory-maintenance":
        from kernel.memory import memory
        result = {"purged": memory.purge_expired(), "stats": memory.stats()}
    else:
        raise HTTPException(404, {"error": "unknown_automation", "detail": f"No automation '{name}'",
                                  "available": [a["name"] for a in automations()["automations"]]})
    result["duration_ms"] = int((time.time() - started) * 1000)
    result["cost_inr"] = 0
    bus.publish("automation.ran", source="workflow-service", severity="notice",
                payload={"automation": name, "duration_ms": result["duration_ms"]})
    return result
