"""Gumroad connector — commerce read path (products, sales, revenue).

Revenue read from Gumroad is *reported* revenue: it is only entered into the ledger as verified
if the owner confirms it corresponds to real settled transactions.
"""
from __future__ import annotations

import os

from .base import Capability, Connector


class GumroadConnector(Connector):
    id = "gumroad"
    label = "Gumroad (Commerce)"
    kind = "commerce"
    docs_url = "https://app.gumroad.com/api"
    required_env = ["EMPIRE_GUMROAD_ACCESS_TOKEN"]
    scopes = ["view_sales", "view_products"]
    free_tier_note = "API access is free; platform fees apply per sale."
    capabilities = [
        Capability("products", "List products and prices", "LOW"),
        Capability("sales", "List sales with amounts and timestamps", "LOW"),
        Capability("revenue_summary", "Summarise revenue by product", "LOW"),
        Capability("update_product", "Change price/description", "HIGH", implemented=False,
                   note="Approval-gated: pricing changes affect real customers."),
    ]

    def _token(self) -> str:
        return os.environ.get("EMPIRE_GUMROAD_ACCESS_TOKEN", "")

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        res = self.http("GET", "https://api.gumroad.com/v2/products",
                        headers={"Authorization": f"Bearer {self._token()}"}, action="probe")
        return {"status": res.get("status"),
                "detail": f"{len((res.get('data') or {}).get('products', []) or [])} product(s) visible."
                if res.get("status") == "ok" else res.get("error"),
                "verified": res.get("status") == "ok"}

    def products(self) -> dict:
        refusal = self._require_credentials("products")
        if refusal:
            return refusal
        self._guard("products")
        return self.http("GET", "https://api.gumroad.com/v2/products",
                         headers={"Authorization": f"Bearer {self._token()}"}, action="products")

    def sales(self, *, after: str | None = None) -> dict:
        refusal = self._require_credentials("sales")
        if refusal:
            return refusal
        self._guard("sales")
        params = {"after": after} if after else None
        return self.http("GET", "https://api.gumroad.com/v2/sales", params=params,
                         headers={"Authorization": f"Bearer {self._token()}"}, action="sales")

    def update_product(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY",
                "reason": "Changing a live price or promise affects real customers — owner approval required.",
                "verified": False}
