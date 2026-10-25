"""Build the demo database for Acme Logistics, an invented company (about 400 staff, offices in Rotterdam and
Manchester). Every AI tool is submitted and approved through the real workflow, so the audit log, register and
review dates are produced by the same code the web app uses. Usage is synthetic and seeded, so every run
produces the same numbers.
"""

from __future__ import annotations

import math
import random
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .db import connect
from .engine import assess
from .intake import Intake
from .workflow import (
    STEPS,
    decide,
    report_incident,
    set_control,
    set_tool_status,
    submit,
)

AS_OF = date(2026, 10, 25)
FIRST_WEEK = date(2026, 4, 27)  # 26 Monday-starting weeks up to 19 Oct 2026
WEEKS = [FIRST_WEEK + timedelta(weeks=i) for i in range(26)]
HOURLY_COST = 40.0  # loaded staff cost per hour, EUR (an assumption shown on every value figure)

TEAMS = {  # team: (staff count, share in Rotterdam)
    "Operations": (118, 0.7), "Warehouse": (90, 0.6), "Fleet & Safety": (52, 0.5), "Customer Service": (46, 0.4),
    "Sales & Marketing": (26, 0.5), "IT": (22, 0.5), "Finance": (20, 0.5), "HR": (12, 0.5), "Leadership": (14, 0.5),
}  # fmt: skip

USERS = [  # name, role, team, job title
    ("Emma Clarke", "requester", "Customer Service", "Customer service supervisor"),
    ("Lucas Visser", "requester", "Operations", "Planning analyst"),
    ("Megan Hall", "requester", "HR", "Recruitment partner"),
    ("Ethan Brooks", "requester", "Fleet & Safety", "Fleet safety officer"),
    ("Amelia Ward", "requester", "Finance", "Accounts payable lead"),
    ("Jack Morris", "team_lead", "Customer Service", "Head of customer service"),
    ("Liam Foster", "team_lead", "Operations", "Head of operations"),
    ("Grace Walker", "team_lead", "HR", "Head of people"),
    ("Noah Price", "team_lead", "Finance", "Finance director"),
    ("Chloe Adams", "team_lead", "Sales & Marketing", "Head of marketing"),
    ("Ryan Cooper", "team_lead", "IT", "Head of IT"),
    ("Hannah Lewis", "team_lead", "Fleet & Safety", "Head of fleet and safety"),
    ("Oscar Jansen", "team_lead", "Warehouse", "Warehouse manager"),
    ("Olivia Bennett", "risk_reviewer", "Leadership", "Risk and privacy manager (DPO)"),
    ("Daniel Hughes", "governance_lead", "Leadership", "AI governance lead"),
    ("Sophie Turner", "auditor", "Leadership", "Internal auditor"),
]


@dataclass
class Tool:
    requester: str
    intake: dict[str, Any]
    submitted: str
    approved: str
    status: str
    eligible_teams: list[str]
    eligible_share: float
    start_week: int
    plateau: float  # share of eligible staff active in a week once settled, before the training effect
    train_share: float  # share of eligible staff who complete the training
    tasks_per_user: float
    est_minutes: float
    minutes_without: float
    true_saving: float
    cost_per_task: float
    monthly_fee: float
    setup_cost: float
    override_rate: float
    error_rate: float
    guides: list[tuple[str, int, str, str]] = field(default_factory=list)
    incidents: list[tuple[str, str, str, str]] = field(default_factory=list)


def _intake(title: str, purpose: str, team: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"title": title, "purpose": purpose, "team": team, "processing_region": "EU", "people_regions": ["EU", "UK"], "org_regions": ["EU", "UK"]}
    base.update(kw)
    return base


GUIDE_START = ("Getting started", 10, "guide", "What the tool is for, what it is not for, and how to open it.")
GUIDE_CHECK = ("Checking its output", 15, "guide", "The mistakes it tends to make and how to spot them before anything is sent.")
GUIDE_PRIVACY = ("Personal data do's and don'ts", 10, "guide", "Which customer and staff details may go into the tool and which may not.")

TOOLS: list[Tool] = [
    Tool(
        "Emma Clarke",
        _intake(
            "Customer email reply drafts",
            "Draft replies to customer emails about deliveries, which an agent edits and sends.",
            "Customer Service",
            use_area="customer_service",
            data_categories=["personal"],
            affected=["customers"],
            decision_mode="suggests",
            vendor="Microsoft Azure OpenAI",
            model="GPT-4o",
            expected_users=40,
            hours_saved_per_week=60,
            flags=[],
        ),
        "2025-09-15T09:10:00",
        "2025-09-29T15:00:00",
        "live",
        ["Customer Service"],
        0.95,
        0,
        0.62,
        0.8,
        38,
        6.0,
        9.0,
        4.6,
        0.012,
        380,
        18000,
        0.18,
        0.02,
        [GUIDE_START, GUIDE_CHECK, GUIDE_PRIVACY],
        [("2026-07-14", "medium", "A draft reply quoted another customer's order number; caught by the agent before sending.", "closed")],
    ),
    Tool(
        "Emma Clarke",
        _intake(
            "Delivery tracking chat assistant",
            "Answer customers' 'where is my parcel' questions on the website chat, handing over to an agent when unsure.",
            "Customer Service",
            use_area="customer_service",
            data_categories=["personal"],
            affected=["customers", "public"],
            decision_mode="acts_with_review",
            vendor="Google Cloud",
            model="Gemini",
            expected_users=12,
            hours_saved_per_week=45,
            flags=["interacts_with_people"],
        ),
        "2025-12-01T10:00:00",
        "2026-01-12T16:30:00",
        "live",
        ["Customer Service"],
        0.5,
        0,
        0.75,
        0.9,
        110,
        3.0,
        5.0,
        2.7,
        0.004,
        650,
        45000,
        0.09,
        0.03,
        [GUIDE_START, ("Taking over a chat", 10, "guide", "When the assistant hands over, and how to pick up the conversation.")],
        [
            ("2026-06-02", "low", "Gave a customer yesterday's delivery window after a depot change.", "closed"),
            ("2026-09-22", "medium", "Told two customers a parcel was delivered when the scan was 'attempted'.", "open"),
        ],
    ),
    Tool(
        "Lucas Visser",
        _intake(
            "Route planning optimiser",
            "Suggest daily delivery routes and loading order from the day's orders and traffic data.",
            "Operations",
            use_area="analytics_forecasting",
            data_categories=[],
            affected=["staff"],
            decision_mode="suggests",
            vendor="RouteWise (invented vendor)",
            model="",
            expected_users=35,
            hours_saved_per_week=50,
            flags=[],
        ),
        "2025-09-15T09:00:00",
        "2025-09-24T11:00:00",
        "live",
        ["Operations"],
        0.35,
        0,
        0.8,
        0.85,
        9,
        25.0,
        55.0,
        21.0,
        0.05,
        1200,
        60000,
        0.22,
        0.01,
        [GUIDE_START, GUIDE_CHECK],
        [],
    ),
    Tool(
        "Lucas Visser",
        _intake(
            "Warehouse demand forecast",
            "Forecast next week's inbound and outbound volumes per warehouse so shifts can be planned.",
            "Warehouse",
            use_area="analytics_forecasting",
            data_categories=["confidential"],
            affected=["staff"],
            decision_mode="suggests",
            vendor="Microsoft Azure ML",
            model="",
            expected_users=12,
            hours_saved_per_week=15,
            flags=[],
        ),
        "2025-10-06T09:00:00",
        "2025-10-13T10:00:00",
        "live",
        ["Warehouse"],
        0.15,
        0,
        0.85,
        0.7,
        4,
        45.0,
        90.0,
        38.0,
        0.30,
        300,
        25000,
        0.15,
        0.02,
        [GUIDE_START],
        [],
    ),
    Tool(
        "Amelia Ward",
        _intake(
            "Invoice data capture",
            "Read supplier invoices and fill in the payment system fields for a clerk to check.",
            "Finance",
            use_area="document_processing",
            data_categories=["confidential"],
            affected=["staff"],
            decision_mode="suggests",
            vendor="Microsoft Azure AI Document Intelligence",
            model="",
            expected_users=14,
            hours_saved_per_week=30,
            flags=[],
        ),
        "2025-10-20T09:00:00",
        "2025-10-29T14:00:00",
        "live",
        ["Finance"],
        0.8,
        0,
        0.8,
        0.9,
        85,
        4.0,
        6.0,
        3.1,
        0.01,
        150,
        20000,
        0.06,
        0.015,
        [GUIDE_START, GUIDE_CHECK],
        [("2026-08-11", "low", "VAT read as 12% instead of 21% on a scanned invoice; corrected by the clerk.", "closed")],
    ),
    Tool(
        "Lucas Visser",
        _intake(
            "Meeting notes summariser",
            "Turn recorded internal meetings into notes and action lists.",
            "Operations",
            use_area="general_productivity",
            data_categories=["personal", "confidential"],
            affected=["staff"],
            decision_mode="suggests",
            vendor="Microsoft",
            model="Copilot",
            expected_users=150,
            hours_saved_per_week=75,
            flags=[],
        ),
        "2026-02-02T09:00:00",
        "2026-02-25T12:00:00",
        "live",
        ["Operations", "Sales & Marketing", "IT", "Finance", "Leadership", "HR"],
        0.7,
        0,
        0.32,
        0.22,
        2.5,
        20.0,
        30.0,
        11.0,
        0.0,
        3200,
        8000,
        0.0,
        0.03,
        [GUIDE_START, GUIDE_PRIVACY],
        [],
    ),
    Tool(
        "Lucas Visser",
        _intake(
            "Customs paperwork classifier",
            "Suggest tariff codes for customs declarations from product descriptions, for a customs clerk to confirm.",
            "Operations",
            use_area="document_processing",
            data_categories=["confidential"],
            affected=["customers"],
            decision_mode="suggests",
            vendor="Google Cloud",
            model="Gemini",
            expected_users=16,
            hours_saved_per_week=25,
            flags=[],
        ),
        "2026-01-12T09:00:00",
        "2026-01-21T15:00:00",
        "live",
        ["Operations"],
        0.14,
        0,
        0.82,
        0.85,
        60,
        5.0,
        8.0,
        3.8,
        0.003,
        120,
        22000,
        0.12,
        0.02,
        [GUIDE_START, GUIDE_CHECK],
        [],
    ),
    Tool(
        "Megan Hall",
        _intake(
            "CV screening shortlist helper",
            "Rank applications for warehouse and driver roles against the job requirements; a recruiter reviews every shortlist.",
            "HR",
            use_area="recruitment",
            data_categories=["personal"],
            affected=["public"],
            decision_mode="suggests",
            vendor="HireSort (invented vendor)",
            model="",
            processing_region="UK",
            expected_users=6,
            hours_saved_per_week=20,
            flags=["about_individuals", "profiling"],
        ),
        "2026-02-09T09:00:00",
        "2026-04-06T17:00:00",
        "pilot",
        ["HR"],
        0.7,
        4,
        0.85,
        1.0,
        45,
        12.0,
        15.0,
        6.5,
        0.05,
        900,
        30000,
        0.27,
        0.04,
        [GUIDE_START, GUIDE_CHECK, ("Fair shortlisting", 20, "workshop", "How to check a shortlist for unfair patterns, and when to stop using the tool.")],
        [("2026-08-26", "high", "Bias check: applicants with a career gap of over a year were ranked lower; tool paused for warehouse roles pending a fix.", "open")],
    ),
    Tool(
        "Hannah Lewis",
        _intake(
            "Fleet maintenance predictor",
            "Predict which trucks need servicing soon from sensor and repair data.",
            "Fleet & Safety",
            use_area="analytics_forecasting",
            data_categories=[],
            affected=["staff"],
            decision_mode="suggests",
            vendor="Microsoft Azure ML",
            model="",
            expected_users=10,
            hours_saved_per_week=12,
            flags=[],
        ),
        "2026-03-02T09:00:00",
        "2026-03-11T10:00:00",
        "live",
        ["Fleet & Safety"],
        0.2,
        2,
        0.4,
        0.7,
        6,
        30.0,
        50.0,
        26.0,
        0.2,
        250,
        20000,
        0.1,
        0.02,
        [GUIDE_START],
        [],
    ),
    Tool(
        "Ryan Cooper",
        _intake(
            "Coding assistant",
            "Suggest code and tests in the IT team's editors.",
            "IT",
            use_area="general_productivity",
            data_categories=["confidential"],
            affected=["staff"],
            decision_mode="suggests",
            vendor="GitHub",
            model="Copilot",
            expected_users=20,
            hours_saved_per_week=40,
            flags=[],
        ),
        "2025-09-01T09:00:00",
        "2025-09-05T10:00:00",
        "live",
        ["IT"],
        0.95,
        0,
        0.8,
        0.75,
        40,
        5.0,
        12.0,
        3.5,
        0.0,
        400,
        3000,
        0.3,
        0.05,
        [GUIDE_START, ("Secure use with our code", 15, "guide", "Secrets, licences and reviewing suggested code.")],
        [],
    ),
    Tool(
        "Chloe Adams",
        _intake(
            "Marketing image generator",
            "Create images for social posts and brochures from a brief.",
            "Sales & Marketing",
            use_area="content_generation",
            data_categories=[],
            affected=["public"],
            decision_mode="suggests",
            vendor="Adobe",
            model="Firefly",
            expected_users=8,
            hours_saved_per_week=10,
            flags=["generates_synthetic_media"],
        ),
        "2026-04-13T09:00:00",
        "2026-04-29T11:00:00",
        "live",
        ["Sales & Marketing"],
        0.4,
        1,
        0.55,
        0.35,
        5,
        40.0,
        70.0,
        22.0,
        0.15,
        300,
        4000,
        0.25,
        0.0,
        [GUIDE_START, ("Labelling AI images", 10, "guide", "When and how we say an image was made with AI.")],
        [],
    ),
    Tool(
        "Grace Walker",
        _intake(
            "Staff policy assistant",
            "Answer staff questions about leave, expenses and safety rules from our handbook.",
            "HR",
            use_area="general_productivity",
            data_categories=[],
            affected=["staff"],
            decision_mode="acts_with_review",
            vendor="Microsoft",
            model="Copilot Studio",
            expected_users=400,
            hours_saved_per_week=40,
            flags=["interacts_with_people"],
        ),
        "2026-05-04T09:00:00",
        "2026-05-27T15:00:00",
        "live",
        ["all"],
        1.0,
        5,
        0.2,
        0.15,
        1.5,
        6.0,
        10.0,
        4.0,
        0.002,
        200,
        9000,
        0.0,
        0.04,
        [GUIDE_START],
        [("2026-09-08", "low", "Quoted last year's mileage rate for expenses after the handbook update.", "closed")],
    ),
]

RETIRED = Tool("Lucas Visser", _intake("Shipment delay predictor (first version)", "Flag shipments likely to be late from carrier data.", "Operations",
               use_area="analytics_forecasting", data_categories=[], affected=["customers"], decision_mode="suggests", vendor="In-house", model="",
               expected_users=10, hours_saved_per_week=8, flags=[]),
               "2025-06-02T09:00:00", "2025-06-10T10:00:00", "retired", ["Operations"], 0.0, 0, 0.0, 0.0, 0, 10.0, 0, 0, 0, 0, 3000, 0, 0)  # fmt: skip

PENDING = [  # requester, intake, submitted at, how far it has got
    ("Emma Clarke", _intake("Call centre voice mood scoring", "Score each call-centre agent's mood and stress from their voice during calls, to help supervisors coach them.", "Customer Service",
     use_area="emotion_recognition", data_categories=["personal", "biometric"], affected=["staff"], decision_mode="acts_with_review", vendor="VoiceSense (invented vendor)",
     expected_users=6, hours_saved_per_week=5, flags=["workplace_or_education", "about_individuals", "profiling"]), "2026-10-06T10:20:00", "none"),
    ("Ethan Brooks", _intake("Driver performance scoring", "Score each driver weekly on braking, speeding and idling from truck telematics, used in performance reviews.", "Fleet & Safety",
     use_area="workforce_management", data_categories=["personal"], affected=["staff"], decision_mode="suggests", vendor="FleetPulse (invented vendor)",
     expected_users=8, hours_saved_per_week=10, flags=["about_individuals", "profiling", "workplace_or_education"]), "2026-10-08T14:00:00", "lead"),
    ("Emma Clarke", _intake("Complaint triage", "Sort incoming customer complaints by topic and urgency and suggest which team should handle each one.", "Customer Service",
     use_area="customer_service", data_categories=["personal"], affected=["customers"], decision_mode="suggests", vendor="Google Cloud", model="Gemini",
     expected_users=20, hours_saved_per_week=15, flags=[]), "2026-10-19T09:30:00", "none"),
    ("Amelia Ward", _intake("Supplier contract clause checker", "Highlight unusual payment and liability clauses in supplier contracts for the finance team to review.", "Finance",
     use_area="document_processing", data_categories=["confidential"], affected=["staff"], decision_mode="suggests", vendor="Microsoft", model="Copilot",
     expected_users=6, hours_saved_per_week=4, flags=[]), "2026-10-21T11:00:00", "none"),
    ("Lucas Visser", _intake("Automatic replies to customs queries", "Send replies to routine customs-authority queries automatically from our shipment records.", "Operations",
     use_area="document_processing", data_categories=["personal", "confidential"], affected=["public"], decision_mode="fully_automatic", vendor="Google Cloud", model="Gemini",
     expected_users=4, hours_saved_per_week=6, flags=["interacts_with_people"]), "2026-09-14T10:00:00", "rejected"),
]  # fmt: skip


def _ts(day: date, hour: int = 10) -> str:
    return f"{day.isoformat()}T{hour:02d}:00:00"


def _users(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["name"]: r for r in conn.execute("SELECT * FROM users")}


Event = tuple[str, int, Callable[[], None]]


def _tool_events(conn: sqlite3.Connection, t: Tool, state: dict[str, int], rng: random.Random) -> list[Event]:
    """Every audited action for one tool, with its timestamp, to be run in time order with all the others."""
    users = _users(conn)
    key = t.intake["title"]
    it = Intake(**t.intake)
    steps = STEPS[assess(it).level]
    start, end = date.fromisoformat(t.submitted[:10]), date.fromisoformat(t.approved[:10])
    team_lead = next(u for u in users.values() if u["role"] == "team_lead" and u["team"] == it.team)
    gov = users["Daniel Hughes"]
    events: list[Event] = []

    def do_submit() -> None:
        state[key], _a = submit(conn, users[t.requester], it, t.submitted)

    events.append((t.submitted, 0, do_submit))
    for i, role in enumerate(steps):
        when = t.approved if i == len(steps) - 1 else _ts(start + timedelta(days=max(1, (end - start).days * (i + 1) // (len(steps) + 1))), 11 + i)
        if role == "team_lead":
            actor = team_lead if team_lead["name"] != t.requester else gov
        else:
            actor = users["Olivia Bennett"] if role == "risk_reviewer" else gov
        if role == "governance_lead":

            def do_controls(when: str = when) -> None:
                sub_id = state[key]
                for c in conn.execute("SELECT * FROM controls WHERE submission_id = ? AND required = 1 AND done = 0", (sub_id,)).fetchall():
                    set_control(conn, users[t.requester], sub_id, c["control_id"], True, f"Evidence filed under AL-{sub_id:03d}-{c['control_id'].upper()}", when[:11] + "08:30:00")

            events.append((when[:11] + "08:30:00", 1, do_controls))
        comment = rng.choice(["Approved.", "Approved; please keep the training up to date.", "Fine to go ahead.", "Approved with the listed controls."])

        def do_decide(actor: sqlite3.Row = actor, when: str = when, comment: str = comment) -> None:
            decide(conn, actor, state[key], True, comment, when)

        events.append((when, 2, do_decide))

    def tool_id() -> int:
        return int(conn.execute("SELECT id FROM register WHERE submission_id = ?", (state[key],)).fetchone()["id"])

    def do_costs() -> None:
        with conn:
            conn.execute(
                "UPDATE register SET est_minutes_per_task = ?, setup_cost = ?, monthly_fee = ?, cost_per_task = ? WHERE id = ?",
                (t.est_minutes, t.setup_cost, t.monthly_fee, t.cost_per_task, tool_id()),
            )

    events.append((t.approved, 3, do_costs))
    live_at = _ts(end + timedelta(days=28), 9)
    if t.status in ("live", "retired"):
        events.append((live_at, 0, lambda: set_tool_status(conn, gov, tool_id(), "live", live_at)))
    if t.status == "retired":
        retired_at = _ts(date(2026, 3, 30), 9)
        events.append((retired_at, 0, lambda: set_tool_status(conn, gov, tool_id(), "retired", retired_at)))
    for day, severity, summary, status in t.incidents:
        at = _ts(date.fromisoformat(day), 16)

        def do_incident(day: str = day, severity: str = severity, summary: str = summary, status: str = status, at: str = at) -> None:
            iid = report_incident(conn, users[t.requester], tool_id(), severity, summary, day, at)
            if status == "closed":
                with conn:
                    conn.execute("UPDATE incidents SET status = 'closed' WHERE id = ?", (iid,))

        events.append((at, 0, do_incident))
    return events


def _pending_events(conn: sqlite3.Connection) -> list[Event]:
    users = _users(conn)
    events: list[Event] = []
    for requester, intake, at, progress in PENDING:
        state: dict[str, int] = {}
        day = date.fromisoformat(at[:10])

        def do_submit(requester: str = requester, intake: dict[str, Any] = intake, at: str = at, state: dict[str, int] = state) -> None:
            state["id"], _a = submit(conn, users[requester], Intake(**intake), at)

        def do_decide(state: dict[str, int], name: str, ok: bool, comment: str, when: str) -> Callable[[], None]:
            return lambda: None if decide(conn, users[name], state["id"], ok, comment, when) else None

        def do_control(state: dict[str, int], name: str, cid: str, note: str, when: str) -> Callable[[], None]:
            return lambda: set_control(conn, users[name], state["id"], cid, True, note, when)

        events.append((at, 0, do_submit))
        if progress == "lead":
            when = _ts(day + timedelta(days=2), 15)
            events.append((when, 0, do_decide(state, "Hannah Lewis", True, "Supported, as long as drivers are told and it is not used alone for discipline.", when)))
            when2 = _ts(day + timedelta(days=5), 10)
            events.append((when2, 1, do_control(state, requester, "data_minimisation", "Only braking, speed and idling events; no location history kept beyond 30 days.", when2)))
            events.append((when2, 1, do_control(state, requester, "logging", "Scores and overrides logged in FleetPulse for 12 months.", when2)))
        if progress == "rejected":
            w1, w2 = _ts(day + timedelta(days=1), 14), _ts(day + timedelta(days=4), 16)
            events.append((w1, 0, do_decide(state, "Liam Foster", True, "Would save the customs desk time.", w1)))
            reason = "Replies go to an authority with no person checking them and include personal data. Resubmit with a person approving each reply."
            events.append((w2, 0, do_decide(state, "Olivia Bennett", False, reason, w2)))
    return events


def build(path: Path | str | None = None, seed: int = 7) -> sqlite3.Connection:
    p = Path(path) if path and str(path) != ":memory:" else path
    if isinstance(p, Path) and p.exists():
        p.unlink()
    conn = connect(p)
    rng = random.Random(seed)
    with conn:
        info = {
            "company": "Acme Logistics", "as_of": AS_OF.isoformat(), "first_week": FIRST_WEEK.isoformat(), "hourly_cost": str(HOURLY_COST),
            "currency": "EUR", "offices": "Rotterdam (Netherlands) and Manchester (UK)",
        }  # fmt: skip
        conn.executemany("INSERT INTO meta VALUES (?,?)", list(info.items()))
        for name, role, team, title in USERS:
            email = name.lower().replace(" ", ".") + "@acme-logistics.example"
            conn.execute("INSERT INTO users (name, email, role, team, title) VALUES (?,?,?,?,?)", (name, email, role, team, title))
        users = _users(conn)
        for team in TEAMS:
            lead = next((u for u in users.values() if u["role"] == "team_lead" and u["team"] == team), None)
            if team == "Leadership":
                lead = users["Daniel Hughes"]
            conn.execute("INSERT INTO teams VALUES (?,?)", (team, lead["id"] if lead else None))
        sid = 0
        for team, (n, rot) in TEAMS.items():
            for i in range(n):
                sid += 1
                conn.execute("INSERT INTO staff VALUES (?,?,?)", (sid, team, "Rotterdam" if i < round(n * rot) else "Manchester"))

    state: dict[str, int] = {}
    events: list[Event] = []
    for t in [*TOOLS, RETIRED]:
        events += _tool_events(conn, t, state, rng)
    events += _pending_events(conn)
    for _when, _order, run in sorted(events, key=lambda e: (e[0], e[1])):
        run()
    tool_ids = {t.intake["title"]: int(conn.execute("SELECT id FROM register WHERE submission_id = ?", (state[t.intake["title"]],)).fetchone()["id"]) for t in TOOLS}
    _usage(conn, tool_ids, rng)
    return conn


def _usage(conn: sqlite3.Connection, tool_ids: dict[str, int], rng: random.Random) -> None:
    staff_by_team: dict[str, list[int]] = {}
    for r in conn.execute("SELECT id, team FROM staff ORDER BY id"):
        staff_by_team.setdefault(r["team"], []).append(int(r["id"]))
    all_staff = [s for v in staff_by_team.values() for s in v]
    with conn:
        for t in TOOLS:
            tid = tool_ids[t.intake["title"]]
            pool = all_staff if t.eligible_teams == ["all"] else [s for team in t.eligible_teams for s in staff_by_team[team]]
            eligible = sorted(rng.sample(pool, max(1, round(len(pool) * t.eligible_share))))
            conn.executemany("INSERT INTO eligible VALUES (?,?)", [(tid, s) for s in eligible])
            guide_ids = []
            for title, minutes, kind, summary in t.guides:
                cur = conn.execute("INSERT INTO training (tool_id, title, minutes, kind, summary) VALUES (?,?,?,?,?)", (tid, title, minutes, kind, summary))
                guide_ids.append(int(cur.lastrowid or 0))
            trained_week: dict[int, int] = {}
            for s in eligible:
                if rng.random() < t.train_share:
                    wk = min(25, t.start_week + int(rng.expovariate(1 / 6)))
                    trained_week[s] = wk
                    for g in guide_ids:
                        conn.execute("INSERT INTO training_done VALUES (?,?,?)", (g, s, (WEEKS[wk] + timedelta(days=rng.randint(0, 4))).isoformat()))
                elif guide_ids and rng.random() < 0.3:  # started but did not finish the course
                    conn.execute("INSERT INTO training_done VALUES (?,?,?)", (guide_ids[0], s, (WEEKS[min(25, t.start_week + rng.randint(0, 12))] + timedelta(days=1)).isoformat()))
            for w, wk_start in enumerate(WEEKS):
                if w < t.start_week:
                    continue
                ramp = t.plateau * (1 - math.exp(-(w - t.start_week + 1) / 4))
                active = tasks = 0
                for s in eligible:
                    trained = s in trained_week and trained_week[s] <= w
                    p_active = min(0.97, ramp * (1.35 if trained else 0.55))
                    if rng.random() < p_active:
                        n = max(1, round(rng.gauss(t.tasks_per_user, t.tasks_per_user * 0.3)))
                        active += 1
                        tasks += n
                        conn.execute("INSERT INTO activity VALUES (?,?,?,?)", (tid, s, wk_start.isoformat(), n))
                overrides = sum(rng.random() < t.override_rate for _ in range(tasks))
                errors = sum(rng.random() < t.error_rate for _ in range(tasks))
                conn.execute("INSERT INTO weekly VALUES (?,?,?,?,?,?,?,?)", (tid, wk_start.isoformat(), len(eligible), active, tasks, overrides, errors, round(tasks * t.cost_per_task, 2)))
            for month in sorted({wk.strftime("%Y-%m") for wk in WEEKS[t.start_week :]}):
                n = rng.randint(18, 30)
                without = [max(0.5, rng.gauss(t.minutes_without, t.minutes_without * 0.15)) for _ in range(n)]
                with_ai = [max(0.2, w - rng.gauss(t.true_saving, t.true_saving * 0.25)) for w in without]
                conn.execute("INSERT INTO time_samples VALUES (?,?,?,?,?)", (tid, month, n, round(sum(without) / n, 2), round(sum(with_ai) / n, 2)))
