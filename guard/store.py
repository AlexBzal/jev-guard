"""Registro de auditoría en SQLite: cada decisión, cada revisión humana, cada etiqueta."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Decision

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id   TEXT PRIMARY KEY,
    action_id     TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    action_type   TEXT NOT NULL,
    tier          TEXT NOT NULL,
    verdict       TEXT NOT NULL,      -- veredicto del guardián
    route         TEXT NOT NULL,
    status        TEXT NOT NULL,      -- final | pending_review
    final_verdict TEXT,               -- veredicto tras la revisión humana, si la hubo
    risk          REAL NOT NULL,
    latency_ms    REAL NOT NULL,
    jev_latency_ms REAL,
    input_tokens  INTEGER NOT NULL,
    cost_usd      REAL NOT NULL,
    llm_used      INTEGER NOT NULL,
    simulated     INTEGER,
    created_at    TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    action_json   TEXT NOT NULL,
    label_safe    INTEGER,            -- verdad de referencia: 1 segura, 0 insegura
    label_source  TEXT,               -- review | audit | dataset
    reviewer      TEXT,
    review_note   TEXT,
    reviewed_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_decisions_created ON decisions(created_at);
CREATE INDEX IF NOT EXISTS ix_decisions_status ON decisions(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def save(self, d: Decision, action: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO decisions (decision_id, action_id, agent_id, action_type, tier, verdict, route, status,
                   final_verdict, risk, latency_ms, jev_latency_ms, input_tokens, cost_usd, llm_used, simulated,
                   created_at, decision_json, action_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d.decision_id, d.action_id, d.agent_id, d.action_type, d.tier.value, d.verdict.value, d.route.value,
                 d.status, None if d.status == "pending_review" else d.verdict.value, d.risk, d.latency_ms,
                 d.jev_latency_ms, d.input_tokens, d.cost_usd, int(d.llm_used),
                 None if d.jev_simulated is None else int(d.jev_simulated), d.created_at.isoformat(),
                 d.model_dump_json(), json.dumps(action, ensure_ascii=False, default=str)),
            )
            self._conn.commit()

    # -- lectura -------------------------------------------------------------

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        out["decision"] = json.loads(out.pop("decision_json"))
        out["action"] = json.loads(out.pop("action_json"))
        for k in ("llm_used", "simulated", "label_safe"):
            if out.get(k) is not None:
                out[k] = bool(out[k])
        return out

    def get(self, decision_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM decisions WHERE decision_id=?", (decision_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, *, status: str | None = None, verdict: str | None = None, action_type: str | None = None,
             agent_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        where, args = [], []
        for col, val in (("status", status), ("verdict", verdict), ("action_type", action_type), ("agent_id", agent_id)):
            if val:
                where.append(f"{col}=?")
                args.append(val)
        sql = "SELECT * FROM decisions" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        with self._lock:
            rows = self._conn.execute(sql, (*args, limit, offset)).fetchall()
        return [self._row(r) for r in rows]

    def all_rows(self) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT decision_id, action_type, tier, verdict, route, status, final_verdict, risk, latency_ms, "
                "jev_latency_ms, input_tokens, cost_usd, llm_used, simulated, label_safe, created_at, agent_id "
                "FROM decisions").fetchall()

    # -- escritura humana ----------------------------------------------------

    def resolve_review(self, decision_id: str, approve: bool, reviewer: str, note: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute(
                """UPDATE decisions SET status='final', final_verdict=?, label_safe=?, label_source='review',
                   reviewer=?, review_note=?, reviewed_at=? WHERE decision_id=? AND status='pending_review'""",
                ("allow" if approve else "block", int(approve), reviewer, note, _now(), decision_id))
            self._conn.commit()
            changed = cur.rowcount
        return self.get(decision_id) if changed else None

    def label(self, decision_id: str, safe: bool, reviewer: str, note: str, source: str = "audit") -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute(
                """UPDATE decisions SET label_safe=?, label_source=?, reviewer=COALESCE(reviewer, ?),
                   review_note=COALESCE(NULLIF(?, ''), review_note), reviewed_at=? WHERE decision_id=?""",
                (int(safe), source, reviewer, note, _now(), decision_id))
            self._conn.commit()
            changed = cur.rowcount
        return self.get(decision_id) if changed else None

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM decisions")
            self._conn.commit()
