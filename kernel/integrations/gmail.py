"""Gmail connector — official OAuth only. Raw passwords are never accepted or stored."""
from __future__ import annotations

import os
import time

from .base import Capability, Connector


class GmailConnector(Connector):
    id = "gmail"
    label = "Gmail (official API)"
    kind = "email"
    docs_url = "https://developers.google.com/gmail/api"
    required_env = ["EMPIRE_GMAIL_CLIENT_ID", "EMPIRE_GMAIL_CLIENT_SECRET", "EMPIRE_GMAIL_REFRESH_TOKEN"]
    scopes = ["gmail.readonly", "gmail.compose"]     # deliberately NOT gmail.send without approval
    free_tier_note = "Google API quota is free within limits. Read-only + draft scopes requested by default."
    oauth = True
    capabilities = [
        Capability("list_unread", "List recent unread messages (metadata only)", "LOW"),
        Capability("summarize", "Summarize a message into facts / asks / deadlines", "LOW"),
        Capability("draft_reply", "Create a Gmail DRAFT — never sends", "MEDIUM"),
        Capability("send", "Send a message", "HIGH", implemented=False,
                   note="Requires gmail.send scope plus explicit owner approval per message. "
                        "Batch sending is intentionally unsupported."),
        Capability("extract_tasks", "Turn a message into internal tasks", "LOW"),
    ]

    def _token(self) -> str:
        """Exchange the refresh token for an access token using the official OAuth endpoint."""
        body = {
            "client_id": os.environ.get("EMPIRE_GMAIL_CLIENT_ID", ""),
            "client_secret": os.environ.get("EMPIRE_GMAIL_CLIENT_SECRET", ""),
            "refresh_token": os.environ.get("EMPIRE_GMAIL_REFRESH_TOKEN", ""),
            "grant_type": "refresh_token",
        }
        res = self.http("POST", "https://oauth2.googleapis.com/token", body=body,
                        action="oauth_refresh", timeout=20)
        if res.get("status") != "ok":
            raise RuntimeError(f"OAuth refresh failed: {res.get('error') or res.get('http_status')}")
        return res["data"]["access_token"]

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        token = self._token()
        res = self.http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                        headers={"Authorization": f"Bearer {token}"}, action="probe")
        if res.get("status") == "ok":
            return {"status": "ok", "detail": f"Mailbox: {res['data'].get('emailAddress', 'unknown')}"}
        return res

    def list_unread(self, *, limit: int = 10) -> dict:
        refusal = self._require_credentials("list_unread")
        if refusal:
            return refusal
        self._guard("list_unread")
        token = self._token()
        res = self.http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                        params={"q": "is:unread", "maxResults": min(limit, 25)},
                        headers={"Authorization": f"Bearer {token}"}, action="list_unread")
        return res

    def draft_reply(self, *, thread_id: str, body: str, requester: str = "agent") -> dict:
        """Creates a draft. Sending is a separate, approval-gated action that is not implemented."""
        refusal = self._require_credentials("draft_reply")
        if refusal:
            return refusal
        self._guard("draft_reply")
        approval = self.request_approval(
            action="draft_reply",
            what=f"Create a Gmail draft on thread {thread_id}",
            why="Drafting is reversible and visible to the owner before any sending.",
            expected_result="A draft appears in the mailbox for owner review.",
            risk_notes="Draft content may contain unverified claims — the claims validator must pass first.",
            reversibility="Fully reversible: drafts can be deleted.",
            requester=requester, payload={"thread_id": thread_id, "body_preview": body[:200]},
        )
        return {"status": "APPROVAL_REQUIRED", "approval_id": approval["id"],
                "detail": "Draft creation queued for owner approval. Nothing was written to Gmail.",
                "requested_at": time.time(), "verified": False}

    def send(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY", "reason":
                "Sending email is a HIGH-risk action. This connector deliberately cannot send; "
                "the owner sends from Gmail after reviewing the draft.",
                "scopes_missing_on_purpose": ["gmail.send"], "verified": False}
