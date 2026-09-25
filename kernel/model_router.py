"""Model Router — multi-model orchestration with honest degradation.

Task → complexity → capability → latency → hardware → cost → privacy → model.

Privacy rule: prompts containing private/local business data never leave the machine unless the
owner explicitly authorizes a cloud provider. Cloud providers are disabled by default.

HONESTY RULE: when no model answers, the `deterministic` engine answers and every result is
stamped `provider="deterministic"`, `model_verified=False`. The system never pretends an LLM
produced templated output.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from . import store
from .config import config
from .eventbus import E, bus

MAX_EVENT_TEXT = 400


@dataclass
class RouteResult:
    text: str
    provider: str
    model: str
    tier: str
    task_type: str
    latency_ms: int
    attempts: list[dict] = field(default_factory=list)
    model_verified: bool = False
    label: str = ""
    tokens_estimate: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {"text": self.text, "provider": self.provider, "model": self.model, "tier": self.tier,
                "task_type": self.task_type, "latency_ms": self.latency_ms, "attempts": self.attempts,
                "model_verified": self.model_verified, "label": self.label,
                "tokens_estimate": self.tokens_estimate, "error": self.error}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class OllamaProvider:
    id = "ollama"

    def __init__(self) -> None:
        self.base_url = config().settings.ollama_url.rstrip("/")
        self.enabled = config().settings.ollama_enabled
        self._models: list[str] | None = None
        self._checked_at = 0.0

    def _get(self, path: str, payload: dict | None = None, timeout: int = 20) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local, owner-controlled URL)
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def models(self, *, refresh: bool = False) -> list[str]:
        if not self.enabled:
            return []
        if self._models is not None and not refresh and (time.time() - self._checked_at) < 30:
            return self._models
        self._checked_at = time.time()
        try:
            data = self._get("/api/tags", timeout=4)
            self._models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            self._models = []
        return self._models

    def has(self, model: str) -> bool:
        avail = self.models()
        if not avail:
            return False
        if model in avail:
            return True
        # tolerate tag differences (qwen2.5:1.5b-instruct vs qwen2.5:1.5b)
        base = model.split(":")[0]
        return any(m.split(":")[0] == base for m in avail)

    def chat(self, model: str, prompt: str, *, system: str = "", max_tokens: int = 512,
             timeout: int = 120) -> str:
        payload = {
            "model": model,
            "messages": ([{"role": "system", "content": system}] if system else [])
                        + [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.4},
        }
        data = self._get("/api/chat", payload, timeout=timeout)
        return (data.get("message") or {}).get("content", "") or ""

    def embed(self, model: str, text: str, timeout: int = 60) -> list[float]:
        data = self._get("/api/embeddings", {"model": model, "prompt": text}, timeout=timeout)
        vec = data.get("embedding") or []
        return [float(x) for x in vec]


class CloudProvider:
    """Placeholder for explicitly authorized cloud providers. Disabled unless configured."""

    def __init__(self, pid: str, key_env: str, base_url: str) -> None:
        import os
        self.id = pid
        self.key = os.environ.get(key_env, "")
        self.base_url = base_url
        self.enabled = bool(self.key)

    def models(self) -> list[str]:
        return []


class DeterministicEngine:
    """No-model fallback.

    It does not pretend to reason. It produces structured, honestly-labelled scaffolding that a
    local model can later enrich, so the civilization keeps operating offline.
    """

    id = "deterministic"

    TEMPLATES: dict[str, str] = {
        "classification": "category: unclassified\nconfidence: LOW\nnote: No model available — rule-based classification only.",
        "extraction": "extracted: []\nnote: No model available — extraction requires a model or a hand-written rule.",
        "summarization": "summary: (not generated — no model available)\nkey_points: []\nnote: Deterministic engine cannot summarize prose honestly.",
        "verification": "verified: false\nreason: No verification model available. Result is UNVERIFIED by model.",
        "coding": "patch: (not generated — no model available)\nnote: Code must not be invented by a template engine.",
        "vision": "note: Vision tasks require a vision model (e.g. llava). None available.",
    }

    def generate(self, task_type: str, prompt: str, *, system: str = "", max_tokens: int = 512,
                 schema: dict | None = None) -> str:
        if task_type in ("content_draft", "copywriting"):
            return self._content_scaffold(prompt)
        if task_type in ("research_synthesis", "strategy", "financial_analysis"):
            return self._analysis_scaffold(task_type, prompt)
        if task_type == "embedding":
            return ""
        return self.TEMPLATES.get(
            task_type,
            "note: No model available. Structured output cannot be invented without one.\n"
            "action: run `ollama serve` and pull a model, or hand-write the rule.",
        )

    def _content_scaffold(self, prompt: str) -> str:
        topic = self._topic(prompt)
        return (
            f"DRAFT SCAFFOLD — {topic}\n"
            "status: templated (no model available)\n\n"
            "1. Hook (truthful curiosity, no exaggeration)\n"
            f"   - One specific, checkable statement about {topic}.\n"
            "2. Relevance\n"
            "   - Who this is for, and the exact problem it addresses.\n"
            "3. Substance\n"
            "   - Three concrete points. Each must be something the reader can act on today.\n"
            "4. Proof\n"
            "   - What evidence exists today? If none: write 'Not verified.'\n"
            "5. Limitations (state them honestly — this increases trust)\n"
            "6. Next step / CTA\n\n"
            "REMINDER: No invented testimonials, numbers, awards or results. "
            "Every claim must be supportable or removed."
        )

    def _analysis_scaffold(self, task_type: str, prompt: str) -> str:
        topic = self._topic(prompt)
        if task_type == "financial_analysis":
            return (
                f"FINANCIAL SCAFFOLD — {topic}\n"
                "status: templated (no model available)\n"
                "1. Revenue: verified entries only (see ledger).\n"
                "2. Variable costs:\n3. Incremental costs:\n"
                "4. Contribution = revenue - variable - incremental\n"
                "5. Scenarios: BASE / UPSIDE / DOWNSIDE / WORST_REASONABLE\n"
                "6. Payback days:\n7. Kill criterion:\n"
                "All numbers are Estimate. unless recorded in the ledger as verified."
            )
        return (
            f"ANALYSIS SCAFFOLD — {topic}\n"
            "status: templated (no model available)\n"
            "FACT: \nASSUMPTION: \nINFERENCE: \nHYPOTHESIS: \nUNKNOWN: \n"
            "Cheapest test that would reduce the most uncertainty:\n"
            "What would falsify the main assumption:\n"
            "Downside if wrong:\nUpside if right:\nDo now (single action):"
        )

    @staticmethod
    def _topic(prompt: str) -> str:
        text = re.sub(r"\s+", " ", prompt or "").strip()
        for marker in ("Topic:", "topic:", "Question:", "question:", "TASK:", "Task:"):
            if marker in text:
                text = text.split(marker, 1)[1]
                break
        return (text[:90] + "…") if len(text) > 90 else (text or "unspecified")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
class ModelRouter:
    def __init__(self) -> None:
        self.cfg = config()
        self.ollama = OllamaProvider()
        self.deterministic = DeterministicEngine()
        self.tiers: dict[str, dict] = self.cfg.get("models.tiers", {}) or {}
        self.routing: dict[str, list[str]] = self.cfg.get("models.routing", {}) or {}
        self.governor: dict = self.cfg.get("models.governor", {}) or {}
        self.system_preamble: str = (self.cfg.get("models.prompting.system_preamble", "") or "").strip()
        self.cloud: list[CloudProvider] = []

    # ---- capability discovery -----------------------------------------
    def available_tiers(self) -> dict[str, dict]:
        out = {}
        for tier, spec in self.tiers.items():
            model = spec.get("model", "")
            if tier == "embedding":
                ok = self.ollama.has(model)
            else:
                ok = self.ollama.has(model)
            out[tier] = {**spec, "available": bool(ok)}
        return out

    def status(self) -> dict:
        models = self.ollama.models()
        return {
            "provider": "ollama" if models else "deterministic-only",
            "ollama_enabled": self.ollama.enabled,
            "ollama_url": self.ollama.base_url,
            "reachable": bool(models),
            "installed_models": models,
            "tiers": self.available_tiers(),
            "cloud_providers": [c.id for c in self.cloud if c.enabled],
            "note": ("Local models are serving requests."
                     if models else
                     "No local models detected. The deterministic engine is answering and every "
                     "artifact is stamped 'templated (no model available)'. Install Ollama and pull "
                     "a model (see README) to enable real reasoning."),
            "honesty": "If a result says provider=deterministic, no model produced it.",
        }

    def _chain(self, task_type: str) -> list[str]:
        chain = self.routing.get(task_type)
        if chain:
            return list(chain)
        fb = self.cfg.get("models.fallback", {}) or {}
        generic = ["small", "nano"]
        return generic + ["deterministic"] if "deterministic" not in generic else generic

    # ---- main entry ----------------------------------------------------
    def route(self, task_type: str, prompt: str, *, system: str = "", max_tokens: int = 512,
              schema: dict | None = None, private: bool = True, retries: int = 0) -> RouteResult:
        started = time.time()
        attempts: list[dict] = []
        chain = self._chain(task_type)

        for tier in chain:
            if tier == "deterministic":
                text = self.deterministic.generate(task_type, prompt, system=system,
                                                   max_tokens=max_tokens, schema=schema)
                attempts.append({"tier": "deterministic", "ok": True, "reason": "fallback"})
                result = RouteResult(
                    text=text, provider="deterministic", model="template", tier="deterministic",
                    task_type=task_type, latency_ms=int((time.time() - started) * 1000),
                    attempts=attempts, model_verified=False,
                    label="No model available — templated output",
                    tokens_estimate=0,
                )
                self._record(result)
                return result

            spec = self.tiers.get(tier)
            if not spec:
                attempts.append({"tier": tier, "ok": False, "reason": "tier_not_configured"})
                continue
            model = spec.get("model", "")
            if not self.ollama.enabled:
                attempts.append({"tier": tier, "ok": False, "reason": "ollama_disabled"})
                continue
            if not self.ollama.has(model):
                attempts.append({"tier": tier, "ok": False, "reason": f"model_not_installed:{model}"})
                bus.publish(E.MODEL_FALLBACK, source="model_router", severity="debug",
                            payload={"tier": tier, "model": model, "reason": "not_installed",
                                     "hint": spec.get("pull", "")})
                continue

            full_system = (self.system_preamble + ("\n\n" + system if system else "")).strip()
            for attempt in range(retries + 1):
                try:
                    text = self.ollama.chat(model, prompt, system=full_system, max_tokens=max_tokens,
                                            timeout=int(self.governor.get("per_call_timeout_seconds", 120)))
                    if text and text.strip():
                        attempts.append({"tier": tier, "model": model, "ok": True})
                        result = RouteResult(
                            text=text.strip(), provider="ollama", model=model, tier=tier,
                            task_type=task_type, latency_ms=int((time.time() - started) * 1000),
                            attempts=attempts, model_verified=True, label="local model",
                            tokens_estimate=max(1, len(text) // 4),
                        )
                        self._record(result)
                        return result
                    attempts.append({"tier": tier, "model": model, "ok": False, "reason": "empty_response"})
                except urllib.error.URLError as exc:
                    attempts.append({"tier": tier, "model": model, "ok": False, "reason": f"network:{exc}"})
                    break
                except Exception as exc:  # model crashed / timeout
                    attempts.append({"tier": tier, "model": model, "ok": False,
                                     "reason": f"{type(exc).__name__}:{str(exc)[:120]}"})

        text = self.deterministic.generate(task_type, prompt, system=system, max_tokens=max_tokens)
        attempts.append({"tier": "deterministic", "ok": True, "reason": "chain_exhausted"})
        result = RouteResult(text=text, provider="deterministic", model="template", tier="deterministic",
                             task_type=task_type, latency_ms=int((time.time() - started) * 1000),
                             attempts=attempts, model_verified=False,
                             label="No model available — templated output")
        self._record(result)
        if str(task_type) in ("strategy", "financial_analysis", "verification"):
            bus.publish(E.MODEL_ERROR, source="model_router", severity="warning",
                        payload={"task_type": task_type, "attempts": attempts,
                                 "escalation": "Important decision produced templated output — owner review advised."})
        return result

    # ---- embeddings ----------------------------------------------------
    def embed(self, text: str) -> tuple[list[float], str]:
        """Returns (vector, method). Lexical hash fallback keeps memory search working offline."""
        spec = self.tiers.get("embedding", {})
        model = spec.get("model", "")
        if self.ollama.enabled and model and self.ollama.has(model):
            try:
                vec = self.ollama.embed(model, text)
                if vec:
                    return vec, f"ollama:{model}"
            except Exception:
                pass
        return self._hash_embedding(text), "hash-lexical"

    @staticmethod
    def _hash_embedding(text: str, dims: int = 128) -> list[float]:
        vec = [0.0] * dims
        for token in re.findall(r"[a-zA-Z0-9\u0900-\u097F']+", (text or "").lower()):
            h = int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16)
            vec[h % dims] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    # ---- accounting ----------------------------------------------------
    def _record(self, result: RouteResult) -> None:
        store.bump_counter("model_calls_total")
        store.bump_counter(f"model_calls::{result.tier}")
        if result.provider == "deterministic":
            store.bump_counter("model_calls_deterministic")
        store.bump_counter("model_tokens_estimate", result.tokens_estimate)
        bus.publish(E.MODEL_CALL, source="model_router", severity="debug",
                    payload={"task_type": result.task_type, "provider": result.provider,
                             "tier": result.tier, "latency_ms": result.latency_ms,
                             "verified": result.model_verified,
                             "preview": (result.text or "")[:120]})

    def stats(self) -> dict:
        tiers = {t: int(store.get_setting(f"model_calls::{t}", 0) or 0) for t in self.tiers}
        return {
            "calls_total": int(store.get_setting("model_calls_total", 0) or 0),
            "calls_deterministic": int(store.get_setting("model_calls_deterministic", 0) or 0),
            "tokens_estimate": int(store.get_setting("model_tokens_estimate", 0) or 0),
            "by_tier": tiers,
            "cost_inr": 0.0,
            "note": "Local inference has no API cost; only your own electricity. Cost is tracked as ₹0 by design.",
        }


_singleton: ModelRouter | None = None


def router() -> ModelRouter:
    global _singleton
    if _singleton is None:
        _singleton = ModelRouter()
    return _singleton


def route(task_type: str, prompt: str, **kwargs: Any) -> RouteResult:
    return router().route(task_type, prompt, **kwargs)
