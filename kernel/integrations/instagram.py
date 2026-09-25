"""Instagram connector — Graph API for Business/Creator accounts only.

Explicitly unsupported by policy: mass DMs, engagement fraud, comment spam, fake testimonials,
scraping private data. Optimise ATTENTION → RELEVANCE → TRUST → ACTION, never vanity metrics alone.
"""
from __future__ import annotations

import os

from .base import Capability, Connector


class InstagramConnector(Connector):
    id = "instagram"
    label = "Instagram (Graph API)"
    kind = "social"
    docs_url = "https://developers.facebook.com/docs/instagram-api"
    required_env = ["EMPIRE_INSTAGRAM_ACCESS_TOKEN", "EMPIRE_INSTAGRAM_BUSINESS_ID"]
    scopes = ["instagram_basic", "instagram_manage_insights", "pages_read_engagement"]
    free_tier_note = "Graph API is free within rate limits. Requires a Business/Creator account linked to a Page."
    capabilities = [
        Capability("profile", "Account profile and follower count", "LOW"),
        Capability("media_insights", "Per-post reach, saves, shares", "LOW"),
        Capability("comment_summary", "Read comments and classify intent (draft responses only)", "LOW"),
        Capability("content_plan", "Plan posts/reels with declared jobs", "LOW"),
        Capability("publish", "Publish a post/reel", "HIGH", implemented=False,
                   note="Publishing requires owner approval per asset. Not enabled by default."),
        Capability("mass_dm", "Bulk direct messages", "HIGH", implemented=False,
                   note="Refused by design: spam, deception and platform-rule violations are forbidden."),
        Capability("engagement_fraud", "Fake engagement", "HIGH", implemented=False,
                   note="Refused by design."),
    ]

    def _token(self) -> str:
        return os.environ.get("EMPIRE_INSTAGRAM_ACCESS_TOKEN", "")

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        biz = os.environ.get("EMPIRE_INSTAGRAM_BUSINESS_ID", "")
        res = self.http("GET", f"https://graph.facebook.com/v21.0/{biz}",
                        params={"fields": "id,username,followers_count", "access_token": self._token()},
                        action="probe")
        return {"status": res.get("status"), "detail": res.get("data", {}).get("username", ""),
                "verified": res.get("status") == "ok"}

    def media_insights(self, *, limit: int = 25) -> dict:
        refusal = self._require_credentials("media_insights")
        if refusal:
            return refusal
        self._guard("media_insights")
        biz = os.environ.get("EMPIRE_INSTAGRAM_BUSINESS_ID", "")
        media = self.http("GET", f"https://graph.facebook.com/v21.0/{biz}/media",
                          params={"fields": "id,caption,media_type,timestamp,permalink",
                                  "limit": limit, "access_token": self._token()},
                          action="media_insights")
        return {"status": media.get("status"), "media": media.get("data"), "verified": media.get("status") == "ok"}

    def publish(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY",
                "reason": "Publishing is HIGH risk: it goes to the owner approval queue with the claims "
                          "review attached. This connector does not publish unattended.",
                "verified": False}

    def mass_dm(self, **_: object) -> dict:
        return {"status": "REFUSED", "reason":
                "Mass DMs are spam. The constitution forbids spam, deception and platform-rule violations.",
                "verified": False}

    def engagement_fraud(self, **_: object) -> dict:
        return {"status": "REFUSED", "reason": "Fabricated engagement is fraud.", "verified": False}
