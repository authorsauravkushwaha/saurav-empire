"""Decision Output Standard — master prompt §28 as executable code.

Every consequential decision leaves this civilization in exactly one shape:

    VERDICT · CONFIDENCE · CLASSIFICATION · EVIDENCE (ranked) · AGREEMENT ·
    DISAGREEMENT · REALITY CHECK · ACTION PLAN (with owner + budget + metric) ·
    EXPECTED IMPACT · FORECAST · OPPORTUNITY COST · KILL CRITERION

Design laws (from the constitution):
  * The eight minds give opinions. A chairman gives a decision. Opinions are averaged into nothing.
  * A claim is only as strong as the tier of evidence behind it (§3 evidence hierarchy).
    FACT beats INFERENCE beats HYPOTHESIS beats ASSUMPTION beats OPINION. UNKNOWN beats nobody.
  * Revenue may never be claimed before a verified ledger entry exists. Projections are labelled
    ESTIMATE / SCENARIO and carry the assumption that produced them.
  * Every action step names an owner, a budget, a duration and a measurable success metric.
    "Improve marketing soon" is not an action. It is a wish, and it is rejected.
  * Every decision declares its kill criterion, and every outcome is written back so the forecast
    can be scored against reality. Prediction without a score is storytelling.

Confidence is not certainty. A decision can be confidently correct in its *reasoning* while its
*outcome* is uncertain — the record keeps those two apart.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import store
from .eventbus import bus
# single source of truth for claim labels and honesty stamps lives in governance.py
from .governance import (ASSUMPTION, EVIDENCE_KINDS as CLAIM_KINDS, ESTIMATE_STAMP, FACT,
                         HYPOTHESIS, INFERENCE, OPINION, SCENARIO_STAMP, UNKNOWN,
                         UNVERIFIED_STAMP)

# ---------------------------------------------------------------------------
# §3 — Evidence hierarchy
# ---------------------------------------------------------------------------

EVIDENCE_HIERARCHY: tuple[dict, ...] = (
    {"tier": 1, "kind": FACT, "weight": 1.00, "name": "Verified reality",
     "accepts": "payments seen in a bank/payment ledger, API responses we stored, files we read, "
                "audit rows, measurements the system itself performed",
     "counts_as_proof": True},
    {"tier": 2, "kind": INFERENCE, "weight": 0.60, "name": "Derived from facts",
     "accepts": "arithmetic over facts, comparisons across stored facts, deterministic model output "
                "over inputs that are themselves FACT",
     "counts_as_proof": False},
    {"tier": 3, "kind": HYPOTHESIS, "weight": 0.35, "name": "Stated guess with a test",
     "accepts": "estimates and scenarios that name their assumptions and their cheapest test",
     "counts_as_proof": False},
    {"tier": 4, "kind": ASSUMPTION, "weight": 0.15, "name": "Unverified belief",
     "accepts": "market size, willingness to pay, conversion, retention, 'people want this'",
     "counts_as_proof": False},
    {"tier": 5, "kind": OPINION, "weight": 0.05, "name": "Judgement",
     "accepts": "taste, framing, aesthetic and strategic preference — useful, not evidence",
     "counts_as_proof": False},
    {"tier": 6, "kind": UNKNOWN, "weight": 0.00, "name": "Not known",
     "accepts": "anything nobody has checked. Declaring UNKNOWN is honest, not weak",
     "counts_as_proof": False},
)

TIER_OF = {entry["kind"]: entry["tier"] for entry in EVIDENCE_HIERARCHY}
WEIGHT_OF = {entry["kind"]: entry["weight"] for entry in EVIDENCE_HIERARCHY}
NAME_OF = {entry["kind"]: entry["name"] for entry in EVIDENCE_HIERARCHY}

# §28 output sections. Missing section = invalid record.
OUTPUT_SECTIONS = ("verdict", "confidence", "classification", "evidence", "agreement",
                   "disagreement", "reality_check", "action_plan", "expected_impact",
                   "forecast", "opportunity_cost")

DECISION_CLASSES = ("STOP", "CONTINUE", "IMPROVE", "SCALE", "TEST", "DEFER", "REJECT")
CONFIDENCE_BANDS = ("LOW", "MEDIUM", "HIGH")

VAGUE_TIME_WORDS = re.compile(r"\b(soon|asap|eventually|later|shortly|in due course|at some point)\b", re.I)
MEASURABLE = re.compile(r"(\d|\bpercent\b|\brate\b|\bcount\b|\bmedian\b|\bp90\b|\bper\b|\bwithin\b)", re.I)


class DecisionError(ValueError):
    """A record that would have shipped dishonesty or a wish instead of a plan."""


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------
@dataclass
class Claim:
    """One labelled statement (§2). The label is not decoration — it is the argument's carrying capacity.

    `governance.Evidence` remains the storage envelope for ledger/opportunity rows; this is the class
    used when a *decision* reasons over evidence, so the two roles stay distinct and single-sourced
    constants (`governance.EVIDENCE_KINDS`) keep the vocabulary identical everywhere.
    """

    text: str
    kind: str = UNKNOWN
    source: str = ""
    verified: bool = False
    url: str | None = None
    captured_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.kind not in CLAIM_KINDS:
            raise DecisionError(f"Unknown claim kind {self.kind!r}. Allowed: {CLAIM_KINDS}")
        if self.kind == FACT and not self.source:
            raise DecisionError("A FACT requires a source. If nobody can point at it, it is an INFERENCE.")
        if self.kind == FACT and not self.verified:
            raise DecisionError("A FACT requires verification. Unverified material is INFERENCE or HYPOTHESIS.")
        if self.kind in (HYPOTHESIS, ASSUMPTION) and self.verified:
            raise DecisionError(f"A {self.kind} cannot be 'verified'. Promote it to FACT with a source instead.")

    @property
    def tier(self) -> int:
        return TIER_OF[self.kind]

    @property
    def weight(self) -> float:
        return WEIGHT_OF[self.kind]

    @property
    def label(self) -> str:
        if self.kind == FACT:
            return f"FACT — {self.source}"
        stamp = {HYPOTHESIS: ESTIMATE_STAMP, ASSUMPTION: SCENARIO_STAMP}.get(self.kind)
        tail = f" [source: {self.source}]" if self.source else ""
        return f"{self.kind}{' — ' + stamp if stamp else ''}{tail}"

    def to_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "tier": self.tier, "weight": self.weight,
                "source": self.source, "verified": self.verified, "url": self.url,
                "captured_at": self.captured_at, "label": self.label}


def claim(kind: str, text: str, source: str = "", verified: bool = False, url: str | None = None) -> Claim:
    return Claim(text=text, kind=kind, source=source, verified=verified, url=url)


def facts_from_rows(rows: Iterable[dict], text_key: str = "label",
                    source_key: str = "source") -> list[Claim]:
    """Turn stored rows into FACT claims only when the row itself carries a source."""
    out: list[Claim] = []
    for row in rows:
        text = str(row.get(text_key) or row.get("text") or "").strip()
        source = str(row.get(source_key) or row.get("verified_by") or "").strip()
        if text and source:
            out.append(Claim(text=text, kind=FACT, source=source, verified=True))
    return out


# ---------------------------------------------------------------------------
# Evidence ledger
# ---------------------------------------------------------------------------
class EvidenceLedger:
    """Ranked evidence with an honest strength score.

    Strength = mean tier weight, halved for anything unverified, then capped at 0.5 unless at
    least one FACT is present. No amount of assumptions stacks up into proof.
    """

    def __init__(self, claims: Iterable[Claim] | None = None) -> None:
        self._claims: list[Claim] = list(claims or [])

    # ---- construction --------------------------------------------------
    def add(self, item: Claim | dict) -> "EvidenceLedger":
        self._claims.append(item if isinstance(item, Claim) else Claim(**item))
        return self

    def add_many(self, items: Iterable[Claim | dict]) -> "EvidenceLedger":
        for item in items:
            self.add(item)
        return self

    def labelled(self, kind: str, items: Iterable[str], source: str = "",
                 verified: bool = False) -> "EvidenceLedger":
        """`verified=True` for FACT means the caller asserts the material was checked and can be pointed at.

        Passing raw hopes in as facts is exactly the hallucination this class exists to make visible.
        """
        for text in items:
            if str(text).strip():
                self.add(Claim(text=str(text), kind=kind, source=source, verified=verified))
        return self

    # ---- analysis ------------------------------------------------------
    @property
    def claims(self) -> list[Claim]:
        return list(self._claims)

    def ranked(self) -> list[Claim]:
        return sorted(self._claims, key=lambda c: (c.tier, not c.verified, c.text))

    def counts(self) -> dict[str, int]:
        counts = {kind: 0 for kind in CLAIM_KINDS}
        for c in self._claims:
            counts[c.kind] += 1
        return counts

    def strength(self) -> float:
        if not self._claims:
            return 0.0
        raw = sum(c.weight * (1.0 if c.verified or c.kind != FACT else 0.5) for c in self._claims) / len(self._claims)
        if not any(c.kind == FACT for c in self._claims):
            raw = min(raw, 0.5)          # assumptions do not compound into evidence
        return round(min(1.0, raw), 4)

    def proof_count(self) -> int:
        return sum(1 for c in self._claims if c.kind == FACT and c.verified)

    def gaps(self) -> list[str]:
        return [c.text for c in self._claims if c.kind == UNKNOWN]

    def blind(self) -> bool:
        return self.proof_count() == 0

    def to_dict(self) -> dict:
        return {"claims": [c.to_dict() for c in self.ranked()], "counts": self.counts(),
                "strength": self.strength(), "proof_count": self.proof_count(),
                "gaps": self.gaps(), "blind": self.blind(),
                "hierarchy": [e for e in EVIDENCE_HIERARCHY]}


# ---------------------------------------------------------------------------
# §28 pieces
# ---------------------------------------------------------------------------
@dataclass
class OpportunityCost:
    """What the same hours and rupees would have produced elsewhere. No decision is free."""

    rupees: float = 0.0
    minutes: float = 0.0
    displaced: str = ""
    ranking_note: str = ""

    def to_dict(self) -> dict:
        return {"rupees": self.rupees, "minutes": self.minutes,
                "displaced": self.displaced or "Nothing compared yet — comparison is itself a gap.",
                "ranking_note": self.ranking_note, "label": ESTIMATE_STAMP}


@dataclass
class Forecast:
    """A falsifiable prediction. No revision rule = no forecast, just a vibe."""

    metric: str
    expected: float
    unit: str = ""
    horizon_days: int = 30
    comparator: str = "vs the last measured value"
    evidence_basis: str = ""
    confidence: str = "LOW"
    kill_criterion: str = ""
    revision_rule: str = ""
    label: str = SCENARIO_STAMP

    def __post_init__(self) -> None:
        if not self.kill_criterion:
            raise DecisionError("A forecast without a kill criterion is a wish. Name the value that stops it.")
        if not self.revision_rule:
            raise DecisionError("A forecast must say when and how it would be revised.")
        if self.confidence not in CONFIDENCE_BANDS:
            raise DecisionError(f"Forecast confidence must be one of {CONFIDENCE_BANDS}")

    def to_dict(self) -> dict:
        return {"metric": self.metric, "expected": self.expected, "unit": self.unit,
                "horizon_days": self.horizon_days, "comparator": self.comparator,
                "evidence_basis": self.evidence_basis, "confidence": self.confidence,
                "kill_criterion": self.kill_criterion, "revision_rule": self.revision_rule,
                "label": self.label}


@dataclass
class RealityCheck:
    what_we_know: list[str] = field(default_factory=list)
    what_we_think: list[str] = field(default_factory=list)
    what_we_are_missing: list[str] = field(default_factory=list)
    what_can_break_this: list[str] = field(default_factory=list)
    cheapest_test: str = ""
    kill_criterion: str = ""
    if_wrong: str = ""
    if_right: str = ""
    do_now: str = ""

    def to_dict(self) -> dict:
        return {"what_we_know": self.what_we_know, "what_we_think": self.what_we_think,
                "what_we_are_missing": self.what_we_are_missing,
                "what_can_break_this": self.what_can_break_this,
                "cheapest_test": self.cheapest_test, "kill_criterion": self.kill_criterion,
                "if_wrong": self.if_wrong, "if_right": self.if_right, "do_now": self.do_now}


@dataclass
class ActionStep:
    """An action with an owner, a budget, a duration and a metric. Anything less is a wish."""

    order: int
    action: str
    owner: str = "owner"
    owner_agent_id: str | None = None
    budget_inr: float = 0.0
    duration_minutes: int = 0
    tool: str = ""
    success_metric: str = ""
    depends_on: str = ""
    reversible: bool = True
    approval_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.action or not self.action.strip():
            raise DecisionError("An action step needs an action.")
        if VAGUE_TIME_WORDS.search(self.action):
            raise DecisionError(f"Vague deadline in action {self.action!r}: name a checkpoint, not 'soon'.")
        if not self.success_metric:
            raise DecisionError(f"Action {self.order} has no measurable success metric.")
        if not MEASURABLE.search(self.success_metric):
            raise DecisionError(f"Action {self.order} success metric is not measurable: {self.success_metric!r}")
        if self.budget_inr > 0 and not self.approval_ref:
            raise DecisionError(f"Action {self.order} spends ₹{self.budget_inr:,.0f} without a human-approval reference. "
                                "Money moves only through the approval queue.")
        if self.budget_inr < 0:
            raise DecisionError("Budget cannot be negative.")
        if self.duration_minutes < 0:
            raise DecisionError("Duration cannot be negative.")

    def to_dict(self) -> dict:
        return {"order": self.order, "action": self.action, "owner": self.owner,
                "owner_agent_id": self.owner_agent_id, "budget_inr": self.budget_inr,
                "duration_minutes": self.duration_minutes, "tool": self.tool,
                "success_metric": self.success_metric, "depends_on": self.depends_on,
                "reversible": self.reversible, "approval_ref": self.approval_ref,
                "spends_money": self.budget_inr > 0}


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------
@dataclass
class DecisionRecord:
    question: str
    verdict: str
    classification: str
    confidence: str
    confidence_basis: str = ""
    domain: str = "business"
    evidence: EvidenceLedger = field(default_factory=EvidenceLedger)
    agreement: list[str] = field(default_factory=list)
    disagreement: list[str] = field(default_factory=list)
    reality_check: RealityCheck = field(default_factory=RealityCheck)
    action_plan: list[ActionStep] = field(default_factory=list)
    expected_impact: dict = field(default_factory=dict)
    forecast: Forecast | None = None
    opportunity_cost: OpportunityCost = field(default_factory=OpportunityCost)
    eight_minds: dict = field(default_factory=dict)
    decided_by: str = "chairman"
    id: str | None = None
    department_id: str | None = None
    task_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.classification not in DECISION_CLASSES:
            raise DecisionError(f"Classification must be one of {DECISION_CLASSES}")
        if self.confidence not in CONFIDENCE_BANDS:
            raise DecisionError(f"Confidence must be one of {CONFIDENCE_BANDS}")
        if self.forecast is not None and self.forecast.confidence == "HIGH" and self.evidence.blind():
            raise DecisionError("A HIGH-confidence forecast with no verified FACT is fabricated certainty.")
        if self.classification in ("SCALE", "CONTINUE") and self.evidence.blind():
            raise DecisionError(f"Classification {self.classification} requires at least one verified FACT.")
        financial = self.expected_impact.get("financial", {}) or {}
        claimed_revenue = float(financial.get("revenue_inr", 0) or 0)
        if claimed_revenue > 0 and self.evidence.proof_count() == 0:
            raise DecisionError("Revenue cannot be projected from zero verified evidence. Record ₹0 revenue "
                                "and the modelled contribution instead.")
        if self.classification in ("SCALE", "CONTINUE") and self.disagreement and not any(
                "resolution" in d.lower() for d in self.disagreement):
            raise DecisionError("Disagreement must be resolved by the chairman, not ignored.")

    # ---- output --------------------------------------------------------
    @property
    def confidence_note(self) -> str:
        base = {"LOW": "directionally reasoned, outcome unproven",
                "MEDIUM": "reasoning sound, some verified evidence, outcome still uncertain",
                "HIGH": "reasoning and evidence both strong; outcome still not guaranteed"}[self.confidence]
        return f"CONFIDENCE {self.confidence} — {base}. Confidence is not certainty."

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "domain": self.domain,
            "id": self.id,
            "classification": self.classification,
            "confidence": self.confidence,
            "verdict": {"decision": self.verdict, "classification": self.classification,
                        "confidence": self.confidence, "confidence_basis": self.confidence_basis,
                        "confidence_note": self.confidence_note, "decided_by": self.decided_by,
                        "decided_at": self.created_at},
            "evidence": self.evidence.to_dict(),
            "agreement": self.agreement,
            "disagreement": self.disagreement,
            "reality_check": self.reality_check.to_dict(),
            "action_plan": [s.to_dict() for s in self.action_plan],
            "expected_impact": self.expected_impact,
            "forecast": self.forecast.to_dict() if self.forecast else None,
            "opportunity_cost": self.opportunity_cost.to_dict(),
            "eight_minds": self.eight_minds,
            "sections": list(OUTPUT_SECTIONS),
            "standard": "master prompt §28 — DECISION OUTPUT STANDARD",
        }

    def validate(self) -> list[str]:
        """Self-audit: a record with an empty required section is not a decision."""
        problems: list[str] = []
        d = self.to_dict()
        for section in OUTPUT_SECTIONS:
            value = d.get(section)
            if value in (None, "", [], {}):
                problems.append(f"empty section: {section}")
        verdict = d.get("verdict") or {}
        for field_name in ("classification", "confidence", "confidence_basis"):
            if not verdict.get(field_name):
                problems.append(f"verdict.{field_name} is empty")
        if not self.action_plan:
            problems.append("action_plan has no steps")
        if self.evidence.blind():
            problems.append("no verified FACT in evidence (declared, not hidden)")
        return problems

    # ---- persistence ---------------------------------------------------
    def persist(self) -> dict:
        self.id = self.id or store.new_id("dec")
        row = {
            "id": self.id, "question": self.question, "domain": self.domain,
            "verdict": self.verdict, "classification": self.classification,
            "confidence": self.confidence, "record_json": store.jdump(self.to_dict()),
            "evidence_json": store.jdump([c.to_dict() for c in self.evidence.ranked()]),
            "opportunity_cost": f"₹{self.opportunity_cost.rupees:,.0f} / {self.opportunity_cost.minutes:,.0f} min — "
                                f"{self.opportunity_cost.displaced}",
            "decided_by": self.decided_by, "department_id": self.department_id,
            "task_id": self.task_id, "created_at": self.created_at,
        }
        if store.get("decisions", row["id"]):
            store.update("decisions", row["id"], row)          # idempotent: same record, no duplicate history
        else:
            store.insert("decisions", row)
        bus.publish("decision.made", source="decision-engine", subject=row["id"],
                    payload={"question": self.question, "classification": self.classification,
                             "confidence": self.confidence, "verdict": self.verdict,
                             "domain": self.domain, "problems": self.validate()})
        return row


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
def _contribution(numbers: dict) -> float:
    rev = float(numbers.get("expected_revenue", 0) or 0)
    var = float(numbers.get("variable_costs", 0) or 0)
    inc = float(numbers.get("incremental_costs", 0) or 0)
    return rev - var - inc


def _band(score: float, has_fact: bool) -> str:
    if not has_fact:
        return "LOW"
    if score >= 0.70:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


class DecisionEngine:
    """Turns a question + labelled evidence + numbers into a §28 record, then scores itself later.

    Rules are deterministic and inspectable. A local model may add a note to a mind, but it may never
    write the verdict, the confidence or the numbers.
    """

    def decide(self, question: str, *, domain: str = "business",
               facts: Iterable[str] | None = None, assumptions: Iterable[str] | None = None,
               unknowns: Iterable[str] | None = None, inferences: Iterable[str] | None = None,
               hypotheses: Iterable[str] | None = None, opinions: Iterable[str] | None = None,
               claims: Iterable[Claim | dict] | None = None,
               numbers: dict | None = None, minutes: int = 0, use_model: bool = True,
               department_id: str | None = None, task_id: str | None = None,
               extra_actions: Iterable[ActionStep] | None = None,
               displaced: str = "", persist: bool = True) -> DecisionRecord:
        numbers = dict(numbers or {})
        ledger = EvidenceLedger()
        ledger.labelled(FACT, facts or [], source="owner-supplied verified fact", verified=bool(facts))
        ledger.labelled(INFERENCE, inferences or [])
        ledger.labelled(HYPOTHESIS, hypotheses or [])
        ledger.labelled(ASSUMPTION, assumptions or [])
        ledger.labelled(OPINION, opinions or [])
        ledger.labelled(UNKNOWN, unknowns or [])
        ledger.add_many(claims or [])

        analysis = self._minds(question, ledger, numbers, use_model=use_model)

        contribution = _contribution(numbers)
        capital = float(numbers.get("required_capital", 0) or 0)
        cash = float(store.get_setting("cash_available_inr", 0) or 0)
        revenue = float(numbers.get("expected_revenue", 0) or 0)
        strength = ledger.strength()
        has_fact = ledger.proof_count() > 0

        # ---- agreement: where independent minds converge on the supplied evidence
        agreement = self._agreement(analysis)
        disagreement = self._disagreement(analysis, contribution, has_fact)

        # ---- reality check first, because it decides the classification
        cheapest = numbers.get("cheapest_test") or self._cheapest_test(ledger, unknowns)
        kill = numbers.get("kill_criterion") or self._kill_criterion(contribution, capital, cash, has_fact)
        reality = RealityCheck(
            what_we_know=[c.text for c in ledger.claims if c.kind == FACT] or ["Nothing verified yet."],
            what_we_think=[c.text for c in ledger.claims if c.kind in (INFERENCE, HYPOTHESIS, ASSUMPTION, OPINION)]
                          or ["No reasoned position supplied."],
            what_we_are_missing=[c.text for c in ledger.claims if c.kind == UNKNOWN]
                                 or ["No unknowns declared — which is itself a warning sign."],
            what_can_break_this=[r for m in analysis.get("minds", []) for r in m.get("risks", [])][:6]
                                or ["Not yet identified."],
            cheapest_test=cheapest, kill_criterion=kill,
            if_wrong=f"Cost is bounded by the declared test budget (₹{float(numbers.get('test_budget_inr', 0) or 0):,.0f}) "
                     f"plus {max(1, minutes or 30)} minutes of owner time.",
            if_right="It becomes a verified input to the next decision and can be scaled with real evidence.",
            do_now="",
        )

        classification = self._classify(contribution, capital, cash, strength, has_fact, numbers, ledger)

        # ---- action plan: the first step depends on the classification, and always carries a metric
        horizon = int(numbers.get("forecast_horizon_days", 30) or 30)
        metric_name = numbers.get("forecast_metric") or "the declared metric"
        if classification in ("SCALE", "CONTINUE", "IMPROVE"):
            first_action = (numbers.get("first_action")
                            or f"Take the smallest reversible step that expands what the evidence already "
                               f"supports — and change nothing else in the same week.")
            first_metric = numbers.get("first_action_metric") or (
                f"1 outcome row scored for {metric_name} within {horizon} days "
                f"(kill criterion recorded before starting)")
        else:
            first_action = cheapest
            first_metric = numbers.get("cheapest_test_metric") or (
                "1 written answer to the named unknown stored in the experiment ledger"
                if reality.what_we_are_missing and ledger.gaps()
                else f"1 outcome row scored for {metric_name} within {horizon} days")
        plan: list[ActionStep] = [ActionStep(
            order=1, action=first_action, owner="owner", budget_inr=0.0,
            duration_minutes=max(1, minutes or 30), tool=numbers.get("tool", "local"),
            success_metric=first_metric,
        )]
        step_n = 1
        for step in (extra_actions or []):
            step_n += 1
            step.order = step_n
            plan.append(step)
        step_n += 1
        plan.append(ActionStep(
            order=step_n, action=f"Record the decision, the metric and the kill criterion: {kill}",
            owner="owner", budget_inr=0.0, duration_minutes=5, tool="empire ledger",
            success_metric="1 decisions row containing the kill criterion and 1 declared metric",
        ))
        step_n += 1
        plan.append(ActionStep(
            order=step_n, action="Re-check at the declared checkpoint and score the forecast against reality",
            owner="owner", budget_inr=0.0, duration_minutes=10, tool="empire ledger",
            success_metric=f"1 outcome row scored (expected vs actual) for "
                           f"{numbers.get('forecast_metric', 'the declared metric')} within "
                           f"{int(numbers.get('forecast_horizon_days', 30) or 30)} days",
        ))
        reality.do_now = plan[0].action

        forecast = self._forecast(numbers, classification, has_fact, kill)

        expected_impact = {
            "customer": numbers.get("customer_impact")
            or ("Unchanged until the cheapest test runs." if not has_fact else "Improves if the tested promise holds."),
            "financial": {
                "revenue_inr": 0.0,
                "modelled_contribution_inr": round(contribution, 2),
                "required_capital_inr": capital,
                "cash_available_inr": cash,
                "label": ESTIMATE_STAMP,
                "note": "Revenue stays ₹0.00 in this record until a verified ledger entry exists.",
            },
            "strategic": numbers.get("strategic_impact")
            or "Builds a reusable asset only if the output is stored as IP, code, audience or data.",
            "learning": "Even a failure produces the cheapest fact we were missing — that is the point of the test."
            if classification in ("TEST", "DEFER") else "The outcome scores this forecast either way.",
        }

        record = DecisionRecord(
            question=question, verdict=self._verdict_text(classification, contribution, strength, has_fact),
            classification=classification,
            confidence=_band(strength, has_fact),
            confidence_basis=f"evidence strength {strength:.2f} from {ledger.proof_count()} verified FACT(s), "
                              f"{len(disagreement)} disagreement(s), {len(reality.what_we_are_missing)} unknown(s)",
            domain=domain, evidence=ledger, agreement=agreement, disagreement=disagreement,
            reality_check=reality, action_plan=plan, expected_impact=expected_impact, forecast=forecast,
            opportunity_cost=self._opportunity_cost(numbers, minutes, displaced),
            eight_minds=analysis, department_id=department_id, task_id=task_id,
        )
        if persist:
            record.persist()
        return record

    # ---- internals -----------------------------------------------------
    def _minds(self, question: str, ledger: EvidenceLedger, numbers: dict, *, use_model: bool) -> dict:
        from .governance import EightMinds   # local import: governance imports this module publicly
        return EightMinds().analyse(
            question,
            facts=[c.text for c in ledger.claims if c.kind == FACT],
            assumptions=[c.text for c in ledger.claims if c.kind == ASSUMPTION],
            unknowns=[c.text for c in ledger.claims if c.kind == UNKNOWN],
            numbers=numbers, use_model=use_model,
        )

    def _agreement(self, analysis: dict) -> list[str]:
        agreeing: dict[str, list[str]] = {}
        for mind in analysis.get("minds", []):
            key = " ".join(mind.get("verdict", "").split()[:4])
            agreeing.setdefault(key, []).append(mind["mind"])
        out = [f"{len(minds)} minds converge ({', '.join(minds)}): {verdict}"
               for verdict, minds in sorted(agreeing.items(), key=lambda kv: -len(kv[1])) if len(minds) > 1]
        if not out:
            out = ["No independent convergence: each mind reached its view on different grounds."]
        return out

    def _disagreement(self, analysis: dict, contribution: float, has_fact: bool) -> list[str]:
        out: list[str] = []
        by_name = {m["mind"]: m for m in analysis.get("minds", [])}
        finance, future = by_name.get("FINANCE_ADVISOR", {}), by_name.get("FUTURE_STRATEGIST", {})
        customer = by_name.get("CUSTOMER_BUYER", {})
        if contribution > 0 and future.get("risks"):
            out.append("FINANCE_ADVISOR likes the economics; FUTURE_STRATEGIST warns the advantage is not durable. "
                       "Resolution: scale only if the advantage survives a platform, provider and price change.")
        if not has_fact and customer.get("risks"):
            out.append("CUSTOMER_BUYER cannot see verifiable proof that anyone wants this. "
                       "Resolution: produce the proof before any spend — no spend is authorised on this record.")
        if contribution <= 0 and finance.get("risks"):
            out.append("FINANCE_ADVISOR rejects the economics while the builder minds still want to ship. "
                       "Resolution: reprice or shrink scope until contribution is positive; shipping at a loss is STOP.")
        if not out:
            out.append("No material conflict among the eight minds on the supplied evidence.")
        return out

    def _cheapest_test(self, ledger: EvidenceLedger, unknowns: Iterable[str] | None) -> str:
        unknown_list = [c.text for c in ledger.claims if c.kind == UNKNOWN] or list(unknowns or [])
        if unknown_list:
            return (f"Design a ₹0 test that answers: {unknown_list[0]} — cap it at the owner's time, "
                    "record the exact answers, change no assumptions without evidence.")
        if ledger.proof_count() == 0:
            return ("Talk to 3 real target humans (or 3 existing readers) and write down their exact objections, "
                    "not the ones we hoped for.")
        return "Ship the smallest version to the smallest real audience and measure one declared metric."

    def _kill_criterion(self, contribution: float, capital: float, cash: float, has_fact: bool) -> str:
        if capital > cash:
            return f"Kill if required capital ₹{capital:,.0f} still exceeds available cash ₹{cash:,.0f} on re-check."
        if contribution <= 0:
            return "Kill if contribution is still ≤ 0 after one reprice attempt or one week of measured traffic."
        if not has_fact:
            return "Kill if no verifiable FACTS exist after the cheapest test — do not proceed on belief."
        return "Kill if the declared metric misses its floor at the checkpoint, or if any cash figure turns negative."

    def _classify(self, contribution: float, capital: float, cash: float, strength: float,
                  has_fact: bool, numbers: dict, ledger: EvidenceLedger) -> str:
        """Deterministic priority: STOP → REJECT → DEFER → IMPROVE → SCALE → TEST → CONTINUE."""
        if numbers.get("destroys_cash") or numbers.get("ethical_violation"):
            return "STOP"
        if contribution <= 0 and float(numbers.get("expected_revenue", 0) or 0) > 0:
            return "STOP"                             # the numbers do not pay for the work
        if numbers.get("breaks_rule") or numbers.get("unethical"):
            return "REJECT"
        if capital > cash:
            return "DEFER"                            # needs capital the civilization does not have
        if numbers.get("kpi_below_target") and has_fact:
            return "IMPROVE"
        if has_fact and strength >= 0.60 and contribution > 0 and not ledger.gaps():
            return "SCALE"
        if not has_fact or strength < 0.40 or ledger.gaps():
            return "TEST"
        return "CONTINUE"

    def _verdict_text(self, classification: str, contribution: float, strength: float, has_fact: bool) -> str:
        if classification == "STOP":
            return "STOP — the numbers do not pay for the work; kill it and keep the lesson."
        if classification == "REJECT":
            return "REJECT — this violates a rule the civilization does not break, regardless of profit."
        if classification == "DEFER":
            return "DEFER — it needs capital or capability we do not have; find a ₹0 path or a paying pre-commitment first."
        if classification == "IMPROVE":
            return "IMPROVE — fix the weak measured link before adding anything new."
        if classification == "SCALE":
            return f"SCALE — verified evidence (strength {strength:.2f}) supports the modelled contribution of {contribution:,.2f}."
        if classification == "TEST":
            return ("TEST FIRST — evidence is too thin to conclude this. Buy the missing fact at ₹0 before "
                    "committing resources." if not has_fact else
                    "TEST SMALL — directionally sensible, not yet evidenced enough to scale.")
        return "CONTINUE — it is working on verified evidence; keep the same measure and watch for decay."

    def _forecast(self, numbers: dict, classification: str, has_fact: bool, kill: str) -> Forecast:
        metric = numbers.get("forecast_metric") or "verified contribution in the declared window"
        expected = float(numbers.get("forecast_expected", numbers.get("expected_revenue", 0)) or 0)
        return Forecast(
            metric=metric, expected=expected, unit=numbers.get("forecast_unit", "INR"),
            horizon_days=int(numbers.get("forecast_horizon_days", 30) or 30),
            comparator=numbers.get("forecast_comparator", "vs the last measured value (₹0 baseline if none)"),
            evidence_basis=f"{'verified facts exist' if has_fact else 'no verified FACT — scenario only'}; "
                           f"classification {classification}",
            confidence="LOW" if not has_fact else ("MEDIUM" if classification in ("TEST", "IMPROVE") else "MEDIUM"),
            kill_criterion=kill,
            revision_rule="Revise on the first real measurement, or at the checkpoint, whichever comes first — "
                          "and write the variance into the ledger.",
        )

    def _opportunity_cost(self, numbers: dict, minutes: int, displaced: str) -> OpportunityCost:
        return OpportunityCost(
            rupees=float(numbers.get("opportunity_cost_inr", 0) or 0),
            minutes=float(minutes or 0),
            displaced=displaced or str(numbers.get("displaced") or ""),
            ranking_note="Compared against the current top-ranked opportunity in the ledger; "
                         "if this is not above it, do the other one first.",
        )

    # ---- reality answers ----------------------------------------------
    def record_outcome(self, decision_id: str, *, metric_value: float, note: str = "",
                       measured_by: str = "owner") -> dict:
        """Every experiment must produce data. This is where the forecast meets reality."""
        row = store.get("decisions", decision_id)
        if not row:
            raise DecisionError(f"No decision {decision_id!r}")
        record = store.jload(row.get("record_json"), {}) or {}
        forecast = (record.get("forecast") or {}) if isinstance(record, dict) else {}
        expected = float(forecast.get("expected", 0) or 0)
        delta = metric_value - expected
        outcome = {
            "metric": forecast.get("metric", "unspecified"), "expected": expected,
            "actual": metric_value, "variance": round(delta, 4),
            "variance_pct": round((delta / expected * 100), 2) if expected else None,
            "verdict_held": (metric_value >= expected) if expected else None,
            "note": note, "measured_by": measured_by, "measured_at": time.time(),
            "honesty": "The forecast is scored as written. Nobody edits the prediction after the fact.",
        }
        store.update("decisions", decision_id, {
            "outcome": "REALITY_RECORDED", "outcome_json": store.jdump(outcome),
            "resolved_at": time.time(),
        })
        bus.publish("decision.outcome", source="decision-engine", subject=decision_id,
                    payload={"expected": expected, "actual": metric_value, "variance_pct": outcome["variance_pct"]})
        # the lesson is stored whether the decision was right or wrong
        store.insert("lessons", {
            "id": store.new_id("lsn"), "ts": time.time(),
            "title": f"decision:{row.get('classification')} — forecast vs reality",
            "lesson": (f"{record.get('question') if isinstance(record, dict) else row.get('question')} — "
                       f"forecast {expected:,.2f}, actual {metric_value:,.2f} "
                       f"({outcome['variance_pct']}%). {note}").strip(),
            "source": f"decision {decision_id}",
            "tags_json": store.jdump(["calibration", str(row.get("classification") or "decision")]),
            "reusable": 1,
        })
        return outcome

    def calibration(self, limit: int = 200) -> dict:
        """How good are our forecasts, honestly? Scored only on outcomes that actually happened."""
        rows = store.query("SELECT classification, confidence, outcome_json FROM decisions "
                           "WHERE outcome_json IS NOT NULL AND outcome_json != '{}' ORDER BY created_at DESC LIMIT ?",
                           (limit,))
        scored: list[dict] = []
        for r in rows:
            o = store.jload(r.get("outcome_json"), {}) or {}
            if isinstance(o, dict) and o.get("verdict_held") is not None:
                scored.append({**o, "classification": r["classification"], "confidence": r["confidence"]})
        held = sum(1 for s in scored if s["verdict_held"])
        by_band: dict[str, dict] = {}
        for band in CONFIDENCE_BANDS:
            subset = [s for s in scored if s["confidence"] == band]
            by_band[band] = {"scored": len(subset), "held": sum(1 for s in subset if s["verdict_held"])}
        return {"scored_decisions": len(scored), "forecasts_held": held,
                "hit_rate": round(held / len(scored), 4) if scored else None, "by_confidence": by_band,
                "note": ("Calibration is measured only on recorded reality. Zero scored decisions means "
                         "zero claims of accuracy — not 100%.")}

    def decisions(self, limit: int = 50, classification: str | None = None) -> list[dict]:
        sql = "SELECT * FROM decisions"
        params: list[Any] = []
        if classification:
            sql += " WHERE classification = ?"
            params.append(classification)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        out = []
        for row in store.query(sql, tuple(params)):
            out.append({**row, "record": store.jload(row.get("record_json"), {}),
                        "outcome_record": store.jload(row.get("outcome_json"), {})})
        return out

    def label_report(self) -> dict:
        """Label discipline across recorded decisions — the anti-hallucination dashboard."""
        rows = store.query("SELECT record_json FROM decisions ORDER BY created_at DESC LIMIT 500")
        totals = {k: 0 for k in CLAIM_KINDS}
        blind = 0
        for r in rows:
            rec = store.jload(r.get("record_json"), {}) or {}
            ev = (rec.get("evidence") or {}) if isinstance(rec, dict) else {}
            counts = ev.get("counts") or {}
            for k in CLAIM_KINDS:
                totals[k] += int(counts.get(k, 0) or 0)
            if ev.get("blind"):
                blind += 1
        return {"records": len(rows), "claim_counts": totals, "decisions_without_a_single_fact": blind,
                "law": "Every claim carries one of: " + ", ".join(CLAIM_KINDS),
                "hierarchy": [{"tier": e["tier"], "kind": e["kind"], "counts_as_proof": e["counts_as_proof"]}
                              for e in EVIDENCE_HIERARCHY]}


decision_engine = DecisionEngine()
