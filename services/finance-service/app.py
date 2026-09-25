"""Finance Service (port 8010) — verified books, unit economics, scenarios, spend guard."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from kernel import store
from kernel.config import config
from kernel.economy import ledger
from kernel.governance import ESTIMATE_STAMP, chairman
from services.base import ServiceCard, require_owner, service_app

PORT = 8010
CARD = ServiceCard(
    name="finance-service", port=PORT, layer="D · economic engine", domain="finance",
    description="Revenue accounting on verified entries only, unit economics, scenario modelling "
                "and the zero-spend guard.",
    owns_tables=["ledger (reads/writes)", "settings (cash)"],
    produces_events=["economy.ledger_entry"],
    consumes_events=["economy.*"],
    endpoints=["GET /finance/summary", "GET /finance/distinctions", "POST /finance/unit-economics",
               "POST /finance/scenarios", "POST /finance/spend-check", "GET /finance/runway"],
    dependencies=["kernel.economy", "kernel.governance"],
)
application = service_app(CARD)


@application.get("/finance/summary")
def summary(_: str = Depends(require_owner)) -> dict:
    kpis = ledger.kpis()
    return {**kpis,
            "initial_capital_inr": float(config().get("governance.identity.initial_capital_inr", 0) or 0),
            "spend_policy": config().get("governance.spend", {}),
            "honesty": "Revenue counts only what the ledger verified. Everything else is intention."}


@application.get("/finance/distinctions")
def distinctions(_: str = Depends(require_owner)) -> dict:
    kpis = ledger.kpis()
    return {
        "definitions": {
            "REVENUE": "Verified money in.",
            "GROSS_PROFIT": "Revenue − direct costs of delivery.",
            "OPEX": "Operating expenses.",
            "NET_PROFIT": "Revenue − all costs.",
            "CASH": "Money actually available now (not receivables).",
            "ACCOUNTS_RECEIVABLE": "Money owed to us but not received.",
            "ACCOUNTS_PAYABLE": "Money we owe but have not paid.",
            "WORKING_CAPITAL": "Current assets − current liabilities.",
            "CAC": "Cost to acquire one customer.",
            "LTV": "Contribution from a customer over the relationship.",
            "ROAS": "Revenue per rupee of ad spend.",
            "ROI": "Return on the capital deployed.",
            "EBITDA": "Earnings before interest, tax, depreciation and amortisation.",
        },
        "current": kpis["distinctions"],
        "why_nulls": ("CAC/LTV/ROAS/ROI/EBITDA stay null until real acquisition and cost data exist. "
                      "A fabricated ratio is worse than an empty field."),
    }


@application.post("/finance/unit-economics")
def unit_economics(body: dict, _: str = Depends(require_owner)) -> dict:
    """Contribution = revenue − variable − incremental (and CAC where supplied)."""
    price = float(body.get("price_inr", 0) or 0)
    units = float(body.get("expected_units", 0) or 0)
    variable = float(body.get("variable_cost_per_unit_inr", 0) or 0)
    incremental = float(body.get("incremental_cost_inr", 0) or 0)
    cac = float(body.get("cac_inr", 0) or 0)
    revenue = price * units
    contribution = revenue - variable * units - incremental - cac * units
    margin = (contribution / revenue * 100) if revenue else 0.0
    return {
        "expected_revenue_inr": round(revenue, 2),
        "expected_contribution_inr": round(contribution, 2),
        "contribution_margin_pct": round(margin, 2),
        "scenarios": {"BASE": round(contribution, 2), "UPSIDE": round(contribution * 1.5, 2),
                      "DOWNSIDE": round(contribution * 0.5, 2),
                      "WORST_REASONABLE": round(-abs(incremental) - abs(cac * units), 2)},
        "label": ESTIMATE_STAMP,
        "assumptions": ["Volumes, price and CAC are inputs, not observations.",
                        "No fixed costs are included — this is contribution, not profit."],
        "scale_gate": config().get("governance.economics.scale_gate", {}),
    }


@application.post("/finance/scenarios")
def scenarios(body: dict, _: str = Depends(require_owner)) -> dict:
    question = body.get("question", "Should we proceed?")
    verdict = chairman.decide(
        question=question,
        facts=body.get("facts") or [],
        assumptions=body.get("assumptions") or [],
        unknowns=body.get("unknowns") or ["Whether anyone will pay"],
        numbers={k: body.get(k, 0) for k in ("expected_revenue", "variable_costs", "incremental_costs",
                                             "required_capital", "payback_days")},
    )
    return verdict.to_dict()


@application.post("/finance/spend-check")
def spend_check(body: dict, _: str = Depends(require_owner)) -> dict:
    amount = float(body.get("amount_inr", 0) or 0)
    limit = float(config().get("governance.spend.daily_limit_inr", 0) or 0)
    policy = str(config().get("governance.spend.policy", "ZERO_BY_DEFAULT"))
    allowed = amount <= limit
    result = {
        "requested_inr": amount, "daily_limit_inr": limit, "policy": policy,
        "allowed_without_approval": allowed,
        "requires_owner_approval": not allowed,
        "decision": "ALLOWED" if allowed else "BLOCKED — owner approval required",
        "reason": (f"ZERO-CAPITAL PHASE: any spend above ₹{limit:,.0f} needs an explicit owner decision."
                   if not allowed else "Within the zero-spend allowance (₹0)."),
        "hard_block": bool(config().get("governance.spend.hard_block", True)),
    }
    if not allowed:
        from kernel.eventbus import E, bus
        bus.publish(E.POLICY_DENIED, source="finance-service", severity="warning",
                    payload={"action": "spend", "amount_inr": amount, "limit_inr": limit})
    return result


@application.get("/finance/runway")
def runway(_: str = Depends(require_owner)) -> dict:
    cash = float(store.get_setting("cash_available_inr", 0) or 0)
    monthly_cost = float(store.get_setting("monthly_cost_inr", 0) or 0)
    return {
        "cash_inr": cash,
        "monthly_cost_inr": monthly_cost,
        "runway_months": (round(cash / monthly_cost, 2) if monthly_cost > 0 else None),
        "note": ("Runway is unknown until someone records real cash and real costs. "
                 "An empty field is honest; a guessed one is not."),
        "capital_rule": "Protect capital → reinvest intelligently. Never spend to look bigger.",
    }
