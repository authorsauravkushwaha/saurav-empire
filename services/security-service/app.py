"""Security Service (port 8011) — audit, approvals, permissions, injection defence, kill switch."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from kernel import store
from kernel.config import config
from kernel.crypto import vault
from kernel.governance import approvals, audit, injection, kill_switch_engaged, permissions, safe_mode
from kernel.killswitch import disengage, engage, enter_safe_mode, exit_safe_mode, status as ks_status
from services.base import ServiceCard, require_owner, service_app

PORT = 8011
CARD = ServiceCard(
    name="security-service", port=PORT, layer="E · governance & security", domain="security",
    description="Permission engine, approval queue, immutable audit trail, prompt-injection defence, "
                "secret vault status and the emergency kill switch.",
    owns_tables=["audit", "approvals"],
    produces_events=["governance.*", "civilization.killswitch", "civilization.safe_mode"],
    consumes_events=["integration.*", "agent.*"],
    endpoints=["GET /security/audit", "GET /security/approvals", "POST /security/approvals/{id}/decide",
               "POST /security/permissions/check", "GET /security/killswitch",
               "POST /security/killswitch/engage", "POST /security/killswitch/disengage",
               "POST /security/safe-mode", "POST /security/injection/scan", "GET /security/vault",
               "GET /security/self-check"],
    dependencies=["kernel.governance", "kernel.killswitch", "kernel.crypto"],
)
application = service_app(CARD)


@application.get("/security/audit")
def read_audit(limit: int = Query(200, le=2000), actor: str | None = None,
               allowed: bool | None = None, _: str = Depends(require_owner)) -> dict:
    clauses, params = [], []
    if actor:
        clauses.append("actor=?"); params.append(actor)
    if allowed is not None:
        clauses.append("allowed=?"); params.append(int(allowed))
    sql = "SELECT * FROM audit" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = store.query(sql, tuple(params))
    for r in rows:
        r["payload"] = store.jload(r.pop("payload_json", None), {})
    return {"count": len(rows), "entries": rows,
            "note": "Audit entries are append-only. Nothing in this system can rewrite history."}


@application.get("/security/approvals")
def list_approvals(status: str = Query("PENDING"), limit: int = Query(100, le=500),
                   _: str = Depends(require_owner)) -> dict:
    if status == "PENDING":
        rows = approvals.pending(limit)
    else:
        rows = store.query("SELECT * FROM approvals WHERE status=? ORDER BY ts DESC LIMIT ?",
                           (status, limit))
        for r in rows:
            r["evidence"] = store.jload(r.pop("evidence_json", None), [])
            r["payload"] = store.jload(r.pop("payload_json", None), {})
    return {"count": len(rows), "approvals": rows,
            "rule": "Unanswered approvals default to HOLD. Nothing irreversible executes silently."}


@application.post("/security/approvals/{approval_id}/decide")
def decide(approval_id: str, body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        row = approvals.decide(approval_id, body.get("decision", "REJECT"),
                               note=body.get("note", ""), edited_payload=body.get("edited_payload"))
    except ValueError as exc:
        raise HTTPException(400, {"error": "bad_decision", "detail": str(exc)}) from exc
    if not row:
        raise HTTPException(404, {"error": "not_found", "detail": "No such approval"})
    if row["status"] == "APPROVED" and row.get("tool", "").startswith("integration."):
        # Approval records the owner's decision. Execution stays a deliberate, separate step.
        row["execution_note"] = ("Approved. The integration action still requires an explicit "
                                 "execute call — approval is consent, not automatic execution.")
    return row


@application.post("/security/approvals/expire-stale")
def expire(_: str = Depends(require_owner)) -> dict:
    return {"expired": approvals.expire_stale()}


@application.post("/security/permissions/check")
def check(body: dict, _: str = Depends(require_owner)) -> dict:
    return permissions.check(actor=body.get("actor", "owner-check"), rank=body.get("rank", "AGENT"),
                             tool=body.get("tool", ""),
                             context=body.get("context") or {}).as_dict()


@application.get("/security/permissions/matrix")
def matrix(_: str = Depends(require_owner)) -> dict:
    return {"ranks": permissions.ranks, "tools": permissions.tools,
            "risk_tiers": permissions.risk_tiers,
            "isolation": permissions.isolation,
            "principle": "Tools not listed are denied by default (allowlist model)."}


@application.get("/security/killswitch")
def killstatus(_: str = Depends(require_owner)) -> dict:
    return ks_status()


@application.post("/security/killswitch/engage")
def engage_kill(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    return engage(by="OWNER", reason=(body or {}).get("reason", "owner emergency stop"))


@application.post("/security/killswitch/disengage")
def disengage_kill(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    try:
        return disengage(by="OWNER", reason=(body or {}).get("reason", "owner resumed"))
    except PermissionError as exc:
        raise HTTPException(403, {"error": "forbidden", "detail": str(exc)}) from exc


@application.post("/security/safe-mode")
def set_safe_mode(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    on = bool((body or {}).get("enabled", True))
    if on:
        return enter_safe_mode(reason=(body or {}).get("reason", "owner requested safe mode"), by="OWNER")
    try:
        return exit_safe_mode(by="OWNER", reason=(body or {}).get("reason", "owner cleared safe mode"))
    except PermissionError as exc:
        raise HTTPException(403, {"error": "forbidden", "detail": str(exc)}) from exc


@application.post("/security/injection/scan")
def scan(body: dict, _: str = Depends(require_owner)) -> dict:
    text = body.get("text", "")
    result = injection.scan(text, origin=body.get("origin", "manual"))
    result["fenced_preview"] = injection.wrap_untrusted(text[:600], origin=body.get("origin", "manual"))
    return result


@application.get("/security/vault")
def vault_status(_: str = Depends(require_owner)) -> dict:
    return vault.status()


@application.get("/security/self-check")
def self_check(_: str = Depends(require_owner)) -> dict:
    """Honest posture report — including what is NOT protected."""
    audit_rows = int(store.query_one("SELECT COUNT(*) n FROM audit")["n"])
    gaps = []
    if not vault.status()["exists"]:
        gaps.append("No secrets are stored in the vault yet (nothing to protect, nothing protected).")
    if os_environ_owner_token_default():
        gaps.append("Owner token is the auto-generated local token — rotate it if this machine is shared.")
    if config().settings.env != "production":
        gaps.append("Running in local mode: HTTP (not HTTPS). Fine on localhost, use a tunnel with care.")
    return {
        "kill_switch": kill_switch_engaged(),
        "safe_mode": safe_mode(),
        "spend_limit_inr_per_day": config().get("governance.spend.daily_limit_inr", 0),
        "audit_entries": audit_rows,
        "approval_rule": "HIGH and CRITICAL actions require the owner; standing approvals are revocable.",
        "credential_rule": "Secrets live in the encrypted vault or .env — never in prompts, code, or memory.",
        "known_gaps": gaps,
        "honesty": "This endpoint reports weaknesses deliberately. A security page that only says 'secure' is marketing.",
    }


def os_environ_owner_token_default() -> bool:
    import os
    return not bool(os.environ.get("EMPIRE_OWNER_TOKEN"))


@application.post("/security/audit/note")
def add_audit_note(body: dict, _: str = Depends(require_owner)) -> dict:
    audit("OWNER", body.get("action", "owner.note"), target=body.get("target"),
          reason=body.get("reason", ""), actor_rank="OWNER", allowed=True,
          payload={"note": body.get("note", "")})
    return {"recorded": True}
