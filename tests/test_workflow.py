"""Permission tests: nobody approves their own idea, nobody skips a step, the auditor changes nothing."""

from __future__ import annotations

import sqlite3

import pytest

from governance_hub.workflow import PermissionDenied, add_months, can_decide, decide, record_review, report_incident, set_control, set_tool_status, submit
from tests.conftest import by_name, make

NOW = "2026-10-25T10:00:00"


def high_idea(conn: sqlite3.Connection) -> int:
    sub, a = submit(conn, by_name(conn, "Emma Clarke"), make(use_area="recruitment", flags=["about_individuals"], data_categories=["personal"], people_regions=["EU"], vendor="V"), NOW)
    assert a.level == "high"
    return sub


def test_low_risk_needs_only_the_team_lead(db: sqlite3.Connection) -> None:
    sub, a = submit(db, by_name(db, "Emma Clarke"), make(), NOW)
    assert a.level == "low"
    assert decide(db, by_name(db, "Jack Morris"), sub, True, "ok", NOW) == "approved"
    reg = db.execute("SELECT * FROM register WHERE submission_id = ?", (sub,)).fetchone()
    assert reg["status"] == "pilot" and reg["review_due"] == "2028-10-25"


def test_nobody_can_approve_their_own_submission(db: sqlite3.Connection) -> None:
    lead = by_name(db, "Jack Morris")
    sub, _ = submit(db, lead, make(), NOW)
    with pytest.raises(PermissionDenied, match="own submission"):
        decide(db, lead, sub, True, "", NOW)
    # the team lead asked, so the AI governance lead stands in for that step
    assert decide(db, by_name(db, "Daniel Hughes"), sub, True, "", NOW) == "approved"


def test_governance_lead_cannot_approve_own_idea_either(db: sqlite3.Connection) -> None:
    gov = by_name(db, "Daniel Hughes")
    sub, _ = submit(db, gov, make(team="Leadership"), NOW)
    assert can_decide(db, gov, sub) == "Nobody can approve their own submission."


def test_only_the_requesters_own_team_lead(db: sqlite3.Connection) -> None:
    sub, _ = submit(db, by_name(db, "Emma Clarke"), make(), NOW)
    with pytest.raises(PermissionDenied, match="Customer Service team lead"):
        decide(db, by_name(db, "Noah Price"), sub, True, "", NOW)


def test_steps_cannot_be_skipped(db: sqlite3.Connection) -> None:
    sub = high_idea(db)
    for name in ("Olivia Bennett", "Daniel Hughes"):
        with pytest.raises(PermissionDenied):
            decide(db, by_name(db, name), sub, True, "", NOW)
    decide(db, by_name(db, "Jack Morris"), sub, True, "", NOW)
    with pytest.raises(PermissionDenied, match="risk and privacy reviewer"):
        decide(db, by_name(db, "Daniel Hughes"), sub, True, "", NOW)
    decide(db, by_name(db, "Olivia Bennett"), sub, True, "", NOW)


def test_high_risk_needs_every_required_control_before_final_approval(db: sqlite3.Connection) -> None:
    sub = high_idea(db)
    decide(db, by_name(db, "Jack Morris"), sub, True, "", NOW)
    decide(db, by_name(db, "Olivia Bennett"), sub, True, "", NOW)
    gov = by_name(db, "Daniel Hughes")
    with pytest.raises(PermissionDenied, match="Required controls are not complete"):
        decide(db, gov, sub, True, "", NOW)
    emma = by_name(db, "Emma Clarke")
    with pytest.raises(PermissionDenied, match="Say what was done"):
        set_control(db, emma, sub, "logging", True, "  ", NOW)
    for c in db.execute("SELECT control_id FROM controls WHERE submission_id = ? AND required = 1", (sub,)).fetchall():
        set_control(db, emma, sub, c["control_id"], True, "done, see file", NOW)
    assert decide(db, gov, sub, True, "", NOW) == "approved"
    assert db.execute("SELECT review_due FROM register WHERE submission_id = ?", (sub,)).fetchone()[0] == "2027-04-25"


def test_prohibited_ideas_are_blocked_with_no_approval_route(db: sqlite3.Connection) -> None:
    sub, a = submit(db, by_name(db, "Emma Clarke"), make(use_area="emotion_recognition", flags=["workplace_or_education"]), NOW)
    assert a.level == "prohibited"
    assert db.execute("SELECT status FROM submissions WHERE id = ?", (sub,)).fetchone()[0] == "blocked"
    assert db.execute("SELECT COUNT(*) FROM approvals WHERE submission_id = ?", (sub,)).fetchone()[0] == 0
    with pytest.raises(PermissionDenied, match="blocked"):
        decide(db, by_name(db, "Daniel Hughes"), sub, True, "", NOW)


def test_rejection_stops_the_route(db: sqlite3.Connection) -> None:
    sub = high_idea(db)
    assert decide(db, by_name(db, "Jack Morris"), sub, False, "no", NOW) == "rejected"
    with pytest.raises(PermissionDenied):
        decide(db, by_name(db, "Olivia Bennett"), sub, True, "", NOW)


def test_auditor_is_read_only(db: sqlite3.Connection) -> None:
    aud = by_name(db, "Sophie Turner")
    sub = high_idea(db)
    tool = db.execute("SELECT id FROM register LIMIT 1").fetchone()[0]
    before = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    for action in (
        lambda: submit(db, aud, make(), NOW),
        lambda: decide(db, aud, sub, True, "", NOW),
        lambda: set_control(db, aud, sub, "logging", True, "x", NOW),
        lambda: set_tool_status(db, aud, tool, "retired", NOW),
        lambda: record_review(db, aud, tool, "", NOW),
        lambda: report_incident(db, aud, tool, "low", "x", "2026-10-25", NOW),
    ):
        with pytest.raises(PermissionDenied):
            action()
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before


def test_review_moves_the_due_date(db: sqlite3.Connection) -> None:
    tool = db.execute("SELECT id FROM register WHERE name = 'CV screening shortlist helper'").fetchone()[0]
    with pytest.raises(PermissionDenied):
        record_review(db, by_name(db, "Emma Clarke"), tool, "", NOW)
    assert record_review(db, by_name(db, "Olivia Bennett"), tool, "Bias fix checked", NOW) == "2027-04-25"


def test_add_months_clamps_month_end() -> None:
    from datetime import date

    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2027, 8, 31), 6) == date(2028, 2, 29)
