"""The one-page monthly report for leadership. Every figure comes from the database; the optional summary
paragraph is written by a model from those same figures, recorded, and labelled as AI-written on the page."""

from __future__ import annotations

import calendar
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .db import meta
from .llm import LLM, CacheMiss
from .value import ToolValue, TrainingEffect, full_months, tool_values, training_effect

SUMMARY_SYSTEM = (
    "You write a short summary paragraph for a company's monthly AI governance report to its leadership team. "
    "Use only the figures given. Plain English, no jargon, 70-110 words, no headings or bullet points. "
    'Return JSON: {"summary": "..."}'
)


@dataclass
class Report:
    company: str
    month: str
    month_label: str
    as_of: str
    currency: str
    hourly_cost: float
    tools: list[ToolValue]
    by_level: dict[str, int]
    by_tier: dict[str, int]
    month_totals: dict[str, float]
    window_totals: dict[str, float]
    incidents: list[sqlite3.Row]
    open_incidents: list[sqlite3.Row]
    overdue: list[sqlite3.Row]
    pending: list[sqlite3.Row]
    blocked: list[sqlite3.Row]
    under_used: list[ToolValue]
    training: TrainingEffect
    decisions: list[str] = field(default_factory=list)
    summary: str = ""
    summary_note: str = ""

    def facts(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "month": self.month_label,
            "tools_in_use": sum(self.by_level.values()),
            "by_risk_level": self.by_level,
            "hours_saved_measured": round(self.month_totals["measured_hours"]),
            "hours_saved_estimated_at_intake": round(self.month_totals["est_hours"]),
            "net_value": round(self.month_totals["net"]),
            "currency": self.currency,
            "incidents_this_month": len(self.incidents),
            "open_incidents": len(self.open_incidents),
            "overdue_reviews": [r["name"] for r in self.overdue],
            "waiting_for_approval": [r["title"] for r in self.pending],
            "blocked": [r["title"] for r in self.blocked],
            "under_used": [t.name for t in self.under_used],
            "decisions_needed": self.decisions,
        }


def build(conn: sqlite3.Connection, month: str | None = None, with_summary: bool = True, llm: LLM | None = None) -> Report:
    months = full_months(conn)
    month = month if month in months else months[-1]
    y, m = int(month[:4]), int(month[5:])
    end = date(y, m, calendar.monthrange(y, m)[1]).isoformat()
    tools = tool_values(conn)
    live = [t for t in tools if t.status != "retired"]
    reg = conn.execute("SELECT * FROM register WHERE status != 'retired' AND approved_at <= ?", (end,)).fetchall()
    by_level = {lvl: sum(r["level"] == lvl for r in reg) for lvl in ("high", "medium", "low")}
    by_tier = {t: sum(r["tier"] == t for r in reg) for t in ("high", "limited", "minimal")}

    def totals(ms: list[str]) -> dict[str, float]:
        agg = [t.totals(ms) for t in live]
        out = {k: sum(getattr(a, k) for a in agg) for k in ("tasks", "est_hours", "measured_hours", "gross", "cost")}
        out["net"] = out["gross"] - out["cost"]
        return out

    incidents = conn.execute("SELECT i.*, r.name AS tool FROM incidents i JOIN register r ON r.id = i.tool_id WHERE substr(i.happened_on, 1, 7) = ? ORDER BY i.happened_on", (month,)).fetchall()
    open_inc = conn.execute("SELECT i.*, r.name AS tool FROM incidents i JOIN register r ON r.id = i.tool_id WHERE i.status = 'open' AND i.happened_on <= ? ORDER BY i.happened_on", (end,)).fetchall()
    overdue = conn.execute("SELECT * FROM register WHERE status != 'retired' AND review_due < ? AND approved_at <= ? ORDER BY review_due", (end, end)).fetchall()
    pending = conn.execute("SELECT * FROM submissions WHERE status = 'in_review' AND created_at <= ? ORDER BY created_at", (end + "T23:59:59",)).fetchall()
    blocked = conn.execute("SELECT * FROM submissions WHERE status = 'blocked' AND substr(created_at, 1, 7) = ?", (month,)).fetchall()
    under = [t for t in live if t.under_used]
    r = Report(
        company=meta(conn, "company"), month=month, month_label=f"{calendar.month_name[m]} {y}", as_of=meta(conn, "as_of"),
        currency=meta(conn, "currency", "EUR"), hourly_cost=float(meta(conn, "hourly_cost", "40")), tools=live, by_level=by_level,
        by_tier=by_tier, month_totals=totals([month]), window_totals=totals(months), incidents=incidents, open_incidents=open_inc,
        overdue=overdue, pending=pending, blocked=blocked, under_used=under, training=training_effect(conn, tools),
    )  # fmt: skip
    for row in overdue:
        r.decisions.append(f"Review {row['name']} ({row['level']} risk): review was due {row['review_due']}.")
    for inc in open_inc:
        if inc["severity"] == "high":
            r.decisions.append(f"Decide on {inc['tool']}: open high-severity incident from {inc['happened_on']}.")
    for t in under:
        r.decisions.append(f"{t.name}: {t.recommendation}")
    if pending:
        r.decisions.append(f"{len(pending)} use case(s) waiting for approval.")
    if with_summary:
        llm = llm or LLM()
        try:
            res = llm.chat_json(SUMMARY_SYSTEM, json.dumps(r.facts(), ensure_ascii=False, sort_keys=True))
            r.summary = str(json.loads(res.content).get("summary", "")).strip()
            r.summary_note = f"Written by an AI model ({llm.model}) from the figures on this page and recorded. Check it before sending."
        except (CacheMiss, json.JSONDecodeError, AttributeError):
            r.summary_note = "No AI-written summary for this month (it needs a model key the first time). The figures below do not depend on it."
    return r
