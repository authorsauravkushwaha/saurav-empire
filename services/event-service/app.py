"""Event Service (port 8012) — the civilization's nervous system.

Owns the append-only `events` table and the WebSocket stream that drives the 3D world.
The 3D world may never invent activity: if it is not in this stream, it does not happen.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time

from fastapi import Depends, Query, WebSocket, WebSocketDisconnect

from kernel import store
from kernel.eventbus import E, bus
from services.base import ServiceCard, require_owner, service_app, ws_authorized

PORT = 8012
CARD = ServiceCard(
    name="event-service", port=PORT, layer="B · event-driven core", domain="events",
    description="Append-only event log plus the real-time WebSocket feed consumed by the 3D world.",
    owns_tables=["events"],
    produces_events=["* (all)"],
    consumes_events=["* (records every event)"],
    endpoints=["GET /events", "GET /events/recent", "GET /events/counters", "GET /events/tail",
               "WS /ws", "POST /events/publish"],
    dependencies=["kernel.store", "kernel.eventbus"],
)
application = service_app(CARD)


class Hub:
    """Fan-out to connected viewers. Slow clients are dropped, never allowed to block the bus."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last_id = 0
        self.sent = 0
        self.dropped = 0

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        dead = []
        text = json.dumps(payload, default=str)
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2.0)
                self.sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)
            self.dropped += 1


hub = Hub()


async def _pump() -> None:
    """Poll the event log and push new events. Cross-process safe: the DB is the contract."""
    hub.last_id = hub.last_id or (store.query_one("SELECT COALESCE(MAX(id),0) m FROM events")["m"] or 0)
    while True:
        try:
            rows = store.query("SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT 200", (hub.last_id,))
            for row in rows:
                hub.last_id = row["id"]
                payload = {"type": row["type"], "id": row["id"], "ts": row["ts"],
                           "source": row["source"], "subject": row["subject"],
                           "severity": row["severity"],
                           "payload": store.jload(row.get("payload_json"), {})}
                await hub.broadcast(payload)
        except Exception as exc:
            bus.publish("event_service.pump_error", source="event-service", severity="error",
                        payload={"error": f"{type(exc).__name__}: {exc}"[:200]})
        await asyncio.sleep(0.6)


@application.on_event("startup")
async def _startup() -> None:
    bus.publish("service.started", source="event-service", payload={"port": PORT, "card": CARD.name})
    application.state.pump = asyncio.create_task(_pump())


@application.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(application.state, "pump", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
@application.get("/events")
def list_events(since: int = Query(0, ge=0), limit: int = Query(300, le=2000),
                types: str | None = None, _: str = Depends(require_owner)) -> dict:
    wanted = [t for t in (types or "").split(",") if t] or None
    rows = bus.since(since, limit, wanted)
    return {"events": rows, "count": len(rows), "last_id": rows[-1]["id"] if rows else since}


@application.get("/events/recent")
def recent(limit: int = Query(80, le=500), _: str = Depends(require_owner)) -> dict:
    return {"events": bus.recent(limit)}


@application.get("/events/counters")
def counters(_: str = Depends(require_owner)) -> dict:
    return {"local_counts": bus.counts(), "window_5m": bus.tail_metrics(300),
            "total": int(store.query_one("SELECT COUNT(*) n FROM events")["n"]),
            "last_id": int(store.query_one("SELECT COALESCE(MAX(id),0) m FROM events")["m"] or 0),
            "viewers": len(hub.clients)}


@application.get("/events/tail")
def tail(seconds: int = Query(60, le=3600), _: str = Depends(require_owner)) -> dict:
    cutoff = time.time() - seconds
    rows = store.query("SELECT type, severity, COUNT(*) n FROM events WHERE ts > ? GROUP BY type, severity "
                       "ORDER BY n DESC", (cutoff,))
    return {"window_seconds": seconds, "types": [{"type": r["type"], "severity": r["severity"],
                                                  "count": r["n"]} for r in rows]}


@application.post("/events/publish")
def publish_event(body: dict, _: str = Depends(require_owner)) -> dict:
    ev = bus.publish(body.get("type", "custom.event"), source=body.get("source", "api"),
                     subject=body.get("subject"), severity=body.get("severity", "info"),
                     payload=body.get("payload") or {})
    return {"published": ev.type, "id": ev.id}


@application.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    if not ws_authorized(websocket):
        await websocket.close(code=4401)
        return
    await hub.connect(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "stream.connected", "ts": time.time(),
                                              "detail": "Real backend state → real-time 3D visualization.",
                                              "last_id": hub.last_id}))
        while True:
            # Client messages are pings/filters only. Nothing is executed from a socket message.
            message = await websocket.receive_text()
            if message.strip() in ("ping", "{\"type\":\"ping\"}"):
                await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.disconnect(websocket)
