"""Integration layer — one connector per platform, official APIs only, isolated by design.

Rules enforced here:
  * No connector works without owner-provided official credentials.
  * Reads are allowed; writes/publishes/sends are HIGH risk and go to the approval queue.
  * Nothing is simulated: a disconnected connector says so and does nothing.
  * All external calls pass the kill-switch / safe-mode guard.
"""
from __future__ import annotations

from .base import Capability, Connector
from .facebook import FacebookConnector
from .gmail import GmailConnector
from .gumroad import GumroadConnector
from .instagram import InstagramConnector
from .web import WebConnector
from .whatsapp import WhatsAppConnector
from .youtube import YouTubeConnector

CONNECTORS: dict[str, Connector] = {
    c.id: c for c in [
        GmailConnector(), YouTubeConnector(), InstagramConnector(), FacebookConnector(),
        WhatsAppConnector(), GumroadConnector(), WebConnector(),
    ]
}


def get(connector_id: str) -> Connector:
    if connector_id not in CONNECTORS:
        raise KeyError(f"Unknown connector '{connector_id}'. Available: {list(CONNECTORS)}")
    return CONNECTORS[connector_id]


def status_all(*, write: bool = True) -> list[dict]:
    return [c.status(write=write) for c in CONNECTORS.values()]


def describe_all() -> list[dict]:
    return [c.describe() for c in CONNECTORS.values()]


def health_check_all() -> dict:
    """Health is only claimed when a live call actually succeeded."""
    results = {}
    for cid, connector in CONNECTORS.items():
        if not connector.credentials_present():
            results[cid] = {"status": "NO_CREDENTIALS", "live_call_succeeded": False}
            connector.status()
            continue
        try:
            probe = connector.probe()
            results[cid] = {"status": probe.get("status", "unknown"),
                            "live_call_succeeded": probe.get("status") == "ok",
                            "detail": probe.get("error") or probe.get("detail")}
        except Exception as exc:
            results[cid] = {"status": "ERROR", "live_call_succeeded": False,
                            "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return results


__all__ = ["CONNECTORS", "Capability", "Connector", "get", "status_all", "describe_all",
           "health_check_all"]
