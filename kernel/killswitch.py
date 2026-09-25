"""Emergency shutdown + safe mode.

Anyone (or any supervisor agent) may STOP the civilization. Only the owner may start it again.
Engaging the kill switch: stops the agent runtime, freezes external actions, preserves all data.
It never deletes evidence — a shutdown that destroys the audit trail is not a safety feature.
"""
from __future__ import annotations

import json
import time

from . import store
from .eventbus import E, bus
from .governance import audit

FREEZE_FLAG = "external_actions_frozen"


def engage(*, by: str = "OWNER", reason: str = "manual emergency shutdown", agent_runtime=None) -> dict:
    store.set_setting("kill_switch", True)
    store.set_setting(FREEZE_FLAG, True)
    store.set_setting("kill_switch_meta", {
        "engaged_at": time.time(), "by": by, "reason": reason,
    })
    bus.publish(E.KILLSWITCH, source="killswitch", severity="critical",
                payload={"engaged": True, "by": by, "reason": reason,
                         "effect": "Agent runtime halted. External actions frozen. Data preserved."})
    audit(by, "kill_switch.engage", tool="kill_switch.engage", risk="HIGH",
          reason=reason, actor_rank="OWNER" if by == "OWNER" else "MANAGER")
    # Stop whatever is running in this process; other services observe the flag.
    stopped = None
    try:
        if agent_runtime is None:
            from .agent_runtime import runtime
            agent_runtime = runtime()
        stopped = agent_runtime.stop()
    except Exception as exc:
        stopped = {"status": "error", "reason": str(exc)[:120]}
    store.set_setting("kill_switch_last_stop", stopped or {})
    return {"engaged": True, "by": by, "reason": reason, "runtime": stopped}


def disengage(*, by: str = "OWNER", reason: str = "owner resumed operations") -> dict:
    if by != "OWNER":
        raise PermissionError("Only the owner may disengage the kill switch. This is not configurable.")
    store.set_setting("kill_switch", False)
    store.set_setting(FREEZE_FLAG, False)
    store.set_setting("kill_switch_meta", {"disengaged_at": time.time(), "by": by, "reason": reason})
    bus.publish(E.KILLSWITCH, source="killswitch", severity="notice",
                payload={"engaged": False, "by": by, "reason": reason})
    audit(by, "kill_switch.disengage", tool="kill_switch.engage", risk="HIGH", reason=reason)
    return {"engaged": False, "by": by}


def status() -> dict:
    return {
        "engaged": bool(store.get_setting("kill_switch", False)),
        "external_frozen": bool(store.get_setting(FREEZE_FLAG, False)),
        "meta": store.get_setting("kill_switch_meta", {}) or {},
        "last_stop": store.get_setting("kill_switch_last_stop", {}) or {},
        "rule": "Any supervisor may STOP. Only the owner may RESUME.",
    }


def enter_safe_mode(*, reason: str, by: str = "system") -> dict:
    """Used when a department/model fails: freeze external actions, preserve data, alert the owner."""
    store.set_setting("safe_mode", True)
    store.set_setting(FREEZE_FLAG, True)
    bus.publish(E.SAFE_MODE, source="killswitch", severity="error",
                payload={"reason": reason, "by": by,
                         "effect": "External actions frozen. Local work continues. Owner alerted."})
    audit(by, "safe_mode.enter", risk="HIGH", reason=reason, allowed=True)
    return {"safe_mode": True, "reason": reason}


def exit_safe_mode(*, by: str = "OWNER", reason: str = "") -> dict:
    if by != "OWNER":
        raise PermissionError("Only the owner may exit safe mode.")
    store.set_setting("safe_mode", False)
    store.set_setting(FREEZE_FLAG, False)
    bus.publish(E.SAFE_MODE, source="killswitch", severity="notice",
                payload={"safe_mode": False, "by": by, "reason": reason})
    return {"safe_mode": False}


def external_frozen() -> bool:
    return bool(store.get_setting(FREEZE_FLAG, False))


def guard_external(action: str, *, confirmed: bool = False) -> None:
    """Every external-facing call must pass through this guard."""
    from .governance import kill_switch_engaged, safe_mode
    if kill_switch_engaged():
        raise RuntimeError(f"KILL SWITCH ENGAGED — '{action}' refused.")
    if safe_mode():
        raise RuntimeError(f"SAFE MODE — external action '{action}' frozen.")
    if external_frozen() and not confirmed:
        raise RuntimeError(f"External actions are frozen — '{action}' refused.")
