"""SQLite storage. The audit log is append-only: database triggers reject UPDATE and DELETE, and each row carries
a SHA-256 hash of the previous row, so any edit made outside the app shows up as a broken chain."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.environ.get("HUB_DB", Path(__file__).resolve().parent.parent / "data" / "hub.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, team TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY, lead_id INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS staff (id INTEGER PRIMARY KEY, team TEXT NOT NULL, office TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, team TEXT NOT NULL, requester_id INTEGER NOT NULL REFERENCES users(id),
  intake TEXT NOT NULL, assessment TEXT NOT NULL, tier TEXT NOT NULL, level TEXT NOT NULL, status TEXT NOT NULL,
  prefilled TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL REFERENCES submissions(id), step INTEGER NOT NULL,
  role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', approver_id INTEGER REFERENCES users(id),
  comment TEXT NOT NULL DEFAULT '', decided_at TEXT);
CREATE TABLE IF NOT EXISTS controls (
  submission_id INTEGER NOT NULL REFERENCES submissions(id), control_id TEXT NOT NULL, name TEXT NOT NULL,
  required INTEGER NOT NULL, source TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, evidence TEXT NOT NULL DEFAULT '',
  done_by INTEGER REFERENCES users(id), done_at TEXT, PRIMARY KEY (submission_id, control_id));
CREATE TABLE IF NOT EXISTS register (
  id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL UNIQUE REFERENCES submissions(id), name TEXT NOT NULL,
  owner_id INTEGER NOT NULL REFERENCES users(id), team TEXT NOT NULL, purpose TEXT NOT NULL, tier TEXT NOT NULL,
  annex_point TEXT, level TEXT NOT NULL, vendor TEXT NOT NULL, model TEXT NOT NULL, data TEXT NOT NULL,
  region TEXT NOT NULL, approved_at TEXT NOT NULL, last_review TEXT NOT NULL, review_due TEXT NOT NULL,
  status TEXT NOT NULL, est_minutes_per_task REAL NOT NULL DEFAULT 0, setup_cost REAL NOT NULL DEFAULT 0,
  monthly_fee REAL NOT NULL DEFAULT 0, cost_per_task REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS eligible (tool_id INTEGER NOT NULL REFERENCES register(id), staff_id INTEGER NOT NULL REFERENCES staff(id),
  PRIMARY KEY (tool_id, staff_id));
CREATE TABLE IF NOT EXISTS activity (
  tool_id INTEGER NOT NULL REFERENCES register(id), staff_id INTEGER NOT NULL, week TEXT NOT NULL, tasks INTEGER NOT NULL,
  PRIMARY KEY (tool_id, staff_id, week));
CREATE TABLE IF NOT EXISTS weekly (
  tool_id INTEGER NOT NULL REFERENCES register(id), week TEXT NOT NULL, eligible INTEGER NOT NULL, active_users INTEGER NOT NULL,
  tasks INTEGER NOT NULL, overrides INTEGER NOT NULL, errors INTEGER NOT NULL, model_cost REAL NOT NULL, PRIMARY KEY (tool_id, week));
CREATE TABLE IF NOT EXISTS time_samples (
  tool_id INTEGER NOT NULL REFERENCES register(id), month TEXT NOT NULL, sampled_tasks INTEGER NOT NULL,
  minutes_without REAL NOT NULL, minutes_with REAL NOT NULL, PRIMARY KEY (tool_id, month));
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY, tool_id INTEGER NOT NULL REFERENCES register(id), happened_on TEXT NOT NULL, severity TEXT NOT NULL,
  summary TEXT NOT NULL, status TEXT NOT NULL, reported_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS training (
  id INTEGER PRIMARY KEY, tool_id INTEGER NOT NULL REFERENCES register(id), title TEXT NOT NULL, minutes INTEGER NOT NULL,
  kind TEXT NOT NULL, summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_done (
  training_id INTEGER NOT NULL REFERENCES training(id), staff_id INTEGER NOT NULL, completed_on TEXT NOT NULL,
  PRIMARY KEY (training_id, staff_id));
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor_id INTEGER, actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL,
  entity TEXT NOT NULL, entity_id INTEGER, before TEXT NOT NULL, after TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE INDEX IF NOT EXISTS activity_week ON activity (week);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or DEFAULT_DB)
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def _hash(prev: str, fields: list[Any]) -> str:
    return hashlib.sha256((prev + "|" + json.dumps(fields, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def audit(
    conn: sqlite3.Connection, ts: str, actor: sqlite3.Row | None, action: str, entity: str, entity_id: int | None, before: Any, after: Any
) -> None:
    """Append one entry. Called inside the same transaction as the change it records."""
    last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["hash"] if last else "genesis"
    name = actor["name"] if actor else "system"
    role = actor["role"] if actor else "system"
    b = json.dumps(before, sort_keys=True, ensure_ascii=False) if before is not None else "{}"
    a = json.dumps(after, sort_keys=True, ensure_ascii=False) if after is not None else "{}"
    h = _hash(prev, [ts, actor["id"] if actor else None, name, role, action, entity, entity_id, b, a])
    conn.execute(
        "INSERT INTO audit_log (ts, actor_id, actor, role, action, entity, entity_id, before, after, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ts, actor["id"] if actor else None, name, role, action, entity, entity_id, b, a, prev, h),
    )


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int]:
    """Recompute every hash. Returns (intact, number of entries checked)."""
    prev = "genesis"
    n = 0
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        n += 1
        expect = _hash(prev, [r["ts"], r["actor_id"], r["actor"], r["role"], r["action"], r["entity"], r["entity_id"], r["before"], r["after"]])
        if r["prev_hash"] != prev or r["hash"] != expect:
            return False, n
        prev = r["hash"]
    return True, n


def audit_csv(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cols = ["id", "ts", "actor", "role", "action", "entity", "entity_id", "before", "after", "hash"]
    w.writerow(cols)
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        w.writerow([r[c] for c in cols])
    return buf.getvalue()
