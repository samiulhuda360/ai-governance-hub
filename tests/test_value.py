"""ROI arithmetic on a tiny database where every number can be worked out by hand."""

from __future__ import annotations

import sqlite3

import pytest

from governance_hub.db import connect
from governance_hub.value import full_months, pearson, tool_values, training_effect


@pytest.fixture()
def tiny(tmp_path: object) -> sqlite3.Connection:
    c = connect(":memory:")
    c.executemany("INSERT INTO meta VALUES (?,?)", [("as_of", "2026-03-10"), ("first_week", "2026-01-05"), ("hourly_cost", "40")])
    c.execute("INSERT INTO users VALUES (1, 'Ann Lee', 'a@x.example', 'requester', 'Ops', 'x')")
    c.execute("INSERT INTO submissions VALUES (1, 'T', 'Ops', 1, '{}', '{}', 'minimal', 'low', 'approved', '[]', '2025-12-01', '2025-12-01')")
    c.execute("INSERT INTO register VALUES (1, 1, 'Tool', 1, 'Ops', 'p', 'minimal', NULL, 'low', 'v', 'm', '[]', 'EU', '2025-12-01', '2025-12-01', '2027-12-01', 'live', 10, 1200, 100, 0)")
    for s in range(1, 11):
        c.execute("INSERT INTO staff VALUES (?, 'Ops', 'Rotterdam')", (s,))
        c.execute("INSERT INTO eligible VALUES (1, ?)", (s,))
    # January and February: 4 weeks each, 300 tasks a week, model cost 10 a week
    weeks = ["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26", "2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23"]
    for i, w in enumerate(weeks):
        active = 2 if i < 4 else 4
        c.execute("INSERT INTO weekly VALUES (1, ?, 10, ?, 300, 30, 3, 10)", (w, active))
    c.execute("INSERT INTO time_samples VALUES (1, '2026-01', 20, 15, 9)")  # 6 minutes saved
    c.execute("INSERT INTO time_samples VALUES (1, '2026-02', 20, 15, 7)")  # 8 minutes saved
    c.execute("INSERT INTO training VALUES (1, 1, 'Start', 10, 'guide', 's')")
    for s in (1, 2, 3, 4):
        c.execute("INSERT INTO training_done VALUES (1, ?, '2026-01-10')", (s,))
        c.execute("INSERT INTO activity VALUES (1, ?, '2026-02-23', 5)", (s,))
    c.execute("INSERT INTO activity VALUES (1, 9, '2026-02-23', 5)")
    return c


def test_full_months(tiny: sqlite3.Connection) -> None:
    assert full_months(tiny) == ["2026-01", "2026-02"]


def test_hours_value_cost_net_and_payback(tiny: sqlite3.Connection) -> None:
    (t,) = tool_values(tiny)
    jan, feb = t.months
    assert jan.tasks == 1200 and feb.tasks == 1200
    assert jan.est_hours == pytest.approx(1200 * 10 / 60)  # 200 h estimated
    assert jan.measured_hours == pytest.approx(1200 * 6 / 60)  # 120 h measured
    assert feb.measured_hours == pytest.approx(160)
    assert jan.gross == pytest.approx(120 * 40)  # 4,800
    assert jan.cost == pytest.approx(4 * 10 + 100)  # model cost + monthly fee = 140
    assert jan.net == pytest.approx(4660)
    assert feb.net == pytest.approx(160 * 40 - 140)  # 6,260
    assert t.payback_months == pytest.approx(round(1200 / ((4660 + 6260) / 2), 1))
    assert t.measured_minutes == 8
    assert t.adoption == pytest.approx(0.4)  # 4 active of 10 eligible over the last 4 weeks
    assert t.override_rate == pytest.approx(0.1) and t.error_rate == pytest.approx(0.01)
    assert t.trained_share == pytest.approx(0.4)


def test_under_used_and_recommendation(tiny: sqlite3.Connection) -> None:
    (t,) = tool_values(tiny)
    assert not t.under_used
    t.adoption, t.trained_share = 0.2, 0.4
    assert t.under_used and t.recommendation.startswith("Train")
    t.trained_share = 0.9
    assert t.recommendation.startswith("Find out why")


def test_no_payback_when_net_value_is_negative(tiny: sqlite3.Connection) -> None:
    tiny.execute("UPDATE register SET monthly_fee = 100000")
    (t,) = tool_values(tiny)
    assert t.payback_months is None


def test_training_effect(tiny: sqlite3.Connection) -> None:
    eff = training_effect(tiny, tool_values(tiny))
    assert eff.trained_n == 4 and eff.untrained_n == 6
    assert eff.trained_active == 1.0 and eff.untrained_active == pytest.approx(1 / 6)


def test_pearson() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert pearson([1, 2], [1, 2]) is None
