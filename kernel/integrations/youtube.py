"""YouTube connector — Data API v3, read-only analytics by default."""
from __future__ import annotations

import os

from .base import Capability, Connector


class YouTubeConnector(Connector):
    id = "youtube"
    label = "YouTube (Data API v3)"
    kind = "media"
    docs_url = "https://developers.google.com/youtube/v3/docs"
    required_env = ["EMPIRE_YOUTUBE_API_KEY"]
    scopes = ["youtube.readonly"]
    free_tier_note = "10,000 quota units/day free. A single search.list costs 100 units — spend carefully."
    capabilities = [
        Capability("channel_stats", "Subscribers, views, video count", "LOW"),
        Capability("recent_videos", "List recent uploads with statistics", "LOW"),
        Capability("analyze_titles", "Analyse titles/hooks for honest curiosity (no deceptive clickbait)", "LOW"),
        Capability("upload", "Upload a video", "HIGH", implemented=False,
                   note="Requires OAuth channel authorization + owner approval. Not enabled by default."),
    ]

    def _key(self) -> str:
        return os.environ.get("EMPIRE_YOUTUBE_API_KEY", "")

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        res = self.http("GET", "https://www.googleapis.com/youtube/v3/videos",
                        params={"part": "id", "chart": "mostPopular", "maxResults": 1, "key": self._key()},
                        action="probe")
        return {"status": res.get("status"), "detail": "API key valid (public data reachable)."
                if res.get("status") == "ok" else res.get("error"), "verified": res.get("status") == "ok"}

    def channel_stats(self, *, channel_id: str) -> dict:
        refusal = self._require_credentials("channel_stats")
        if refusal:
            return refusal
        self._guard("channel_stats")
        return self.http("GET", "https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "statistics,snippet", "id": channel_id, "key": self._key()},
                         action="channel_stats")

    def analyze_titles(self, *, titles: list[str]) -> dict:
        """Offline heuristic review — flags deceptive clickbait patterns, no API cost."""
        banned = ["you won't believe", "shocking truth", "they don't want you to know",
                  "this one trick", "guaranteed", "get rich"]
        flagged = [{"title": t, "issue": [b for b in banned if b in t.lower()]}
                   for t in titles if any(b in t.lower() for b in banned)]
        return {"status": "ok", "checked": len(titles), "flagged": flagged,
                "rule": "A strong title creates curiosity while remaining truthful.",
                "verified": True}

    def upload(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY",
                "reason": "Uploading requires channel OAuth plus per-video owner approval. "
                          "This connector cannot publish on its own.",
                "verified": False}
