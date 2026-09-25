"""Customer and offer intelligence — master prompt §9–§18 as executable gates.

Three things live here:

  * `OfferDesign` (§12–§14) — an offer is refused a LIVE status until it answers TARGET CUSTOMER,
    PROBLEM, DESIRED OUTCOME, OFFER, PROOF, OBJECTION, CTA, FUNNEL, FOLLOW-UP, RETENTION, REFERRAL.
    Every proof item must be a labelled claim, so a testimonial nobody wrote cannot be typed in by
    accident: it would have to be written as `Claim(kind=FACT, source=...)` and would then be
    auditable, or it fails the schema.
  * `customer` records (§15–§18) — minimum necessary data, consent-aware, qualification by
    NEED + ABILITY TO PAY + URGENCY + FIT + TRUST + CONVERSION PROBABILITY + LTV. Segmentation is
    for relevance, not surveillance; there is no field here for anything sensitive.
  * `WriterNationGate` (§11) — DEMAND → TRUST → DELIVERY COST → MARGIN → SCALABILITY → LEGAL RISK →
    CUSTOMER OUTCOME. Impressive is not buildable, and the gate says so before launch, not after.

Revenue attributed to a customer comes only from verified ledger entries. No entry, no revenue.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import store
from .eventbus import bus
from .governance import (ASSUMPTION, FACT, HYPOTHESIS, INFERENCE, OPINION, UNKNOWN,
                         ESTIMATE_STAMP, UNVERIFIED_STAMP, claims as claims_validator)
# Claim lives with the decision standard so there is exactly one claim class in the system.
from .decision import Claim

# ---------------------------------------------------------------------------
# §11 Writer Nation gate
# ---------------------------------------------------------------------------
GATE_STAGES = ("DEMAND", "TRUST", "DELIVERY_COST", "MARGIN", "SCALABILITY", "LEGAL_RISK",
               "CUSTOMER_OUTCOME")

GATE_QUESTIONS = {
    "DEMAND": "Do real people, who are not friends or relatives, want this and have asked for it?",
    "TRUST": "What lets a stranger verify we can deliver — shown, not claimed?",
    "DELIVERY_COST": "What does it cost in hours and rupees to deliver once, measured?",
    "MARGIN": "After delivery cost, is the contribution positive at the planned price?",
    "SCALABILITY": "What breaks at 10x volume — and what is the fix?",
    "LEGAL_RISK": "Which claims, data, IP or platform rules apply, and what is approval-gated?",
    "CUSTOMER_OUTCOME": "What measurable result does the customer get, and who confirms it?",
}


@dataclass
class WriterNationGate:
    """A service may not launch on enthusiasm. Each stage needs an answer and its evidence kind."""

    answers: dict = field(default_factory=dict)     # stage -> {"answer": str, "kind": label, "evidence": str}

    def pass_stage(self, stage: str, answer: str, *, kind: str = UNKNOWN, evidence: str = "") -> "WriterNationGate":
        if stage not in GATE_STAGES:
            raise ValueError(f"Unknown gate stage {stage!r}. Allowed: {GATE_STAGES}")
        self.answers[stage] = {"answer": answer, "kind": kind, "evidence": evidence,
                               "passed_clean": kind == FACT and bool(evidence)}
        return self

    def review(self) -> dict:
        missing = [s for s in GATE_STAGES if not self.answers.get(s, {}).get("answer")]
        unproven = [s for s in GATE_STAGES
                    if self.answers.get(s) and not self.answers[s].get("passed_clean")]
        verdict = "PASS" if not missing and not unproven else ("BLOCK" if missing else "TEST")
        return {
            "gate": "WRITER NATION — " + " → ".join(GATE_STAGES),
            "verdict": verdict,
            "missing_stages": missing,
            "stages_answered_without_verified_evidence": unproven,
            "questions": {s: GATE_QUESTIONS[s] for s in (missing + unproven)},
            "note": "Impressive is not buildable. A stage answered on opinion is a stage that has not been answered.",
        }


# ---------------------------------------------------------------------------
# §12–§14 Offer design
# ---------------------------------------------------------------------------
OFFER_FIELDS = ("target_customer", "problem", "desired_outcome", "what_it_is", "proof", "objections",
                "call_to_action", "funnel", "follow_up", "retention", "referral")
JOURNEY = ("ATTRACT", "EDUCATE", "BUILD_TRUST", "QUALIFY", "CONVERT", "DELIVER", "RETAIN", "REFER")
CONTENT_JOBS = ("awareness", "education", "trust", "authority", "engagement", "lead-gen",
                "conversion", "retention", "referral")
FORBIDDEN_PERSUASION = re.compile(
    r"\b(fake (?:scarcity|reviews?|testimonials?|urgency)|guaranteed income|get rich quick|"
    r"no[- ]risk guaranteed|hack the algorithm|impersonate)\b", re.I)


@dataclass
class OfferDesign:
    name: str
    target_customer: str = ""
    problem: str = ""
    desired_outcome: str = ""
    what_it_is: str = ""
    proof: list[Claim] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    call_to_action: str = ""
    funnel: list[dict] = field(default_factory=list)      # [{"step": "ATTRACT", "job": "...", "asset": "..."}]
    follow_up: str = ""
    retention: str = ""
    referral: str = ""
    price_inr: float = 0.0
    status: str = "DRAFT"
    id: str | None = None

    # ---- construction --------------------------------------------------
    def add_proof(self, text: str, *, kind: str = UNKNOWN, source: str = "", verified: bool = False) -> "OfferDesign":
        self.proof.append(Claim(text=text, kind=kind, source=source, verified=verified))
        return self

    @classmethod
    def from_dict(cls, data: dict) -> "OfferDesign":
        proof = [p if isinstance(p, Claim) else Claim(**p) for p in (data.get("proof") or [])]
        return cls(**{**{k: v for k, v in data.items() if k in OFFER_FIELDS}, "name": data.get("name", ""),
                      "price_inr": float(data.get("price_inr", 0) or 0),
                      "status": data.get("status", "DRAFT"), "proof": proof})

    # ---- gates ---------------------------------------------------------
    def gaps(self) -> list[str]:
        out = [f"missing field: {f}" for f in OFFER_FIELDS if not getattr(self, f)]
        if self.price_inr < 0:
            out.append("price cannot be negative")
        if not any(c.kind == FACT and c.verified for c in self.proof):
            out.append("no verified FACT in proof — the offer may not go live on claims alone")
        steps = {str(s.get("step", "")).upper() for s in self.funnel}
        missing_journey = [s for s in ("ATTRACT", "CONVERT", "DELIVER") if s not in steps]
        if missing_journey:
            out.append(f"funnel missing mandatory journey step(s): {', '.join(missing_journey)}")
        for s in self.funnel:
            job = str(s.get("job", "")).lower()
            if job and job not in CONTENT_JOBS:
                out.append(f"funnel step {s.get('step') or '?'} declares an unknown job {job!r}")
        return out

    def ethics_scan(self) -> dict:
        body = " ".join([self.name, self.problem, self.desired_outcome, self.what_it_is,
                         self.call_to_action, self.follow_up, self.retention, self.referral,
                         *self.objections])
        review = claims_validator.review(body, context="offer")
        forbidden = [m.group(0) for m in FORBIDDEN_PERSUASION.finditer(body)]
        blocks = list(review["blocks"])
        if forbidden:
            blocks.append({"severity": "block", "rule": "forbidden_persuasion", "detail":
                           "Fake scarcity, fake proof, false urgency, deception and impersonation are "
                           "hard-coded refusals, not preferences.", "match": forbidden[0][:120]})
        return {"blocks": blocks, "warnings": review["warnings"], "clean": not blocks}

    def may_go_live(self) -> dict:
        gaps, ethics = self.gaps(), self.ethics_scan()
        allowed = not gaps and ethics["clean"]
        return {"allowed": allowed, "gaps": gaps, "ethics": ethics,
                "reason": "Offer passes demand/trust/delivery gates and the ethical screen."
                if allowed else "Offer is not launchable yet: " + "; ".join(gaps or [b["rule"] for b in ethics["blocks"]])}

    def launch(self) -> dict:
        check = self.may_go_live()
        if not check["allowed"]:
            return {"status": self.status, "launched": False, **check}
        self.status = "LIVE"
        row = self.persist()
        bus.publish("customer.offer_live", source="customer-intelligence", subject=row["id"],
                    payload={"name": self.name, "price_inr": self.price_inr,
                             "proof_verified": sum(1 for c in self.proof if c.kind == FACT and c.verified)})
        return {"status": "LIVE", "launched": True, "id": row["id"], "gaps": []}

    # ---- persistence ---------------------------------------------------
    def persist(self) -> dict:
        self.id = self.id or store.new_id("off")
        row = {
            "id": self.id, "name": self.name, "target_customer": self.target_customer,
            "problem": self.problem, "desired_outcome": self.desired_outcome,
            "what_it_is": self.what_it_is, "proof_json": store.jdump([p.to_dict() for p in self.proof]),
            "objections_json": store.jdump(self.objections), "call_to_action": self.call_to_action,
            "funnel_json": store.jdump(self.funnel), "follow_up": self.follow_up,
            "retention": self.retention, "referral": self.referral, "price_inr": self.price_inr,
            "status": self.status, "gaps_json": store.jdump(self.gaps()),
            "created_at": store.now(), "updated_at": store.now(),
        }
        if store.get("offers", self.id):
            store.update("offers", self.id, row)
        else:
            store.insert("offers", row)
        return row

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, **{f: getattr(self, f) for f in OFFER_FIELDS
                                                     if f != "proof"},
                "proof": [p.to_dict() for p in self.proof], "price_inr": self.price_inr,
                "status": self.status, "gaps": self.gaps(), "journey": list(JOURNEY),
                "may_go_live": self.may_go_live()}


# ---------------------------------------------------------------------------
# §15–§18 Customer intelligence
# ---------------------------------------------------------------------------
CUSTOMER_STATUSES = ("LEAD", "QUALIFIED", "CUSTOMER", "REPEAT", "INACTIVE", "DISQUALIFIED")
CONSENT_STATES = ("GRANTED", "WITHDRAWN", "UNKNOWN")
QUALIFICATION_BANDS = ("HIGH", "MEDIUM", "LOW", "DISQUALIFY")

# Minimum necessary means exactly that: no free-text basket of personal detail.
SENSITIVE = re.compile(
    r"\b(aadhaar|pan\s*(?:number|card)|passport|credit\s*card|cvv|password|otp|bank\s*account|"
    r"ifsc|upi\s*(?:id|pin)|diagnosis|medical|health\s*condition|religion|caste|sexual)\b", re.I)
CREDENTIAL_SHAPE = re.compile(r"(?:^|\s)(?:sk-|ghp_|xox[baprs]-|AKIA|eyJ[A-Za-z0-9_\-]{10,})")


@dataclass
class Qualification:
    need: float = 0.0
    ability_to_pay: float = 0.0
    urgency: float = 0.0
    fit: float = 0.0
    trust: float = 0.0
    conversion_probability: float = 0.0
    ltv_inr: float = 0.0

    def __post_init__(self) -> None:
        for name in ("need", "ability_to_pay", "urgency", "fit", "trust", "conversion_probability"):
            v = float(getattr(self, name))
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be a probability between 0 and 1, got {v}")

    def score(self) -> float:
        """Weighted and rational on purpose: attachment may not override disqualifying facts."""
        return round((0.25 * self.need + 0.20 * self.ability_to_pay + 0.15 * self.urgency +
                      0.15 * self.fit + 0.15 * self.trust + 0.10 * self.conversion_probability), 4)

    def band(self) -> str:
        if self.need < 0.4 or self.ability_to_pay < 0.3 or self.trust < 0.3:
            return "DISQUALIFY"
        s = self.score()
        if s >= 0.70:
            return "HIGH"
        if s >= 0.50:
            return "MEDIUM"
        return "LOW"

    def verdict_line(self) -> str:
        return (f"{self.band()} (score {self.score():.2f}) — NEED + ABILITY TO PAY + URGENCY + FIT + "
                f"TRUST + CONVERSION PROBABILITY + LTV({self.ltv_inr:,.0f} INR). "
                "Emotional attachment does not override rational qualification.")

    def to_dict(self) -> dict:
        return {"need": self.need, "ability_to_pay": self.ability_to_pay, "urgency": self.urgency,
                "fit": self.fit, "trust": self.trust,
                "conversion_probability": self.conversion_probability, "ltv_inr": self.ltv_inr,
                "score": self.score(), "band": self.band(), "verdict": self.verdict_line()}


class CustomerLedger:
    """Customer records with consent, minimum-data and real-revenue discipline."""

    def add(self, *, display_name: str, segment: str = "", source: str = "",
            status: str = "LEAD", consent: str = "UNKNOWN", contact_ref: str = "",
            interest: Iterable[str] | None = None, objections: Iterable[str] | None = None,
            qualification: Qualification | None = None, notes: str = "",
            customer_id: str | None = None) -> dict:
        if status not in CUSTOMER_STATUSES:
            raise ValueError(f"status must be one of {CUSTOMER_STATUSES}")
        if consent not in CONSENT_STATES:
            raise ValueError(f"consent must be one of {CONSENT_STATES}")
        blob = " ".join([display_name, segment, source, contact_ref, notes, *(interest or []),
                         *(objections or [])])
        if SENSITIVE.search(blob):
            raise ValueError("Refused: this looks like sensitive personal data. Collect only what is "
                             "necessary, lawful and consent-compatible — segmentation is for relevance, "
                             "not surveillance.")
        if CREDENTIAL_SHAPE.search(blob):
            raise ValueError("Refused: a credential shape (key/token/password) may never be stored in a "
                             "customer record. Credentials live in the secret manager, never in data.")
        q = qualification or Qualification()
        row = {
            "id": customer_id or store.new_id("cus"), "display_name": display_name, "segment": segment,
            "source": source, "status": status, "consent": consent, "contact_ref": contact_ref,
            "interest_json": store.jdump(list(interest or [])),
            "objections_json": store.jdump(list(objections or [])),
            "score": q.score(), "band": q.band(), "ltv_inr": q.ltv_inr, "revenue_inr": 0.0,
            "notes": notes, "created_at": store.now(), "updated_at": store.now(),
        }
        store.insert("customers", row)
        return row

    def may_contact(self, customer_id: str, *, purpose: str = "service") -> dict:
        """Consent is a precondition, not a formality. Unknown consent means no outbound contact."""
        row = store.get("customers", customer_id)
        if not row:
            return {"allowed": False, "reason": f"no customer {customer_id!r}"}
        consent = row.get("consent")
        allowed = consent == "GRANTED" or (consent == "UNKNOWN" and purpose == "service")
        return {"allowed": allowed, "consent": consent, "purpose": purpose,
                "reason": {"GRANTED": "Consent recorded.",
                           "WITHDRAWN": "Consent withdrawn — no contact of any kind, and delete on request.",
                           "UNKNOWN": "No consent on record: transactional service messages only, "
                                      "never marketing."}[consent]}

    def verified_revenue(self, customer_id: str) -> float:
        """Only money the ledger verified counts. An invoice is not revenue."""
        rows = store.query("SELECT amount_inr FROM ledger WHERE customer_id = ? AND direction = 'IN' "
                           "AND verified = 1", (customer_id,))
        return float(sum(float(r["amount_inr"] or 0) for r in rows))

    def scorecard(self) -> dict:
        rows = store.query("SELECT status, band, consent, COUNT(*) AS n FROM customers GROUP BY status, band, consent")
        total = sum(int(r["n"]) for r in rows) or 0
        by_band: dict[str, int] = {}
        by_consent: dict[str, int] = {}
        for r in rows:
            by_band[r["band"] or "UNSCORED"] = by_band.get(r["band"] or "UNSCORED", 0) + int(r["n"])
            by_consent[r["consent"]] = by_consent.get(r["consent"], 0) + int(r["n"])
        revenue = float(store.get_setting("verified_revenue_inr", 0) or 0)
        return {"customers": total, "by_band": by_band, "by_consent": by_consent,
                "by_status": {r["status"]: int(r["n"]) for r in rows if r["band"] is None or True},
                "verified_revenue_inr": revenue,
                "data_policy": "minimum necessary, lawful, consent-compatible",
                "honesty": "Reported revenue counts verified ledger entries only. Everything else is intention."}

    def objections(self, limit: int = 100) -> list[str]:
        out: list[str] = []
        for r in store.query("SELECT objections_json FROM customers ORDER BY updated_at DESC LIMIT ?", (limit,)):
            out.extend(store.jload(r["objections_json"], []) or [])
        return out


offer_ledger = CustomerLedger()
customers = offer_ledger        # the module exposes one ledger; the name records the intent
