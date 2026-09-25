"""Task system — queues, assignment, verification.

Every task carries its department, priority, payload and result. Critical results are verified
before they are accepted (never blindly trust agent output). Verification is deterministic by
default and uses a second model pass when a model is available.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import store
from .config import config
from .eventbus import E, bus
from .governance import claims as claims_validator
from .governance import audit, permissions

# Fields that could be published verbatim. Screening these — and only these — keeps the
# ethics gate aimed at the words a customer could actually read.
CUSTOMER_FACING_FIELDS = ("draft", "body", "copy", "text", "message", "email_body", "caption",
                          "post", "script", "subject", "headline", "cta")


def _customer_text(result: dict) -> str:
    parts = []
    for field in CUSTOMER_FACING_FIELDS:
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value)
        elif isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False, default=str))
    if parts:
        return "\n".join(parts)
    # No publishable field was produced — screen whatever the tool returned.
    return json.dumps(result, ensure_ascii=False, default=str)


TASK_TYPES = [
    "research", "market_scan", "content_draft", "copywriting", "analysis",
    "financial_model", "code_task", "verification", "outreach_draft", "catalog_audit",
    "experiment_design", "exam", "coursework", "report", "general",
]

STATUSES = ["QUEUED", "ASSIGNED", "IN_PROGRESS", "BLOCKED", "VERIFYING", "DONE", "FAILED", "CANCELLED"]


class TaskBoard:
    # ---- creation ------------------------------------------------------
    def create(self, *, title: str, description: str = "", task_type: str = "general",
               department_id: str | None = None, created_by: str = "system",
               priority: int = 5, payload: dict | None = None, assignee_id: str | None = None,
               sla_hours: float | None = None) -> dict:
        if task_type not in TASK_TYPES:
            task_type = "general"
        row = {
            "id": store.new_id("tsk"), "title": title, "description": description,
            "task_type": task_type, "department_id": department_id, "assignee_id": assignee_id,
            "created_by": created_by, "status": "QUEUED" if not assignee_id else "ASSIGNED",
            "priority": int(priority), "payload_json": json.dumps(payload or {}, default=str),
            "sla_hours": sla_hours, "created_at": store.now(),
        }
        store.insert("tasks", row)
        bus.publish(E.TASK_CREATED, source="tasks", subject=row["id"],
                    payload={"title": title, "type": task_type, "department": department_id,
                             "priority": priority})
        if assignee_id:
            bus.publish(E.TASK_ASSIGNED, source="tasks", subject=row["id"],
                        payload={"assignee": assignee_id, "title": title})
        return self.get(row["id"])  # type: ignore[return-value]

    def get(self, task_id: str) -> dict | None:
        row = store.get("tasks", task_id)
        return self._expand(row) if row else None

    def _expand(self, row: dict) -> dict:
        row["payload"] = store.jload(row.pop("payload_json", None), {})
        row["result"] = store.jload(row.pop("result_json", None), {})
        row["verification"] = store.jload(row.pop("verification_json", None), {})
        return row

    def list(self, *, status: str | None = None, department_id: str | None = None,
             assignee_id: str | None = None, limit: int = 200) -> list[dict]:
        clauses, params = [], []
        for col, val in (("status", status), ("department_id", department_id), ("assignee_id", assignee_id)):
            if val is not None:
                clauses.append(f"{col}=?"); params.append(val)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        sql += " ORDER BY priority ASC, created_at ASC LIMIT ?"
        params.append(limit)
        return [self._expand(r) for r in store.query(sql, tuple(params))]

    # ---- assignment ----------------------------------------------------
    def assign(self, task_id: str, agent_id: str, *, by: str = "system") -> dict:
        task = self.get(task_id)
        if not task:
            raise ValueError("Unknown task")
        if task["status"] in ("DONE", "CANCELLED"):
            raise ValueError(f"Task is {task['status']} and cannot be reassigned.")
        store.update("tasks", task_id, {"assignee_id": agent_id, "status": "ASSIGNED"})
        bus.publish(E.TASK_ASSIGNED, source="tasks", subject=task_id,
                    payload={"assignee": agent_id, "title": task["title"], "by": by})
        return self.get(task_id)  # type: ignore[return-value]

    def claim_next(self, agent: dict) -> dict | None:
        """Highest-priority queued task that the agent is allowed and able to take."""
        rows = store.query(
            "SELECT * FROM tasks WHERE status='QUEUED' AND (department_id IS NULL OR department_id=?) "
            "ORDER BY priority ASC, created_at ASC LIMIT 12",
            (agent.get("department_id"),),
        )
        for row in rows:
            task = self._expand(row)
            decision = permissions.check(actor=agent["name"], rank=agent["rank"],
                                        tool="task.complete",
                                        context={"department_id": task.get("department_id"),
                                                 "own_department_id": agent.get("department_id")})
            if decision.allowed:
                self.assign(task["id"], agent["id"], by="claim_next")
                return self.get(task["id"])
        return None

    # ---- execution -----------------------------------------------------
    def start(self, task_id: str, agent_id: str) -> dict:
        store.update("tasks", task_id, {"status": "IN_PROGRESS", "started_at": store.now(),
                                        "attempts": int((self.get(task_id) or {}).get("attempts") or 0) + 1})
        task = self.get(task_id)
        bus.publish(E.TASK_STARTED, source="tasks", subject=task_id,
                    payload={"agent": agent_id, "type": task["task_type"] if task else None,
                             "title": task["title"] if task else None})
        return task  # type: ignore[return-value]

    def progress(self, task_id: str, note: str, *, percent: float | None = None) -> None:
        bus.publish(E.TASK_PROGRESS, source="tasks", subject=task_id,
                    payload={"note": note, "percent": percent})

    def block(self, task_id: str, reason: str) -> dict:
        store.update("tasks", task_id, {"status": "BLOCKED", "error": reason})
        task = self.get(task_id)
        bus.publish(E.TASK_BLOCKED, source="tasks", subject=task_id, severity="warning",
                    payload={"reason": reason, "title": task["title"] if task else None})
        return task  # type: ignore[return-value]

    def complete(self, task_id: str, *, agent_id: str, result: dict, quality: float | None = None) -> dict:
        """Completes a task, then routes it through verification."""
        task = self.get(task_id)
        if not task:
            raise ValueError("Unknown task")
        store.update("tasks", task_id, {"status": "VERIFYING", "result_json": json.dumps(result, default=str)})
        verification = self.verify(task_id, agent_id=agent_id)
        passed = bool(verification.get("passed"))
        final_status = "DONE" if passed else "FAILED"
        store.update("tasks", task_id, {
            "status": final_status, "completed_at": store.now(),
            "verification_json": json.dumps(verification, default=str),
            "error": None if passed else "; ".join(verification.get("issues", []))[:500],
        })
        evt = E.TASK_DONE if passed else E.TASK_FAILED
        bus.publish(evt, source="tasks", subject=task_id,
                    severity="info" if passed else "warning",
                    payload={"agent": agent_id, "title": task["title"], "quality": verification.get("score"),
                             "issues": verification.get("issues", [])[:4]})
        if passed:
            bus.publish(E.TASK_VERIFIED, source="tasks", subject=task_id,
                        payload={"method": verification.get("method"), "score": verification.get("score")})
        return self.get(task_id)  # type: ignore[return-value]

    # ---- verification --------------------------------------------------
    def verify(self, task_id: str, *, agent_id: str | None = None) -> dict:
        """Rubric first (deterministic), model second (if available). Both results are stored."""
        task = self.get(task_id)
        if not task:
            raise ValueError("Unknown task")
        issues: list[str] = []
        vetoes: list[str] = []
        passed_checks = 0
        total_checks = 0
        result = task.get("result") or {}
        text_result = json.dumps(result, ensure_ascii=False, default=str)

        def check(ok: bool, message: str, *, veto: bool = False) -> None:
            nonlocal passed_checks, total_checks
            total_checks += 1
            if ok:
                passed_checks += 1
            else:
                issues.append(message)
                if veto:
                    vetoes.append(message)

        # These four are vetoes: passing the others cannot compensate for them.
        check(bool(result), "Result is empty. An empty result is not a completed task.", veto=True)
        check("Not verified" in text_result or "FACT" in text_result or "ASSUMPTION" in text_result
              or "UNKNOWN" in text_result
              or task["task_type"] in ("code_task", "coursework", "exam"),
              "Missing evidence labelling (FACT/ASSUMPTION/INFERENCE/HYPOTHESIS/UNKNOWN or 'Not verified.').",
              veto=True)
        check(str(result.get("status", "")).lower() not in ("failed", "error"),
              "Result self-reports failure.", veto=True)

        # Ethics gate: the text that could reach a customer must survive the claims validator.
        # The vetted fields are the ones that would be published; tool metadata (labels, ids,
        # reviewer notes) is not customer-facing and is never screened as if it were.
        if task["task_type"] in ("content_draft", "copywriting", "outreach_draft"):
            review = claims_validator.review(_customer_text(result), context=task["task_type"])
            detail = ", ".join(b["rule"] for b in review["blocks"]) or "unprintable claim"
            check(review["safe_to_publish"], f"Blocked claim(s): {detail}", veto=True)

        score = round(passed_checks / total_checks, 4) if total_checks else 0.0
        method = "deterministic-rubric"

        # Optional second-pass model verification (never invents a pass)
        try:
            from .model_router import router
            status = router().status()
            if status.get("reachable"):
                res = router().route("verification", (
                    "You are a strict verifier. A task result is below. Decide if it satisfies the task.\n"
                    f"TASK: {task['title']}\nTYPE: {task['task_type']}\nRESULT:\n{text_result[:2000]}\n"
                    "Answer EXACTLY as: VERDICT: PASS or FAIL, then one line of reason. "
                    "Do not invent facts. If unsure, answer FAIL."
                ), max_tokens=120)
                if res.model_verified:
                    verdict_line = res.text.strip().splitlines()[0] if res.text.strip() else ""
                    model_pass = "PASS" in verdict_line.upper() and "FAIL" not in verdict_line.upper()
                    method = "deterministic-rubric + model-second-pass"
                    if not model_pass:
                        issues.append(f"Model second pass: {verdict_line[:160]}")
                        score = round(score * 0.5, 4)
        except Exception as exc:
            issues.append(f"Model verification unavailable: {type(exc).__name__}")

        if vetoes:
            score = min(score, 0.5)
        passed = bool(result) and not vetoes and score >= 0.6
        verification = {"passed": passed, "score": score, "checks_passed": passed_checks,
                        "checks_total": total_checks, "issues": issues, "vetoes": vetoes,
                        "method": method, "verified_at": store.now(),
                        "verified_by": agent_id or "system"}
        self._record_verification(task, verification)
        return verification

    def _record_verification(self, task: dict, verification: dict) -> None:
        """Persist a verdict and reconcile the task status with it.

        Re-verification never erases history: the previous verdict stays in the event log, and
        a task whose result stops verifying is moved back out of DONE. Verification is the
        authority on whether work counts — not the fact that someone once marked it complete.
        """
        task_id = task["id"]
        previous = task.get("verification") or {}
        was_done = task["status"] == "DONE"
        changes: dict[str, Any] = {"verification_json": json.dumps(verification, default=str)}
        now = verification["verified_at"]
        if verification["passed"] and not was_done:
            changes["status"] = "DONE"
            changes["completed_at"] = task.get("completed_at") or now
            changes["error"] = None
        elif not verification["passed"] and was_done:
            changes["status"] = "FAILED"
            changes["error"] = "Verification revoked a previously accepted result: " + \
                (", ".join(verification.get("vetoes") or verification.get("issues") or [])[:300])
        store.update("tasks", task_id, changes)
        bus.publish(
            E.TASK_DONE if verification["passed"] else E.TASK_FAILED,
            source="tasks", subject=task_id,
            severity="notice" if verification["passed"] else "warning",
            payload={"title": task["title"], "score": verification["score"],
                     "method": verification["method"], "reverified": bool(previous),
                     "status": changes.get("status", task["status"])})
        if previous and previous.get("passed") != verification["passed"]:
            bus.publish("task.verification.changed", source="tasks", subject=task_id,
                        severity="warning",
                        payload={"from": previous.get("passed"), "to": verification["passed"],
                                 "reason": "claims fix / re-verification",
                                 "previous_issues": previous.get("issues", [])[:5]})

    # ---- reporting -----------------------------------------------------
    def metrics(self) -> dict:
        counts = {r["status"]: int(r["n"]) for r in store.query(
            "SELECT status, COUNT(*) n FROM tasks GROUP BY status")}
        done = counts.get("DONE", 0)
        failed = counts.get("FAILED", 0)
        total_finished = done + failed
        latency = store.query_one(
            "SELECT AVG(completed_at - started_at) avg_s FROM tasks "
            "WHERE completed_at IS NOT NULL AND started_at IS NOT NULL")
        by_dept = store.query(
            "SELECT department_id, COUNT(*) n, SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) ok "
            "FROM tasks WHERE department_id IS NOT NULL GROUP BY department_id ORDER BY n DESC LIMIT 20")
        return {
            "counts": counts,
            "completed": done,
            "failed": failed,
            "failure_rate": round(failed / total_finished, 4) if total_finished else 0.0,
            "avg_latency_seconds": round(float(latency["avg_s"]), 2) if latency and latency.get("avg_s") else None,
            "by_department": [{"department_id": r["department_id"], "tasks": r["n"],
                               "completed": r["ok"],
                               "success_rate": round((r["ok"] or 0) / r["n"], 3)} for r in by_dept],
        }


board = TaskBoard()
