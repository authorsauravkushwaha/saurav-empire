"""SQLite-backed system of record.

Why SQLite first: the civilization must boot at ₹0 on one machine, with transactions,
zero setup, and no daemon. `postgres.py` (services/) can swap in PostgreSQL later —
the SQL here stays ANSI-shaped on purpose.

Concurrency: WAL mode + busy timeout lets the ~14 service processes share one file safely.
Runtime state lives in `data/state/` which is git-ignored.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from . import paths

_local = threading.local()
_write_lock = threading.Lock()

SCHEMA_VERSION = 1

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS departments (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  parent_id     TEXT,
  kind          TEXT NOT NULL DEFAULT 'department',   -- department|subdepartment|project|team|squad
  city          TEXT,
  building      TEXT,
  objective     TEXT,
  kpis_json     TEXT DEFAULT '[]',
  boss_agent_id TEXT,
  budget_inr    REAL DEFAULT 0,
  spend_inr     REAL DEFAULT 0,
  status        TEXT DEFAULT 'ACTIVE',                -- ACTIVE|PAUSED|DISSOLVED
  namespace     TEXT,                                 -- db/analytics/memory namespace
  channel       TEXT,                                 -- comms channel id
  security_policy TEXT,
  created_by    TEXT,
  created_at    REAL,
  meta_json     TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS agents (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,
  role           TEXT,
  rank           TEXT NOT NULL DEFAULT 'TRAINEE',
  department_id  TEXT,
  manager_id     TEXT,
  model_tier     TEXT DEFAULT 'nano',
  status         TEXT NOT NULL DEFAULT 'IDLE',
  lifecycle      TEXT DEFAULT 'TRAINEE',              -- TRAINEE|GRADUATE|EMPLOYED|SUSPENDED|TERMINATED
  skills_json    TEXT DEFAULT '{}',
  certs_json     TEXT DEFAULT '[]',
  scores_json    TEXT DEFAULT '{}',
  permissions_json TEXT DEFAULT '[]',
  energy         REAL DEFAULT 100,
  performance    REAL DEFAULT 0.5,
  reliability    REAL DEFAULT 0.5,
  learning_progress REAL DEFAULT 0,
  tasks_done     INTEGER DEFAULT 0,
  tasks_failed   INTEGER DEFAULT 0,
  revenue_inr    REAL DEFAULT 0,
  cost_inr       REAL DEFAULT 0,
  risk           TEXT DEFAULT 'LOW',
  active_task_id TEXT,
  building       TEXT,
  pos_x          REAL DEFAULT 0,
  pos_y          REAL DEFAULT 0,
  target_building TEXT,
  created_at     REAL,
  updated_at     REAL,
  meta_json      TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_agents_dept ON agents(department_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);

CREATE TABLE IF NOT EXISTS tasks (
  id            TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  description   TEXT,
  task_type     TEXT DEFAULT 'general',
  department_id TEXT,
  assignee_id   TEXT,
  created_by    TEXT,
  status        TEXT DEFAULT 'QUEUED',   -- QUEUED|ASSIGNED|IN_PROGRESS|BLOCKED|VERIFYING|DONE|FAILED|CANCELLED
  priority      INTEGER DEFAULT 5,       -- 1 = highest
  payload_json  TEXT DEFAULT '{}',
  result_json   TEXT DEFAULT '{}',
  verification_json TEXT DEFAULT '{}',
  attempts      INTEGER DEFAULT 0,
  sla_hours     REAL,
  cost_inr      REAL DEFAULT 0,
  value_inr     REAL DEFAULT 0,
  created_at    REAL,
  started_at    REAL,
  completed_at  REAL,
  error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);

CREATE TABLE IF NOT EXISTS events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       REAL NOT NULL,
  type     TEXT NOT NULL,
  source   TEXT,
  subject  TEXT,
  severity TEXT DEFAULT 'info',          -- debug|info|notice|warning|error|critical
  payload_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS messages (
  id            TEXT PRIMARY KEY,
  ts            REAL,
  sender        TEXT,
  receiver      TEXT,
  department    TEXT,
  task_id       TEXT,
  priority      INTEGER DEFAULT 5,
  objective     TEXT,
  context       TEXT,
  requested_action TEXT,
  deadline      REAL,
  evidence_json TEXT DEFAULT '[]',
  result        TEXT,
  confidence    TEXT DEFAULT 'UNKNOWN',
  status        TEXT DEFAULT 'SENT'
);

CREATE TABLE IF NOT EXISTS memory (
  id          TEXT PRIMARY KEY,
  ts          REAL,
  agent_id    TEXT,
  layer       TEXT NOT NULL,   -- working|episodic|semantic|procedural|organizational|strategic
  key         TEXT,
  content     TEXT,
  source      TEXT,
  evidence_kind TEXT DEFAULT 'UNKNOWN',
  confidence  REAL DEFAULT 0.5,
  importance  REAL DEFAULT 0.5,
  expires_at  REAL,
  access_scope TEXT DEFAULT 'department',   -- own|department|organization|public
  tags_json   TEXT DEFAULT '[]',
  embedding_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory(agent_id, layer);
CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory(access_scope);

CREATE TABLE IF NOT EXISTS ledger (
  id          TEXT PRIMARY KEY,
  ts          REAL,
  direction   TEXT NOT NULL,      -- IN|OUT
  amount_inr  REAL NOT NULL,
  category    TEXT,
  description TEXT,
  source      TEXT,
  verified    INTEGER DEFAULT 0,
  evidence_json TEXT DEFAULT '{}',
  recorded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_ledger_ts ON ledger(ts);

CREATE TABLE IF NOT EXISTS opportunities (
  id            TEXT PRIMARY KEY,
  ts            REAL,
  title         TEXT,
  problem       TEXT,
  customer      TEXT,
  market        TEXT,
  competition   TEXT,
  required_skills_json TEXT DEFAULT '[]',
  required_capital_inr REAL DEFAULT 0,
  expected_revenue_inr REAL DEFAULT 0,
  expected_margin_pct  REAL DEFAULT 0,
  time_to_mvp_days     REAL,
  time_to_first_customer_days REAL,
  risk          TEXT DEFAULT 'MEDIUM',
  legal_risk    TEXT DEFAULT 'LOW',
  technical_risk TEXT DEFAULT 'MEDIUM',
  demand_confidence REAL DEFAULT 0.5,
  model_confidence  REAL DEFAULT 0.5,
  status        TEXT DEFAULT 'DISCOVERED',
  score         REAL DEFAULT 0,
  owner_agent   TEXT,
  evidence_json TEXT DEFAULT '[]',
  updated_at    REAL
);

CREATE TABLE IF NOT EXISTS experiments (
  id            TEXT PRIMARY KEY,
  ts            REAL,
  opportunity_id TEXT,
  hypothesis    TEXT,
  cost_inr      REAL DEFAULT 0,
  expected_result TEXT,
  mvp_definition TEXT,
  test_method   TEXT,
  success_metric TEXT,
  kill_metric   TEXT,
  decision_rule TEXT,
  status        TEXT DEFAULT 'DESIGNED',   -- DESIGNED|RUNNING|MEASURED|DECIDED|ABANDONED
  result_json   TEXT DEFAULT '{}',
  decision      TEXT,
  learning      TEXT,
  decided_at    REAL,
  owner_agent   TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
  id            TEXT PRIMARY KEY,
  ts            REAL,
  action        TEXT NOT NULL,
  risk          TEXT NOT NULL,
  requester     TEXT,
  requester_rank TEXT,
  department_id TEXT,
  what          TEXT,
  why           TEXT,
  expected_result TEXT,
  risk_notes    TEXT,
  reversibility TEXT,
  evidence_json TEXT DEFAULT '[]',
  status        TEXT DEFAULT 'PENDING',    -- PENDING|APPROVED|REJECTED|EDITED|DELAYED|EXPIRED
  decided_at    REAL,
  decision_note TEXT,
  expires_at    REAL,
  tool          TEXT,
  payload_json  TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, ts);

CREATE TABLE IF NOT EXISTS audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         REAL,
  actor      TEXT,
  actor_rank TEXT,
  action     TEXT,
  tool       TEXT,
  risk       TEXT,
  target     TEXT,
  allowed    INTEGER DEFAULT 1,
  reason     TEXT,
  payload_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);

CREATE TABLE IF NOT EXISTS exams (
  id            TEXT PRIMARY KEY,
  ts            REAL,
  agent_id      TEXT,
  track         TEXT,
  scores_json   TEXT DEFAULT '{}',
  total_score   REAL DEFAULT 0,
  threshold     REAL DEFAULT 0.6,
  passed        INTEGER DEFAULT 0,
  anti_hallucination_passed INTEGER DEFAULT 0,
  ethics_passed INTEGER DEFAULT 0,
  attempt       INTEGER DEFAULT 1,
  mode          TEXT DEFAULT 'full',   -- full (model assessed) | deterministic (model unavailable)
  assessed_json TEXT DEFAULT '{}',
  feedback      TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
  id       TEXT PRIMARY KEY,
  ts       REAL,
  source   TEXT,
  experiment_id TEXT,
  title    TEXT,
  lesson   TEXT,
  tags_json TEXT DEFAULT '[]',
  reusable INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS integrations (
  id          TEXT PRIMARY KEY,          -- gmail|youtube|instagram|facebook|whatsapp|gumroad
  status      TEXT DEFAULT 'DISCONNECTED',   -- CONNECTED|DISCONNECTED|ERROR|NO_CREDENTIALS
  scopes_json TEXT DEFAULT '[]',
  last_check  REAL,
  last_error  TEXT,
  calls_today INTEGER DEFAULT 0,
  quota_note  TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(paths.DB_PATH), timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


def conn() -> sqlite3.Connection:
    return _connect()


def init_db() -> None:
    c = _connect()
    with _write_lock:
        c.executescript(DDL)
        c.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES('schema_version', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (str(SCHEMA_VERSION), time.time()),
        )
        for name in ("gmail", "youtube", "instagram", "facebook", "whatsapp", "gumroad"):
            c.execute("INSERT OR IGNORE INTO integrations(id, status) VALUES(?, 'NO_CREDENTIALS')", (name,))


def now() -> float:
    return time.time()


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}-{raw}" if prefix else raw


def jdump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def jload(value: Any, default: Any = None) -> Any:
    if value in (None, "", b""):
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else {}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    c = _connect()
    with _write_lock:
        return c.execute(sql, params)


def executemany(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    c = _connect()
    with _write_lock:
        c.executemany(sql, rows)


def query(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    cur = _connect().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Sequence[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def insert(table: str, row: dict, *, replace: bool = False) -> dict:
    payload = {k: (_jsonify(v)) for k, v in row.items()}
    cols = ", ".join(payload.keys())
    marks = ", ".join("?" for _ in payload)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    execute(f"{verb} INTO {table} ({cols}) VALUES ({marks})", tuple(payload.values()))
    return row


def update(table: str, row_id: str, changes: dict, id_col: str = "id") -> None:
    if not changes:
        return
    payload = {k: _jsonify(v) for k, v in changes.items()}
    sets = ", ".join(f"{k}=?" for k in payload)
    execute(f"UPDATE {table} SET {sets} WHERE {id_col}=?", (*payload.values(), row_id))


def get(table: str, row_id: str, id_col: str = "id") -> dict | None:
    return query_one(f"SELECT * FROM {table} WHERE {id_col}=?", (row_id,))


def _jsonify(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    c = _connect()
    with _write_lock:
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------------------
# Settings & counters
# ---------------------------------------------------------------------------
def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, jdump(value) if isinstance(value, (dict, list)) else str(value), now()),
    )


def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if not row:
        return default
    raw = row["value"]
    if isinstance(raw, str):
        if raw[:1] in "[{":
            return jload(raw, default)
        # Booleans are stored as text; '"False"' must not become truthy.
        if raw.strip().lower() in ("true", "false"):
            return raw.strip().lower() == "true"
    return raw


def bump_counter(key: str, delta: int = 1) -> int:
    current = int(get_setting(key, 0) or 0) + delta
    set_setting(key, current)
    return current


def table_counts() -> dict[str, int]:
    out = {}
    for t in ("agents", "departments", "tasks", "events", "messages", "memory", "ledger",
              "opportunities", "experiments", "approvals", "audit", "exams", "lessons"):
        row = query_one(f"SELECT COUNT(*) AS n FROM {t}")
        out[t] = int(row["n"]) if row else 0
    return out


def db_size_bytes() -> int:
    try:
        return Path(paths.DB_PATH).stat().st_size
    except OSError:
        return 0
