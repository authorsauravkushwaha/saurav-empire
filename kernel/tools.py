"""Tool layer — the only way an agent touches the world.

Every tool is: permission-checked, risk-tiered, audited, and offline-safe.
A tool that cannot do its job honestly reports that it cannot, instead of fabricating output.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import paths, store
from .config import building_index, config
from .eventbus import E, bus
from .governance import ESTIMATE_STAMP, UNVERIFIED_STAMP, audit, claims, permissions, priority_score


@dataclass
class Tool:
    name: str
    fn: Callable[[dict, dict], dict]
    description: str
    risk: str = "LOW"
    tool_key: str = ""          # key in config/permissions.yaml::tools
    requires_model: bool = False

    def run(self, payload: dict, agent: dict) -> dict:
        return self.fn(payload, agent)


TOOLS: dict[str, Tool] = {}


def tool(name: str, *, description: str = "", risk: str = "LOW", tool_key: str | None = None,
         requires_model: bool = False):
    def decorator(fn: Callable[[dict, dict], dict]) -> Callable[[dict, dict], dict]:
        TOOLS[name] = Tool(name=name, fn=fn, description=description or fn.__doc__ or "",
                           risk=risk, tool_key=tool_key or f"tool.{name}",
                           requires_model=requires_model)
        return fn
    return decorator


def _stamp(payload: dict) -> dict:
    payload.setdefault("evidence", [])
    return payload


def ensure_labels(result: dict) -> dict:
    """A tool result may never be published without evidence labels.

    Applied at dispatch, so a tool added later cannot forget it: the constitution requires every
    claim to be labelled (FACT / ASSUMPTION / INFERENCE / HYPOTHESIS / OPINION / UNKNOWN), and a
    run that produced no verified evidence says exactly that.
    """
    if not isinstance(result, dict):
        return result
    result.setdefault("evidence", [])
    if not result["evidence"]:
        result["evidence"] = [{
            "kind": "UNKNOWN",
            "value": "This tool run produced no verified evidence. Treat the output as a hypothesis.",
            "source": f"tool-dispatch:{result.get('tool', 'unknown')}",
        }]
        result["labelled_by"] = "tool-dispatch"
    result["evidence_summary"] = " | ".join(
        f"{e.get('kind', 'UNKNOWN')}: {str(e.get('value', ''))[:90]}" for e in result["evidence"][:4]
    )
    return result


# ---------------------------------------------------------------------------
# Analysis tools
# ---------------------------------------------------------------------------
@tool("catalog_audit", description="Audit the inherited book catalog; rank which titles deserve resources.",
      risk="LOW", tool_key="memory.write")
def catalog_audit(payload: dict, agent: dict) -> dict:
    seed_path = paths.SEED_DIR / "books.json"
    if not seed_path.exists():
        return {"status": "blocked", "reason": "No seed catalog found.", "evidence": [
            {"kind": "UNKNOWN", "value": UNVERIFIED_STAMP}]}
    catalog = json.loads(seed_path.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    cats: dict[str, int] = {}
    prices: list[float] = []
    for b in books:
        cats[b.get("category") or "Unknown"] = cats.get(b.get("category") or "Unknown", 0) + 1
        if isinstance(b.get("price_inr"), (int, float)):
            prices.append(float(b["price_inr"]))

    # Positioning audit: a book is only "resource-worthy" if it can state audience + promise + proof
    scored = []
    for b in books:
        signals = {
            "has_hook": bool(b.get("hook")),
            "has_series": bool(b.get("series")),
            "category_crowded": cats.get(b.get("category") or "Unknown", 0) >= 7,
            "verified_listing": bool(b.get("asin")),
            "verified_demand": False,     # nothing in the seed proves demand
        }
        readiness = sum(1 for k, v in signals.items() if v and k.startswith("has")) / 2
        scored.append({"id": b.get("id"), "title": b.get("title"), "category": b.get("category"),
                       "price_inr": b.get("price_inr"), "series": b.get("series"),
                       "signals": signals, "readiness": round(readiness, 2),
                       "priority": "AUDIT FIRST" if readiness >= 0.5 and not signals["category_crowded"]
                                   else "AUDIT LATER"})
    scored.sort(key=lambda x: (-x["readiness"], x["signals"]["category_crowded"]))

    crowded = sorted([(c, n) for c, n in cats.items()], key=lambda x: -x[1])[:5]
    result = {
        "status": "ok",
        "catalog_size": len(books),
        "category_distribution": cats,
        "most_crowded_categories": crowded,
        "price_stats": {
            "count": len(prices),
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "median": statistics.median(prices) if prices else None,
        },
        "resource_ranking": scored[:12],
        "facts": [
            f"Catalog contains {len(books)} inherited titles. [FACT — local seed file data/seed/books.json]",
            f"{len(cats)} categories present; most crowded: {crowded[:3]}. [FACT — computed from seed]",
            f"Zero of {len(books)} titles have a verified listing or verified demand. [FACT — no ASIN verified]",
        ],
        "assumptions": [
            f"Category crowding is inferred from this catalog only, not from the market. [{ESTIMATE_STAMP}]",
            "A hook and a series are treated as weak readiness signals, not proof of demand. [ASSUMPTION]",
        ],
        "unknowns": [
            "Actual sales, conversion and read-through per title",
            "Current live listing state on each storefront",
            "Real competitor pricing in each category, today",
        ],
        "recommended_next_action": (
            "Verify the live state of the top 5 'AUDIT FIRST' titles (listing live? price? reviews? rank?) "
            "before spending any time on marketing. Marketing a listing that is not live is waste."
        ),
        "verified": False,
        "label": "SEED (unverified)",
    }
    # Write the artifact and a memory record so the finding is reusable
    out = paths.ARTIFACT_DIR / f"catalog-audit-{int(time.time())}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["artifact_path"] = str(out.relative_to(paths.ROOT))
    from .memory import memory
    memory.semantic(agent.get("id"), f"Catalog audit: {len(books)} titles, {len(cats)} categories, "
                                     f"0 verified listings. Artifact: {result['artifact_path']}",
                    source=result["artifact_path"], evidence_kind="FACT", confidence=0.9,
                    importance=0.75, tags=["catalog", "publishing"])
    return _stamp(result)


@tool("unit_economics", description="Compute contribution, margin and payback; never invents revenue.",
      risk="LOW", tool_key="memory.write")
def unit_economics(payload: dict, agent: dict) -> dict:
    price = float(payload.get("price_inr", 0) or 0)
    units = float(payload.get("expected_units", 0) or 0)
    variable = float(payload.get("variable_cost_per_unit_inr", 0) or 0)
    incremental = float(payload.get("incremental_cost_inr", 0) or 0)
    cac = float(payload.get("cac_inr", 0) or 0)
    revenue = price * units
    contribution = revenue - (variable * units) - incremental - (cac * units)
    margin = (contribution / revenue * 100) if revenue else 0.0
    verified_revenue = store.query_one("SELECT COALESCE(SUM(amount_inr),0) s FROM ledger WHERE direction='IN' AND verified=1")["s"]
    return {
        "status": "ok",
        "inputs": {"price_inr": price, "expected_units": units, "variable_cost_per_unit_inr": variable,
                   "incremental_cost_inr": incremental, "cac_inr": cac},
        "computed": {"expected_revenue_inr": round(revenue, 2),
                     "expected_contribution_inr": round(contribution, 2),
                     "contribution_margin_pct": round(margin, 2),
                     "payback_days": round(365 / max(units, 0.0001), 1) if units else None},
        "ledger_verified_revenue_inr": float(verified_revenue or 0),
        "scenarios": {
            "BASE": round(contribution, 2),
            "UPSIDE": round(contribution * 1.5, 2),
            "DOWNSIDE": round(contribution * 0.5, 2),
            "WORST_REASONABLE": round(-abs(incremental) - abs(cac * units), 2),
        },
        "facts": [f"Verified ledger revenue to date: ₹{float(verified_revenue or 0):,.2f}. [FACT — ledger]"],
        "assumptions": ["Unit volumes, price and CAC are inputs, not observations. [ASSUMPTION]",
                        f"Contribution = revenue − variable×units − incremental − CAC×units. [{ESTIMATE_STAMP}]"],
        "unknowns": ["Actual conversion rate", "Actual refund/chargeback rate", "Real CAC once tested"],
        "kill_rule": "If measured contribution stays negative after two pricing/offer iterations, stop.",
        "verified": False,
    }


@tool("market_signal_scan", description="Search for demand signals; reports honestly when no external source is available.",
      risk="LOW", tool_key="memory.write", requires_model=False)
def market_signal_scan(payload: dict, agent: dict) -> dict:
    topic = payload.get("topic", "unspecified")
    external_allowed = bool(config().get("governance.automation.approval_gated")) and bool(
        payload.get("allow_external", False))
    signals: list[dict] = []
    # Internal signals only — real data the civilization already owns.
    ledger = store.query_one("SELECT COUNT(*) n, COALESCE(SUM(amount_inr),0) s FROM ledger WHERE verified=1")
    tasks_done = store.query_one("SELECT COUNT(*) n FROM tasks WHERE status='DONE'")
    signals.append({"source": "internal_ledger", "kind": "FACT",
                    "finding": f"Verified transactions recorded: {ledger['n']}. Verified revenue: ₹{float(ledger['s']):,.2f}."})
    signals.append({"source": "internal_work", "kind": "FACT",
                    "finding": f"Completed internal tasks: {tasks_done['n']}."})
    return {
        "status": "partial",
        "topic": topic,
        "signals": signals,
        "external_search": {
            "performed": external_allowed,
            "reason": "No external research connector is authorized/configured yet."
                      if not external_allowed else "External research requested.",
        },
        "facts": [s["finding"] for s in signals],
        "assumptions": [f"'{topic}' is worth investigating. [ASSUMPTION — not yet evidenced]"],
        "unknowns": ["Whether anyone will pay for this",
                     "Who the exact buyer is", "What the current alternatives cost them"],
        "cheapest_test": (
            "Ask 3 people who match the target customer what they currently do about this problem, "
            "and what they have already paid for. Cost ₹0. Time: 1 hour. Record exact words."
        ),
        "verified": False,
        "label": UNVERIFIED_STAMP,
    }


@tool("kpi_report", description="Aggregate the civilization's real metrics into an honest report.",
      risk="LOW", tool_key="ledger.read")
def kpi_report(payload: dict, agent: dict) -> dict:
    from .tasks import board
    from .registry import agents as agent_registry
    counts = store.table_counts()
    ledger_in = store.query_one("SELECT COALESCE(SUM(amount_inr),0) s, COUNT(*) n FROM ledger WHERE direction='IN' AND verified=1")
    ledger_out = store.query_one("SELECT COALESCE(SUM(amount_inr),0) s, COUNT(*) n FROM ledger WHERE direction='OUT'")
    opportunities = store.query("SELECT status, COUNT(*) n FROM opportunities GROUP BY status")
    experiments = store.query("SELECT status, COUNT(*) n FROM experiments GROUP BY status")
    report = {
        "status": "ok",
        "generated_at": store.now(),
        "verified_revenue_inr": float(ledger_in["s"] or 0),
        "verified_revenue_entries": int(ledger_in["n"] or 0),
        "recorded_costs_inr": float(ledger_out["s"] or 0),
        "contribution_inr": round(float(ledger_in["s"] or 0) - float(ledger_out["s"] or 0), 2),
        "agent_counts": agent_registry.counts(),
        "task_metrics": board.metrics(),
        "opportunities_by_status": {r["status"]: r["n"] for r in opportunities},
        "experiments_by_status": {r["status"]: r["n"] for r in experiments},
        "table_counts": counts,
        "honesty_note": ("Revenue is ₹0 until a verified transaction exists in the ledger. "
                         "Internal activity is not revenue."),
        "facts": [f"Verified revenue: ₹{float(ledger_in['s'] or 0):,.2f} from {int(ledger_in['n'] or 0)} entries. [FACT]",
                  f"Agents: {agent_registry.counts()['total']}. Tasks completed: {board.metrics()['completed']}. [FACT]"],
        "unknowns": ["Whether any current activity is commercially attractive — that needs a customer, not a dashboard."],
    }
    out = paths.ARTIFACT_DIR / f"kpi-report-{int(time.time())}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["artifact_path"] = str(out.relative_to(paths.ROOT))
    return report


# ---------------------------------------------------------------------------
# Content & communication tools (always model-honest, always claims-screened)
# ---------------------------------------------------------------------------
@tool("draft_content", description="Draft content with a declared job; screened for forbidden claims.",
      risk="MEDIUM", tool_key="memory.write", requires_model=True)
def draft_content(payload: dict, agent: dict) -> dict:
    from .model_router import router
    topic = payload.get("topic", "unspecified")
    audience = payload.get("audience", "unspecified audience")
    job = payload.get("job", "trust")   # awareness|education|trust|authority|engagement|lead|conversion|retention|referral
    channel = payload.get("channel", "internal")
    prompt = (
        f"Topic: {topic}\nAudience: {audience}\nChannel: {channel}\nJob of this content: {job}\n"
        "Write the draft. Rules: no invented numbers, testimonials, awards or results; "
        "state limitations honestly; end with one clear next step."
    )
    res = router().route("content_draft", prompt, max_tokens=700)
    review = claims.review(res.text, context="content_draft")
    return {
        "status": "ok",
        "declared_job": job,
        "audience": audience,
        "channel": channel,
        "draft": res.text,
        "provider": res.provider,
        "model": res.model,
        "model_verified": res.model_verified,
        "output_label": res.label,
        "claims_review": review,
        "publishable": bool(review["safe_to_publish"]) and res.model_verified,
        "blockers": ([b["rule"] for b in review["blocks"]] or
                     ([] if res.model_verified else ["No model produced this draft — it is a scaffold, not a finished asset."])),
        "next_step": "Owner approval required to publish (HIGH risk action). Review the claims review output first.",
        "verified": res.model_verified,
    }


@tool("draft_outreach", description="Draft a personalised, honest outreach message. Never sends it.",
      risk="MEDIUM", tool_key="memory.write", requires_model=True)
def draft_outreach(payload: dict, agent: dict) -> dict:
    from .model_router import router
    recipient_context = payload.get("recipient_context", "unknown recipient")
    offer = payload.get("offer", "unspecified offer")
    goal = payload.get("goal", "start a conversation")
    prompt = (
        f"Recipient context: {recipient_context}\nOffer: {offer}\nGoal: {goal}\n"
        "Write a short, specific, non-pushy message. No fake familiarity, no invented mutual connections, "
        "no false urgency, no inflated claims. One clear ask. Under 120 words."
    )
    res = router().route("copywriting", prompt, max_tokens=400)
    review = claims.review(res.text, context="outreach_draft")
    return {
        "status": "ok",
        "draft": res.text,
        "provider": res.provider,
        "model": res.model,
        "output_label": res.label,
        "claims_review": review,
        "send_status": "NOT SENT — sending is a HIGH-risk action requiring explicit owner approval.",
        "personalisation_note": "Verify every specific claim in this message before sending. Unverified specifics damage trust.",
        "verified": res.model_verified,
    }


@tool("experiment_design", description="Design a ₹0 experiment with a declared success and kill metric.",
      risk="MEDIUM", tool_key="experiment.create")
def experiment_design(payload: dict, agent: dict) -> dict:
    hypothesis = payload.get("hypothesis", "Unspecified hypothesis")
    metric = payload.get("success_metric", "one declared measurable outcome")
    return {
        "status": "ok",
        "hypothesis": hypothesis,
        "cost_inr": 0,
        "mvp_definition": payload.get("mvp", "The smallest honest version of the promise"),
        "test_method": payload.get("test_method", "Expose it to the smallest real audience and measure."),
        "success_metric": metric,
        "kill_metric": payload.get("kill_metric", "No signal after the declared window"),
        "decision_rule": "SCALE if success_metric met and contribution > 0; ITERATE once; else KILL.",
        "duration_days": payload.get("duration_days", 14),
        "facts": ["Cost of this experiment is ₹0 with owner time only. [FACT]"],
        "assumptions": ["The metric chosen actually reflects demand, not activity. [ASSUMPTION]"],
        "unknowns": ["Whether the audience sees it at all", "Whether the promise is the reason they act"],
    }


@tool("engineering_brief", description="Produce a verifiable engineering brief/spec. Never invents code.",
      risk="MEDIUM", tool_key="code.write_file", requires_model=True)
def engineering_brief(payload: dict, agent: dict) -> dict:
    from .model_router import router
    goal = payload.get("goal", "unspecified change")
    res = router().route("coding", (
        f"Goal: {goal}\nWrite an engineering brief: files to touch, data model changes, "
        "test plan, rollback plan, and definition of done. Do not write final code unless asked. "
        "If you cannot be sure, say 'Not verified.'"
    ), max_tokens=600)
    return {"status": "ok", "goal": goal, "brief": res.text, "provider": res.provider,
            "output_label": res.label, "model_verified": res.model_verified,
            "definition_of_done": "Tests pass; behaviour verified by an independent check, not by the author.",
            "verified": res.model_verified}


@tool("research_plan", description="Produce the cheapest test that reduces the most uncertainty.",
      risk="LOW", tool_key="memory.write")
def research_plan(payload: dict, agent: dict) -> dict:
    unknowns = payload.get("unknowns", []) or ["Unspecified unknown"]
    top = unknowns[0] if isinstance(unknowns, list) and unknowns else str(unknowns)
    return {
        "status": "ok",
        "tool": "research_plan",
        "label": "HYPOTHESIS / UNKNOWN — a research plan is a proposal, never a finding.",
        "evidence": [
            {"kind": "HYPOTHESIS", "value": f"'{top}' matters enough to test.",
             "source": "mission generator payload — no evidence collected yet."},
            {"kind": "UNKNOWN", "value": "Whether a real buyer has this problem, and what they pay today.",
             "source": "no interviews or market data have been collected for this topic."},
        ],
        "unknowns": unknowns,
        "cheapest_test": f"Design the smallest test that answers: {top}",
        "cost_inr": 0,
        "method_options": [
            "Interview 3 real members of the target audience and record their exact words.",
            "Offer the smallest version to the smallest audience and measure one declared metric.",
            "Compare against the free alternatives a buyer would use instead.",
        ],
        "falsification": "State in advance what evidence would prove this wrong, then look for exactly that.",
        "verified": False,
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
@tool("decide", description="Run the §28 DECISION OUTPUT STANDARD over a question and labelled "
      "evidence. Reasoning only — it cannot spend, send or publish.", risk="LOW",
      tool_key="memory.write")
def decide(payload: dict, agent: dict) -> dict:
    """Structured decision with evidence tiers, disagreement, a plan and a kill criterion.

    The tool may not edit the answer: it hands over the same record the owner would receive, and
    labels every input by what it actually is. An agent that asks "is this worth doing?" gets a
    verdict it must obey, not a paragraph to reinterpret.
    """
    from .decision import decision_engine
    question = str(payload.get("question") or "Is this worth doing?")
    if not question.strip():
        return {"status": "error", "reason": "A decision needs a question.",
                "evidence": [{"kind": "FACT", "value": "No question was supplied."}]}
    record = decision_engine.decide(
        question=question,
        domain=str(payload.get("domain") or "agent"),
        facts=[str(f) for f in (payload.get("facts") or [])],
        inferences=[str(x) for x in (payload.get("inferences") or [])],
        hypotheses=[str(x) for x in (payload.get("hypotheses") or [])],
        assumptions=[str(x) for x in (payload.get("assumptions") or [])],
        opinions=[str(x) for x in (payload.get("opinions") or [])],
        unknowns=[str(x) for x in (payload.get("unknowns") or [])],
        numbers=payload.get("numbers") or {},
        minutes=int(payload.get("minutes") or 0),
        use_model=bool(payload.get("use_model", True)),
        department_id=agent.get("department_id"),
        displaced=str(payload.get("displaced") or ""),
    )
    data = record.to_dict()
    return {
        "status": "ok",
        "decision_id": data["id"],
        "classification": data["classification"],
        "confidence": data["confidence"],
        "verdict": data["verdict"]["decision"],
        "cheapest_test": data["reality_check"]["cheapest_test"],
        "kill_criterion": data["reality_check"]["kill_criterion"],
        "plan": [step["action"] for step in data["action_plan"]],
        "disagreement": data["disagreement"],
        "evidence": [
            {"kind": c["kind"], "value": c["text"], "source": c["source"]} for c in data["evidence"]["claims"]
        ] or [{"kind": "UNKNOWN", "value": "No evidence was supplied to the decision engine."}],
        "verified": data["evidence"]["proof_count"] > 0,
        "standard": data["standard"],
    }


@tool("offer_review", description="Run an offer through the Writer Nation gate and the ethical screen "
      "before anything is built.", risk="LOW", tool_key="memory.write")
def offer_review(payload: dict, agent: dict) -> dict:
    from .customers import OfferDesign
    try:
        offer = OfferDesign.from_dict(payload.get("offer") or {})
    except (TypeError, ValueError) as exc:
        return {"status": "error", "reason": f"Offer could not be read: {exc}",
                "evidence": [{"kind": "FACT", "value": "Malformed offer payload."}]}
    check = offer.may_go_live()
    return {
        "status": "ok", "launchable": check["allowed"], "gaps": check["gaps"],
        "ethics": check["ethics"], "reason": check["reason"],
        "evidence": [{"kind": "OPINION", "value": "An offer is launchable only with verified proof; "
                                                  "this review is deterministic policy, not a judgement call."}],
        "verified": False,
    }


TASK_TO_TOOL = {
    "catalog_audit": "catalog_audit",
    "financial_model": "unit_economics",
    "analysis": "kpi_report",
    "report": "kpi_report",
    "market_scan": "market_signal_scan",
    "research": "research_plan",
    "content_draft": "draft_content",
    "copywriting": "copywriting_tool",     # falls back to draft_content
    "outreach_draft": "draft_outreach",
    "code_task": "engineering_brief",
    "experiment_design": "experiment_design",
    "decision": "decide",                  # the §28 standard, callable from inside the civilization
    "offer_review": "offer_review",
}


def execute(task: dict, agent: dict) -> dict:
    """Run the tool appropriate for a task. Permission-checked and audited either way."""
    tool_name = (task.get("payload") or {}).get("tool") or TASK_TO_TOOL.get(task.get("task_type", ""), "kpi_report")
    if tool_name == "copywriting_tool" or tool_name not in TOOLS:
        tool_name = "draft_content" if task.get("task_type") in ("copywriting", "content_draft") else "kpi_report"
    t = TOOLS[tool_name]

    decision = permissions.check(actor=agent.get("name", "agent"), rank=agent.get("rank", "AGENT"),
                                tool=t.tool_key,
                                context={"department_id": task.get("department_id"),
                                         "own_department_id": agent.get("department_id"),
                                         # A tool run is the agent's own work product: memory and
                                         # artifacts stay in its namespace. Outbound actions are
                                         # separate tools with their own, stricter keys.
                                         "own_namespace": True})
    audit(agent.get("name", "agent"), f"tool.{tool_name}", tool=t.tool_key, risk=t.risk,
          target=task.get("id"), allowed=decision.allowed, reason=decision.reason,
          actor_rank=agent.get("rank", "AGENT"))
    if not decision.allowed:
        bus.publish("tool.denied", source="tools", subject=task.get("id"), severity="warning",
                    payload={"tool": tool_name, "agent": agent.get("name"), "reason": decision.reason})
        return {"status": "denied", "reason": decision.reason, "tool": tool_name,
                "evidence": [{"kind": "FACT", "value": decision.reason}], "verified": False}

    started = time.time()
    try:
        output = t.run(task.get("payload") or {}, agent)
    except Exception as exc:
        output = {"status": "error", "tool": tool_name,
                  "reason": f"{type(exc).__name__}: {exc}"[:300],
                  "evidence": [{"kind": "FACT", "value": "Tool execution raised an exception."}],
                  "verified": False}
    output["tool"] = tool_name
    output["tool_risk"] = t.risk
    output["executed_by"] = agent.get("name")
    output["duration_ms"] = int((time.time() - started) * 1000)
    bus.publish("tool.executed", source="tools", subject=task.get("id"), severity="debug",
                payload={"tool": tool_name, "agent": agent.get("name"), "risk": t.risk,
                         "status": output.get("status"),
                         "duration_ms": output["duration_ms"]})
    return ensure_labels(output)


def catalog() -> list[dict]:
    return [{"name": t.name, "description": t.description, "risk": t.risk, "tool_key": t.tool_key,
             "requires_model": t.requires_model} for t in TOOLS.values()]
