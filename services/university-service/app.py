"""University Service (port 8007) — the training pipeline that produces the workforce."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from kernel import store
from kernel.university import TRACKS, university
from services.base import ServiceCard, require_owner, service_app

PORT = 8007
CARD = ServiceCard(
    name="university-service", port=PORT, layer="C · agent organization", domain="university",
    description="RECRUIT → TEST → EDUCATE → PRACTICE → EXAM → CERTIFY → SPECIALIZE → GRADUATE → JOB MATCHING.",
    owns_tables=["exams"],
    produces_events=["university.*", "university.job_matched"],
    consumes_events=["task.*"],
    endpoints=["GET /university/status", "GET /university/tracks", "POST /university/enroll",
               "POST /university/{agent_id}/coursework", "POST /university/{agent_id}/exam",
               "POST /university/{agent_id}/match-job", "POST /university/induct",
               "POST /university/graduate-batch", "GET /university/exams"],
    dependencies=["kernel.university", "model-service (optional — exams are limited without a model)"],
)
application = service_app(CARD)


@application.get("/university/status")
def status(_: str = Depends(require_owner)) -> dict:
    data = university.status()
    from kernel.model_router import router
    data["model_available"] = bool(router().status().get("reachable"))
    data["caveat"] = (None if data["model_available"] else
                      "No local model: knowledge, reasoning, ethics and hallucination resistance "
                      "cannot be examined. Certifications are limited to tool and evidence discipline "
                      "and are stamped accordingly.")
    return data


@application.get("/university/tracks")
def tracks(_: str = Depends(require_owner)) -> dict:
    return {"tracks": TRACKS}


@application.get("/university/exams")
def exams(limit: int = Query(50, le=300), _: str = Depends(require_owner)) -> dict:
    rows = store.query("SELECT * FROM exams ORDER BY ts DESC LIMIT ?", (limit,))
    for r in rows:
        r["scores"] = store.jload(r.pop("scores_json", None), {})
        r["assessed"] = store.jload(r.pop("assessed_json", None), {})
    return {"count": len(rows), "exams": rows}


@application.post("/university/enroll")
def enroll(body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        return university.enroll(body.get("agent_id", ""), body.get("track"))
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc


@application.post("/university/{agent_id}/coursework")
def coursework(agent_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    try:
        tasks = university.start_coursework(agent_id, max_subjects=int((body or {}).get("max_subjects", 3)))
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc
    return {"tasks": [{"id": t["id"], "title": t["title"], "status": t["status"]} for t in tasks]}


@application.post("/university/{agent_id}/exam")
def exam(agent_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    try:
        return university.run_exam(agent_id, (body or {}).get("track"))
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc


@application.post("/university/{agent_id}/match-job")
def match(agent_id: str, _: str = Depends(require_owner)) -> dict:
    try:
        return university.match_jobs(agent_id)
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc


@application.post("/university/induct")
def induct(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    return {"inducted": university.induct_trainees(limit=int((body or {}).get("limit", 8)))}


@application.post("/university/graduate-batch")
def graduate(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    return {"results": university.graduate_batch(limit=int((body or {}).get("limit", 5)))}
