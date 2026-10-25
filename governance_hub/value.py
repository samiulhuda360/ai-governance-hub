"""Adoption, value and training figures, computed from the stored usage. No model is involved.

Definitions (shown on the dashboard next to each figure):

- adoption: average weekly active users over the last 4 weeks divided by eligible staff
- estimated hours: tasks x the minutes saved per task estimated at intake / 60
- measured hours: tasks x the minutes saved per task measured in that month's timed sample / 60
  (sample average of minutes without the tool minus minutes with it)
- gross value: measured hours x the loaded hourly staff cost
- cost: model usage cost + the monthly fee
- net value: gross value - cost
- payback: one-off setup cost / average monthly net value over the last 3 full months
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from .db import meta

UNDER_USED = 0.35  # adoption below this share of eligible staff is flagged


@dataclass
class MonthFigures:
    month: str
    tasks: int = 0
    est_hours: float = 0.0
    measured_hours: float = 0.0
    gross: float = 0.0
    cost: float = 0.0

    @property
    def net(self) -> float:
        return self.gross - self.cost


@dataclass
class ToolValue:
    id: int
    name: str
    team: str
    level: str
    tier: str
    status: str
    eligible: int
    adoption: float
    trained_share: float
    est_minutes: float
    measured_minutes: float | None
    months: list[MonthFigures] = field(default_factory=list)
    weekly_active: list[tuple[str, int]] = field(default_factory=list)
    payback_months: float | None = None
    setup_cost: float = 0.0
    override_rate: float = 0.0
    error_rate: float = 0.0
    incidents: int = 0
    open_incidents: int = 0

    @property
    def under_used(self) -> bool:
        return self.status != "retired" and self.adoption < UNDER_USED

    @property
    def recommendation(self) -> str:
        if not self.under_used:
            return ""
        last3 = self.months[-4:-1] or self.months
        net = sum(m.net for m in last3)
        if self.trained_share < 0.5:
            return f"Train: only {self.trained_share:.0%} of eligible staff have finished its training."
        if net < 0:
            return "Consider retiring: low use and it costs more than it saves."
        return "Find out why: most staff are trained but few use it."

    def totals(self, months: list[str] | None = None) -> MonthFigures:
        t = MonthFigures("total")
        for m in self.months:
            if months is None or m.month in months:
                t.tasks += m.tasks
                t.est_hours += m.est_hours
                t.measured_hours += m.measured_hours
                t.gross += m.gross
                t.cost += m.cost
        return t


def full_months(conn: sqlite3.Connection) -> list[str]:
    """Calendar months fully covered by the data, oldest first."""
    as_of = date.fromisoformat(meta(conn, "as_of"))
    first = date.fromisoformat(meta(conn, "first_week"))
    out = []
    y, m = first.year, first.month
    if first.day != 1:
        m += 1
        if m > 12:
            y, m = y + 1, 1
    while (y, m) < (as_of.year, as_of.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def tool_values(conn: sqlite3.Connection) -> list[ToolValue]:
    rate = float(meta(conn, "hourly_cost", "40"))
    months = full_months(conn)
    out: list[ToolValue] = []
    for r in conn.execute("SELECT * FROM register WHERE id IN (SELECT DISTINCT tool_id FROM weekly) ORDER BY name"):
        weeks = conn.execute("SELECT * FROM weekly WHERE tool_id = ? ORDER BY week", (r["id"],)).fetchall()
        eligible = int(weeks[-1]["eligible"]) if weeks else 0
        last4 = weeks[-4:]
        adoption = sum(w["active_users"] for w in last4) / (len(last4) * eligible) if last4 and eligible else 0.0
        guides = conn.execute("SELECT COUNT(*) AS n FROM training WHERE tool_id = ?", (r["id"],)).fetchone()["n"]
        trained = conn.execute(
            "SELECT COUNT(*) AS n FROM (SELECT td.staff_id FROM training_done td JOIN training t ON t.id = td.training_id "
            "JOIN eligible e ON e.staff_id = td.staff_id AND e.tool_id = t.tool_id WHERE t.tool_id = ? GROUP BY td.staff_id HAVING COUNT(*) = ?)",
            (r["id"], guides),
        ).fetchone()["n"]
        samples = {s["month"]: s["minutes_without"] - s["minutes_with"] for s in conn.execute("SELECT * FROM time_samples WHERE tool_id = ?", (r["id"],))}
        tv = ToolValue(
            id=r["id"], name=r["name"], team=r["team"], level=r["level"], tier=r["tier"], status=r["status"], eligible=eligible,
            adoption=adoption, trained_share=(trained / eligible if eligible else 0.0), est_minutes=r["est_minutes_per_task"],
            measured_minutes=None, setup_cost=r["setup_cost"],
        )  # fmt: skip
        tasks_total = sum(w["tasks"] for w in weeks)
        tv.override_rate = sum(w["overrides"] for w in weeks) / tasks_total if tasks_total else 0.0
        tv.error_rate = sum(w["errors"] for w in weeks) / tasks_total if tasks_total else 0.0
        tv.weekly_active = [(w["week"], int(w["active_users"])) for w in weeks]
        for month in months:
            mw = [w for w in weeks if w["week"][:7] == month]
            tasks = sum(w["tasks"] for w in mw)
            measured = samples.get(month)
            mf = MonthFigures(month, tasks)
            mf.est_hours = tasks * r["est_minutes_per_task"] / 60
            mf.measured_hours = tasks * (measured or 0.0) / 60
            mf.gross = mf.measured_hours * rate
            mf.cost = sum(w["model_cost"] for w in mw) + (r["monthly_fee"] if mw else 0.0)
            tv.months.append(mf)
        if samples:
            tv.measured_minutes = samples[max(samples)]
        recent = [m for m in tv.months[-3:] if m.tasks]
        avg_net = sum(m.net for m in recent) / len(recent) if recent else 0.0
        tv.payback_months = round(r["setup_cost"] / avg_net, 1) if avg_net > 0 else None
        inc = conn.execute("SELECT COUNT(*) AS n, SUM(status = 'open') AS o FROM incidents WHERE tool_id = ?", (r["id"],)).fetchone()
        tv.incidents, tv.open_incidents = int(inc["n"]), int(inc["o"] or 0)
        out.append(tv)
    return out


def portfolio_weekly(conn: sqlite3.Connection) -> list[tuple[str, int, int]]:
    """Per week: total active users across tools, total tasks."""
    return [(r["week"], int(r["a"]), int(r["t"])) for r in conn.execute("SELECT week, SUM(active_users) AS a, SUM(tasks) AS t FROM weekly GROUP BY week ORDER BY week")]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


@dataclass
class TrainingEffect:
    trained_active: float
    untrained_active: float
    trained_n: int
    untrained_n: int
    tool_r: float | None


def training_effect(conn: sqlite3.Connection, tools: list[ToolValue]) -> TrainingEffect:
    """Share of eligible staff active in the last 4 weeks, for those who finished the tool's training vs those who did not."""
    weeks = [r["week"] for r in conn.execute("SELECT DISTINCT week FROM weekly ORDER BY week DESC LIMIT 4")]
    ph = ",".join("?" * len(weeks))
    rows = conn.execute(
        f"""
        WITH guides AS (SELECT tool_id, COUNT(*) AS n FROM training GROUP BY tool_id),
        done AS (SELECT t.tool_id, td.staff_id, COUNT(*) AS n FROM training_done td JOIN training t ON t.id = td.training_id GROUP BY t.tool_id, td.staff_id),
        recent AS (SELECT DISTINCT tool_id, staff_id FROM activity WHERE week IN ({ph}))
        SELECT e.tool_id, e.staff_id, COALESCE(d.n, 0) = g.n AS trained, r.staff_id IS NOT NULL AS active
        FROM eligible e JOIN guides g ON g.tool_id = e.tool_id
        LEFT JOIN done d ON d.tool_id = e.tool_id AND d.staff_id = e.staff_id
        LEFT JOIN recent r ON r.tool_id = e.tool_id AND r.staff_id = e.staff_id
        """,
        weeks,
    ).fetchall()
    t = [r for r in rows if r["trained"]]
    u = [r for r in rows if not r["trained"]]
    live = [x for x in tools if x.status != "retired"]
    return TrainingEffect(
        trained_active=sum(r["active"] for r in t) / len(t) if t else 0.0,
        untrained_active=sum(r["active"] for r in u) / len(u) if u else 0.0,
        trained_n=len(t),
        untrained_n=len(u),
        tool_r=pearson([x.trained_share for x in live], [x.adoption for x in live]),
    )
