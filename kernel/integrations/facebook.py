"""Facebook Page connector — Graph API, insights read-only by default."""
from __future__ import annotations

import os

from .base import Capability, Connector


class FacebookConnector(Connector):
    id = "facebook"
    label = "Facebook Page (Graph API)"
    kind = "social"
    docs_url = "https://developers.facebook.com/docs/graph-api"
    required_env = ["EMPIRE_FACEBOOK_PAGE_TOKEN", "EMPIRE_FACEBOOK_PAGE_ID"]
    scopes = ["pages_read_engagement", "read_insights"]
    free_tier_note = "Free within Graph API rate limits."
    capabilities = [
        Capability("page_insights", "Reach, engagement, follower growth", "LOW"),
        Capability("post_summary", "Summarise recent posts and response quality", "LOW"),
        Capability("publish", "Publish to the Page", "HIGH", implemented=False,
                   note="Approval-gated; not enabled by default."),
    ]

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        page = os.environ.get("EMPIRE_FACEBOOK_PAGE_ID", "")
        res = self.http("GET", f"https://graph.facebook.com/v21.0/{page}",
                        params={"fields": "id,name,fan_count",
                                "access_token": os.environ.get("EMPIRE_FACEBOOK_PAGE_TOKEN", "")},
                        action="probe")
        return {"status": res.get("status"), "detail": res.get("data", {}).get("name", ""),
                "verified": res.get("status") == "ok"}

    def page_insights(self, *, metric: str = "page_impressions") -> dict:
        refusal = self._require_credentials("page_insights")
        if refusal:
            return refusal
        self._guard("page_insights")
        page = os.environ.get("EMPIRE_FACEBOOK_PAGE_ID", "")
        return self.http("GET", f"https://graph.facebook.com/v21.0/{page}/insights",
                         params={"metric": metric,
                                 "access_token": os.environ.get("EMPIRE_FACEBOOK_PAGE_TOKEN", "")},
                         action="page_insights")

    def publish(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY",
                "reason": "Publishing is approval-gated. This connector cannot post unattended.",
                "verified": False}
