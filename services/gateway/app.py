"""API Gateway (port 8000) — the single door to the civilization.

  * One origin for the UI: /api/{service}/{path} proxies to the owning microservice.
  * WebSocket proxy: /ws → event-service (real-time backend state → 3D world).
  * Aggregated dashboard + Owner Command Center (natural language → controlled actions).
  * Owner token auth in front of everything except health/meta.

Service-to-service calls carry the internal key; browser calls carry the owner token.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
from fastapi import Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from kernel import auth, store, paths
from kernel.config import config
from kernel.eventbus import E, bus
from kernel.model_router import router
from kernel.registry import agents as agent_registry
from services.base import ServiceCard, require_owner, service_app, ws_authorized
from services.gateway import command_center

PORT = 8000
CARD = ServiceCard(
    name="gateway", port=PORT, layer="B · boundary", domain="api",
    description="Single entry point: request routing, aggregation, owner auth, command center and the "
                "WebSocket fan-through to the 3D client.",
    owns_tables=[],
    produces_events=["command.executed", "gateway.*"],
    consumes_events=["*"],
    endpoints=["GET /api/health", "GET /api/services", "GET /api/dashboard", "GET /api/commands",
               "POST /api/command", "ANY /api/{service}/{path}", "WS /ws"],
    dependencies=["all services"],
)
application = service_app(CARD)

# The proxy map is derived from config/services.yaml — one topology, one source of truth. A new
# service becomes reachable through the gateway without editing this file (and can never be listed
# here while missing from the topology, or vice versa). The literal below is only a fallback for a
# missing/unreadable config file.
_FALLBACK_SERVICES = {
    "agent": 8001, "model": 8002, "memory": 8003, "analytics": 8004, "workflow": 8005,
    "economy": 8006, "university": 8007, "research": 8008, "integration": 8009,
    "finance": 8010, "security": 8011, "event": 8012, "world": 8013, "customer": 8014,
}


def _service_map() -> dict[str, int]:
    try:
        topology = config().section("services") or {}
    except Exception:
        return dict(_FALLBACK_SERVICES)
    out: dict[str, int] = {}
    for name, spec in topology.items():
        if name == "gateway" or not isinstance(spec, dict) or "port" not in spec:
            continue
        key = name[:-8] if name.endswith("-service") else name
        out[key] = int(spec["port"])
    return out or dict(_FALLBACK_SERVICES)


SERVICES = _service_map()
HOST = os.environ.get("EMPIRE_SERVICE_HOST", "127.0.0.1")
TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_client: httpx.AsyncClient | None = None


async def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    return _client


def _forward_headers(request: Request) -> dict:
    headers = {"X-Empire-Key": config().settings.internal_key}
    for h in ("x-owner-token", "authorization", "content-type"):
        if request.headers.get(h):
            headers[h] = request.headers[h]
    return headers


@application.get("/api/health")
def health() -> dict:
    return {"service": "gateway", "status": "ok", "port": PORT,
            "services": list(SERVICES), "version": CARD.version,
            "kill_switch": bool(store.get_setting("kill_switch", False)),
            "checked_at": time.time()}


@application.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    token = request.headers.get("x-owner-token") or request.query_params.get("token")
    return {"authenticated": auth.verify_token(token),
            "where_to_find_token": "data/state/secrets/owner_token (also printed by scripts/empire.py up)",
            "note": "The civilization is owner-gated because it may be reachable through a tunnel."}


@application.get("/api/services")
async def services(_: str = Depends(require_owner)) -> dict:
    c = await client()
    async def probe(name: str, port: int) -> dict:
        try:
            r = await c.get(f"http://{HOST}:{port}/health", timeout=3.0)
            data = r.json()
            return {"name": name, "port": port, "up": True, "status": data.get("status"),
                    "requests": data.get("requests"), "details": data}
        except Exception as exc:
            return {"name": name, "port": port, "up": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    results = await asyncio.gather(*[probe(n, p) for n, p in SERVICES.items()])
    return {"count": len(results), "up": sum(1 for r in results if r["up"]), "services": results}


@application.get("/api/dashboard")
async def dashboard(_: str = Depends(require_owner)) -> dict:
    """Aggregated owner view with graceful degradation if a service is down."""
    c = await client()
    async def fetch(path: str) -> dict:
        try:
            r = await c.get(f"http://{HOST}:8004{path}", headers={"X-Empire-Key": config().settings.internal_key},
                            timeout=8.0)
            return r.json()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    overview, owner_view, world, events = await asyncio.gather(
        fetch("/analytics/overview"), fetch("/analytics/owner-dashboard"),
        fetch("/analytics/system"), fetch("/analytics/models"))
    return {"generated_at": time.time(), "overview": overview, "owner": owner_view,
            "system": world, "models": events,
            "kill_switch": bool(store.get_setting("kill_switch", False)),
            "safe_mode": bool(store.get_setting("safe_mode", False))}


@application.get("/api/commands")
def commands(_: str = Depends(require_owner)) -> dict:
    return {"commands": command_center.catalogue(),
            "examples": ["show me everything generating revenue", "status",
                         "create a new AI department for digital products",
                         "train 50 agents in Python",
                         "find five business opportunities requiring zero initial capital",
                         "show me the top-performing agents",
                         "stop all social-media publishing",
                         "give marketing access to YouTube analytics",
                         "build a new product experiment",
                         "explain why this experiment failed"],
            "rule": "Unmatched sentences change nothing — they are answered with analysis instead."}


@application.post("/api/command")
def run_command(body: dict, _: str = Depends(require_owner)) -> dict:
    text = (body.get("text") or body.get("command") or "").strip()
    if not text:
        raise HTTPException(400, {"error": "empty_command"})
    return command_center.interpret(text)


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------
@application.api_route("/api/{service}/{path:path}",
                       methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(service: str, path: str, request: Request) -> JSONResponse:
    if service not in SERVICES:
        raise HTTPException(404, {"error": "unknown_service", "detail": f"'{service}' is not a service",
                                  "available": list(SERVICES)})
    port = SERVICES[service]
    url = f"http://{HOST}:{port}/{path}"
    body = None
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        raw = await request.body()
        body = json.loads(raw) if raw else None
    try:
        c = await client()
        resp = await c.request(request.method, url, params=dict(request.query_params),
                               json=body, headers=_forward_headers(request))
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text[:4000]}
        return JSONResponse(status_code=resp.status_code, content=payload)
    except httpx.ConnectError:
        raise HTTPException(503, {"error": "service_unavailable", "service": service, "port": port,
                                  "detail": f"{service}-service is not running. Start it with "
                                            f"`python scripts/empire.py up`.",
                                  "hint": "The civilization degrades gracefully: other services keep working."})


# ---------------------------------------------------------------------------
# WebSocket proxy → event-service
# ---------------------------------------------------------------------------
@application.websocket("/ws")
async def ws_proxy(websocket: WebSocket) -> None:
    if not ws_authorized(websocket):
        await websocket.close(code=4401)
        return
    token = websocket.query_params.get("token", "")
    await websocket.accept()
    url = f"ws://{HOST}:8012/ws?token={token}"
    try:
        async with httpx.AsyncClient(timeout=None) as c:
            # httpx has no WS client; use the websockets library through a tiny relay.
            import websockets
            async with websockets.connect(url, max_size=2_000_000) as upstream:
                async def pump_up() -> None:
                    async for message in upstream:
                        await websocket.send_text(message)
                await pump_up()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "stream.error",
                                                  "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@application.post("/api/shutdown")
def shutdown(body: dict | None = None, _: str = Depends(require_owner)) -> dict:
    """Graceful stop signal. Never kills processes silently — it sets the flag services watch."""
    store.set_setting("shutdown_requested", True)
    bus.publish(E.SHUTDOWN, source="gateway", severity="notice",
                payload={"requested_by": "OWNER", "note": "Services will exit on their own supervision loop."})
    return {"shutdown_requested": True,
            "note": "Use Ctrl+C in the terminal running the supervisor, or `python scripts/empire.py down`."}


# ---------------------------------------------------------------------------
# Optional static hosting of the built 3D client
# ---------------------------------------------------------------------------
_dist = paths.APPS_DIR / "civilization-web" / "dist"
if _dist.exists():
    application.mount("/", StaticFiles(directory=str(_dist), html=True), name="civilization-web")
else:
    @application.get("/", response_class=HTMLResponse)
    def root() -> str:
        return f"""
        <html><head><title>Saurav AI Civilization</title>
        <style>body{{background:#05060a;color:#e6e9f2;font:15px/1.6 ui-monospace,monospace;padding:40px}}
        a{{color:#8b9cff}} code{{background:#111624;padding:2px 6px;border-radius:4px}}</style></head>
        <body><h1>Saurav AI Civilization</h1>
        <p>API gateway is live on port {PORT}. The 3D client is served by the Vite dev server:</p>
        <ul><li>3D world → <a href="http://127.0.0.1:3000">http://127.0.0.1:3000</a></li>
        <li>This gateway → <code>/api/*</code>, WebSocket <code>/ws</code></li>
        <li>Service cards → <a href="/api/services">/api/services</a></li></ul>
        <p>Owner token: <code>data/state/secrets/owner_token</code></p>
        <p>Build the client for production with
        <code>cd apps/civilization-web && npm run build</code> and it will be served from here instead.</p>
        </body></html>
        """
