"""Economic engine — ledger, opportunities, experiments, and the zero-capital resource scan.

Hard rules:
  * Revenue is ₹0 until a *verified* transaction exists in the ledger. Internal activity is not revenue.
  * Opportunities are scored with the strategic priority formula and can be hard-rejected.
  * Experiments always declare a success metric, a kill metric, and a ₹0 budget during the
    zero-capital phase.
  * Every kill writes a reusable lesson.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable

from . import paths, store
from .config import config
from .eventbus import E, bus
from .governance import ESTIMATE_STAMP, UNVERIFIED_STAMP, audit, priority_score

OPPORTUNITY_STATUSES = config().get("economy.opportunity.statuses", []) or [
    "DISCOVERED", "VALIDATING", "REJECTED", "MVP", "TESTING", "FIRST_REVENUE", "GROWING",
    "SCALING", "AUTOMATED", "PAUSED", "KILLED"]

RISK_SCORE = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.9}


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
class Ledger:
    def record(self, *, direction: str, amount_inr: float, category: str, description: str,
               source: str, verified: bool = False, evidence: dict | None = None,
               recorded_by: str = "system") -> dict:
        direction = direction.upper()
        if direction not in ("IN", "OUT"):
            raise ValueError("direction must be IN or OUT")
        if direction == "IN" and amount_inr > 0 and not verified:
            raise ValueError(
                "Refused: unverified revenue. A rupee is revenue only when a real, attributable "
                "transaction is recorded with a source and evidence. Mark verified=True only with evidence."
            )
        if direction == "IN" and verified and not (source and evidence):
            raise ValueError("Refused: verified revenue requires both a source and evidence.")
        row = {
            "id": store.new_id("led"), "ts": store.now(), "direction": direction,
            "amount_inr": float(amount_inr), "category": category, "description": description,
            "source": source, "verified": bool(verified),
            "evidence_json": json.dumps(evidence or {}, default=str), "recorded_by": recorded_by,
        }
        store.insert("ledger", row)
        bus.publish(E.LEDGER_ENTRY, source="economy", subject=row["id"],
                    severity="notice" if verified and direction == "IN" else "info",
                    payload={"direction": direction, "amount_inr": amount_inr, "category": category,
                             "verified": verified, "description": description})
        return row

    def revenue(self, *, verified_only: bool = True) -> float:
        sql = "SELECT COALESCE(SUM(amount_inr),0) s FROM ledger WHERE direction='IN'"
        if verified_only:
            sql += " AND verified=1"
        return float(store.query_one(sql)["s"] or 0)

    def costs(self) -> float:
        return float(store.query_one("SELECT COALESCE(SUM(amount_inr),0) s FROM ledger WHERE direction='OUT'")["s"] or 0)

    def kpis(self) -> dict:
        revenue = self.revenue()
        costs = self.costs()
        entries = store.query(
            "SELECT direction, amount_inr, verified, category, ts FROM ledger ORDER BY ts DESC LIMIT 200")
        return {
            "revenue_inr": round(revenue, 2),
            "costs_inr": round(costs, 2),
            "contribution_inr": round(revenue - costs, 2),
            "distinctions": {
                "REVENUE": round(revenue, 2),
                "GROSS_PROFIT": round(revenue - costs, 2),
                "OPEX": round(costs, 2),
                "NET_PROFIT": round(revenue - costs, 2),
                "CASH": round(revenue - costs, 2),
                "ACCOUNTS_RECEIVABLE": 0.0,
                "ACCOUNTS_PAYABLE": 0.0,
                "WORKING_CAPITAL": round(revenue - costs, 2),
                "CAC": None, "LTV": None, "ROAS": None, "ROI": None, "EBITDA": None,
            },
            "note": ("CAC/LTV/ROAS/ROI/EBITDA stay null until real acquisition and cost data exist. "
                     "Null is honest; a fabricated ratio is not."),
            "recent_entries": entries,
            "verified_entries": sum(1 for e in entries if e["verified"]),
        }


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------
class Opportunities:
    def create(self, *, title: str, problem: str, customer: str, market: str = "unspecified",
               competition: str = "unassessed", required_skills: list[str] | None = None,
               required_capital_inr: float = 0.0, expected_revenue_inr: float = 0.0,
               expected_margin_pct: float = 0.0, time_to_mvp_days: float | None = None,
               time_to_first_customer_days: float | None = None, risk: str = "MEDIUM",
               legal_risk: str = "LOW", technical_risk: str = "MEDIUM",
               demand_confidence: float = 0.3, model_confidence: float = 0.3,
               evidence: list | None = None, owner_agent: str | None = None) -> dict:
        hard_rejects = []
        cap_limit = float(config().get("economy.opportunity.hard_reject_if.requires_capital_above_inr", 0) or 0)
        if required_capital_inr > cap_limit:
            hard_rejects.append(f"Requires ₹{required_capital_inr:,.0f} capital; zero-capital phase allows ₹{cap_limit:,.0f}.")
        if legal_risk == "HIGH":
            hard_rejects.append("HIGH legal risk — needs professional counsel before progression.")
        row = {
            "id": store.new_id("opp"), "ts": store.now(), "title": title, "problem": problem,
            "customer": customer, "market": market, "competition": competition,
            "required_skills_json": json.dumps(required_skills or []),
            "required_capital_inr": float(required_capital_inr),
            "expected_revenue_inr": float(expected_revenue_inr),
            "expected_margin_pct": float(expected_margin_pct),
            "time_to_mvp_days": time_to_mvp_days, "time_to_first_customer_days": time_to_first_customer_days,
            "risk": risk, "legal_risk": legal_risk, "technical_risk": technical_risk,
            "demand_confidence": float(demand_confidence), "model_confidence": float(model_confidence),
            "status": "REJECTED" if hard_rejects else "DISCOVERED",
            "evidence_json": json.dumps(evidence or [], default=str), "owner_agent": owner_agent,
            "updated_at": store.now(),
        }
        store.insert("opportunities", row)
        scored = self.score(row)
        store.update("opportunities", row["id"], {"score": scored["score"]})
        bus.publish(E.OPPORTUNITY_DISCOVERED, source="economy", subject=row["id"],
                    severity="notice" if not hard_rejects else "warning",
                    payload={"title": title, "customer": customer, "score": scored["score"],
                             "band": scored["band"], "rejected": hard_rejects})
        if hard_rejects:
            bus.publish(E.OPPORTUNITY_STATUS, source="economy", subject=row["id"], severity="warning",
                        payload={"status": "REJECTED", "reasons": hard_rejects})
        return self.get(row["id"])  # type: ignore[return-value]

    def score(self, opp: dict) -> dict:
        impact = min(1.0, float(opp.get("expected_revenue_inr") or 0) / 50000 + 0.3)
        probability = float(opp.get("demand_confidence") or 0.3)
        strategic = 0.7
        customer_value = 0.7
        reversibility = 0.9 if float(opp.get("required_capital_inr") or 0) <= 0 else 0.5
        cost = 0.1 if float(opp.get("required_capital_inr") or 0) <= 0 else 0.7
        complexity = 0.4
        time_cost = min(1.0, float(opp.get("time_to_mvp_days") or 30) / 60)
        risk = RISK_SCORE.get(str(opp.get("risk", "MEDIUM")).upper(), 0.5)
        opportunity_cost = 0.3
        return priority_score(impact=impact, probability=probability, strategic_value=strategic,
                              customer_value=customer_value, reversibility=reversibility, cost=cost,
                              complexity=complexity, time_cost=time_cost, risk=risk,
                              opportunity_cost=opportunity_cost)

    def get(self, opp_id: str) -> dict | None:
        row = store.get("opportunities", opp_id)
        if not row:
            return None
        row["required_skills"] = store.jload(row.pop("required_skills_json", None), [])
        row["evidence"] = store.jload(row.pop("evidence_json", None), [])
        row["experiments"] = [self._exp(r) for r in store.query(
            "SELECT * FROM experiments WHERE opportunity_id=? ORDER BY ts DESC", (opp_id,))]
        return row

    @staticmethod
    def _exp(row: dict) -> dict:
        row["result"] = store.jload(row.pop("result_json", None), {})
        return row

    def list(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM opportunities"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY score DESC, ts DESC LIMIT ?"
        return [self.get(r["id"]) for r in store.query(sql, params + (limit,))]  # type: ignore[misc]

    def set_status(self, opp_id: str, status: str, *, reason: str = "", by: str = "SUPREME") -> dict:
        if status not in OPPORTUNITY_STATUSES:
            raise ValueError(f"Unknown status. Allowed: {OPPORTUNITY_STATUSES}")
        store.update("opportunities", opp_id, {"status": status, "updated_at": store.now()})
        bus.publish(E.OPPORTUNITY_STATUS, source="economy", subject=opp_id, severity="notice",
                    payload={"status": status, "reason": reason, "by": by})
        return self.get(opp_id)  # type: ignore[return-value]

    def judge(self, opp_id: str, *, facts: list[str] | None = None, unknowns: list[str] | None = None) -> dict:
        """Run the 8-mind engine + chairman verdict over a live opportunity."""
        from .governance import chairman
        opp = self.get(opp_id)
        if not opp:
            raise ValueError("Unknown opportunity")
        numbers = {
            "expected_revenue": opp.get("expected_revenue_inr") or 0,
            "variable_costs": 0,
            "incremental_costs": 0,
            "required_capital": opp.get("required_capital_inr") or 0,
            "strategic_fit": 0.7,
        }
        verdict = chairman.decide(
            question=f"Should we pursue: {opp['title']} — {opp['problem']} (buyer: {opp['customer']})?",
            facts=facts or [e.get("value", "") if isinstance(e, dict) else str(e) for e in opp.get("evidence", [])],
            assumptions=[f"Demand confidence is self-assessed at {opp.get('demand_confidence')}."],
            unknowns=unknowns or ["Whether the buyer will pay", "Whether the channel reaches them"],
            numbers=numbers,
        )
        store.update("opportunities", opp_id, {"updated_at": store.now(),
                                              "model_confidence": 0.5 if verdict.confidence == "MEDIUM" else 0.25})
        bus.publish(E.OPPORTUNITY_SCORED, source="economy", subject=opp_id, severity="notice",
                    payload={"verdict": verdict.verdict, "confidence": verdict.confidence})
        return verdict.to_dict()

    # ---- zero-capital discovery ---------------------------------------
    def discover_zero_capital(self, *, owner_agent: str | None = None) -> list[dict]:
        """Generate candidate opportunities from assets that already exist. Every claim is labelled."""
        created = []
        catalog_exists = (paths.SEED_DIR / "books.json").exists()
        book_count = 0
        if catalog_exists:
            try:
                book_count = json.loads((paths.SEED_DIR / "books.json").read_text(encoding="utf-8")).get("count", 0)
            except Exception:
                book_count = 0

        candidates = [
            dict(
                title="Verify and revive the top 5 catalog titles",
                problem="An inherited catalog exists but no listing, price or demand is verified — so any "
                        "marketing spend would be aimed at an unknown target.",
                customer="Existing readers of the author's catalog",
                market="Self-published non-fiction (India) — unverified",
                competition="Unassessed",
                required_skills=["metadata", "category positioning", "cover review"],
                required_capital_inr=0, expected_revenue_inr=0, expected_margin_pct=0,
                time_to_mvp_days=7, time_to_first_customer_days=30, risk="LOW", legal_risk="LOW",
                technical_risk="LOW", demand_confidence=0.25, model_confidence=0.3,
                evidence=[{"kind": "FACT", "value": f"{book_count} catalog rows exist locally (unverified)."},
                          {"kind": "UNKNOWN", "value": f"Live listing state: {UNVERIFIED_STAMP}"}],
                owner_agent=owner_agent,
            ),
            dict(
                title="Sell one ₹0-delivery service the author can already perform",
                problem="Skill exists, offer does not. A paid service converts skill into verified revenue "
                        "without capital, and reveals what buyers actually want.",
                customer="Aspiring authors who need help finishing or publishing a manuscript",
                market="Author services (India, English + Hindi) — unverified",
                competition="Unassessed",
                required_skills=["editing", "publishing guidance", "communication"],
                required_capital_inr=0, expected_revenue_inr=0, expected_margin_pct=80,
                time_to_mvp_days=3, time_to_first_customer_days=14, risk="MEDIUM", legal_risk="LOW",
                technical_risk="LOW", demand_confidence=0.3, model_confidence=0.35,
                evidence=[{"kind": "ASSUMPTION", "value": "Authors will pay for guided help."},
                          {"kind": "UNKNOWN", "value": "Willingness to pay is unmeasured."}],
                owner_agent=owner_agent,
            ),
            dict(
                title="Turn existing long-form material into a ₹0 lead magnet + email capture",
                problem="Attention without capture is wasted; an existing chapter or essay can become the "
                        "first step of a funnel at zero cost.",
                customer="Readers of the author's existing content",
                market="Email list building — unverified",
                competition="Unassessed",
                required_skills=["editing", "landing page", "email"],
                required_capital_inr=0, expected_revenue_inr=0, expected_margin_pct=0,
                time_to_mvp_days=5, time_to_first_customer_days=45, risk="LOW", legal_risk="LOW",
                technical_risk="LOW", demand_confidence=0.3, model_confidence=0.3,
                evidence=[{"kind": "ASSUMPTION", "value": "Existing content can attract the target reader."},
                          {"kind": "UNKNOWN", "value": "Current traffic and conversion: unmeasured."}],
                owner_agent=owner_agent,
            ),
        ]
        for c in candidates:
            if store.query_one("SELECT id FROM opportunities WHERE title=?", (c["title"],)):
                continue
            created.append(self.create(**c))
        return created


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------
class Experiments:
    def create(self, *, hypothesis: str, expected_result: str, mvp_definition: str, test_method: str,
               success_metric: str, kill_metric: str, opportunity_id: str | None = None,
               cost_inr: float = 0.0, decision_rule: str = "SCALE if success metric met; else ITERATE once; else KILL.",
               owner_agent: str | None = None) -> dict:
        if cost_inr > 0:
            raise ValueError("Zero-capital phase: experiments costing money must be approved by the owner first.")
        row = {"id": store.new_id("exp"), "ts": store.now(), "opportunity_id": opportunity_id,
               "hypothesis": hypothesis, "cost_inr": float(cost_inr), "expected_result": expected_result,
               "mvp_definition": mvp_definition, "test_method": test_method, "success_metric": success_metric,
               "kill_metric": kill_metric, "decision_rule": decision_rule, "status": "DESIGNED",
               "owner_agent": owner_agent}
        store.insert("experiments", row)
        bus.publish(E.EXPERIMENT_CREATED, source="economy", subject=row["id"],
                    payload={"hypothesis": hypothesis, "success_metric": success_metric,
                             "kill_metric": kill_metric})
        return row

    def measure(self, exp_id: str, *, observed: dict, notes: str = "") -> dict:
        exp = store.get("experiments", exp_id)
        if not exp:
            raise ValueError("Unknown experiment")
        store.update("experiments", exp_id, {"status": "MEASURED",
                                            "result_json": json.dumps({"observed": observed, "notes": notes}, default=str)})
        bus.publish(E.EXPERIMENT_MEASURED, source="economy", subject=exp_id,
                    payload={"observed": observed, "notes": notes})
        return store.get("experiments", exp_id)  # type: ignore[return-value]

    def decide(self, exp_id: str, decision: str, *, learning: str = "", by: str = "SUPREME") -> dict:
        decision = decision.upper()
        allowed = config().get("economy.experiment.decisions", ["SCALE", "ITERATE", "PAUSE", "KILL"])
        if decision not in allowed:
            raise ValueError(f"Decision must be one of {allowed}")
        store.update("experiments", exp_id, {"decision": decision, "decided_at": store.now(),
                                             "status": "DECIDED", "learning": learning})
        row = store.get("experiments", exp_id)
        assert row is not None
        bus.publish(E.EXPERIMENT_DECIDED, source="economy", subject=exp_id, severity="notice",
                    payload={"decision": decision, "learning": learning, "by": by})
        if decision == "KILL":
            self.record_lesson(title=f"Killed: {(row.get('hypothesis') or '')[:80]}",
                               lesson=learning or "No learning recorded — that is itself a failure.",
                               source=exp_id, tags=["experiment", "kill"])
        elif decision == "SCALE":
            self.record_lesson(title=f"Scaled: {(row.get('hypothesis') or '')[:80]}",
                               lesson=learning or "Success metric met; channel assumed repeatable — verify.",
                               source=exp_id, tags=["experiment", "scale"])
        return row

    def record_lesson(self, *, title: str, lesson: str, source: str = "manual",
                      tags: Iterable[str] | None = None, reusable: bool = True) -> dict:
        row = {"id": store.new_id("les"), "ts": store.now(), "source": source,
               "experiment_id": source if source.startswith("exp-") else None, "title": title,
               "lesson": lesson, "tags_json": json.dumps(list(tags or [])), "reusable": int(reusable)}
        store.insert("lessons", row)
        bus.publish(E.LESSON_LEARNED, source="economy", subject=row["id"], severity="notice",
                    payload={"title": title, "lesson": lesson[:240]})
        return row

    def list(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM experiments"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY ts DESC LIMIT ?"
        out = []
        for row in store.query(sql, params + (limit,)):
            row["result"] = store.jload(row.pop("result_json", None), {})
            out.append(row)
        return out


# ---------------------------------------------------------------------------
# Free-resource engine
# ---------------------------------------------------------------------------
class FreeResourceEngine:
    """Finds legal, free capability and turns it into concrete next actions — never unauthorized access."""

    def catalogue(self) -> dict:
        return config().section("economics").get("free_resources", {})

    def scan(self) -> dict:
        findings: list[dict] = []
        # 1. local model capability
        from .model_router import router
        status = router().status()
        findings.append({
            "resource": "local_model_inference", "available": bool(status["reachable"]),
            "detail": (f"Ollama reachable with {len(status['installed_models'])} model(s)."
                       if status["reachable"] else
                       "No local model detected. Install Ollama (free) and pull a small model to enable "
                       "real reasoning. Until then the deterministic engine answers and labels its output."),
            "cost_inr": 0, "requires": "ollama serve",
        })
        # 2. catalog asset
        seed = paths.SEED_DIR / "books.json"
        findings.append({"resource": "existing_ip_catalog", "available": seed.exists(),
                         "detail": "Inherited catalog present (unverified)." if seed.exists() else "No catalog found.",
                         "cost_inr": 0})
        # 3. integrations (all free-tier official APIs)
        rows = store.query("SELECT id, status FROM integrations")
        findings.append({"resource": "official_apis", "available": any(r["status"] == "CONNECTED" for r in rows),
                         "detail": {r["id"]: r["status"] for r in rows}, "cost_inr": 0,
                         "requires": "owner-provided OAuth credentials (free tiers)"})
        # 4. distribution (existing accounts)
        findings.append({"resource": "existing_distribution", "available": None,
                         "detail": "Unverified: the system cannot see follower counts or email list size "
                                   "until the owner connects an account or states the numbers.",
                         "cost_inr": 0})
        return {"scanned_at": store.now(), "findings": findings,
                "forbidden_tactics_reminder": (self.catalogue().get("forbidden_tactics", [])
                                               or ["paywall_bypass", "rate_limit_evasion", "tos_violation"]),
                "next_actions": [
                    "Install Ollama + one small model (₹0, ~10 minutes, offline capable).",
                    "Owner states real numbers: email list size, follower counts, live listings.",
                    "Pick ONE ₹0 offer and expose it to the smallest real audience this week.",
                ]}


# Singletons
ledger = Ledger()
opportunities = Opportunities()
experiments = Experiments()
free_resources = FreeResourceEngine()


def economic_summary() -> dict:
    kpis = ledger.kpis()
    opps = store.query("SELECT status, COUNT(*) n FROM opportunities GROUP BY status")
    return {
        "capital_initial_inr": float(config().get("governance.identity.initial_capital_inr", 0) or 0),
        "revenue_inr": kpis["revenue_inr"],
        "costs_inr": kpis["costs_inr"],
        "contribution_inr": kpis["contribution_inr"],
        "opportunities": {r["status"]: r["n"] for r in opps},
        "experiments_open": int(store.query_one(
            "SELECT COUNT(*) n FROM experiments WHERE status IN ('DESIGNED','RUNNING','MEASURED')")["n"]),
        "lessons_learned": int(store.query_one("SELECT COUNT(*) n FROM lessons")["n"]),
        "honesty": ("Revenue is ₹0 until a verified transaction exists. "
                    "Everything else here is activity, not income."),
        "estimate_note": ESTIMATE_STAMP,
    }
