"""Model Service (port 8002) — multi-model discovery, routing and honest generation.

Reports exactly what is installed and what answered. When nothing is installed, it says so.
"""
from __future__ import annotations

from fastapi import Depends, Query

from kernel.model_router import router
from services.base import ServiceCard, require_owner, service_app

PORT = 8002
CARD = ServiceCard(
    name="model-service", port=PORT, layer="B · intelligence", domain="models",
    description="Model router: capability discovery, task→model routing, fallback chain, embeddings.",
    owns_tables=["settings (counters)"],
    produces_events=["model.call", "model.fallback", "model.error"],
    consumes_events=[],
    endpoints=["GET /models/status", "GET /models/tiers", "POST /models/generate",
               "POST /models/embed", "GET /models/stats", "GET /models/install-hints"],
    dependencies=["kernel.model_router", "Ollama (external, optional)"],
)
application = service_app(CARD)


@application.get("/models/status")
def status(_: str = Depends(require_owner)) -> dict:
    return router().status()


@application.get("/models/tiers")
def tiers(_: str = Depends(require_owner)) -> dict:
    r = router()
    return {"tiers": r.available_tiers(), "routing": r.routing,
            "default_model": r.cfg.settings.default_model}


@application.get("/models/install-hints")
def install_hints(_: str = Depends(require_owner)) -> dict:
    """The zero-cost path to real reasoning, in order of value per gigabyte."""
    return {
        "why": "Without a local model the deterministic engine answers, and every artifact is stamped "
               "'templated'. With a model, agents can actually reason, write and verify.",
        "steps": [
            "1. Install Ollama (free, offline): https://ollama.com/download",
            "2. ollama pull qwen2.5:0.5b-instruct      # ~400MB — classification, tagging",
            "3. ollama pull qwen2.5-coder:1.5b         # ~1GB — coding tasks",
            "4. ollama pull qwen2.5:1.5b-instruct      # ~1GB — drafts and summaries",
            "5. ollama pull qwen2.5:3b-instruct        # ~2GB — analysis and strategy (needs ~4GB RAM)",
            "6. ollama pull nomic-embed-text           # ~275MB — semantic memory",
            "7. Restart the civilization: python scripts/empire.py up",
        ],
        "cost_inr": 0,
        "hardware_note": "A 2-core / 4GB machine should stay with the 0.5b and 1.5b tiers.",
        "privacy": "Prompts never leave the machine. Cloud providers are disabled until the owner enables them.",
    }


@application.post("/models/generate")
def generate(body: dict, _: str = Depends(require_owner)) -> dict:
    res = router().route(body.get("task_type", "classification"), body.get("prompt", ""),
                         system=body.get("system", ""), max_tokens=int(body.get("max_tokens", 512)),
                         private=bool(body.get("private", True)))
    return res.to_dict()


@application.post("/models/embed")
def embed(body: dict, _: str = Depends(require_owner)) -> dict:
    text = body.get("text", "")
    vec, method = router().embed(text)
    return {"method": method, "dimensions": len(vec),
            "vector_preview": [round(v, 4) for v in vec[:12]],
            "note": ("A real embedding model produced this." if method.startswith("ollama") else
                     "No embedding model available: a lexical hash vector was used. Semantic search "
                     "quality is limited — this is labelled, not hidden."),
            "vector": vec}


@application.get("/models/stats")
def stats(_: str = Depends(require_owner)) -> dict:
    return router().stats()


@application.get("/models/health")
def health_check(_: str = Depends(require_owner)) -> dict:
    r = router()
    installed = r.ollama.models(refresh=True)
    return {"ollama_reachable": bool(installed), "installed_models": installed,
            "endpoint": r.ollama.base_url,
            "latency_note": "Model health is only claimed after a successful /api/tags call."}
