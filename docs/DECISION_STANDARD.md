# THE DECISION STANDARD — how this civilization decides

Master prompt §2–§6 and §28 are not advice in a document here. They are code paths that either
produce a decision or refuse to.

| Constitution | Executable form |
|---|---|
| §2 claim labels (FACT / ASSUMPTION / INFERENCE / HYPOTHESIS / OPINION / UNKNOWN) | `kernel/decision.py::Claim` — a FACT without a source **raises**; a HYPOTHESIS cannot be marked verified |
| §3 evidence hierarchy | `EVIDENCE_HIERARCHY` (6 tiers, tier 1 = verified reality only) + `EvidenceLedger.strength()` |
| §4 anti-hallucination | revenue is written as `₹0.00` until a verified ledger entry exists; projections carry `Estimate.` / `Scenario.`; `label_report()` counts labels across every stored decision |
| §5 the eight minds | `kernel/governance.py::MINDS` + `MIND_DOMAINS` + `MIND_QUESTIONS` (8 mandates, 41 rubric questions) |
| §6 chairman | `Chairman.decide(..., structured=True)` — resolves, never averages; names the disagreement and its resolution |
| §11 Writer Nation gate | `kernel/customers.py::WriterNationGate` — DEMAND → TRUST → DELIVERY COST → MARGIN → SCALABILITY → LEGAL RISK → CUSTOMER OUTCOME |
| §12–§14 offer design | `OfferDesign` — 11 required fields, journey steps, ethical screen; `launch()` refuses while a gap or a fake-scarcity pattern exists |
| §15–§18 customer intelligence | `CustomerLedger` — minimum necessary data, consent-gated contact, rational qualification, revenue only from verified entries |
| §28 decision output | `DecisionEngine.decide()` — the record whose shape is below |
| §36 approval gate | an `ActionStep` with `budget_inr > 0` cannot exist without an `approval_ref` |
| §37 verification | every decision persists its forecast, and `record_outcome()` scores it against reality |

## The output shape (§28)

```
VERDICT          classification ∈ STOP | CONTINUE | IMPROVE | SCALE | TEST | DEFER | REJECT
                 + confidence LOW | MEDIUM | HIGH and the reason it is that and not higher
EVIDENCE         claims ranked by tier, strength score, proof count, declared gaps
8-MIND ANALYSIS  all eight mandates, each with findings, risks, questions, missing inputs, blind spots
AGREEMENT        where independent minds converge, and on what grounds
DISAGREEMENT     the real conflict, plus the chairman's resolution — never ignored
REALITY CHECK    what we know · think · are missing · what can break this · cheapest test
                 · kill criterion · if wrong · if right · do now
ACTION PLAN      ordered steps, each with owner, budget, duration, tool and a measurable metric
EXPECTED IMPACT  customer · financial (revenue ₹0.00 + modelled contribution, labelled) · strategic · learning
FORECAST         metric, expected value, horizon, comparator, evidence basis, revision rule, kill criterion
OPPORTUNITY COST what the same rupees and hours would otherwise have produced
```

## Classification rules (deterministic, inspectable)

| Test | Class |
|---|---|
| destroys cash, or violates an ethics rule | `STOP` |
| revenue > 0 but contribution ≤ 0 | `STOP` (reprice or kill) |
| a rule would be broken regardless of profit | `REJECT` |
| required capital > available cash | `DEFER` |
| a measured KPI is below target and facts exist | `IMPROVE` |
| verified facts, strength ≥ 0.60, positive contribution, no open gaps | `SCALE` |
| no verified FACT, strength < 0.40, or open unknowns | `TEST` (buy the missing fact first) |
| otherwise | `CONTINUE` |

Priority is exact: `STOP → REJECT → DEFER → IMPROVE → SCALE → TEST → CONTINUE`.

## What is refused, by construction

* A FACT with no source, or an unverified FACT.
* `SCALE` / `CONTINUE` without at least one verified FACT.
* Projected revenue above `₹0.00` with no verified evidence.
* A `HIGH`-confidence forecast with no FACT behind it.
* An action step with no measurable metric, a vague deadline ("soon", "ASAP"), or spending with no
  human-approval reference.
* An offer going LIVE with a missing field, no verified proof, a broken journey, fake scarcity,
  fake reviews, false urgency, guaranteed results or impersonation.
* A customer record containing sensitive personal data, or a credential-shaped string.
* Outbound marketing contact where consent is not `GRANTED`.
* Revenue attributed to a customer from anything other than a verified ledger entry.

## Honesty about the model itself

`GET /api/customer/decision/calibration` reports how often forecasts actually held, per confidence
band. With zero scored decisions it reports `hit_rate: null` and says so — it never claims accuracy
it has not measured. Confidence is about the strength of the reasoning and evidence; it is never a
promise about the outcome.
