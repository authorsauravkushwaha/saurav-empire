"""Economy Service (port 8006) — ledger, opportunities, experiments, lessons, free resources."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from kernel.economy import economic_summary, experiments, free_resources, ledger, opportunities
from services.governance_helpers import chairman
from services.base import ServiceCard, require_owner, service_app

PORT = 8006
CARD = ServiceCard(
    name="economy-service", port=PORT, layer="D · economic engine", domain="economy",
    description="Experiment-driven revenue engine starting from ₹0: verified ledger, opportunity "
                "scoring, ₹0 experiments, learning store and the free-resource scanner.",
    owns_tables=["ledger", "opportunities", "experiments", "lessons"],
    produces_events=["economy.*"],
    consumes_events=["task.*", "model.*"],
    endpoints=["GET /economy/summary", "GET /economy/ledger", "POST /economy/ledger",
               "GET /economy/opportunities", "POST /economy/opportunities",
               "POST /economy/opportunities/{id}/judge", "POST /economy/opportunities/{id}/status",
               "GET /economy/experiments", "POST /economy/experiments",
               "POST /economy/experiments/{id}/measure", "POST /economy/experiments/{id}/decide",
               "GET /economy/lessons", "GET /economy/free-resources",
               "POST /economy/discover"],
    dependencies=["kernel.economy", "kernel.governance (chairman)"],
)
application = service_app(CARD)


@application.get("/economy/summary")
def summary(_: str = Depends(require_owner)) -> dict:
    return economic_summary()


@application.get("/economy/ledger")
def get_ledger(limit: int = Query(200, le=1000), _: str = Depends(require_owner)) -> dict:
    rows = ledger.kpis()
    rows["entries"] = [dict(e, evidence=__import__("kernel.store", fromlist=["x"]).jload(
        e.get("evidence_json"), {})) for e in
        __import__("kernel.store", fromlist=["x"]).query(
            "SELECT * FROM ledger ORDER BY ts DESC LIMIT ?", (limit,))]
    for e in rows["entries"]:
        e.pop("evidence_json", None)
    return rows


@application.post("/economy/ledger")
def record_ledger(body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        row = ledger.record(direction=body.get("direction", "OUT"),
                            amount_inr=float(body.get("amount_inr", 0)),
                            category=body.get("category", "uncategorised"),
                            description=body.get("description", ""),
                            source=body.get("source", "owner entry"),
                            verified=bool(body.get("verified", False)),
                            evidence=body.get("evidence") or {},
                            recorded_by="OWNER")
    except ValueError as exc:
        raise HTTPException(400, {"error": "ledger_refused", "detail": str(exc)}) from exc
    return {"entry": row,
            "rules": ["Direction IN with verification requires a source and evidence.",
                      "Unverified income is refused outright — that refusal is the feature."]}


@application.get("/economy/opportunities")
def list_opportunities(status: str | None = None, limit: int = Query(50, le=200),
                       _: str = Depends(require_owner)) -> dict:
    return {"opportunities": opportunities.list(status=status, limit=limit),
            "statuses": ["DISCOVERED", "VALIDATING", "REJECTED", "MVP", "TESTING", "FIRST_REVENUE",
                         "GROWING", "SCALING", "AUTOMATED", "PAUSED", "KILLED"]}


@application.post("/economy/opportunities")
def create_opportunity(body: dict, _: str = Depends(require_owner)) -> dict:
    return {"opportunity": opportunities.create(
        title=body.get("title", "Untitled opportunity"),
        problem=body.get("problem", ""), customer=body.get("customer", ""),
        market=body.get("market", "unspecified"), competition=body.get("competition", "unassessed"),
        required_skills=body.get("required_skills") or [],
        required_capital_inr=float(body.get("required_capital_inr", 0) or 0),
        expected_revenue_inr=float(body.get("expected_revenue_inr", 0) or 0),
        expected_margin_pct=float(body.get("expected_margin_pct", 0) or 0),
        time_to_mvp_days=body.get("time_to_mvp_days"),
        time_to_first_customer_days=body.get("time_to_first_customer_days"),
        risk=body.get("risk", "MEDIUM"), legal_risk=body.get("legal_risk", "LOW"),
        technical_risk=body.get("technical_risk", "MEDIUM"),
        demand_confidence=float(body.get("demand_confidence", 0.3)),
        model_confidence=float(body.get("model_confidence", 0.3)),
        evidence=body.get("evidence") or [], owner_agent=body.get("owner_agent"))}


@application.post("/economy/opportunities/{opp_id}/judge")
def judge(opp_id: str, body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    try:
        return opportunities.judge(opp_id, facts=(body or {}).get("facts"),
                                   unknowns=(body or {}).get("unknowns"))
    except ValueError as exc:
        raise HTTPException(404, {"error": "not_found", "detail": str(exc)}) from exc


@application.post("/economy/opportunities/{opp_id}/status")
def set_status(opp_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        return {"opportunity": opportunities.set_status(opp_id, body.get("status", "PAUSED"),
                                                        reason=body.get("reason", ""), by="OWNER")}
    except ValueError as exc:
        raise HTTPException(400, {"error": "bad_status", "detail": str(exc)}) from exc


@application.get("/economy/experiments")
def list_experiments(status: str | None = None, _: str = Depends(require_owner)) -> dict:
    return {"experiments": experiments.list(status=status)}


@application.post("/economy/experiments")
def create_experiment(body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        row = experiments.create(hypothesis=body.get("hypothesis", ""),
                                 expected_result=body.get("expected_result", ""),
                                 mvp_definition=body.get("mvp_definition", ""),
                                 test_method=body.get("test_method", ""),
                                 success_metric=body.get("success_metric", ""),
                                 kill_metric=body.get("kill_metric", ""),
                                 opportunity_id=body.get("opportunity_id"),
                                 cost_inr=float(body.get("cost_inr", 0) or 0))
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc
    return {"experiment": row,
            "discipline": "One hypothesis, one metric, one kill criterion, ₹0 cost."}


@application.post("/economy/experiments/{exp_id}/measure")
def measure(exp_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    return {"experiment": experiments.measure(exp_id, observed=body.get("observed") or {},
                                              notes=body.get("notes", ""))}


@application.post("/economy/experiments/{exp_id}/decide")
def decide(exp_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        return {"experiment": experiments.decide(exp_id, body.get("decision", "KILL"),
                                                 learning=body.get("learning", ""), by="OWNER")}
    except ValueError as exc:
        raise HTTPException(400, {"error": "bad_decision", "detail": str(exc)}) from exc


@application.get("/economy/lessons")
def lessons(limit: int = Query(100, le=500), _: str = Depends(require_owner)) -> dict:
    from kernel import store
    rows = store.query("SELECT * FROM lessons ORDER BY ts DESC LIMIT ?", (limit,))
    for r in rows:
        r["tags"] = store.jload(r.pop("tags_json", None), [])
    return {"count": len(rows), "lessons": rows}


@application.get("/economy/free-resources")
def resources(scan: bool = True, _: str = Depends(require_owner)) -> dict:
    data = {"catalogue": free_resources.catalogue()}
    if scan:
        data["scan"] = free_resources.scan()
    return data


@application.post("/economy/discover")
def discover(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    created = opportunities.discover_zero_capital(owner_agent=(body or {}).get("owner_agent"))
    return {"created": len(created), "opportunities": created,
            "note": "Every generated candidate is labelled ASSUMPTION until a customer says otherwise."}


@application.get("/economy/decide")
def decide_endpoint(question: str, _: str = Depends(require_owner)) -> dict:
    """Run the 8-MIND engine + chairman over an arbitrary owner question (no numbers supplied)."""
    return chairman.decide(question=question, facts=[], assumptions=[], unknowns=[
        "Whether the buyer will pay", "Whether the channel reaches them"]).to_dict()
