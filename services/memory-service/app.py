"""Memory Service (port 8003) — six-layer hierarchical memory with provenance and deletion rights."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from kernel.memory import LAYERS, memory
from services.base import ServiceCard, require_owner, service_app

PORT = 8003
CARD = ServiceCard(
    name="memory-service", port=PORT, layer="C · agent organization", domain="memory",
    description="Working, episodic, semantic, procedural, organizational and strategic memory "
                "with timestamps, source, confidence, importance, expiry and owner-inspectable records.",
    owns_tables=["memory"],
    produces_events=["memory.written"],
    consumes_events=["task.*", "university.*"],
    endpoints=["POST /memory", "GET /memory/search", "GET /memory/agent/{id}", "GET /memory/layers",
               "DELETE /memory/{id}", "POST /memory/purge-expired", "GET /memory/stats"],
    dependencies=["kernel.memory", "model-service (embeddings, optional)"],
)
application = service_app(CARD)


@application.get("/memory/layers")
def layers(_: str = Depends(require_owner)) -> dict:
    return {"layers": [
        {"id": "working", "purpose": "current task scratchpad", "ttl": "6 hours"},
        {"id": "episodic", "purpose": "what happened", "ttl": "90 days"},
        {"id": "semantic", "purpose": "knowledge learned, with sources", "ttl": "permanent"},
        {"id": "procedural", "purpose": "how to perform tasks (playbooks)", "ttl": "permanent"},
        {"id": "organizational", "purpose": "department knowledge", "ttl": "permanent"},
        {"id": "strategic", "purpose": "long-term business objectives", "ttl": "permanent"},
    ], "stats": memory.stats()}


@application.post("/memory")
def write(body: dict, _: str = Depends(require_owner)) -> dict:
    try:
        row = memory.write(
            agent_id=body.get("agent_id"), layer=body.get("layer", "semantic"),
            content=body.get("content", ""), key=body.get("key", ""),
            source=body.get("source", "owner"), evidence_kind=body.get("evidence_kind", "FACT"),
            confidence=float(body.get("confidence", 0.7)), importance=float(body.get("importance", 0.6)),
            access_scope=body.get("access_scope", "organization"),
            tags=body.get("tags") or [], embed=bool(body.get("embed", False)),
        )
    except ValueError as exc:
        raise HTTPException(400, {"error": "rejected", "detail": str(exc)}) from exc
    return {"stored": {k: v for k, v in row.items() if k != "embedding_json"}}


@application.get("/memory/search")
def search(q: str = Query(..., min_length=1), agent_id: str | None = None,
           limit: int = Query(20, le=200), _: str = Depends(require_owner)) -> dict:
    rows = memory.search(q, agent_id=agent_id, limit=limit)
    return {"query": q, "count": len(rows),
            "results": [{**r, "embedding": None} for r in rows],
            "note": "Lexical + optional vector scoring. Relevance is a heuristic, not a truth claim."}


@application.get("/memory/agent/{agent_id}")
def read_agent(agent_id: str, layer: str | None = None, limit: int = Query(100, le=500),
               _: str = Depends(require_owner)) -> dict:
    layers = [layer] if layer else None
    if layers and layer not in LAYERS:
        raise HTTPException(400, {"error": "bad_layer", "detail": f"Allowed: {LAYERS}"})
    rows = memory.read(agent_id=agent_id, layers=layers, limit=limit)
    return {"agent_id": agent_id, "count": len(rows), "memories": rows}


@application.delete("/memory/{memory_id}")
def delete(memory_id: str, _: str = Depends(require_owner)) -> dict:
    ok = memory.delete(memory_id, by="OWNER")
    if not ok:
        raise HTTPException(404, {"error": "not_found", "detail": "No such memory record"})
    return {"deleted": memory_id, "note": "The owner's right to delete memory is absolute."}


@application.post("/memory/purge-expired")
def purge(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    keep = float((body or {}).get("keep_important_above", 0.7))
    return {"purged": memory.purge_expired(keep_important_above=keep), "stats": memory.stats()}


@application.get("/memory/stats")
def stats(_: str = Depends(require_owner)) -> dict:
    return memory.stats()
