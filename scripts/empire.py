#!/usr/bin/env python3
"""SAURAV AI CIVILIZATION — single control script.

    python scripts/empire.py up            start every service (+ the 3D client if npm deps exist)
    python scripts/empire.py down          stop everything started by `up`
    python scripts/empire.py status        health of every service
    python scripts/empire.py seed          initialise the database and the starting organization
    python scripts/empire.py doctor        check the environment and report honestly
    python scripts/empire.py demo          run the full loop headlessly (train → task → verify → report)
    python scripts/empire.py token         show the owner token location (never prints it in full)
    python scripts/empire.py rotate-token  generate a new owner token
    python scripts/empire.py repair        fix known data-hygiene problems (reports every change)
    python scripts/empire.py backup        copy data/state into backups/<timestamp>/

Design: standard library only for process management (no supervisor dependency).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import yaml
except ModuleNotFoundError:
    print("PyYAML is required. Run: pip install -r requirements.txt")
    raise SystemExit(1)

TOPOLOGY = yaml.safe_load((ROOT / "config" / "services.yaml").read_text(encoding="utf-8"))
SERVICES: dict = TOPOLOGY["services"]
START_ORDER: list[str] = TOPOLOGY.get("startup_order") or list(SERVICES)
HOST = TOPOLOGY.get("host", "0.0.0.0")
LOCAL = TOPOLOGY.get("service_host", "127.0.0.1")
PID_DIR = ROOT / "data" / "state" / "run"
LOG_DIR = ROOT / "data" / "logs"
GREEN, RED, YEL, DIM, BOLD, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def _ok(msg: str) -> None: print(f"  {GREEN}✓{RST} {msg}")
def _bad(msg: str) -> None: print(f"  {RED}✗{RST} {msg}")
def _warn(msg: str) -> None: print(f"  {YEL}!{RST} {msg}")
def _dim(msg: str) -> None: print(f"  {DIM}{msg}{RST}")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def http_json(url: str, timeout: float = 4.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (localhost)
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# up / down
# ---------------------------------------------------------------------------
def cmd_up(args: argparse.Namespace) -> int:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    from kernel import store
    from kernel.auth import ensure_token, masked
    store.init_db()

    print(f"\n{BOLD}SAURAV AI CIVILIZATION{RST} — starting {len(SERVICES)} services + 3D client\n")
    if not args.no_seed:
        from kernel.registry import bootstrap_organization
        created = bootstrap_organization()
        if created["departments"]:
            _ok(f"organization seeded: {created['departments']} departments, {created['agents']} agents")
        else:
            _ok("organization already present")

    started: list[str] = []
    for name in START_ORDER:
        spec = SERVICES.get(name)
        if not spec:
            continue
        if not args.force and not port_free(spec["port"]):
            _warn(f"{name} — port {spec['port']} already in use (skipping)")
            continue
        log = LOG_DIR / f"{name}.log"
        cmd = [sys.executable, "-m", "uvicorn", "app:application", "--host", HOST,
               "--port", str(spec["port"]), "--app-dir", str(ROOT / spec["dir"]),
               "--log-level", "info"]
        with open(log, "ab") as fh:
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        (PID_DIR / f"{name}.pid").write_text(str(proc.pid), encoding="utf-8")
        started.append(name)
        _ok(f"{name:<22} → http://127.0.0.1:{spec['port']:<5} {DIM}{spec['description'][:60]}{RST}")

    # frontend
    fe = TOPOLOGY.get("frontend", {})
    fe_dir = ROOT / fe.get("dir", "apps/civilization-web")
    # The gateway serves the built client from its own origin when a build exists. Build it now
    # if dependencies are installed, so `up` yields one URL for both the API and the 3D world.
    dist_index = fe_dir / "dist" / "index.html"
    if fe_dir.exists() and (fe_dir / "node_modules").exists() and not dist_index.exists():
        print(f"  {DIM}building the 3D client once (npm run build)…{RST}")
        built = subprocess.run(["npm", "run", "build"], cwd=str(fe_dir), capture_output=True, text=True)
        if built.returncode == 0:
            _ok("3D client built → the gateway will serve it at http://127.0.0.1:8000/")
        else:
            _warn("client build failed — the Vite dev server (if started) still serves the UI")
            _dim((built.stderr or built.stdout or "").strip().splitlines()[-1][:140] if
                 (built.stderr or built.stdout) else "")

    if fe_dir.exists() and not args.no_frontend:
        if (fe_dir / "node_modules").exists():
            log = LOG_DIR / "frontend.log"
            with open(log, "ab") as fh:
                proc = subprocess.Popen(fe["dev_command"].split(), cwd=str(fe_dir), stdout=fh,
                                        stderr=subprocess.STDOUT, start_new_session=True)
            (PID_DIR / "frontend.pid").write_text(str(proc.pid), encoding="utf-8")
            _ok(f"{'3D civilization (vite)':<22} → http://127.0.0.1:{fe.get('port', 3000)}")
        else:
            _warn("frontend dependencies missing — run: cd apps/civilization-web && npm install")

    print(f"\n  {BOLD}Waiting for services to answer /health…{RST}")
    for name in started:
        spec = SERVICES[name]
        deadline = time.time() + 25
        healthy = False
        while time.time() < deadline:
            if http_json(f"http://{LOCAL}:{spec['port']}/health"):
                healthy = True
                break
            time.sleep(0.5)
        (_ok if healthy else _bad)(f"{name} {'healthy' if healthy else 'did not answer /health (see data/logs)'}")

    token = ensure_token()
    print(f"""
  {BOLD}OPEN THE CIVILIZATION{RST}
    3D world   →  http://127.0.0.1:{TOPOLOGY.get('frontend', {}).get('port', 3000)}
    API gateway→  http://127.0.0.1:8000/api/health
    Dashboard  →  http://127.0.0.1:8000/api/dashboard  (send X-Owner-Token)

  {BOLD}OWNER TOKEN{RST} (required by the UI and every API call)
    {masked(token)}
    full value: data/state/secrets/owner_token

  Stop everything with:  python scripts/empire.py down
""")
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    stopped = 0
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        try:
            pid = int(pid_file.read_text().strip())
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            stopped += 1
            _ok(f"stopped {pid_file.stem} (pid {pid})")
        except ProcessLookupError:
            _dim(f"{pid_file.stem} was not running")
        except Exception as exc:
            _warn(f"{pid_file.stem}: {type(exc).__name__}: {exc}")
        finally:
            pid_file.unlink(missing_ok=True)
    if not stopped:
        _warn("nothing was running under this script")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(f"\n{BOLD}SERVICE STATUS{RST}\n")
    up = 0
    for name, spec in SERVICES.items():
        data = http_json(f"http://{LOCAL}:{spec['port']}/health")
        if data:
            up += 1
            rows = list((data.get("db_rows") or {}).items())[:2]
            detail = ", ".join(f"{k}={v}" for k, v in rows)
            _ok(f"{name:<22} up   requests={data.get('requests', 0):<6} {DIM}{detail}{RST}")
        else:
            _bad(f"{name:<22} down (port {spec['port']})")
    print(f"\n  {up}/{len(SERVICES)} services healthy")
    dash = http_json(f"http://{LOCAL}:8000/api/health")
    if not dash:
        _dim("gateway is down; the 3D client will show the lock screen and offline state.")
    return 0 if up else 1


# ---------------------------------------------------------------------------
# seed / demo / doctor
# ---------------------------------------------------------------------------
def cmd_seed(args: argparse.Namespace) -> int:
    from kernel import store
    from kernel.registry import bootstrap_organization, agents, departments
    from kernel.university import university
    from kernel.economy import opportunities, free_resources
    from kernel.memory import memory

    store.init_db()
    created = bootstrap_organization()
    _ok(f"departments created: {created['departments']}  agents hired: {created['agents']}")
    _ok(f"workforce: {agents.counts()['total']} agents, {len(departments.list())} departments")

    inducted = university.induct_trainees(limit=6)
    _ok(f"university: {len(inducted)} trainee actions")
    opps = opportunities.discover_zero_capital()
    _ok(f"economy: {len(opps)} zero-capital opportunity candidates")
    scan = free_resources.scan()
    _ok(f"free-resource scan: {len(scan['findings'])} findings")
    memory.strategic("The objective is durable economic value, not the appearance of an empire. "
                     "Revenue is ₹0 until a verified transaction exists.", key="objective")
    _ok("strategic memory written")
    print(f"\n  Seeded. Start the civilization with: python scripts/empire.py up\n")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Headless proof that the full loop works — no UI, no network, no model required."""
    from kernel import store
    from kernel.registry import bootstrap_organization, agents
    from kernel.tasks import board
    from kernel.university import university
    from kernel.agent_runtime import AgentRuntime
    from kernel.economy import opportunities, experiments, economic_summary

    store.init_db()
    bootstrap_organization()
    print(f"\n{BOLD}THE COMPLETE LOOP{RST} (no model, no network, ₹0)\n")

    rt = AgentRuntime(tick_seconds=0.35)
    rt.start()
    ticks = int(getattr(args, "ticks", 40))
    for i in range(ticks):
        time.sleep(0.35)
        if (i + 1) % 10 == 0:
            s = rt.stats
            _dim(f"tick {s.tick}: travelers={s.travelers} assigned={s.assigned} executed={s.executed}")
    rt.stop()

    metrics = board.metrics()
    _ok(f"TASK   {metrics['completed']} completed / {metrics['failed']} failed "
        f"(failure rate {metrics['failure_rate']:.0%})")
    for t in board.list(status="DONE", limit=3):
        v = t.get("verification") or {}
        _dim(f"       verified: {t['title'][:58]} (score {v.get('score')}, {v.get('method')})")

    trainee = agents.list(rank="TRAINEE")
    if trainee:
        exam = university.run_exam(trainee[0]["id"])
        verdict = "CERTIFIED" if exam["passed"] else "NOT certified"
        _ok(f"UNIVERSITY  deterministic dimensions {exam['total']:.2f} "
            f"(threshold {exam['threshold']}) → {verdict} · mode: {exam['mode']}")
        if exam.get("caveat"):
            _dim(f"       {exam['caveat'][:130]}")

    opps = opportunities.discover_zero_capital() or opportunities.list()[:1]
    if opps:
        verdict = opportunities.judge(opps[0]["id"])
        _ok(f"DECISION    {verdict['verdict'][:80]}")
        _dim(f"       confidence={verdict['confidence']}  cheapest test: {verdict['cheapest_test'][:80]}")
    exp = experiments.create(hypothesis="A ₹0 offer converts at least one real buyer within 14 days",
                             expected_result="1 verified transaction",
                             mvp_definition="Smallest honest version of the offer",
                             test_method="Expose to the smallest real audience", success_metric="1 sale",
                             kill_metric="0 conversations in 14 days")
    _ok(f"EXPERIMENT  designed with kill criterion ({exp['id'][:12]}…)")

    econ = economic_summary()
    _ok(f"ECONOMY     verified revenue ₹{econ['revenue_inr']:.2f}  (honest: activity ≠ income)")
    print(f"\n  Loop proven: TRAIN → TASK → TOOL → VERIFY → REPORT → LEARN → DECIDE.\n"
          f"  Now start the 3D view:  python scripts/empire.py up\n")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"\n{BOLD}ENVIRONMENT DOCTOR{RST}\n")
    _ok(f"python {sys.version.split()[0]}") if sys.version_info >= (3, 10) else _bad("python 3.10+ required")

    for module, why in (("fastapi", "services"), ("uvicorn", "services"), ("yaml", "config"),
                        ("httpx", "gateway"), ("websockets", "real-time stream")):
        try:
            __import__(module)
            _ok(f"python package: {module}")
        except ModuleNotFoundError:
            _bad(f"missing '{module}' — needed for {why}. Run: pip install -r requirements.txt")

    from kernel.model_router import router
    status = router().status()
    if status["reachable"]:
        _ok(f"ollama reachable with {len(status['installed_models'])} model(s)")
    else:
        _warn("no local model detected — the deterministic engine will answer and label its output")
        _dim("install Ollama then: ollama pull qwen2.5:0.5b-instruct")

    node = shutil.which("node")
    if node:
        version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        _ok(f"node {version}")
    else:
        _warn("node not found — the 3D client cannot run (the API still works)")

    for name, spec in SERVICES.items():
        free = port_free(spec["port"])
        (_ok if free else _warn)(f"port {spec['port']} ({name}) {'free' if free else 'in use'}")

    from kernel import paths
    _ok(f"state dir: {paths.STATE_DIR.relative_to(ROOT)}  (git-ignored)")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    (_ok if free_gb > 2 else _warn)(f"disk free: {free_gb:.1f} GB")

    # --- the 3D client ---
    fe_dir = ROOT / "apps" / "civilization-web"
    have_deps = (fe_dir / "node_modules").exists()
    have_dist = (fe_dir / "dist" / "index.html").exists()
    if have_deps:
        _ok("3D client dependencies installed")
    else:
        _warn("3D client dependencies missing — cd apps/civilization-web && npm install")
    (_ok if have_dist else _warn)(
        "3D client built (served by the gateway at /)" if have_dist
        else "3D client not built yet — run: npm run build, or just `empire.py up`")
    if have_dist and node:
        smoke = subprocess.run(["node", "scripts/smoke.mjs"], cwd=str(fe_dir),
                               capture_output=True, text=True)
        (_ok if smoke.returncode == 0 else _bad)(
            "3D client boots in a headless DOM" if smoke.returncode == 0
            else "3D client failed to boot headlessly — see: cd apps/civilization-web && npm run smoke")

    # --- the guarantees, proven rather than asserted ---
    print()
    print(f"  {BOLD}GUARANTEE CHECKS{RST}")
    try:
        from kernel.governance import claims as _claims, permissions as _perms, kill_switch_engaged
        from kernel.economy import Ledger as _Ledger
        _ok("governance vocabulary loads") if _claims.review("x")["safe_to_publish"] else None
        blocked = not _claims.review("We earned ₹50,000 last month.")["safe_to_publish"]
        (_ok if blocked else _bad)("unverified income statements are still blocked")
        allowed = _claims.review("Budget ₹0, price ₹199.")["safe_to_publish"]
        (_ok if allowed else _bad)("honest prices and ₹0 budgets are not flagged")
        denied = not _perms.check(actor="x", rank="AGENT", tool="made.up.tool").allowed
        (_ok if denied else _bad)("unknown tools are denied by default")
        gated = _perms.check(actor="x", rank="SUPREME", tool="system.shell").requires_approval
        (_ok if gated else _bad)("CRITICAL capabilities stay owner-gated")
        try:
            _Ledger().record(direction="IN", amount_inr=100, category="sales",
                             description="unverified", source="guess", verified=False,
                             evidence={}, recorded_by="doctor")
            _bad("the ledger accepted an unverified revenue entry")
        except ValueError:
            _ok("revenue entries without a source and evidence are refused")
        (_warn if kill_switch_engaged() else _ok)(
            "kill switch is engaged — only the owner can resume" if kill_switch_engaged()
            else "kill switch is disengaged (external actions permitted)")
    except Exception as exc:  # a broken guarantee is a bad doctor result, not a crash
        _bad(f"guarantee check failed: {type(exc).__name__}: {exc}")

    # --- the test suite is the proof, so run it ---
    print()
    print(f"  {BOLD}TEST SUITE{RST}")
    tests_dir = ROOT / "tests"
    if tests_dir.exists():
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=str(ROOT), capture_output=True, text=True)
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout) else ""
        (_ok if proc.returncode == 0 else _bad)(f"unit tests: {tail or 'no output'}")
    else:
        _warn("no tests directory — the guarantees are unproven")

    # --- live state, when the services are up ---
    print()
    print(f"  {BOLD}LIVE STATE{RST}")
    token_path = paths.SECRETS_DIR / "owner_token"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        _ok(f"owner token present ({token[:4]}…{token[-4:]})")
        for label, path in (("gateway", "/api/health"), ("dashboard", "/api/dashboard")):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{SERVICES['gateway']['port']}{path}",
                                             headers={"X-Owner-Token": token})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                if label == "gateway":
                    _ok(f"gateway answers ({len(payload.get('services', []))} service cards)")
                else:
                    overview = payload.get("overview") or {}
                    tasks = overview.get("tasks") or {}
                    economy = overview.get("economy") or {}
                    approvals = overview.get("approvals_pending")
                    _ok(f"tasks {tasks.get('counts') or tasks} · approvals waiting: {approvals}")
                    _dim(f"verified revenue ₹{float(economy.get('revenue_inr') or 0):,.2f} — "
                         f"activity is not income")
                    (_warn if approvals else _ok)(
                        f"{approvals} decision(s) waiting in the owner queue" if approvals
                        else "owner approval queue is empty")
                    try:
                        from kernel.agent_runtime import runtime_snapshot
                        snap = runtime_snapshot()
                        (_ok if snap["running"] else _warn)(
                            f"agent runtime {'running' if snap['running'] else 'NOT running'} "
                            f"(tick {snap['tick']}, from the shared heartbeat)")
                    except Exception:
                        pass
            except Exception as exc:
                _warn(f"{label} not reachable: {type(exc).__name__}")
    else:
        _warn("no owner token yet — run: python3 scripts/empire.py up (creates one)")
    print()
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    from kernel.auth import ensure_token, masked, token_path
    print(f"\n  owner token: {masked(ensure_token())}\n  file: {token_path()}\n")
    return 0


def cmd_rotate_token(args: argparse.Namespace) -> int:
    from kernel.auth import masked, rotate_token
    print(f"\n  new owner token: {masked(rotate_token())}\n  Restart services to apply.\n")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    from kernel import paths
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = ROOT / "backups" / stamp
    target.mkdir(parents=True, exist_ok=True)
    if paths.STATE_DIR.exists():
        shutil.copytree(paths.STATE_DIR, target / "state", dirs_exist_ok=True)
    for cfg in (ROOT / "config").glob("*.yaml"):
        shutil.copy2(cfg, target / cfg.name)
    meta = {"created_at": stamp, "state_dir": str(paths.STATE_DIR.relative_to(ROOT)),
            "note": "Runtime state + policy snapshot. Secrets vault is copied encrypted; "
                    "the passphrase is not included (by design)."}
    (target / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _ok(f"backup written to {target.relative_to(ROOT)}")
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    """Data hygiene for problems the runtime cannot fix by itself. Reports every change."""
    from kernel import store
    from kernel.eventbus import bus
    from kernel.governance import audit
    from kernel.university import TRACKS, university

    store.init_db()
    print(f"\n{BOLD}REPAIR{RST}\n")
    changed = 0

    # 1. Duplicate open coursework: keep the oldest task per (agent, subject), cancel the rest.
    rows = store.query(
        "SELECT id, assignee_id, payload_json, created_at FROM tasks WHERE task_type='coursework' "
        "AND status IN ('QUEUED','ASSIGNED','IN_PROGRESS') ORDER BY created_at ASC")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        subject = (store.jload(row["payload_json"], {}) or {}).get("subject")
        key = (row["assignee_id"] or "", subject or "")
        if not subject or key not in seen:
            seen.add(key)
            continue
        store.update("tasks", row["id"], {"status": "CANCELLED",
                                          "error": "duplicate coursework — removed by repair"})
        bus.publish("task.cancelled", source="repair", subject=row["id"], severity="notice",
                    payload={"reason": "duplicate coursework", "subject": subject})
        changed += 1
    _ok(f"duplicate coursework cancelled: {changed}")

    # 2. Learners parked in LEARNING with nothing to do go back to IDLE.
    idle_learning = store.query(
        "SELECT id, name FROM agents WHERE status='LEARNING' AND active_task_id IS NULL "
        "AND lifecycle='TRAINEE' AND id NOT IN (SELECT assignee_id FROM tasks WHERE "
        "status IN ('QUEUED','ASSIGNED','IN_PROGRESS') AND assignee_id IS NOT NULL)")
    for row in idle_learning:
        store.update("agents", row["id"], {"status": "IDLE"})
    _ok(f"learners returned to idle: {len(idle_learning)}")
    changed += len(idle_learning)

    # 3. Trainees with no track enrolled are pointed at the least-served track.
    enrolled = 0
    for row in store.query("SELECT id, meta_json FROM agents WHERE rank='TRAINEE' AND lifecycle='TRAINEE'"):
        meta = store.jload(row["meta_json"], {}) or {}
        if not meta.get("track"):
            chosen = getattr(args, "track", None)
            if chosen not in TRACKS:
                chosen = None
            # Let the university pick by department demand rather than defaulting everyone
            # into the same track (Skill Matrix, spec §19).
            try:
                chosen = chosen or university._suggest_track({"department_id": None, "id": row["id"]})
            except Exception:
                chosen = chosen or next(iter(TRACKS))
            meta["track"] = chosen
            store.update("agents", row["id"], {"meta_json": json.dumps(meta, default=str)})
            enrolled += 1
    _ok(f"trainees enrolled into a track: {enrolled}")
    changed += enrolled

    audit("OWNER", "repair.run", tool="repair", risk="LOW",
          reason=f"{changed} rows changed", actor_rank="OWNER")
    if changed:
        print(f"\n  {changed} record(s) changed. Every change is in the event log and the audit trail.\n")
    else:
        print("\n  Nothing to repair — state is clean.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Saurav AI Civilization control script")
    sub = parser.add_subparsers(dest="command", required=True)

    p_up = sub.add_parser("up", help="start all services")
    p_up.add_argument("--no-frontend", action="store_true")
    p_up.add_argument("--no-seed", action="store_true")
    p_up.add_argument("--force", action="store_true", help="start even if the port is busy")
    p_up.set_defaults(func=cmd_up)

    sub.add_parser("down", help="stop all services").set_defaults(func=cmd_down)
    sub.add_parser("status", help="service health").set_defaults(func=cmd_status)
    sub.add_parser("seed", help="create the starting organization").set_defaults(func=cmd_seed)
    p_demo = sub.add_parser("demo", help="headless proof of the full loop")
    p_demo.add_argument("--ticks", type=int, default=40)
    p_demo.set_defaults(func=cmd_demo)
    sub.add_parser("doctor", help="environment check").set_defaults(func=cmd_doctor)
    sub.add_parser("token", help="show owner token location").set_defaults(func=cmd_token)
    sub.add_parser("rotate-token", help="generate a new owner token").set_defaults(func=cmd_rotate_token)
    sub.add_parser("backup", help="snapshot state + policy").set_defaults(func=cmd_backup)
    p_repair = sub.add_parser("repair", help="fix data-hygiene problems (reports every change)")
    p_repair.add_argument("--track", help="track for un-enrolled trainees")
    p_repair.set_defaults(func=cmd_repair)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
