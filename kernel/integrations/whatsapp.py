"""WhatsApp Cloud API connector — consent-based messaging only.

The constitution's rules for messaging are enforced here: no unsolicited bulk messaging, no
template spam, and every outbound message is approval-gated. Messaging costs money beyond the
free service window, so spend approval applies as well.
"""
from __future__ import annotations

import os

from .base import Capability, Connector


class WhatsAppConnector(Connector):
    id = "whatsapp"
    label = "WhatsApp Cloud API"
    kind = "messaging"
    docs_url = "https://developers.facebook.com/docs/whatsapp/cloud-api"
    required_env = ["EMPIRE_WHATSAPP_TOKEN", "EMPIRE_WHATSAPP_PHONE_ID"]
    scopes = ["whatsapp_business_messaging"]
    free_tier_note = ("Free service conversations within Meta's current allowance; template/business-initiated "
                      "messages are billed. This system treats paid messaging as requiring owner approval.")
    capabilities = [
        Capability("webhook_summary", "Classify inbound messages and extract asks", "LOW"),
        Capability("draft_template", "Draft an approved-template message", "MEDIUM"),
        Capability("send_template", "Send a template message to a consenting contact", "HIGH",
                   implemented=False,
                   note="Requires opt-in proof, owner approval, and a spend decision. Not enabled by default."),
        Capability("broadcast", "Bulk broadcast", "HIGH", implemented=False,
                   note="Refused by design: bulk messaging without consent is spam."),
    ]

    def probe(self) -> dict:
        refusal = self._require_credentials("probe")
        if refusal:
            return refusal
        self._guard("probe")
        phone_id = os.environ.get("EMPIRE_WHATSAPP_PHONE_ID", "")
        res = self.http("GET", f"https://graph.facebook.com/v21.0/{phone_id}",
                        params={"fields": "id,display_phone_number,verified_name",
                                "access_token": os.environ.get("EMPIRE_WHATSAPP_TOKEN", "")},
                        action="probe")
        return {"status": res.get("status"), "detail": res.get("data", {}).get("verified_name", ""),
                "verified": res.get("status") == "ok"}

    def send_template(self, **_: object) -> dict:
        return {"status": "NOT_IMPLEMENTED_BY_POLICY",
                "reason": "Sending requires: verified consent, owner approval, and a confirmed spend decision.",
                "verified": False}

    def broadcast(self, **_: object) -> dict:
        return {"status": "REFUSED", "reason": "Bulk unsolicited messaging is spam.", "verified": False}
