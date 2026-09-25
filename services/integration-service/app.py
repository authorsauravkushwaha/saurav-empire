"""Integration Service (port 8009) — one connector per platform, official APIs, approval-gated writes."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from kernel import store
from kernel.integrations import CONNECTORS, describe_all, health_check_all, status_all
from kernel.killswitch import external_frozen
from services.base import ServiceCard, require_owner, service_app

PORT = 8009
CARD = ServiceCard(
    name="integration-service", port=PORT, layer="B · external boundary", domain="integrations",
    description="Gmail, YouTube, Instagram, Facebook, WhatsApp, Gumroad and public-web connectors. "
                "Reads only by default; writes/publishes/sends are approval-gated. Disconnected "
                "connectors do nothing and say so.",
    owns_tables=["integrations"],
    produces_events=["integration.status", "integration.call", "governance.approval_requested"],
    consumes_events=["governance.approval_decided"],
    endpoints=["GET /integrations", "GET /integrations/{id}", "POST /integrations/{id}/probe",
               "GET /integrations/health", "POST /integrations/{id}/read",
               "POST /integrations/{id}/request-action", "POST /integrations/health-check-all"],
    dependencies=["kernel.integrations", "kernel.crypto (credential handling)"],
)
application = service_app(CARD)

READ_ACTIONS = {
    "gmail": ["list_unread"],
    "youtube": ["channel_stats", "analyze_titles"],
    "instagram": ["media_insights"],
    "facebook": ["page_insights"],
    "gumroad": ["products", "sales"],
    "web": ["fetch_public_page"],
    "whatsapp": ["webhook_summary"],
}

REFUSALS = {
    "instagram": ["publish", "mass_dm", "engagement_fraud"],
    "facebook": ["publish"],
    "whatsapp": ["send_template", "broadcast"],
    "youtube": ["upload"],
    "gmail": ["send"],
    "gumroad": ["update_product"],
    "web": ["search"],
}


@application.get("/integrations")
def list_integrations(_: str = Depends(require_owner)) -> dict:
    return {"connectors": status_all(), "describe": describe_all(),
            "frozen": external_frozen(),
            "principle": "Nothing is simulated. No credentials means no data and no action."}


@application.get("/integrations/health")
def health(_: str = Depends(require_owner)) -> dict:
    return {"health": health_check_all(),
            "rule": "Health is only claimed after a successful live call."}


@application.post("/integrations/health-check-all")
def health_all(_: str = Depends(require_owner)) -> dict:
    return {"health": health_check_all()}


@application.get("/integrations/{connector_id}")
def describe(connector_id: str, _: str = Depends(require_owner)) -> dict:
    if connector_id not in CONNECTORS:
        raise HTTPException(404, {"error": "not_found", "detail": f"No connector '{connector_id}'",
                                  "available": list(CONNECTORS)})
    c = CONNECTORS[connector_id]
    return {"description": c.describe(), "status": c.status(),
            "read_actions": READ_ACTIONS.get(connector_id, []),
            "refused_by_policy": REFUSALS.get(connector_id, [])}


@application.post("/integrations/{connector_id}/probe")
def probe(connector_id: str, _: str = Depends(require_owner)) -> dict:
    if connector_id not in CONNECTORS:
        raise HTTPException(404, {"error": "not_found", "detail": "Unknown connector"})
    return CONNECTORS[connector_id].probe()


@application.post("/integrations/{connector_id}/read")
def read(connector_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    """Execute a read-only capability. Writes are impossible here — they belong to the approval path."""
    connector = CONNECTORS.get(connector_id)
    if not connector:
        raise HTTPException(404, {"error": "not_found", "detail": "Unknown connector"})
    action = body.get("action", "")
    if action in REFUSALS.get(connector_id, []):
        return {"status": "REFUSED_BY_POLICY", "connector": connector_id, "action": action,
                "reason": "This action is refused by design, regardless of credentials.",
                "why": "The constitution forbids spam, deception, engagement fraud and unattended publishing."}
    if action not in READ_ACTIONS.get(connector_id, []):
        raise HTTPException(400, {"error": "unknown_action", "detail": f"Allowed reads: "
                                  f"{READ_ACTIONS.get(connector_id, [])}"})
    fn = getattr(connector, action, None)
    if fn is None:
        raise HTTPException(400, {"error": "not_implemented", "detail": f"{action} is not implemented"})
    try:
        kwargs = {k: v for k, v in (body.get("args") or {}).items()}
        return fn(**kwargs)
    except TypeError as exc:
        raise HTTPException(400, {"error": "bad_args", "detail": str(exc)}) from exc


@application.post("/integrations/{connector_id}/request-action")
def request_action(connector_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    """Queue a HIGH-risk external action for owner approval. Nothing executes here."""
    connector = CONNECTORS.get(connector_id)
    if not connector:
        raise HTTPException(404, {"error": "not_found", "detail": "Unknown connector"})
    action = body.get("action", "")
    if action in REFUSALS.get(connector_id, []):
        return {"status": "REFUSED_BY_POLICY", "connector": connector_id, "action": action,
                "reason": "Refused by design.", "why": "Forbidden tactic."}
    approval = connector.request_approval(
        action=action,
        what=body.get("what", f"{connector_id}:{action}"),
        why=body.get("why", "Not stated — an approval without a reason should be rejected."),
        expected_result=body.get("expected_result", "Not stated."),
        risk_notes=body.get("risk_notes", "Not stated."),
        reversibility=body.get("reversibility", "Unknown — assume irreversible until stated."),
        evidence=body.get("evidence") or [],
        requester=body.get("requester", "integration-agent"),
        department_id=body.get("department_id"),
        payload=body.get("payload") or {},
    )
    return {"approval": approval, "executed": False,
            "note": "Approval is consent, not execution. A separate, explicit step performs the action."}


@application.get("/integrations/quota")
def quota(_: str = Depends(require_owner)) -> dict:
    rows = store.query("SELECT id, status, calls_today, last_error, quota_note FROM integrations")
    counters = {r["id"]: int(store.get_setting(f"integration_calls::{r['id']}", 0) or 0) for r in rows}
    return {"quota": rows, "lifetime_call_counters": counters,
            "rule": "Free tiers are respected. Rate limits are never evaded — that is unauthorized access."}
