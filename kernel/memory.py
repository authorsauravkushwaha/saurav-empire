"""Hierarchical agent memory — six layers, with provenance the owner can inspect and delete.

Layers:
  working         current task scratchpad (short-lived)
  episodic        what happened (events the agent was part of)
  semantic        knowledge learned (facts, sources, confidence)
  procedural      how to perform tasks (playbooks, proven steps)
  organizational  department knowledge (shared inside the department namespace)
  strategic       long-term business objectives (readable by supervisors)

Every record carries: timestamp, source, evidence_kind, confidence, importance, expiry,
owner, access scope. Nothing is stored without provenance.
"""
from __future__ import annotations

import math
import time
from typing import Any, Iterable

from . import store
from .eventbus import E, bus

LAYERS = ("working", "episodic", "semantic", "procedural", "organizational", "strategic")
DEFAULT_TTL = {"working": 3600 * 6, "episodic": 3600 * 24 * 90, "semantic": None,
               "procedural": None, "organizational": None, "strategic": None}
IMPORTANCE_FLOOR = 0.15   # below this, expired records may be compacted away


class MemoryStore:
    # ---- write ---------------------------------------------------------
    def write(self, *, agent_id: str | None, layer: str, content: str, key: str = "",
              source: str = "agent", evidence_kind: str = "UNKNOWN", confidence: float = 0.5,
              importance: float = 0.5, access_scope: str = "department", tags: Iterable[str] | None = None,
              ttl_seconds: float | None = None, embed: bool = False) -> dict:
        if layer not in LAYERS:
            raise ValueError(f"Unknown memory layer '{layer}'. Allowed: {LAYERS}")
        expires_at = None
        ttl = DEFAULT_TTL.get(layer) if ttl_seconds is None else ttl_seconds
        if ttl:
            expires_at = time.time() + float(ttl)
        embedding_json = None
        if embed:
            try:
                from .model_router import router
                vec, method = router().embed(content)
                embedding_json = store.jdump({"method": method, "vector": vec})
            except Exception:
                embedding_json = None
        row = {
            "id": store.new_id("mem"), "ts": store.now(), "agent_id": agent_id, "layer": layer,
            "key": key, "content": content, "source": source, "evidence_kind": evidence_kind,
            "confidence": float(confidence), "importance": float(importance), "expires_at": expires_at,
            "access_scope": access_scope, "tags_json": store.jdump(list(tags or [])),
            "embedding_json": embedding_json,
        }
        store.insert("memory", row)
        bus.publish(E.MEMORY_WRITTEN, source="memory", subject=agent_id, severity="debug",
                    payload={"layer": layer, "key": key, "chars": len(content or "")})
        return row

    # ---- read ----------------------------------------------------------
    def read(self, *, agent_id: str | None = None, layers: Iterable[str] | None = None,
             keys: Iterable[str] | None = None, limit: int = 50) -> list[dict]:
        clauses, params = ["(expires_at IS NULL OR expires_at > ?)"], [time.time()]
        if agent_id:
            clauses.append("agent_id=?"); params.append(agent_id)
        if layers:
            layers = list(layers)
            clauses.append("layer IN (" + ",".join("?" * len(layers)) + ")"); params.extend(layers)
        if keys:
            keys = list(keys)
            clauses.append("key IN (" + ",".join("?" * len(keys)) + ")"); params.extend(keys)
        sql = f"SELECT * FROM memory WHERE {' AND '.join(clauses)} ORDER BY importance DESC, ts DESC LIMIT ?"
        params.append(limit)
        return [self._expand(r) for r in store.query(sql, tuple(params))]

    def search(self, query: str, *, agent_id: str | None = None, limit: int = 20,
               scope_ok: tuple[str, ...] = ("own", "department", "organization", "public")) -> list[dict]:
        """Lexical + optional vector search. Offline-safe: hash embeddings keep it working with no model."""
        rows = self.read(agent_id=agent_id, limit=2000)
        rows = [r for r in rows if r.get("access_scope") in scope_ok]
        if not rows:
            return []
        terms = [t for t in (query or "").lower().split() if len(t) > 2]
        q_vec = None
        try:
            from .model_router import router
            q_vec, _ = router().embed(query or "")
        except Exception:
            q_vec = None

        scored: list[tuple[float, dict]] = []
        for row in rows:
            text = (row.get("content") or "").lower()
            lexical = sum(text.count(t) for t in terms) / (len(terms) or 1)
            recency = 1.0 / (1.0 + max(0.0, (time.time() - float(row.get("ts") or 0)) / 86400.0))
            score = (lexical * 0.6) + (float(row.get("importance") or 0.5) * 0.25) + (recency * 0.15)
            if q_vec and row.get("embedding"):
                vec = row["embedding"].get("vector") if isinstance(row["embedding"], dict) else None
                if vec:
                    score += 0.35 * max(0.0, self._cosine(q_vec, vec))
            scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, row in scored[:limit]:
            row = dict(row)
            row["relevance"] = round(score, 4)
            out.append(row)
        return out

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if not n:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(n))
        na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
        nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
        return dot / (na * nb)

    def _expand(self, row: dict) -> dict:
        row["tags"] = store.jload(row.pop("tags_json", None), [])
        row["embedding"] = store.jload(row.pop("embedding_json", None), None)
        return row

    # ---- housekeeping --------------------------------------------------
    def delete(self, memory_id: str, *, by: str = "OWNER") -> bool:
        if not store.get("memory", memory_id):
            return False
        store.execute("DELETE FROM memory WHERE id=?", (memory_id,))
        store.insert("audit", {"ts": store.now(), "actor": by, "action": "memory.delete",
                               "target": memory_id, "allowed": 1, "reason": "owner deletion request"})
        return True

    def purge_expired(self, *, keep_important_above: float = 0.7) -> int:
        cur = store.execute(
            "DELETE FROM memory WHERE expires_at IS NOT NULL AND expires_at < ? AND importance < ?",
            (time.time(), keep_important_above),
        )
        return cur.rowcount or 0

    def stats(self) -> dict:
        by_layer = {r["layer"]: int(r["n"]) for r in store.query(
            "SELECT layer, COUNT(*) n FROM memory GROUP BY layer")}
        total = store.query_one("SELECT COUNT(*) n FROM memory")["n"]
        embedded = store.query_one("SELECT COUNT(*) n FROM memory WHERE embedding_json IS NOT NULL")["n"]
        return {"total": total, "by_layer": by_layer, "embedded": embedded,
                "layers": list(LAYERS)}

    # ---- convenience ---------------------------------------------------
    def working(self, agent_id: str, content: str, key: str = "current") -> dict:
        return self.write(agent_id=agent_id, layer="working", key=key, content=content,
                          source="agent", evidence_kind="FACT", confidence=0.8, importance=0.3,
                          access_scope="own")

    def episodic(self, agent_id: str, content: str, importance: float = 0.4) -> dict:
        return self.write(agent_id=agent_id, layer="episodic", content=content, source="runtime",
                          evidence_kind="FACT", confidence=0.9, importance=importance, access_scope="own")

    def semantic(self, agent_id: str, content: str, *, source: str, evidence_kind: str = "FACT",
                 confidence: float = 0.7, importance: float = 0.6, tags: list[str] | None = None) -> dict:
        return self.write(agent_id=agent_id, layer="semantic", content=content, source=source,
                          evidence_kind=evidence_kind, confidence=confidence, importance=importance,
                          access_scope="organization", tags=tags)

    def procedural(self, agent_id: str, content: str, key: str) -> dict:
        return self.write(agent_id=agent_id, layer="procedural", key=key, content=content,
                          source="learned", evidence_kind="INFERENCE", confidence=0.6,
                          importance=0.7, access_scope="department")

    def organizational(self, department_id: str, content: str, key: str = "") -> dict:
        return self.write(agent_id=None, layer="organizational", key=key or department_id,
                          content=content, source=f"department:{department_id}", evidence_kind="FACT",
                          confidence=0.7, importance=0.6, access_scope="department",
                          tags=[department_id])

    def strategic(self, content: str, key: str) -> dict:
        return self.write(agent_id=None, layer="strategic", key=key, content=content, source="owner",
                          evidence_kind="FACT", confidence=0.9, importance=0.9, access_scope="organization")


memory = MemoryStore()
