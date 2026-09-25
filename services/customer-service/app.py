"""Customer Intelligence Service (port 8014) — offers, customers, the Writer Nation gate.

Layer D (economic engine): §11–§18 of the constitution. This service owns the two things money
actually depends on — a real offer and a real customer — and it refuses to pretend either exists
before it does. Every endpoint answers in the §28 shape where a judgement is involved, so the owner
sees the reasoning, not a verdict from a black box.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from kernel import store
from kernel.customers import (CONSENT_STATES, CUSTOMER_STATUSES, GATE_STAGES, JOURNEY, OFFER_FIELDS,
                              CustomerLedger, OfferDesign, Qualification, WriterNationGate)
from kernel.decision import Claim, decision_engine
from kernel.governance import EVIDENCE_KINDS, MINDS, decision_engine_status
from services.base import ServiceCard, require_owner, service_app

PORT = 8014
CARD = ServiceCard(
    name="customer-service", port=PORT, layer="D · economic engine", domain="customer",
    description="Offer design gates (Writer Nation), consent-aware customer records, rational "
                "qualification, and the §28 decision standard for go/no-go calls.",
    owns_tables=["offers", "customers", "decisions (writes)", "lessons (writes)"],
    produces_events=["customer.offer_live", "customer.created", "decision.made", "decision.outcome"],
    consumes_events=["economy.*", "workflow.*"],
    endpoints=["GET /customer/meta", "POST /customer/offers/validate", "POST /customer/offers",
               "POST /customer/offers/{offer_id}/launch", "GET /customer/offers",
               "POST /customer/customers", "GET /customer/customers",
               "GET /customer/customers/{customer_id}/contact-check",
               "POST /customer/qualify", "GET /customer/objections", "GET /customer/scorecard",
               "POST /customer/gate/writer-nation",
               "POST /decision/standard", "GET /decision/engine", "GET /decision/records",
               "GET /decision/labels", "GET /decision/calibration",
               "POST /decision/{decision_id}/outcome"],
    dependencies=["kernel.customers", "kernel.decision", "kernel.governance"],
)
application = service_app(CARD)
ledger = CustomerLedger()


# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------
class ProofIn(BaseModel):
    text: str
    kind: str = "UNKNOWN"
    source: str = ""
    verified: bool = False


class OfferIn(BaseModel):
    name: str
    target_customer: str = ""
    problem: str = ""
    desired_outcome: str = ""
    what_it_is: str = ""
    proof: list[ProofIn] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    funnel: list[dict] = Field(default_factory=list)
    follow_up: str = ""
    retention: str = ""
    referral: str = ""
    price_inr: float = 0.0


class QualificationIn(BaseModel):
    need: float = 0.0
    ability_to_pay: float = 0.0
    urgency: float = 0.0
    fit: float = 0.0
    trust: float = 0.0
    conversion_probability: float = 0.0
    ltv_inr: float = 0.0


class CustomerIn(BaseModel):
    display_name: str
    segment: str = ""
    source: str = ""
    status: str = "LEAD"
    consent: str = "UNKNOWN"
    contact_ref: str = ""
    interest: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    qualification: QualificationIn | None = None
    notes: str = ""


class GateIn(BaseModel):
    name: str = "unnamed service"
    answers: dict[str, dict] = Field(default_factory=dict)   # stage -> {"answer","kind","evidence"}


class DecisionIn(BaseModel):
    question: str
    domain: str = "business"
    facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    opinions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    numbers: dict = Field(default_factory=dict)
    minutes: int = 0
    use_model: bool = True
    displaced: str = ""


class OutcomeIn(BaseModel):
    metric_value: float
    note: str = ""
    measured_by: str = "owner"


def _offer_from(payload: OfferIn) -> OfferDesign:
    offer = OfferDesign(
        name=payload.name, target_customer=payload.target_customer, problem=payload.problem,
        desired_outcome=payload.desired_outcome, what_it_is=payload.what_it_is,
        objections=list(payload.objections), call_to_action=payload.call_to_action,
        funnel=list(payload.funnel), follow_up=payload.follow_up, retention=payload.retention,
        referral=payload.referral, price_inr=float(payload.price_inr),
    )
    for p in payload.proof:
        if p.kind not in EVIDENCE_KINDS:
            raise HTTPException(status_code=422, detail={"error": "invalid_claim_kind",
                                                         "allowed": list(EVIDENCE_KINDS)})
        offer.proof.append(Claim(text=p.text, kind=p.kind, source=p.source, verified=p.verified))
    return offer


# ---------------------------------------------------------------------------
# meta + storefronts
# ---------------------------------------------------------------------------
@application.get("/customer/meta")
def meta(_: str = Depends(require_owner)) -> dict:
    return {"service": CARD.name, "layer": CARD.layer,
            "offer_fields_required": list(OFFER_FIELDS), "journey": list(JOURNEY),
            "consent_states": list(CONSENT_STATES), "customer_statuses": list(CUSTOMER_STATUSES),
            "gate_stages": list(GATE_STAGES),
            "data_policy": "Collect only what is necessary, lawful and consent-compatible. "
                           "Segmentation is for relevance, not surveillance. No sensitive fields exist.",
            "revenue_policy": "A customer's revenue counts verified ledger entries only.",
            "minds": list(MINDS),
            "decision_standard": "master prompt §28 — VERDICT / EVIDENCE / 8-MIND / "
                                 "AGREEMENT-DISAGREEMENT / REALITY CHECK / ACTION PLAN / "
                                 "EXPECTED IMPACT / CONFIDENCE"}


@application.post("/customer/offers")
def create_offer(payload: OfferIn, _: str = Depends(require_owner)) -> dict:
    offer = _offer_from(payload)
    row = offer.persist()
    return {"offer": row, "validation": offer.may_go_live(), "gaps": offer.gaps()}


@application.post("/customer/offers/validate")
def validate_offer(payload: OfferIn, _: str = Depends(require_owner)) -> dict:
    offer = _offer_from(payload)
    return {"name": offer.name, "may_go_live": offer.may_go_live(), "gaps": offer.gaps(),
            "ethics": offer.ethics_scan(),
            "note": "An offer goes live only when every required field is answered and at least one "
                    "verified FACT stands behind the proof."}


@application.get("/customer/offers")
def list_offers(limit: int = 50, _: str = Depends(require_owner)) -> dict:
    rows = store.query("SELECT * FROM offers ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["proof"] = store.jload(r.get("proof_json"), [])
        r["gaps"] = store.jload(r.get("gaps_json"), [])
    return {"offers": rows, "count": len(rows)}


@application.post("/customer/offers/{offer_id}/launch")
def launch_offer(offer_id: str, _: str = Depends(require_owner)) -> dict:
    row = store.get("offers", offer_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "offer_not_found", "id": offer_id})
    offer = OfferDesign.from_dict({**row, "proof": store.jload(row.get("proof_json"), []),
                                   "funnel": store.jload(row.get("funnel_json"), []),
                                   "objections": store.jload(row.get("objections_json"), [])})
    offer.id = offer_id
    result = offer.launch()
    if not result["launched"]:
        return {"launched": False, **result}
    return result


# ---------------------------------------------------------------------------
# customers
# ---------------------------------------------------------------------------
@application.post("/customer/customers")
def create_customer(payload: CustomerIn, _: str = Depends(require_owner)) -> dict:
    q = Qualification(**payload.qualification.model_dump()) if payload.qualification else None
    try:
        row = ledger.add(display_name=payload.display_name, segment=payload.segment,
                         source=payload.source, status=payload.status, consent=payload.consent,
                         contact_ref=payload.contact_ref, interest=payload.interest,
                         objections=payload.objections, qualification=q, notes=payload.notes)
    except ValueError as exc:
        # data-minimisation and consent are refusals, not validation warnings
        raise HTTPException(status_code=422, detail={"error": "customer_record_refused", "detail": str(exc)})
    return {"customer": row, "verified_revenue_inr": ledger.verified_revenue(row["id"]),
            "contact": ledger.may_contact(row["id"])}


@application.get("/customer/customers")
def list_customers(limit: int = 100, band: str | None = None,
                   _: str = Depends(require_owner)) -> dict:
    sql = "SELECT * FROM customers"
    params: list = []
    if band:
        sql += " WHERE band = ?"
        params.append(band)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = store.query(sql, tuple(params))
    for r in rows:
        r["verified_revenue_inr"] = ledger.verified_revenue(r["id"])
    return {"customers": rows, "count": len(rows)}


@application.get("/customer/customers/{customer_id}/contact-check")
def contact_check(customer_id: str, purpose: str = "marketing",
                  _: str = Depends(require_owner)) -> dict:
    return ledger.may_contact(customer_id, purpose=purpose)


@application.post("/customer/qualify")
def qualify(payload: QualificationIn, _: str = Depends(require_owner)) -> dict:
    try:
        q = Qualification(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "invalid_qualification", "detail": str(exc)})
    return {"qualification": q.to_dict(),
            "rule": "NEED + ABILITY TO PAY + URGENCY + FIT + TRUST + CONVERSION PROBABILITY + LTV. "
                    "A disqualifying fact (no need, no ability to pay, no trust) cannot be overridden "
                    "by attachment."}


@application.get("/customer/objections")
def objections(limit: int = 100, _: str = Depends(require_owner)) -> dict:
    items = ledger.objections(limit=limit)
    return {"objections": items, "count": len(items),
            "use": "Real objections are the cheapest market research in existence. Never invent one; "
                   "write down what was actually said."}


@application.get("/customer/scorecard")
def scorecard(_: str = Depends(require_owner)) -> dict:
    return ledger.scorecard()


@application.post("/customer/gate/writer-nation")
def writer_nation(payload: GateIn, _: str = Depends(require_owner)) -> dict:
    gate = WriterNationGate()
    for stage, answer in (payload.answers or {}).items():
        if stage not in GATE_STAGES:
            raise HTTPException(status_code=422, detail={"error": "unknown_gate_stage", "stage": stage,
                                                         "allowed": list(GATE_STAGES)})
        gate.pass_stage(stage, str(answer.get("answer", "")), kind=str(answer.get("kind", "UNKNOWN")),
                        evidence=str(answer.get("evidence", "")))
    review = gate.review()
    return {"service": payload.name, **review}


# ---------------------------------------------------------------------------
# the decision standard (§28) — one engine, exposed where the owner can reach it
# ---------------------------------------------------------------------------
@application.post("/decision/standard")
def decision_standard(payload: DecisionIn, _: str = Depends(require_owner)) -> dict:
    record = decision_engine.decide(
        payload.question, domain=payload.domain, facts=payload.facts, inferences=payload.inferences,
        hypotheses=payload.hypotheses, assumptions=payload.assumptions, opinions=payload.opinions,
        unknowns=payload.unknowns, numbers=payload.numbers, minutes=payload.minutes,
        use_model=payload.use_model, displaced=payload.displaced,
    )
    return {**record.to_dict(), "self_audit": record.validate()}


@application.get("/decision/engine")
def engine(_: str = Depends(require_owner)) -> dict:
    return decision_engine_status()


@application.get("/decision/records")
def records(limit: int = 50, classification: str | None = None,
            _: str = Depends(require_owner)) -> dict:
    rows = decision_engine.decisions(limit=limit, classification=classification)
    return {"decisions": rows, "count": len(rows)}


@application.get("/decision/labels")
def labels(_: str = Depends(require_owner)) -> dict:
    return decision_engine.label_report()


@application.get("/decision/calibration")
def calibration(_: str = Depends(require_owner)) -> dict:
    return decision_engine.calibration()


@application.post("/decision/{decision_id}/outcome")
def outcome(decision_id: str, payload: OutcomeIn, _: str = Depends(require_owner)) -> dict:
    try:
        return decision_engine.record_outcome(decision_id, metric_value=payload.metric_value,
                                              note=payload.note, measured_by=payload.measured_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "decision_not_found", "detail": str(exc)})
