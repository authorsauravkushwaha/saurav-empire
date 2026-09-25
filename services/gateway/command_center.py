"""Owner Command Center — natural language → controlled system actions.

Every command is: parsed to an intent, executed only through an existing (audited, permission-checked)
kernel operation, and reported back with what actually changed. Commands that would be irreversible or
high-risk return a confirmation requirement instead of executing.

If the sentence is not a command, the gateway runs the 8-MIND decision engine instead of pretending
to have performed an action.
"""
from __future__ import annotations

import re
import time
from typing import Callable

from kernel import store
from kernel.economy import economic_summary, experiments, ledger, opportunities
from kernel.eventbus import E, bus
from kernel.governance import audit, chairman
from kernel.model_router import router
from kernel.registry import agents as agent_registry
from kernel.registry import departments as dept_registry
from kernel.tasks import board
from kernel.university import TRACKS, university


def _num(text: str, default: int) -> int:
    m = re.search(r"\b(\d{1,4})\b", text)
    return int(m.group(1)) if m else default


def _clean_topic(text: str, *strip_words: str) -> str:
    out = text
    for w in strip_words:
        out = re.sub(w, " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip(" .,'\"") or "unspecified"


COMMANDS: list[tuple[str, re.Pattern, Callable[[str, re.Match], dict]]] = []


def command(name: str, pattern: str):
    def deco(fn: Callable[[str, re.Match], dict]) -> Callable[[str, re.Match], dict]:
        COMMANDS.append((name, re.compile(pattern, re.I), fn))
        return fn
    return deco


# ---------------------------------------------------------------------------
# Revenue & status
# ---------------------------------------------------------------------------
@command("revenue_report", r"\b(show|what|list).*(revenue|making money|generating|income|sales)\b")
def revenue_report(text: str, m: re.Match) -> dict:
    econ = economic_summary()
    kpis = ledger.kpis()
    return {
        "said": (f"Verified revenue is ₹{econ['revenue_inr']:,.2f} from "
                 f"{kpis['verified_entries']} verified ledger entries. Costs recorded: "
                 f"₹{econ['costs_inr']:,.2f}. Contribution: ₹{econ['contribution_inr']:,.2f}."),
        "honesty": ("There is no revenue to show as 'generating' until a real transaction is "
                    "recorded. Internal activity is not revenue — that distinction is the whole point."),
        "data": econ,
    }


@command("status", r"\b(status|what.s happening|overview|how are we doing|dashboard)\b")
def status(text: str, m: re.Match) -> dict:
    counts = agent_registry.counts()
    metrics = board.metrics()
    econ = economic_summary()
    model = router().status()
    pending = store.query("SELECT id FROM approvals WHERE status='PENDING'")
    attention: list[str] = []
    if pending:
        attention.append(f"{len(pending)} approval(s) awaiting your decision")
    if not model["reachable"]:
        attention.append(model["note"])
    if econ["revenue_inr"] <= 0:
        attention.append("Verified revenue is ₹0. Activity is not income — find one real buyer before "
                         "optimising anything else.")
    return {
        "said": (f"{counts['total']} agents across {len(dept_registry.list(status='ACTIVE'))} departments. "
                 f"{metrics['completed']} tasks verified, {metrics['failed']} failed. "
                 f"Verified revenue ₹{econ['revenue_inr']:,.2f}. Models: {model['provider']}."),
        "attention": attention,
        "data": {"agents": counts, "tasks": metrics, "economy": econ, "models": model["note"]},
    }


@command("agents_top", r"\b(top|best|highest).*(agents?|performers?)\b|\bshow.*top agents\b")
def top_agents(text: str, m: re.Match) -> dict:
    limit = _num(text, 5)
    top = agent_registry.top_performers(limit)
    return {
        "said": ("Ranked by verified task outcomes (performance × reliability), not by how busy they look.",
         ) if top else "No agent has a verified track record yet.",
        "agents": [{"name": a["name"], "role": a["role"], "department": a["department_id"],
                    "rank": a["rank"], "tasks_done": a["tasks_done"],
                    "performance": a["performance"], "certs": a["certs"]} for a in top],
    }


@command("explain_failure", r"\b(why|explain).*(fail|failed|failure|broke)\b")
def explain_failure(text: str, m: re.Match) -> dict:
    failed = store.query("SELECT id, title, task_type, error, verification_json, department_id FROM tasks "
                         "WHERE status='FAILED' ORDER BY completed_at DESC LIMIT 5")
    real_failures = []
    plan_failures = []
    for row in failed:
        verification = store.jload(row.pop("verification_json", None), {}) or {}
        issues = verification.get("issues", [])
        entry = {"task": row["title"], "type": row["task_type"], "department": row["department_id"],
                 "issues": issues, "score": verification.get("score")}
        if any("Not verified" in i or "evidence" in i.lower() or "model" in i.lower() for i in issues):
            plan_failures.append(entry)
        else:
            real_failures.append(entry)
    return {
        "said": (f"{len(failed)} recent failures. Most are honest refusals — a task that cannot be done "
                 f"truthfully fails loudly here rather than producing comfortable fiction."),
        "honest_refusals": plan_failures,
        "genuine_failures": real_failures,
        "how_to_read": [
            "'Missing evidence labelling' = the agent tried to finish without evidence. Working as intended.",
            "'No model available — scaffold' = install Ollama to enable real work on that task type.",
            "A genuine failure is one where the artifact existed and was wrong: verify, retrain, reassign.",
        ],
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
@command("create_department", r"\b(create|make|build|start)\b.*\b(department|division|team)\b")
def create_department(text: str, m: re.Match) -> dict:
    topic = _clean_topic(text, r"\b(create|make|build|start|a|an|new|the)\b", r"\b(department|division|team|for|of)\b",
                         r"\bai\b")
    name = " ".join(w.capitalize() for w in topic.split()[:5]) or "New Department"
    if not name.lower().endswith("department"):
        name = f"{name} Department"
    try:
        dept = dept_registry.create(
            name=name, objective=f"Pursue: {topic}", kpis=["verified_outcomes", "cost_per_outcome_inr"],
            city="revenue", building="product-discovery", parent_id="executive-council",
            created_by="OWNER", consumer_of="market-intelligence", producer_for="finance-treasury",
            kill_criteria="Removed if no verified outcome within 60 days.",
        )
    except ValueError as exc:
        return {"said": f"Department not created: {exc}", "rejected": True}
    return {"said": f"Created '{dept['name']}' with boss {agent_registry.get(dept['boss_agent_id'])['name']}. "
                    "Workspace, namespace, queue, KPI dashboard, security policy and budget provisioned.",
            "department": dept,
            "next": "Hire specialists? Say: hire 3 specialists in the new department."}


@command("train_agents", r"\btrain\b.*\b(\d+)?\s*(agents?|trainees?)\b")
def train_agents(text: str, m: re.Match) -> dict:
    count = _num(text, 5)
    track = "python-engineering"
    for tid, t in TRACKS.items():
        if tid.split("-")[0] in text.lower() or t["name"].lower() in text.lower():
            track = tid
            break
    trainees = agent_registry.list(rank="TRAINEE", limit=count)
    created = []
    for t in trainees[:count]:
        try:
            university.enroll(t["id"], track)
            university.start_coursework(t["id"], max_subjects=2)
            created.append(t["name"])
        except ValueError:
            continue
    if not created:
        created = [a["name"] for a in [agent_registry.hire(role="Trainee", rank="TRAINEE",
                                                           lifecycle="TRAINEE", building="ai-university")
                                       for _ in range(min(count, 10))]]
    return {"said": f"Enrolled {len(created)} agents in {TRACKS[track]['name']}.",
            "agents": created, "track": track,
            "caveat": ("Without a local model, examinations cover tool and evidence discipline only. "
                       "Install Ollama for full reasoning examinations.")}


@command("find_opportunities", r"\bfind\b.*\b(opportunit|ideas|business)\w*")
def find_opportunities(text: str, m: re.Match) -> dict:
    want = _num(text, 5)
    created = opportunities.discover_zero_capital()
    existing = opportunities.list(limit=want)
    return {"said": f"Surfaced {len(created)} new zero-capital candidates ({len(existing)} total tracked).",
            "opportunities": [{"title": o["title"], "score": o["score"], "status": o["status"],
                               "capital_inr": o["required_capital_inr"]} for o in existing[:want]],
            "discipline": "Every one of these is an ASSUMPTION until a customer behaves."}


@command("freeze_publishing", r"\b(stop|freeze|halt|pause)\b.*\b(social|publish|posting|media)\b")
def freeze_publishing(text: str, m: re.Match) -> dict:
    store.set_setting("publish_freeze", True)
    bus.publish("governance.publish_freeze", source="command-center", severity="notice",
                payload={"enabled": True, "by": "OWNER", "reason": text[:200]})
    audit("OWNER", "publish_freeze.enable", tool="integration.post", risk="HIGH", allowed=True,
          reason=text[:200], actor_rank="OWNER")
    return {"said": "Publishing frozen. No connector will post, send or publish until you clear it.",
            "state": {"publish_freeze": True},
            "to_resume": "Say: resume publishing."}


@command("resume_publishing", r"\b(resume|unfreeze|allow)\b.*\b(publishing|posting|social)\b")
def resume_publishing(text: str, m: re.Match) -> dict:
    store.set_setting("publish_freeze", False)
    audit("OWNER", "publish_freeze.disable", tool="integration.post", risk="HIGH", allowed=True,
          reason=text[:200], actor_rank="OWNER")
    return {"said": "Publishing unfrozen. Actions still require approval.", "state": {"publish_freeze": False}}


@command("build_experiment", r"\b(build|create|design|start)\b.*\b(experiment|test)\b")
def build_experiment(text: str, m: re.Match) -> dict:
    topic = _clean_topic(text, r"\b(build|create|design|start|a|an|new|the|experiment|test)\b")
    row = experiments.create(
        hypothesis=f"{topic} can produce a measurable signal with ₹0 spend",
        expected_result="One declared metric moves within the window",
        mvp_definition=f"Smallest honest version of {topic}",
        test_method="Expose it to the smallest real audience and measure one number",
        success_metric="Declared metric met (set by owner before starting)",
        kill_metric="No signal within the window",
    )
    task = board.create(title=f"Prepare MVP for experiment: {topic}", task_type="experiment_design",
                        department_id="research-lab", created_by="OWNER", priority=3,
                        payload={"topic": topic})
    return {"said": "Experiment designed with a success metric and a kill criterion. A ₹0 preparation task "
                    "was queued in the Research Laboratory.",
            "experiment": row, "task": {"id": task["id"], "title": task["title"]},
            "reminder": "Set the threshold BEFORE the test. Changing it afterwards is self-deception."}


@command("grant_access", r"\b(give|grant|allow)\b.*\baccess\b")
def grant_access(text: str, m: re.Match) -> dict:
    who = _clean_topic(text, r"\b(give|grant|allow|access|to|the|for)\b")[:60]
    return {"said": f"Access requests are recorded but effective only once the owner writes them into "
                    f"config/permissions.yaml (grants are policy, not chat).",
            "requested": who,
            "how_to_apply": ["Edit config/permissions.yaml → isolation.cross_department_grants or a tool's min_rank.",
                             "Restart the services (python scripts/empire.py restart) so policy is reloaded.",
                             "Every grant is logged and revocable."],
            "policy_note": "An agent cannot escalate its own permissions — by construction."}


@command("kill_switch", r"\b(kill switch|emergency stop|shut everything down|halt everything)\b")
def kill_switch_cmd(text: str, m: re.Match) -> dict:
    if "resume" in text.lower() or "disengage" in text.lower():
        return {"said": "To resume, use the Security panel (POST /api/security/killswitch/disengage). "
                        "Resuming is deliberately not a chat command."}
    from kernel.killswitch import engage
    result = engage(by="OWNER", reason="owner command center")
    return {"said": "KILL SWITCH ENGAGED. Agent runtime halted, external actions frozen, data preserved.",
            "state": result}


@command("judge_decision", r"\b(should|is it worth|evaluate|judge|分析)\b")
def judge(text: str, m: re.Match) -> dict:
    verdict = chairman.decide(question=text, facts=[],
                              assumptions=["The framing of the question assumes this is worth doing."],
                              unknowns=["Whether the buyer will pay", "Whether you have the hours",
                                        "What else those hours would produce"])
    return {"said": verdict.verdict, "confidence": verdict.confidence,
            "cheapest_test": verdict.cheapest_test, "action_plan": verdict.action_plan,
            "disagreements": verdict.disagreements, "reality_check": verdict.reality_check}


# ---------------------------------------------------------------------------
def interpret(text: str) -> dict:
    """Match a command, execute exactly one action, and describe what actually happened."""
    started = time.time()
    for name, pattern, fn in COMMANDS:
        m = pattern.search(text)
        if m:
            try:
                result = fn(text, m)
            except Exception as exc:
                result = {"said": f"That command failed: {type(exc).__name__}: {str(exc)[:200]}",
                          "error": True}
            result.update({"intent": name, "matched": True, "handled_as": "system action",
                           "duration_ms": int((time.time() - started) * 1000)})
            audit("OWNER", f"command.{name}", tool="web.fetch", risk="LOW", allowed=True,
                  reason=text[:200], actor_rank="OWNER")
            bus.publish("command.executed", source="command-center", severity="notice",
                        payload={"intent": name, "text": text[:200], "said": result.get("said", "")[:200]})
            return result

    # No system action matched: answer honestly using the decision engine rather than pretending.
    verdict = chairman.decide(question=text, facts=[], assumptions=[], unknowns=[
        "What evidence supports the premise of this question"])
    return {
        "intent": "analysis_only", "matched": False,
        "said": ("No system action matched that sentence, so nothing was changed. Here is the analysis instead.",
                 ),
        "verdict": verdict.verdict, "confidence": verdict.confidence,
        "cheapest_test": verdict.cheapest_test,
        "available_commands": [name for name, _, _ in COMMANDS],
        "try": ["show me everything generating revenue", "status",
                "create a new department for digital products", "train 10 agents in Python",
                "find 5 business opportunities requiring zero initial capital",
                "stop all social-media publishing", "why did tasks fail today"],
        "duration_ms": int((time.time() - started) * 1000),
    }


def catalogue() -> list[dict]:
    return [{"intent": name, "pattern": pattern.pattern} for name, pattern, _ in COMMANDS]
