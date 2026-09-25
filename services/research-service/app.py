"""Research Service (port 8008) — evidence capture, cheapest-test design, zero-capital discovery."""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException

from kernel import store
from kernel.economy import free_resources, opportunities
from kernel.governance import claims, injection
from kernel.integrations import get as get_connector
from kernel.memory import memory
from kernel.model_router import router
from services.base import ServiceCard, require_owner, service_app

PORT = 8008
CARD = ServiceCard(
    name="research-service", port=PORT, layer="D · economic engine", domain="research",
    description="Source capture with quality metadata, falsification-first research plans, "
                "cheapest-test design and opportunity discovery.",
    owns_tables=["opportunities (writes)", "memory (semantic layer)"],
    produces_events=["economy.opportunity_discovered", "research.*"],
    consumes_events=["economy.*"],
    endpoints=["POST /research/plan", "POST /research/fetch", "POST /research/note",
               "GET /research/sources", "POST /research/discover", "GET /research/free-resources",
               "POST /research/hypothesis"],
    dependencies=["kernel.integrations.web", "kernel.memory", "kernel.economy"],
)
application = service_app(CARD)


@application.post("/research/plan")
def plan(body: dict, _: str = Depends(require_owner)) -> dict:
    question = body.get("question", "Unspecified question")
    unknowns = body.get("unknowns") or [question]
    return {
        "question": question,
        "unknowns": unknowns,
        "evidence_required": "Primary source, official documentation, or direct customer evidence.",
        "cheapest_test": f"Design the smallest test that answers: {unknowns[0]}. Budget ₹0, ≤60 minutes.",
        "falsification": "State in advance exactly what evidence would prove this wrong.",
        "source_quality_checks": ["who benefits if I believe this", "date", "sample size",
                                  "methodology", "what contradicts it"],
        "output_format": "FACT / ASSUMPTION / INFERENCE / HYPOTHESIS / OPINION / UNKNOWN",
        "warning": "Market intuition sits at the bottom of the evidence hierarchy. It may be used, "
                   "but it must be labelled as intuition.",
    }


@application.post("/research/fetch")
def fetch(body: dict, _: str = Depends(require_owner)) -> dict:
    """Fetch a public page (robots-aware, rate-limited). Content returns fenced as untrusted data."""
    connector = get_connector("web")
    url = body.get("url", "")
    if not url:
        raise HTTPException(400, {"error": "bad_request", "detail": "Provide a url."})
    result = connector.fetch_public_page(url=url, max_chars=int(body.get("max_chars", 6000)))
    if result.get("status") == "ok":
        memory.semantic(None, content=f"Fetched {url} ({result['chars']} chars): {result['title']}",
                        source=url, evidence_kind="FACT", confidence=0.6, importance=0.5,
                        tags=["research", "web"])
        result["fenced"] = injection.wrap_untrusted(result["text"][:1500], origin=f"web:{url}")
    return result


@application.post("/research/note")
def note(body: dict, _: str = Depends(require_owner)) -> dict:
    """Store a research note with explicit provenance and evidence kind."""
    content = body.get("content", "")
    kind = body.get("evidence_kind", "ASSUMPTION")
    review = claims.review(content, context="research_note")
    row = memory.semantic(body.get("agent_id"), content=content,
                          source=body.get("source", "unstated"),
                          evidence_kind=kind, confidence=float(body.get("confidence", 0.5)),
                          importance=float(body.get("importance", 0.6)),
                          tags=body.get("tags") or ["research"])
    return {"stored": row["id"], "evidence_kind": kind, "claims_review": review,
            "reminder": "A source of 'unstated' is not a source. Record where this came from."}


@application.get("/research/sources")
def sources(limit: int = 100, _: str = Depends(require_owner)) -> dict:
    rows = store.query("SELECT id, ts, source, evidence_kind, confidence, substr(content,1,300) content "
                       "FROM memory WHERE layer='semantic' ORDER BY ts DESC LIMIT ?", (limit,))
    return {"count": len(rows), "sources": rows}


@application.post("/research/discover")
def discover(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    created = opportunities.discover_zero_capital(owner_agent=(body or {}).get("owner_agent"))
    return {"created": len(created), "opportunities": created}


@application.get("/research/free-resources")
def resources(_: str = Depends(require_owner)) -> dict:
    return free_resources.scan()


@application.post("/research/hypothesis")
def hypothesis(body: dict, _: str = Depends(require_owner)) -> dict:
    """Turn a belief into a falsifiable hypothesis with a decision rule."""
    statement = body.get("statement", "Unspecified belief")
    res = router().route("strategy", (
        f"Turn this belief into ONE falsifiable hypothesis.\nBelief: {statement}\n"
        "Output: hypothesis, measurement, threshold, window, kill condition. "
        "No invented evidence. Label anything unverified as 'Not verified.'"
    ), max_tokens=400)
    return {"statement": statement, "hypothesis_work": res.text, "provider": res.provider,
            "model_verified": res.model_verified,
            "deterministic_shape": {
                "hypothesis": f"If we do X for Y, then Z will be measurable within N days.",
                "measurement": "one number you can actually read",
                "threshold": "the value that counts as success (set BEFORE the test)",
                "window": "maximum duration before you stop",
                "kill_condition": "the value that ends it early",
            },
            "generated_at": time.time()}
