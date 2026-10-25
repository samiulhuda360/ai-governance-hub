from __future__ import annotations

import csv
import io
import json
import sqlite3

import pytest

from governance_hub.db import audit_csv, verify_chain
from governance_hub.workflow import decide, submit
from tests.conftest import by_name, make


def test_seeded_log_is_complete_and_in_time_order(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT ts FROM audit_log ORDER BY id").fetchall()
    assert len(rows) > 50
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)
    assert verify_chain(db) == (True, len(rows))


def test_updates_and_deletes_are_rejected(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE audit_log SET actor = 'someone else' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM audit_log WHERE id = 1")


def test_tampering_breaks_the_hash_chain(db: sqlite3.Connection) -> None:
    db.execute("DROP TRIGGER audit_no_update")  # someone with direct database access
    db.execute('UPDATE audit_log SET after = \'{"status": "approved"}\' WHERE id = 5')
    ok, at = verify_chain(db)
    assert not ok and at == 5


def test_each_action_records_who_when_before_and_after(db: sqlite3.Connection) -> None:
    sub, _ = submit(db, by_name(db, "Emma Clarke"), make(), "2026-10-25T09:00:00")
    decide(db, by_name(db, "Jack Morris"), sub, True, "fine", "2026-10-25T09:30:00")
    rows = db.execute("SELECT * FROM audit_log WHERE ts LIKE '2026-10-25T09%' ORDER BY id").fetchall()
    assert [(r["actor"], r["action"]) for r in rows] == [("Emma Clarke", "submit"), ("Jack Morris", "approved"), ("Jack Morris", "status"), ("Jack Morris", "register")]
    status = rows[2]
    assert json.loads(status["before"]) == {"status": "in_review"} and json.loads(status["after"]) == {"status": "approved"}
    assert verify_chain(db)[0]


def test_csv_export(db: sqlite3.Connection) -> None:
    rows = list(csv.reader(io.StringIO(audit_csv(db))))
    assert rows[0] == ["id", "ts", "actor", "role", "action", "entity", "entity_id", "before", "after", "hash"]
    assert len(rows) - 1 == db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
