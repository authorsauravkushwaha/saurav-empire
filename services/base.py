"""Shared service scaffolding.

Every service is an independent process with its own port, its own domain, and its own
Service Card at `/meta`. It owns a slice of the database, publishes events, and never depends on
another service being alive to answer its own domain questions (local-first, fail-soft).
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kernel import auth, store
from kernel.config import config
from kernel.eventbus import E, bus
from kernel.governance import audit

SERVICE_VERSION = "1.0.0"


@dataclass
class ServiceCard:
    name: str
    port: int
    layer: str
    domain: str
    description: str
    owns_tables: list[str] = field(default_factory=list)
    produces_events: list[str] = field(default_factory=list)
    consumes_events: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    version: str = SERVICE_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------
def _extract_token(request: Request | None, x_owner_token: str | None,
                   authorization: str | None, query_token: str | None = None) -> str | None:
    if x_owner_token:
        return x_owner_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:]
    if query_token:
        return query_token
    if request is not None:
        cookie = request.cookies.get("empire_owner") if hasattr(request, "cookies") else None
        if cookie:
            return cookie
    return None


def require_owner(request: Request,
                  x_owner_token: str | None = Header(default=None),
                  authorization: str | None = Header(default=None),
                  x_empire_key: str | None = Header(default=None)) -> str:
    """Owner token OR the internal service key (used service-to-service)."""
    if auth.verify_internal_key(x_empire_key):
        return "INTERNAL"
    token = _extract_token(request, x_owner_token, authorization)
    if auth.verify_token(token):
        return "OWNER"
    raise HTTPException(status_code=401, detail={
        "error": "owner_token_required",
        "detail": "This civilization is owner-gated. Send X-Owner-Token.",
        "where": "The token is in data/state/secrets/owner_token and is printed by scripts/empire.py up.",
        "never_shared": "The token is never sent anywhere except this local API.",
    })


def maybe_owner(request: Request,
                x_owner_token: str | None = Header(default=None),
                authorization: str | None = Header(default=None)) -> bool:
    return auth.verify_token(_extract_token(request, x_owner_token, authorization))


def ws_authorized(websocket: WebSocket) -> bool:
    token = websocket.query_params.get("token")
    return auth.verify_token(token)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def service_app(card: ServiceCard, *, require_auth: bool = True,
                add_cors: bool = True) -> FastAPI:
    store.init_db()
    app = FastAPI(title=f"Saurav AI Civilization — {card.name}", version=SERVICE_VERSION,
                  description=card.description, docs_url="/docs")
    app.state.card = card
    app.state.started_at = time.time()
    app.state.requests = 0

    if add_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"https?://.*",      # local + preview hosts; auth still applies
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def _gate(request: Request, call_next: Callable) -> Any:
        app.state.requests += 1
        path = request.url.path
        if require_auth and not auth.is_public_path(path) and request.method != "OPTIONS":
            token = _extract_token(request, request.headers.get("x-owner-token"),
                                   request.headers.get("authorization"))
            internal = request.headers.get("x-empire-key")
            if not (auth.verify_token(token) or auth.verify_internal_key(internal)):
                return JSONResponse(status_code=401, content={
                    "error": "owner_token_required",
                    "detail": "Send X-Owner-Token (or login through the Command Center).",
                })
        try:
            return await call_next(request)
        except Exception as exc:  # never leak a stack trace to the UI
            audit("service", "error", target=path, allowed=False,
                  reason=f"{type(exc).__name__}: {str(exc)[:200]}")
            return JSONResponse(status_code=500, content={
                "error": "internal_error", "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
                "service": card.name,
            })

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        counts = store.table_counts()
        return {
            "service": card.name, "status": "ok", "version": SERVICE_VERSION,
            "uptime_seconds": round(time.time() - app.state.started_at, 1),
            "requests": app.state.requests, "port": card.port, "layer": card.layer,
            "db_rows": {k: v for k, v in counts.items() if v},
            "kill_switch": bool(store.get_setting("kill_switch", False)),
            "safe_mode": bool(store.get_setting("safe_mode", False)),
            "checked_at": time.time(),
        }

    @app.get("/meta", tags=["meta"])
    def meta() -> dict:
        return card.as_dict()

    app.add_exception_handler(HTTPException, _http_error_handler)
    return app


async def _http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                        content=exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail})


def publish(source: str, event: str, *, subject: str | None = None, severity: str = "info",
            payload: dict | None = None) -> None:
    bus.publish(event, source=source, subject=subject, severity=severity, payload=payload or {})


def boot_banner(name: str, port: int, host: str = "0.0.0.0") -> str:
    return (
        f"\n  ┌─ {name}\n"
        f"  │  http://127.0.0.1:{port}   (bind {host})\n"
        f"  │  health: /health   card: /meta\n"
        f"  └─ Saurav AI Civilization v{SERVICE_VERSION}\n"
    )


def run(name: str, port: int, *, host: str = "0.0.0.0", card: ServiceCard | None = None) -> None:
    """Convenience entrypoint used by `python -m services.<name>.app`."""
    import uvicorn
    target = "app:application"
    print(boot_banner(name, port, host))
    uvicorn.run(target, host=host, port=port, log_level=os.environ.get("EMPIRE_LOG_LEVEL", "info"))
