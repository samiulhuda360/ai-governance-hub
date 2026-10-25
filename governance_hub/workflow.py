"""Submission, approval routing, controls checklist and the AI register, with every change in the audit log.

Who must approve, by overall risk level (approvals happen in this order):

    low         team lead
    medium      team lead, then risk and privacy reviewer
    high        team lead, then risk and privacy reviewer, then AI governance lead (all required controls done)
    prohibited  blocked at submission; nobody can approve it

Nobody can approve their own submission. The auditor can read everything and change nothing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from .db import audit
from .engine import Assessment, assess, review_months
from .intake import Intake

ROLES = {
    "requester": "Requester",
    "team_lead": "Team lead",
    "risk_reviewer": "Risk and privacy reviewer",
    "governance_lead": "AI governance lead",
    "auditor": "Auditor (read-only)",
}
STEPS = {"low": ["team_lead"], "medium": ["team_lead", "risk_reviewer"], "high": ["team_lead", "risk_reviewer", "governance_lead"]}


class PermissionDenied(Exception):
    """The action is not allowed for this person, with the reason in plain words."""


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    month_days = [31, 29 if (d.year + y) % 4 == 0 and ((d.year + y) % 100 != 0 or (d.year + y) % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(d.year + y, m + 1, min(d.day, month_days[m]))


def user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise PermissionDenied("Unknown user.")
    return row


def _sub(conn: sqlite3.Connection, sub_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone()
    if row is None:
        raise PermissionDenied("No such submission.")
    return row


def _not_auditor(actor: sqlite3.Row) -> None:
    if actor["role"] == "auditor":
        raise PermissionDenied("The auditor role is read-only.")


def submit(conn: sqlite3.Connection, actor: sqlite3.Row, intake: Intake, now: str, prefilled: list[str] | None = None) -> tuple[int, Assessment]:
    _not_auditor(actor)
    a = assess(intake)
    status = "blocked" if a.tier == "prohibited" else "in_review"
    with conn:
        cur = conn.execute(
            "INSERT INTO submissions (title, team, requester_id, intake, assessment, tier, level, status, prefilled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (intake.title, intake.team, actor["id"], intake.model_dump_json(), json.dumps(a.to_dict()), a.tier, a.level, status, json.dumps(prefilled or []), now, now),
        )
        sub_id = int(cur.lastrowid or 0)
        for i, role in enumerate(STEPS.get(a.level, []), start=1):
            conn.execute("INSERT INTO approvals (submission_id, step, role) VALUES (?,?,?)", (sub_id, i, role))
        for c in a.controls:
            conn.execute("INSERT INTO controls (submission_id, control_id, name, required, source) VALUES (?,?,?,?,?)", (sub_id, c.id, c.name, int(c.required), c.source))
        audit(conn, now, actor, "submit", "submission", sub_id, None, {"title": intake.title, "tier": a.tier, "level": a.level, "status": status, "prefilled_fields": prefilled or []})
        if status == "blocked":
            audit(conn, now, None, "block", "submission", sub_id, {"status": "submitted"}, {"status": "blocked", "reason": a.summary()})
    return sub_id, a


def next_step(conn: sqlite3.Connection, sub_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute("SELECT * FROM approvals WHERE submission_id = ? AND status = 'pending' ORDER BY step LIMIT 1", (sub_id,)).fetchone()
    return row


def team_lead_of(conn: sqlite3.Connection, team: str) -> int | None:
    row = conn.execute("SELECT lead_id FROM teams WHERE name = ?", (team,)).fetchone()
    return int(row["lead_id"]) if row and row["lead_id"] is not None else None


def can_decide(conn: sqlite3.Connection, actor: sqlite3.Row, sub_id: int) -> str | None:
    """None when the actor may decide the current step; otherwise the reason they may not."""
    sub = _sub(conn, sub_id)
    if actor["role"] == "auditor":
        return "The auditor role is read-only."
    if sub["status"] != "in_review":
        return f"This submission is {sub['status'].replace('_', ' ')}, so there is nothing to approve."
    if sub["requester_id"] == actor["id"]:
        return "Nobody can approve their own submission."
    step = next_step(conn, sub_id)
    if step is None:
        return "No approval step is waiting."
    if step["role"] == "team_lead":
        lead = team_lead_of(conn, sub["team"])
        if lead == sub["requester_id"]:  # the team lead asked: the governance lead stands in
            if actor["role"] != "governance_lead":
                return "The requester leads this team, so the AI governance lead approves this step."
        elif actor["role"] != "team_lead" or actor["id"] != lead:
            return f"Step {step['step']} needs the {sub['team']} team lead."
    elif actor["role"] != step["role"]:
        return f"Step {step['step']} needs the {ROLES[step['role']].lower()}; earlier steps cannot be skipped."
    if step["role"] == "governance_lead":
        open_controls = conn.execute("SELECT name FROM controls WHERE submission_id = ? AND required = 1 AND done = 0", (sub_id,)).fetchall()
        if open_controls:
            return "Required controls are not complete: " + "; ".join(r["name"] for r in open_controls) + "."
    return None


def decide(conn: sqlite3.Connection, actor: sqlite3.Row, sub_id: int, approve: bool, comment: str, now: str) -> str:
    reason = can_decide(conn, actor, sub_id)
    if reason:
        raise PermissionDenied(reason)
    sub = _sub(conn, sub_id)
    step = next_step(conn, sub_id)
    assert step is not None
    decision = "approved" if approve else "rejected"
    with conn:
        conn.execute("UPDATE approvals SET status = ?, approver_id = ?, comment = ?, decided_at = ? WHERE id = ?", (decision, actor["id"], comment, now, step["id"]))
        audit(conn, now, actor, decision, "approval", step["id"], {"step": step["step"], "role": step["role"], "status": "pending"}, {"status": decision, "comment": comment})
        new_status: str = sub["status"]
        if not approve:
            new_status = "rejected"
        elif next_step(conn, sub_id) is None:
            new_status = "approved"
        if new_status != sub["status"]:
            conn.execute("UPDATE submissions SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, sub_id))
            audit(conn, now, actor, "status", "submission", sub_id, {"status": sub["status"]}, {"status": new_status})
        if new_status == "approved":
            _register(conn, actor, sub_id, now)
    return new_status


def set_control(conn: sqlite3.Connection, actor: sqlite3.Row, sub_id: int, control_id: str, done: bool, evidence: str, now: str) -> None:
    _not_auditor(actor)
    sub = _sub(conn, sub_id)
    allowed = actor["id"] == sub["requester_id"] or actor["role"] in ("risk_reviewer", "governance_lead") or actor["id"] == team_lead_of(conn, sub["team"])
    if not allowed:
        raise PermissionDenied("Only the requester, their team lead, or a reviewer can update controls.")
    if sub["status"] not in ("in_review",):
        raise PermissionDenied("Controls can only change while the submission is in review.")
    row = conn.execute("SELECT * FROM controls WHERE submission_id = ? AND control_id = ?", (sub_id, control_id)).fetchone()
    if row is None:
        raise PermissionDenied("No such control on this submission.")
    if done and not evidence.strip():
        raise PermissionDenied("Say what was done (a link or a short note) before ticking a control.")
    with conn:
        conn.execute(
            "UPDATE controls SET done = ?, evidence = ?, done_by = ?, done_at = ? WHERE submission_id = ? AND control_id = ?",
            (int(done), evidence.strip(), actor["id"], now, sub_id, control_id),
        )
        audit(
            conn,
            now,
            actor,
            "control",
            "submission",
            sub_id,
            {"control": control_id, "done": bool(row["done"]), "evidence": row["evidence"]},
            {"control": control_id, "done": done, "evidence": evidence.strip()},
        )


def _register(conn: sqlite3.Connection, actor: sqlite3.Row, sub_id: int, now: str) -> int:
    sub = _sub(conn, sub_id)
    it = Intake.model_validate_json(sub["intake"])
    a = json.loads(sub["assessment"])
    approved = date.fromisoformat(now[:10])
    due = add_months(approved, review_months(sub["level"])).isoformat()
    cur = conn.execute(
        "INSERT INTO register (submission_id, name, owner_id, team, purpose, tier, annex_point, level, vendor, model, data, region, approved_at, last_review, review_due, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pilot')",
        (sub_id, it.title, sub["requester_id"], it.team, it.purpose, sub["tier"], a.get("annex_point"), sub["level"], it.vendor, it.model,
         json.dumps(it.data_categories), it.processing_region, now[:10], now[:10], due),
    )  # fmt: skip
    rid = int(cur.lastrowid or 0)
    audit(conn, now, actor, "register", "register", rid, None, {"name": it.title, "status": "pilot", "review_due": due})
    return rid


def set_tool_status(conn: sqlite3.Connection, actor: sqlite3.Row, tool_id: int, status: str, now: str) -> None:
    if status not in ("pilot", "live", "retired"):
        raise PermissionDenied("Status must be pilot, live or retired.")
    if actor["role"] != "governance_lead":
        raise PermissionDenied("Only the AI governance lead changes a tool's status.")
    row = conn.execute("SELECT status FROM register WHERE id = ?", (tool_id,)).fetchone()
    if row is None:
        raise PermissionDenied("No such tool.")
    with conn:
        conn.execute("UPDATE register SET status = ? WHERE id = ?", (status, tool_id))
        audit(conn, now, actor, "status", "register", tool_id, {"status": row["status"]}, {"status": status})


def record_review(conn: sqlite3.Connection, actor: sqlite3.Row, tool_id: int, note: str, now: str) -> str:
    if actor["role"] not in ("risk_reviewer", "governance_lead"):
        raise PermissionDenied("Only a risk reviewer or the AI governance lead can record a review.")
    row = conn.execute("SELECT * FROM register WHERE id = ?", (tool_id,)).fetchone()
    if row is None:
        raise PermissionDenied("No such tool.")
    due = add_months(date.fromisoformat(now[:10]), review_months(row["level"])).isoformat()
    with conn:
        conn.execute("UPDATE register SET last_review = ?, review_due = ? WHERE id = ?", (now[:10], due, tool_id))
        audit(
            conn,
            now,
            actor,
            "review",
            "register",
            tool_id,
            {"last_review": row["last_review"], "review_due": row["review_due"]},
            {"last_review": now[:10], "review_due": due, "note": note},
        )
    return due


def report_incident(conn: sqlite3.Connection, actor: sqlite3.Row, tool_id: int, severity: str, summary: str, happened_on: str, now: str) -> int:
    _not_auditor(actor)
    if severity not in ("low", "medium", "high"):
        raise PermissionDenied("Severity must be low, medium or high.")
    with conn:
        cur = conn.execute(
            "INSERT INTO incidents (tool_id, happened_on, severity, summary, status, reported_by) VALUES (?,?,?,?, 'open', ?)",
            (tool_id, happened_on, severity, summary, actor["id"]),
        )
        iid = int(cur.lastrowid or 0)
        audit(conn, now, actor, "incident", "incident", iid, None, {"tool_id": tool_id, "severity": severity, "summary": summary})
    return iid
