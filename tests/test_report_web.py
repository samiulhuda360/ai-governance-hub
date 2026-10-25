from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from governance_hub.llm import LLM
from governance_hub.prefill import clean, parse_json, prefill
from governance_hub.report import build
from governance_hub.web import create_app
from tests.conftest import by_name


def test_report_figures_and_decisions(db: sqlite3.Connection) -> None:
    r = build(db, "2026-09", with_summary=False)
    assert r.month_label == "September 2026"
    assert sum(r.by_level.values()) == 12
    assert r.month_totals["net"] == pytest.approx(r.month_totals["gross"] - r.month_totals["cost"])
    assert r.month_totals["measured_hours"] < r.month_totals["est_hours"]
    assert [o["name"] for o in r.overdue] == ["Customer email reply drafts"]
    assert any("CV screening" in d and "high-severity" in d for d in r.decisions)
    assert any(d.startswith("Meeting notes summariser: Train") for d in r.decisions)
    assert r.summary == ""


def test_report_month_defaults_to_last_full_month(db: sqlite3.Connection) -> None:
    assert build(db, None, with_summary=False).month == "2026-09"
    assert build(db, "1999-01", with_summary=False).month == "2026-09"


def test_report_summary_is_replayed_and_labelled(db: sqlite3.Connection) -> None:
    r = build(db, "2026-09", llm=LLM(offline=True))
    assert r.summary and "Written by an AI model" in r.summary_note


def test_report_without_recorded_summary_still_works(db: sqlite3.Connection) -> None:
    r = build(db, "2026-06", llm=LLM(offline=True, cache_dir=Path("does-not-exist")))
    assert r.summary == "" and "No AI-written summary" in r.summary_note
    assert r.month_totals["tasks"] > 0


@pytest.fixture()
def client(db: sqlite3.Connection, tmp_path: Path) -> TestClient:
    db.close()
    return TestClient(create_app(tmp_path / "hub.db"))


def signin(c: TestClient, name: str) -> None:
    uid = by_name(c.app.state.conn, name)["id"]  # type: ignore[attr-defined]
    assert c.post(f"/demo/signin/{uid}", follow_redirects=False).status_code == 303


def test_pages_need_sign_in_and_reject_forged_cookie(client: TestClient) -> None:
    assert client.get("/dashboard", follow_redirects=False).headers["location"] == "/demo"
    client.cookies.set("hub_user", "1.forged")
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("path", ["/dashboard", "/intake", "/submissions", "/submissions/1", "/register", "/register/1", "/training", "/audit", "/report"])
def test_pages_render(client: TestClient, path: str) -> None:
    signin(client, "Sophie Turner")
    r = client.get(path)
    assert r.status_code == 200 and "not legal advice" in r.text


def test_report_page_is_printable_and_labels_ai_text(client: TestClient) -> None:
    signin(client, "Daniel Hughes")
    html = client.get("/report", params={"month": "2026-09"}).text
    assert "Decisions needed" in html and "window.print()" in html and "Written by an AI model" in html


def test_suggested_answers_must_each_be_confirmed(client: TestClient) -> None:
    signin(client, "Emma Clarke")
    form = {"title": "Claims drafts", "purpose": "Draft damage claim replies", "team": "Customer Service", "use_area": "customer_service",
            "decision_mode": "suggests", "processing_region": "EU", "suggested": "title,use_area"}  # fmt: skip
    r = client.post("/intake", data={**form, "confirm_title": "1"})
    assert "Please confirm every suggested answer" in r.text and "use_area" in r.text
    r = client.post("/intake", data={**form, "confirm_title": "1", "confirm_use_area": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/submissions/")


def test_auditor_cannot_approve_over_http(client: TestClient) -> None:
    signin(client, "Sophie Turner")
    sub = client.app.state.conn.execute("SELECT id FROM submissions WHERE status = 'in_review' LIMIT 1").fetchone()[0]  # type: ignore[attr-defined]
    r = client.post(f"/submissions/{sub}/decide", data={"decision": "approve"}, follow_redirects=False)
    assert "Not%20allowed" in r.headers["location"]


def test_api_assess(client: TestClient) -> None:
    r = client.post("/api/assess", json={"title": "CV ranker", "purpose": "Rank CVs", "team": "HR", "use_area": "recruitment"})
    assert r.status_code == 200 and r.json()["annex_point"] == "Annex III 4(a)"
    assert client.post("/api/assess", json={"title": "x"}).status_code == 422
    assert client.post("/api/assess", json={"title": "Bad", "purpose": "Bad", "team": "HR", "use_area": "nope"}).status_code == 422


def test_audit_csv_download(client: TestClient) -> None:
    signin(client, "Sophie Turner")
    r = client.get("/audit.csv")
    assert r.headers["content-type"].startswith("text/csv") and r.text.startswith("id,ts,actor")


def test_prefill_cleaning_drops_values_the_form_does_not_allow() -> None:
    p = clean({"title": "X tool", "use_area": "mind_reading", "data_categories": ["health", "dna"], "flags": "profiling", "expected_users": "12", "hours_saved_per_week": "n/a"})
    assert "use_area" not in p.values and p.values["data_categories"] == ["health"] and p.values["flags"] == ["profiling"]
    assert p.values["expected_users"] == 12 and p.values["hours_saved_per_week"] == 0.0
    assert "use_area='mind_reading'" in p.dropped and "data_categories='dna'" in p.dropped


def test_parse_json_repairs_bare_keys() -> None:
    assert parse_json('{\n  "a": 1,\n  data_categories: []\n}') == {"a": 1, "data_categories": []}
    assert parse_json("not json") is None


def test_prefill_without_key_or_recording_says_so() -> None:
    p = prefill("A brand new description nobody has recorded.", LLM(offline=True))
    assert p.error.startswith("Pre-fill needs a model key")


def test_unknown_team_is_rejected(client: TestClient) -> None:
    signin(client, "Emma Clarke")
    r = client.post("/intake", data={"title": "Claims drafts", "purpose": "Draft replies", "team": "Claims", "use_area": "customer_service", "decision_mode": "suggests", "processing_region": "EU"})
    assert "unknown team" in r.text
