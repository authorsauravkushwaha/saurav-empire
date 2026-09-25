"""Agent Registry + Department Factory.

Two registries, one rule: nothing exists without a purpose, a KPI, and an owner.

* `Agents`      — identity, hierarchy, lifecycle, status, location, metrics.
* `Departments` — dynamic creation of departments / subdepartments / projects / teams / squads.
                  There is NO hard-coded maximum. A new department automatically receives a
                  workspace, DB namespace, analytics namespace, task queue, memory namespace,
                  comms channel, KPI dashboard, security policy, budget, boss and employees.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Iterable

from . import store, world_layout
from .config import building_index, city_index, config, department_seeds
from .eventbus import E, bus
from .governance import audit
from .naming import NameRegistry

STATUSES = ["IDLE", "LEARNING", "TRAVELING", "WORKING", "WAITING", "NEGOTIATING", "ANALYZING",
            "CODING", "RESEARCHING", "PUBLISHING", "SELLING", "ERROR", "BLOCKED", "ESCALATED",
            "COMPLETED"]

RANKS = ["OWNER", "SUPREME", "COMMANDER", "MANAGER", "AGENT", "TRAINEE"]

# Workforce plan used at bootstrap: department -> (specialists, trainees, specialist roles)
WORKFORCE_PLAN: dict[str, tuple[int, int, list[str]]] = {
    "executive-council":     (2, 0, ["Decision Analyst", "Evidence Auditor"]),
    "security-governance":   (3, 1, ["Red Team Operator", "Audit Officer", "Secret Custodian"]),
    "market-intelligence":   (4, 3, ["Demand Researcher", "Competitor Analyst", "Pricing Scout", "Source Auditor"]),
    "engineering":           (5, 3, ["Backend Engineer", "Agent Runtime Engineer", "Data Engineer", "QA Engineer", "DevOps Operator"]),
    "product-development":   (3, 2, ["Product Analyst", "MVP Builder", "Spec Writer"]),
    "growth-distribution":   (4, 2, ["Content Strategist", "Channel Analyst", "SEO Operator", "Community Operator"]),
    "sales-partnerships":    (3, 2, ["Lead Qualifier", "Outreach Drafter", "Deal Analyst"]),
    "finance-treasury":      (3, 1, ["Bookkeeper", "Unit Economics Analyst", "Forecast Modeler"]),
    "data-analytics":        (3, 2, ["Metrics Engineer", "Event Modeler", "Dashboard Operator"]),
    "content-creative":      (4, 3, ["Long-form Writer", "Copywriter", "Cover Designer", "Story Architect"]),
    "publishing-operations": (4, 3, ["Metadata Specialist", "Catalog Analyst", "Series Strategist", "Reader Researcher"]),
    "customer-success":      (3, 2, ["Onboarding Operator", "Support Analyst", "Outcome Tracker"]),
    "integration-automation": (3, 2, ["Connector Engineer", "Automation Designer", "Quota Monitor"]),
    "research-lab":          (3, 3, ["Experiment Designer", "Falsification Officer", "Methodology Reviewer"]),
    "university":            (4, 4, ["Curriculum Engineer", "Examiner", "Career Matcher", "Skills Assessor"]),
}

DEPT_SKILLS: dict[str, dict[str, float]] = {
    "engineering": {"python": 0.7, "testing": 0.6, "systems": 0.5},
    "data-analytics": {"sql": 0.7, "metrics": 0.6, "event_modeling": 0.5},
    "market-intelligence": {"source_quality": 0.7, "falsification": 0.6, "positioning": 0.4},
    "growth-distribution": {"copy": 0.6, "audience": 0.6, "ethics": 0.7},
    "sales-partnerships": {"qualification": 0.6, "objections": 0.6, "negotiation": 0.5},
    "finance-treasury": {"unit_economics": 0.7, "scenarios": 0.6, "cash": 0.6},
    "publishing-operations": {"metadata": 0.7, "discoverability": 0.6, "catalog_economics": 0.5},
    "content-creative": {"writing": 0.7, "editing": 0.6, "brand": 0.5},
    "customer-success": {"empathy": 0.7, "retention": 0.6, "outcomes": 0.5},
    "integration-automation": {"apis": 0.7, "automation": 0.6, "oauth": 0.5},
    "research-lab": {"experiment_design": 0.7, "statistics": 0.5, "sourcing": 0.6},
    "university": {"curriculum": 0.7, "examination": 0.7, "assessment": 0.6},
    "security-governance": {"least_privilege": 0.8, "injection_defence": 0.7, "audit": 0.7},
    "executive-council": {"judgement": 0.7, "strategy": 0.6, "synthesis": 0.7},
    "product-development": {"specification": 0.6, "mvp": 0.6, "user_research": 0.5},
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")[:48] or "unnamed"


class Departments:
    """Department Factory — unlimited departments, each fully provisioned."""

    def create(self, *, name: str, objective: str, kpis: list[str], city: str, building: str,
               parent_id: str | None = None, kind: str = "department", boss_name: str | None = None,
               budget_inr: float = 0.0, permissions: list[str] | None = None,
               tools: list[str] | None = None, consumer_of: str | None = None,
               producer_for: str | None = None, kill_criteria: str | None = None,
               created_by: str = "OWNER", meta: dict | None = None,
               requested_id: str | None = None) -> dict:
        required = config().get("departments.required_declaration", []) or []
        declaration = {"objective": objective, "kpis": kpis, "consumer_of": consumer_of,
                       "producer_for": producer_for, "kill_criteria": kill_criteria}
        missing = [r for r in required if not declaration.get(r)]
        if kind == "department" and missing:
            raise ValueError(
                "Department rejected: a department must declare " + ", ".join(missing) +
                ". Decorative org-building is not permitted."
            )
        if not objective or not kpis:
            raise ValueError("Every unit must declare an objective and at least one measurable KPI.")
        if city not in city_index():
            raise ValueError(f"Unknown city '{city}'.")
        if building not in building_index():
            raise ValueError(f"Unknown building '{building}'.")
        existing = store.query_one("SELECT id FROM departments WHERE lower(name)=lower(?)", (name,))
        if existing:
            raise ValueError(f"Department '{name}' already exists ({existing['id']}).")

        dept_id = slugify(requested_id or name)
        suffix = 2
        while store.get("departments", dept_id):
            dept_id = f"{slugify(requested_id or name)}-{suffix}"
            suffix += 1

        row = {
            "id": dept_id, "name": name, "parent_id": parent_id, "kind": kind, "city": city,
            "building": building, "objective": objective, "kpis_json": json.dumps(kpis),
            "budget_inr": float(budget_inr), "spend_inr": 0.0, "status": "ACTIVE",
            "namespace": f"ns.{dept_id}", "channel": f"#{dept_id}",
            "security_policy": f"least_privilege:{dept_id}",
            "created_by": created_by, "created_at": store.now(),
            "meta_json": json.dumps({"permissions": permissions or [], "tools": tools or [],
                                     "consumer_of": consumer_of, "producer_for": producer_for,
                                     "kill_criteria": kill_criteria, **(meta or {})}, default=str),
        }
        store.insert("departments", row)
        bus.publish(E.DEPT_CREATED, source="registry", subject=dept_id,
                    payload={"name": name, "city": city, "building": building, "kind": kind,
                             "objective": objective, "kpis": kpis})
        audit(created_by, "department.create", tool="department.create", risk="MEDIUM",
              target=dept_id, actor_rank="OWNER" if created_by == "OWNER" else "SUPREME")

        boss = agents.hire(
            role=f"{name} Boss", rank="COMMANDER" if kind == "department" else "MANAGER",
            department_id=dept_id, name=boss_name, model_tier="reasoning",
            skills=DEPT_SKILLS.get(dept_id, {"management": 0.6}),
            permissions=(permissions or []) + ["task.assign", "agent.hire", "memory.write"],
            building=building, meta={"is_boss": True},
        )
        store.update("departments", dept_id, {"boss_agent_id": boss["id"]})
        return self.get(dept_id)  # type: ignore[return-value]

    def hire_workforce(self, dept_id: str, specialists: int, trainees: int,
                       roles: list[str] | None = None) -> dict:
        dept = self.get(dept_id)
        if not dept:
            raise ValueError(f"Unknown department {dept_id}")
        roles = roles or ["Operator"]
        devs = []
        for i in range(specialists):
            devs.append(agents.hire(
                role=roles[i % len(roles)], rank="AGENT", department_id=dept_id,
                manager_id=dept.get("boss_agent_id"), model_tier="small",
                skills=DEPT_SKILLS.get(dept_id, {"execution": 0.5}),
                building=dept["building"],
            ))
        learners = []
        for _ in range(trainees):
            learner = agents.hire(role="Trainee", rank="TRAINEE", department_id=dept_id,
                                  manager_id=dept.get("boss_agent_id"), model_tier="nano",
                                  skills={}, building="ai-university", lifecycle="TRAINEE")
            learners.append(learner)
        return {"specialists": devs, "trainees": learners}

    def get(self, dept_id: str) -> dict | None:
        row = store.get("departments", dept_id)
        if not row:
            return None
        row["kpis"] = store.jload(row.pop("kpis_json", None), [])
        row["meta"] = store.jload(row.pop("meta_json", None), {})
        row["headcount"] = store.query_one(
            "SELECT COUNT(*) n FROM agents WHERE department_id=? AND lifecycle != 'TERMINATED'",
            (dept_id,))["n"]
        return row

    def list(self, *, status: str | None = None, parent_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM departments"
        clauses, params = [], []
        if status:
            clauses.append("status=?"); params.append(status)
        if parent_id is not None:
            clauses.append("parent_id IS ?" if parent_id is None else "parent_id=?"); params.append(parent_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC"
        out = []
        for row in store.query(sql, tuple(params)):
            row["kpis"] = store.jload(row.pop("kpis_json", None), [])
            row["meta"] = store.jload(row.pop("meta_json", None), {})
            row["headcount"] = store.query_one(
                "SELECT COUNT(*) n FROM agents WHERE department_id=? AND lifecycle != 'TERMINATED'",
                (row["id"],))["n"]
            out.append(row)
        return out

    def tree(self) -> list[dict]:
        nodes = {d["id"]: {**d, "children": []} for d in self.list()}
        roots = []
        for node in nodes.values():
            parent = nodes.get(node.get("parent_id") or "")
            (parent["children"] if parent else roots).append(node)
        return roots

    def dissolve(self, dept_id: str, reason: str, by: str = "OWNER") -> dict:
        dept = self.get(dept_id)
        if not dept:
            raise ValueError("Unknown department")
        store.update("departments", dept_id, {"status": "DISSOLVED",
                                              "meta_json": json.dumps({**dept["meta"], "dissolved_reason": reason,
                                                                       "dissolved_at": store.now()}, default=str)})
        moves = store.query("SELECT id FROM agents WHERE department_id=? AND lifecycle != 'TERMINATED'", (dept_id,))
        for m in moves:
            agents.transfer(m["id"], None, reason=f"Department dissolved: {reason}")
        bus.publish(E.DEPT_DISSOLVED, source="registry", subject=dept_id, severity="notice",
                    payload={"reason": reason, "reassigned_agents": len(moves)})
        audit(by, "department.dissolve", tool="department.dissolve", risk="HIGH", target=dept_id,
              reason=reason, actor_rank="OWNER")
        return dept


class Agents:
    """Agent Registry — identity, hierarchy, status, location, performance."""

    def hire(self, *, role: str, rank: str = "AGENT", department_id: str | None = None,
             name: str | None = None, manager_id: str | None = None, model_tier: str = "nano",
             skills: dict[str, float] | None = None, building: str | None = None,
             lifecycle: str = "EMPLOYED", meta: dict | None = None,
             permissions: list[str] | None = None) -> dict:
        if rank not in RANKS:
            raise ValueError(f"Unknown rank {rank}")
        registry = NameRegistry()
        if name:
            # `next_agent_name` already reserves; an explicit name must be claimed here.
            if not registry.reserve(name):
                raise ValueError(f"Name '{name}' is already taken. The naming subsystem never duplicates.")
            agent_name = name
        elif rank in ("COMMANDER", "SUPREME") or (meta or {}).get("is_boss"):
            # Bosses and commanders draw from the historically-themed pool (de-duplicated).
            agent_name = registry.next_boss_name()
        else:
            agent_name = registry.next_agent_name(department_id)
        dept = departments.get(department_id) if department_id else None
        building = building or (dept["building"] if dept else "owner-command-center")
        pos = world_layout.building_world_pos(building)["pos"]
        row = {
            "id": store.new_id("agt"), "name": agent_name, "role": role, "rank": rank,
            "department_id": department_id, "manager_id": manager_id,
            "model_tier": model_tier, "status": "IDLE", "lifecycle": lifecycle,
            "skills_json": json.dumps(skills or {}), "certs_json": "[]", "scores_json": "{}",
            "permissions_json": json.dumps(permissions or []),
            "energy": 100.0, "performance": 0.5, "reliability": 0.5, "learning_progress": 0.0,
            "building": building, "pos_x": float(pos[0]), "pos_y": float(pos[2]),
            "created_at": store.now(), "updated_at": store.now(),
            "meta_json": json.dumps(meta or {}, default=str),
        }
        store.insert("agents", row)
        bus.publish(E.AGENT_CREATED, source="registry", subject=row["id"],
                    payload={"name": agent_name, "role": role, "rank": rank,
                             "department": department_id, "building": building})
        return self.get(row["id"])  # type: ignore[return-value]

    def get(self, agent_id: str) -> dict | None:
        row = store.get("agents", agent_id)
        if not row:
            return None
        return self._expand(row)

    def by_name(self, name: str) -> dict | None:
        row = store.query_one("SELECT * FROM agents WHERE name=?", (name,))
        return self._expand(row) if row else None

    def list(self, *, department_id: str | None = None, rank: str | None = None,
             status: str | None = None, lifecycle: str | None = None, limit: int = 500,
             building: str | None = None) -> list[dict]:
        clauses, params = [], []
        for col, val in (("department_id", department_id), ("rank", rank), ("status", status),
                         ("lifecycle", lifecycle), ("building", building)):
            if val is not None:
                clauses.append(f"{col}=?"); params.append(val)
        sql = "SELECT * FROM agents" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        sql += " ORDER BY rank ASC, created_at ASC LIMIT ?"
        params.append(limit)
        return [self._expand(r) for r in store.query(sql, tuple(params))]

    def _expand(self, row: dict) -> dict:
        row["skills"] = store.jload(row.pop("skills_json", None), {})
        row["certs"] = store.jload(row.pop("certs_json", None), [])
        row["scores"] = store.jload(row.pop("scores_json", None), {})
        row["permissions"] = store.jload(row.pop("permissions_json", None), [])
        row["meta"] = store.jload(row.pop("meta_json", None), {})
        row["position"] = [row.get("pos_x", 0.0), row.get("pos_y", 0.0)]
        return row

    # ---- lifecycle -----------------------------------------------------
    def set_status(self, agent_id: str, status: str, *, reason: str = "") -> dict:
        if status not in STATUSES:
            raise ValueError(f"Unknown status {status}")
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        store.update("agents", agent_id, {"status": status, "updated_at": store.now()})
        bus.publish(E.AGENT_STATUS, source="registry", subject=agent_id,
                    payload={"name": agent["name"], "from": agent["status"], "to": status, "reason": reason})
        return self.get(agent_id)  # type: ignore[return-value]

    def move_to(self, agent_id: str, building_id: str, *, reason: str = "task") -> dict:
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        store.update("agents", agent_id, {"target_building": building_id, "status": "TRAVELING",
                                          "updated_at": store.now()})
        bus.publish(E.AGENT_MOVED, source="registry", subject=agent_id,
                    payload={"name": agent["name"], "to": building_id, "reason": reason,
                             "from_building": agent.get("building")})
        return agent

    def arrive(self, agent_id: str, building_id: str) -> None:
        store.update("agents", agent_id, {"building": building_id, "target_building": None,
                                          "updated_at": store.now()})

    def update_position(self, agent_id: str, x: float, z: float) -> None:
        store.update("agents", agent_id, {"pos_x": float(x), "pos_y": float(z)})

    def transfer(self, agent_id: str, department_id: str | None, *, reason: str = "") -> dict:
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        store.update("agents", agent_id, {"department_id": department_id, "updated_at": store.now()})
        bus.publish(E.AGENT_ASSIGNED, source="registry", subject=agent_id,
                    payload={"name": agent["name"], "from": agent.get("department_id"),
                             "to": department_id, "reason": reason})
        return self.get(agent_id)  # type: ignore[return-value]

    def promote(self, agent_id: str, to_rank: str, *, reason: str = "", by: str = "OWNER") -> dict:
        if to_rank not in RANKS:
            raise ValueError("Unknown rank")
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        store.update("agents", agent_id, {"rank": to_rank, "updated_at": store.now()})
        bus.publish(E.AGENT_PROMOTED, source="registry", subject=agent_id, severity="notice",
                    payload={"name": agent["name"], "from": agent["rank"], "to": to_rank,
                             "reason": reason, "by": by})
        audit(by, "agent.promote", tool="agent.promote", risk="MEDIUM", target=agent_id,
              reason=reason, actor_rank="OWNER")
        return self.get(agent_id)  # type: ignore[return-value]

    def suspend(self, agent_id: str, reason: str, *, by: str = "OWNER") -> dict:
        store.update("agents", agent_id, {"status": "BLOCKED", "lifecycle": "SUSPENDED",
                                          "updated_at": store.now()})
        bus.publish(E.AGENT_SUSPENDED, source="registry", subject=agent_id, severity="warning",
                    payload={"reason": reason, "by": by})
        return self.get(agent_id)  # type: ignore[return-value]

    def reinstate(self, agent_id: str, *, reason: str = "") -> dict:
        store.update("agents", agent_id, {"status": "IDLE", "lifecycle": "EMPLOYED",
                                          "updated_at": store.now()})
        return self.get(agent_id)  # type: ignore[return-value]

    def terminate(self, agent_id: str, reason: str, *, by: str = "OWNER") -> dict:
        store.update("agents", agent_id, {"lifecycle": "TERMINATED", "status": "IDLE",
                                          "department_id": None, "updated_at": store.now()})
        bus.publish(E.AGENT_TERMINATED, source="registry", subject=agent_id, severity="notice",
                    payload={"reason": reason, "by": by})
        audit(by, "agent.terminate", tool="agent.terminate", risk="MEDIUM", target=agent_id,
              reason=reason)
        return self.get(agent_id)  # type: ignore[return-value]

    def record_result(self, agent_id: str, *, success: bool, quality: float, cost_inr: float = 0.0,
                      value_inr: float = 0.0, energy_cost: float = 3.0) -> dict:
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        done = int(agent.get("tasks_done") or 0) + (1 if success else 0)
        failed = int(agent.get("tasks_failed") or 0) + (0 if success else 1)
        # exponential moving averages keep the score responsive without erasing history
        performance = 0.8 * float(agent.get("performance") or 0.5) + 0.2 * float(quality)
        reliability = 0.85 * float(agent.get("reliability") or 0.5) + 0.15 * (1.0 if success else 0.0)
        energy = max(0.0, float(agent.get("energy") or 100.0) - energy_cost)
        if energy < 15:
            energy = 100.0   # deterministic rest cycle; compute budget is a local resource
        store.update("agents", agent_id, {
            "tasks_done": done, "tasks_failed": failed, "performance": round(performance, 4),
            "reliability": round(reliability, 4), "energy": round(energy, 2),
            "revenue_inr": float(agent.get("revenue_inr") or 0) + float(value_inr),
            "cost_inr": float(agent.get("cost_inr") or 0) + float(cost_inr),
            "learning_progress": round(min(1.0, float(agent.get("learning_progress") or 0) + 0.01), 4),
            "updated_at": store.now(),
        })
        return self.get(agent_id)  # type: ignore[return-value]

    def set_certification(self, agent_id: str, cert: str, scores: dict) -> dict:
        agent = self.get(agent_id)
        if not agent:
            raise ValueError("Unknown agent")
        certs = list({*agent.get("certs", []), cert})
        store.update("agents", agent_id, {"certs_json": json.dumps(certs),
                                          "scores_json": json.dumps({**agent.get("scores", {}), **scores}),
                                          "lifecycle": "GRADUATE", "updated_at": store.now()})
        return self.get(agent_id)  # type: ignore[return-value]

    # ---- reporting -----------------------------------------------------
    def org_chart(self) -> dict:
        all_agents = self.list(limit=2000)
        by_id = {a["id"]: {**a, "reports": []} for a in all_agents}
        roots = []
        for node in by_id.values():
            mgr = by_id.get(node.get("manager_id") or "")
            if mgr:
                mgr["reports"].append(node)
            else:
                roots.append(node)
        return {"roots": roots, "total": len(all_agents)}

    def top_performers(self, limit: int = 10) -> list[dict]:
        rows = store.query(
            "SELECT * FROM agents WHERE lifecycle != 'TERMINATED' AND tasks_done > 0 "
            "ORDER BY (performance * 0.6 + reliability * 0.4) DESC, tasks_done DESC LIMIT ?", (limit,))
        return [self._expand(r) for r in rows]

    def counts(self) -> dict:
        total = store.query_one("SELECT COUNT(*) n FROM agents WHERE lifecycle != 'TERMINATED'")["n"]
        by_status = {r["status"]: r["n"] for r in store.query(
            "SELECT status, COUNT(*) n FROM agents WHERE lifecycle != 'TERMINATED' GROUP BY status")}
        by_rank = {r["rank"]: r["n"] for r in store.query(
            "SELECT rank, COUNT(*) n FROM agents WHERE lifecycle != 'TERMINATED' GROUP BY rank")}
        return {"total": total, "by_status": by_status, "by_rank": by_rank}


# ---------------------------------------------------------------------------
# Bootstrap — the initial organization, seeded from config
# ---------------------------------------------------------------------------
def bootstrap_organization(*, force: bool = False, city_commanders: bool = True) -> dict:
    """Create the starting civilization: supreme, commanders, departments, workforce, trainees.

    Idempotent: running it twice does not duplicate anything.
    """
    created = {"departments": 0, "agents": 0, "skipped": []}
    if force:
        for row in store.query("SELECT id FROM agents"):
            store.update("agents", row["id"], {"lifecycle": "TERMINATED"})

    if not agents.by_name("SUPREME"):
        agents.hire(role="Supreme Operating System", rank="SUPREME", name="SUPREME",
                    department_id=None, model_tier="reasoning",
                    skills={"orchestration": 0.9, "judgement": 0.85, "synthesis": 0.8},
                    building="owner-command-center",
                    permissions=["orchestrate", "create_department", "assign_task", "suspend_agent",
                                 "task.assign", "memory.write", "agent.hire"],
                    meta={"is_supreme": True})
        created["agents"] += 1

    if city_commanders:
        for city in config().get("civilization.cities", []) or []:
            title = f"{city['name']} Commander"
            if store.query_one("SELECT id FROM agents WHERE role=? AND lifecycle != 'TERMINATED'", (title,)):
                continue
            agents.hire(role=title, rank="COMMANDER", name=None, department_id=None,
                        model_tier="reasoning",
                        skills={"coordination": 0.7, "triage": 0.65},
                        building=(city.get("buildings") or [{"id": "owner-command-center"}])[0]["id"],
                        permissions=["coordinate_departments", "assign_task", "task.assign"],
                        meta={"city": city["id"], "is_city_commander": True})
            created["agents"] += 1

    for seed in department_seeds():
        dept_id = seed["id"]
        if store.get("departments", dept_id):
            created["skipped"].append(dept_id)
            continue
        dept = departments.create(
            name=seed["name"], objective=seed["objective"], kpis=seed["kpis"],
            city=seed["city"], building=seed["building"], parent_id=seed.get("parent"),
            boss_name=seed.get("boss"), created_by="BOOTSTRAP", requested_id=seed["id"],
            consumer_of="internal", producer_for="internal",
            kill_criteria=f"Removed if {seed['kpis'][0]} shows no improvement over 60 days.",
            meta={"seeded": True},
        )
        created["departments"] += 1
        specialists, trainees, roles = WORKFORCE_PLAN.get(dept_id, (2, 1, ["Operator"]))
        workforce = departments.hire_workforce(dept_id, specialists, trainees, roles)
        created["agents"] += len(workforce["specialists"]) + len(workforce["trainees"])
        created["skipped"] = created["skipped"] if isinstance(created["skipped"], list) else []
        # keep name-lookup stable: record the seeded boss name in settings for reporting
        if dept and dept.get("boss_agent_id"):
            boss = agents.get(dept["boss_agent_id"])
            if boss:
                store.set_setting(f"boss::{dept_id}", boss["name"])
    bus.publish(E.BOOT, source="registry", payload={"created": created})
    return created


# Singletons
agents = Agents()
departments = Departments()
