"""Base connector: official APIs only, read-first, approval-gated writes, honest status.

A connector that has no credentials reports `NO_CREDENTIALS` and every capability call returns a
structured refusal — it never simulates a successful API call.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .. import store
from ..crypto import redact
from ..eventbus import E, bus
from ..governance import audit, approvals, kill_switch_engaged, safe_mode
from ..killswitch import external_frozen


@dataclass
class Capability:
    name: str
    description: str
    risk: str = "LOW"        # LOW read | HIGH write/publish/send
    implemented: bool = True
    note: str = ""


class Connector:
    id: str = "base"
    label: str = "Base connector"
    kind: str = "api"
    docs_url: str = ""
    required_env: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    free_tier_note: str = ""
    capabilities: list[Capability] = field(default_factory=list)
    oauth: bool = False

    # ---- credentials ---------------------------------------------------
    def credentials_present(self) -> bool:
        return all(bool(os.environ.get(k)) for k in self.required_env)

    def missing_env(self) -> list[str]:
        return [k for k in self.required_env if not os.environ.get(k)]

    def status(self, *, write: bool = True) -> dict:
        if not self.required_env:
            state = "DISCONNECTED"
            error = "No credential variables declared for this connector."
        elif self.credentials_present():
            state = "CONNECTED"
            error = None
        else:
            state = "NO_CREDENTIALS"
            error = f"Missing: {', '.join(self.missing_env())}"
        info = {
            "id": self.id, "label": self.label, "kind": self.kind, "status": state,
            "required_env": self.required_env, "missing_env": self.missing_env(),
            "scopes": self.scopes, "docs_url": self.docs_url,
            "free_tier": self.free_tier_note, "error": error,
            "capabilities": [c.__dict__ for c in self.capabilities],
            "last_check": time.time(),
            "honesty": ("Connected: credentials present. Health is confirmed only by a successful live call."
                        if state == "CONNECTED" else
                        "Not connected. Nothing is being read from or written to this platform."),
            "frozen": external_frozen(),
        }
        if write:
            row = store.get("integrations", self.id)
            if row:
                store.update("integrations", self.id, {"status": state, "last_check": time.time(),
                                                       "last_error": error,
                                                       "scopes_json": json.dumps(self.scopes)})
            else:
                store.insert("integrations", {"id": self.id, "status": state, "last_check": time.time(),
                                              "last_error": error, "scopes_json": json.dumps(self.scopes)})
        return info

    # ---- guards --------------------------------------------------------
    def _guard(self, action: str, *, approval_payload: dict | None = None) -> None:
        if kill_switch_engaged():
            raise RuntimeError(f"Kill switch engaged — '{self.id}.{action}' refused.")
        if safe_mode():
            raise RuntimeError(f"Safe mode — '{self.id}.{action}' refused.")
        if external_frozen():
            raise RuntimeError(f"External actions frozen — '{self.id}.{action}' refused.")

    def _require_credentials(self, action: str) -> dict | None:
        """Returns a structured refusal when credentials are missing (never fakes success)."""
        if self.credentials_present():
            return None
        refusal = {
            "status": "NO_CREDENTIALS",
            "connector": self.id,
            "action": action,
            "required_env": self.missing_env(),
            "detail": (f"{self.label} is not connected. Add {', '.join(self.missing_env())} to .env "
                       f"(official API credentials only — never a password). Docs: {self.docs_url}"),
            "verified": False,
            "did_nothing": True,
        }
        bus.publish(E.INTEGRATION_CALL, source="integrations", severity="warning",
                    payload={"connector": self.id, "action": action, "result": "NO_CREDENTIALS"})
        return refusal

    def request_approval(self, *, action: str, what: str, why: str, expected_result: str,
                         risk_notes: str, reversibility: str, evidence: list | None = None,
                         requester: str = "integration-agent", department_id: str | None = None,
                         payload: dict | None = None) -> dict:
        return approvals.request(action=f"{self.id}.{action}", risk="HIGH", requester=requester,
                                 requester_rank="AGENT", what=what, why=why,
                                 expected_result=expected_result, risk_notes=risk_notes,
                                 reversibility=reversibility, evidence=evidence or [],
                                 department_id=department_id, tool=f"integration.{action}",
                                 payload=payload or {})

    # ---- HTTP ----------------------------------------------------------
    def http(self, method: str, url: str, *, params: dict | None = None, body: dict | None = None,
             headers: dict | None = None, timeout: int = 20, action: str = "http",
             approved: bool = False) -> dict:
        """Single audited HTTP path. Every call is quota-counted and logged (secrets redacted)."""
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "SauravAICivilization/1.0 (local, owner-run)",
                                              **(headers or {})})
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="replace")
                code = resp.status
            parsed: Any
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = {"raw": raw[:2000]}
            result = {"status": "ok", "http_status": code, "data": parsed,
                      "duration_ms": int((time.time() - started) * 1000), "verified": True}
        except urllib.error.HTTPError as exc:
            result = {"status": "error", "http_status": exc.code,
                      "error": redact(exc.read().decode("utf-8", errors="replace")[:400]),
                      "verified": False}
        except Exception as exc:
            result = {"status": "error", "error": f"{type(exc).__name__}: {redact(str(exc))[:200]}",
                      "verified": False}
        store.bump_counter(f"integration_calls::{self.id}")
        bus.publish(E.INTEGRATION_CALL, source="integrations", severity="debug",
                    payload={"connector": self.id, "action": action, "status": result["status"],
                             "http_status": result.get("http_status"),
                             "duration_ms": result.get("duration_ms")})
        audit("integration-agent", f"{self.id}.{action}", tool=f"integration.{action}",
              risk="HIGH" if approved else "LOW", target=action, allowed=True,
              reason="owner-approved external call" if approved else "read-only external call",
              payload={"http_status": result.get("http_status"), "url": redact(url)[:200]})
        return result

    def describe(self) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind, "docs_url": self.docs_url,
                "required_env": self.required_env, "scopes": self.scopes,
                "free_tier": self.free_tier_note,
                "capabilities": [c.__dict__ for c in self.capabilities],
                "connected": self.credentials_present()}
