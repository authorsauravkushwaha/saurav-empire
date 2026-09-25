# Saurav AI Civilization

A local-first, self-training, multi-agent **business organization** that runs on this machine and
shows its real state in a 3D world. Departments are created on demand, agents are hired, trained,
examined, certified and sent to work; every claim they produce is labelled and verified before it
is allowed near a customer.

₹0 starting capital. No invented customers, sales, revenue, reviews, awards or partnerships — the
system refuses to produce them, and the tests prove it.

```
python3 -m pip install -r requirements.txt      # fastapi, uvicorn, pyyaml, httpx, websockets
python3 scripts/empire.py up                    # 14 services + builds and serves the 3D console
open http://localhost:8000                      # one origin: API + 3D owner console
python3 scripts/empire.py token                 # where the owner token lives (never printed in full)
python3 scripts/empire.py demo                  # headless proof of the full loop
python3 scripts/empire.py doctor                # environment + guarantees + tests + live state
python3 scripts/empire.py down
```

---

## The loop that actually runs

```
TRAIN → GRADUATE → JOB → TASK → TOOL → VERIFY → REPORT → MEASURE → LEARN → DECIDE
```

Nothing in that chain needs an LLM. With no local model installed every artifact is produced by the
**deterministic engine** and stamped `templated (no model available)`; install Ollama and the same
tasks route through real models instead (`config/models.yaml`).

## Architecture

| Layer | What lives there |
| --- | --- |
| **Apps** | `apps/civilization-web` — React + three.js owner console (HUD, panels, live feed) |
| **Services** | `services/*` — 14 FastAPI services on ports 8000–8013 (see `config/services.yaml`) |
| **Kernel** | `kernel/*` — governance, registry, tasks, tools, memory, economy, university, runtime |
| **Config** | `config/*.yaml` — the world layout, departments, models, permissions, governance, economics |
| **Data** | `data/state` (SQLite + WAL, git-ignored), `data/seed/books.json` (50 unverified titles) |
| **Docs** | `docs/MASTER_PROMPT.md` — the constitution this code is built to obey |

Service map: gateway `8000` · agent `8001` · model `8002` · memory `8003` · analytics `8004` ·
workflow `8005` · economy `8006` · university `8007` · research `8008` · integration `8009` ·
finance `8010` · security `8011` · event `8012` · world `8013`.

## What is enforced in code (not in prose)

| Rule | Where it is enforced |
| --- | --- |
| Every claim carries a label (FACT / ASSUMPTION / INFERENCE / HYPOTHESIS / OPINION / UNKNOWN) | `kernel/governance.py` `Evidence`, and the verifier in `kernel/tasks.py` |
| A tool result can never leave unlabelled | `kernel/tools.py` `ensure_labels` (dispatch boundary) |
| No fabricated testimonials, income, guarantees, authority, scarcity or urgency | `kernel/governance.py` `ClaimsValidator` — a `block` finding fails verification |
| Revenue is ₹0 until a *verified* transaction exists | `kernel/economy.py` `Ledger.record` refuses unverified income |
| ₹0 capital: nothing may spend money that does not exist | `kernel/economy.py` experiments/opportunities reject capital > treasury |
| Unknown tools are denied by default; CRITICAL actions are always owner-gated | `kernel/governance.py` `PermissionEngine`, `config/permissions.yaml` |
| HIGH-risk external actions queue for the owner | `PermissionEngine` → `ApprovalQueue` |
| Any supervisor may STOP; only the owner may RESUME | `kernel/killswitch.py` |
| Prompt-injection from the web is quarantined, never obeyed | `kernel/governance.py` `InjectionDefence` |
| Papers, not promises: data hygiene problems get fixed and reported | `scripts/empire.py repair` |

## The 3D world is a read-out, not a cartoon

`REAL BACKEND STATE → REAL-TIME 3D VISUALIZATION`. The client polls `/api/world/state` and consumes
the event WebSocket; agent positions, travel, building activity and event pulses all originate from
rows the runtime wrote. If the backend is silent the world is still, and the HUD says so instead of
inventing a scene. Camera framing is computed by the backend from the configured world size, so the
default view always contains every city instead of cropping it.

Because the world is data, it can be checked without a browser:

```
python3 scripts/empire.py worldcheck     # geometry, seating, camera framing + a map you can look at
```

It fails loudly when a building pokes outside its city, two cities touch, agents pile onto one
point (which would render a crowd as a single capsule), a department points at a building nobody
can reach, or a camera preset crops the civilization. It writes
`data/state/artifacts/world-map.svg` and `.png` — a top-down projection of the exact coordinates
the client renders.

## Tests

```
python3 -m unittest discover -s tests -v      # 63 tests, standard library only
cd apps/civilization-web && npm run build     # type-checks then builds the client
cd apps/civilization-web && npm run smoke     # boots the built bundle in jsdom
```

The suite asserts the guarantees directly: fake revenue is refused, manipulation is blocked,
trainees cannot act externally, unanswered approvals never auto-execute, duplicate coursework is
never queued, an agent that keeps failing ends up in front of the owner instead of retrying forever.

## Honest status (2026-09-25)

* Verified revenue: **₹0.00** — no real customer has paid yet. That is the truth, not a bug.
* No local model is installed in this environment, so every artifact is templated and says so.
* The API, the event stream, the task loop and the client build are verified; the *visual* look of
  the 3D scene has not been eyeballed in a browser by the author of this file — open
  `http://localhost:8000` and judge it yourself.
* External connectors (`kernel/integrations/*`) read/simulate only. Sending and publishing are
  deliberately unimplemented until the owner adds official API credentials and approves an action.

## Controlling it

```
python3 scripts/empire.py up|down|status|seed|demo|doctor|repair|worldcheck|backup|token|rotate-token
```

In the console: click agents and buildings to inspect, use the command bar
(`status report`, `hire 3 agents for research-lab`, `create a department for paid templates`,
`run the free resource scan`), approve or reject gated actions in **Approvals**, and stop everything
with the kill switch in **Security**.
