"""FastAPI web app: server-rendered pages, a demo sign-in per role, and a JSON endpoint for assessments."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from . import charts
from .db import audit_csv, connect, meta, verify_chain
from .engine import assess
from .intake import AFFECTED, DATA_CATEGORIES, DECISION_MODES, FLAGS, REGIONS, USE_AREAS, Intake, validate_choices
from .prefill import prefill
from .report import build as build_report
from .value import full_months, portfolio_weekly, tool_values, training_effect
from .workflow import ROLES, STEPS, PermissionDenied, can_decide, decide, next_step, record_review, report_incident, set_control, set_tool_status, submit

HERE = Path(__file__).resolve().parent
EXAMPLE_TEXT = (
    "Our claims team would like an AI to read drivers' delivery notes and photos of damaged parcels and draft the damage "
    "claim reply for the customer. A claims handler checks and edits every draft before it is sent. Customers are in the "
    "Netherlands and the UK. It would use Google Gemini, with data processed in the EU. About 15 handlers would use it "
    "and we think it saves around 20 hours a week."
)
LIST_FIELDS = ("data_categories", "affected", "people_regions", "org_regions", "flags")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="AI Governance Hub", docs_url=None, redoc_url=None)
    conn = connect(db_path)
    secret = os.environ.get("HUB_SECRET", "").encode() or secrets.token_bytes(32)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(ROLES=ROLES, REGIONS=REGIONS, USE_AREAS=USE_AREAS)
    templates.env.filters["money"] = lambda v: f"€{v:,.0f}" if v >= 0 else f"-€{-v:,.0f}"
    templates.env.filters["pct"] = lambda v: "n/a" if v is None else f"{v:.0%}"
    templates.env.filters["num"] = lambda v: f"{v:,.0f}"
    templates.env.filters["fromjson"] = json.loads
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.state.conn = conn

    def now() -> str:
        return datetime.now().replace(microsecond=0).isoformat()

    def sign(uid: int) -> str:
        return f"{uid}.{hmac.new(secret, str(uid).encode(), hashlib.sha256).hexdigest()}"

    def current(request: Request) -> sqlite3.Row | None:
        raw = request.cookies.get("hub_user", "")
        uid, _, mac = raw.partition(".")
        if not uid.isdigit() or not hmac.compare_digest(sign(int(uid)), raw) or not mac:
            return None
        row: sqlite3.Row | None = conn.execute("SELECT * FROM users WHERE id = ?", (int(uid),)).fetchone()
        return row

    def need(request: Request) -> sqlite3.Row:
        u = current(request)
        if u is None:
            raise HTTPException(status_code=303, headers={"Location": "/demo"})
        return u

    def page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        ctx.update(request=request, me=current(request), company=meta(conn, "company"), as_of=meta(conn, "as_of"), notice=request.query_params.get("notice", ""))
        return templates.TemplateResponse(request, name, ctx)

    def back(url: str, notice: str = "") -> RedirectResponse:
        return RedirectResponse(url + (f"?notice={quote(notice)}" if notice else ""), status_code=303)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        return RedirectResponse("/dashboard" if current(request) else "/demo", status_code=303)

    @app.get("/demo", response_class=HTMLResponse)
    def demo(request: Request) -> HTMLResponse:
        users = conn.execute("SELECT * FROM users ORDER BY CASE role WHEN 'requester' THEN 1 WHEN 'team_lead' THEN 2 WHEN 'risk_reviewer' THEN 3 WHEN 'governance_lead' THEN 4 ELSE 5 END, team").fetchall()
        return page(request, "demo.html", users=users)

    @app.post("/demo/signin/{uid}")
    def signin(uid: int) -> Response:
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
            raise HTTPException(404)
        r = RedirectResponse("/dashboard", status_code=303)
        r.set_cookie("hub_user", sign(uid), httponly=True, samesite="lax")
        return r

    @app.post("/signout")
    def signout() -> Response:
        r = RedirectResponse("/demo", status_code=303)
        r.delete_cookie("hub_user")
        return r

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        need(request)
        tools = tool_values(conn)
        live = [t for t in tools if t.status != "retired"]
        months = full_months(conn)
        weekly = portfolio_weekly(conn)
        eff = training_effect(conn, tools)
        totals = {k: sum(getattr(t.totals(), k) for t in live) for k in ("est_hours", "measured_hours", "gross", "cost")}
        totals["net"] = totals["gross"] - totals["cost"]
        reg = conn.execute("SELECT level, tier, status, review_due FROM register WHERE status != 'retired'").fetchall()
        pending = conn.execute("SELECT COUNT(*) AS n FROM submissions WHERE status = 'in_review'").fetchone()["n"]
        overdue = sum(r["review_due"] < meta(conn, "as_of") for r in reg)
        bars = sorted(((t.name, t.totals().est_hours, t.totals().measured_hours) for t in live), key=lambda r: -r[2])
        return page(
            request, "dashboard.html", tools=live, months=months, totals=totals, eff=eff, pending=pending, overdue=overdue,
            by_level={lvl: sum(r["level"] == lvl for r in reg) for lvl in ("high", "medium", "low")},
            adoption_svg=charts.line([(w, a) for w, a, _t in weekly], "weekly active users (all tools)"),
            hours_svg=charts.paired_bars(bars, ("Estimated at intake", "Measured")),
            training_svg=charts.scatter([(t.name, t.trained_share, t.adoption) for t in live], "Staff who finished the training", "Weekly active staff"),
            weekly=weekly,
        )  # fmt: skip

    # ----- intake -----
    def form_ctx(values: dict[str, Any], suggested: list[str], error: str = "", text: str = "", dropped: list[str] | None = None) -> dict[str, Any]:
        return {
            "v": values, "suggested": suggested, "error": error, "text": text, "dropped": dropped or [], "DATA": DATA_CATEGORIES, "AFFECTED": AFFECTED,
            "MODES": DECISION_MODES, "FLAGS": FLAGS, "example": EXAMPLE_TEXT, "teams": [r["name"] for r in conn.execute("SELECT name FROM teams ORDER BY name")],
        }  # fmt: skip

    @app.get("/intake", response_class=HTMLResponse)
    def intake_form(request: Request) -> HTMLResponse:
        me = need(request)
        return page(request, "intake.html", **form_ctx({"team": me["team"], "processing_region": "EU", "people_regions": [], "org_regions": ["EU", "UK"]}, []))

    @app.post("/intake/prefill", response_class=HTMLResponse)
    def intake_prefill(request: Request, text: str = Form("")) -> HTMLResponse:
        me = need(request)
        p = prefill(text) if text.strip() else None
        if p is None or p.error:
            err = p.error if p else "Paste a description first."
            return page(request, "intake.html", **form_ctx({"team": me["team"], "org_regions": ["EU", "UK"]}, [], err, text))
        values = {"team": me["team"], **p.values}
        return page(request, "intake.html", **form_ctx(values, p.suggested, "", text, p.dropped))

    async def parse_form(request: Request) -> tuple[dict[str, Any], list[str], set[str]]:
        form = await request.form()
        values: dict[str, Any] = {k: form.getlist(k) for k in LIST_FIELDS}
        for k in ("title", "purpose", "team", "use_area", "decision_mode", "vendor", "model", "processing_region"):
            values[k] = str(form.get(k, "")).strip()
        for k, cast in (("expected_users", int), ("hours_saved_per_week", float)):
            try:
                values[k] = cast(str(form.get(k) or 0))
            except ValueError:
                values[k] = 0
        suggested = [s for s in str(form.get("suggested", "")).split(",") if s]
        confirmed = {k[len("confirm_") :] for k in form if k.startswith("confirm_")}
        return values, suggested, confirmed

    @app.post("/intake", response_class=HTMLResponse)
    async def intake_submit(request: Request) -> Response:
        me = need(request)
        values, suggested, confirmed = await parse_form(request)
        unconfirmed = [s for s in suggested if s not in confirmed]
        if unconfirmed:
            return page(request, "intake.html", **form_ctx(values, suggested, "Please confirm every suggested answer (tick 'Checked') before submitting: " + ", ".join(unconfirmed) + "."))
        try:
            it = Intake(**values)
        except ValidationError as e:
            return page(request, "intake.html", **form_ctx(values, suggested, "Please check the form: " + "; ".join(f"{x['loc'][0]}: {x['msg']}" for x in e.errors())))
        problems = validate_choices(it)
        if problems:
            return page(request, "intake.html", **form_ctx(values, suggested, "; ".join(problems)))
        try:
            sub_id, _a = submit(conn, me, it, now(), prefilled=suggested)
        except PermissionDenied as e:
            return page(request, "intake.html", **form_ctx(values, suggested, str(e)))
        return back(f"/submissions/{sub_id}", "Submitted. The assessment and the approval route are below.")

    @app.post("/api/assess")
    async def api_assess(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            it = Intake(**body)
        except (ValidationError, json.JSONDecodeError, TypeError) as e:
            return JSONResponse({"error": str(e)[:500]}, status_code=422)
        if validate_choices(it):
            return JSONResponse({"error": "; ".join(validate_choices(it))}, status_code=422)
        return JSONResponse(assess(it).to_dict())

    @app.post("/intake/preview", response_class=HTMLResponse)
    async def intake_preview(request: Request) -> HTMLResponse:
        values, _s, _c = await parse_form(request)
        for k in ("title", "purpose", "team"):
            if len(str(values.get(k) or "")) < 3:
                values[k] = "Draft"
        try:
            it = Intake(**values)
            a = assess(it)
        except ValidationError:
            return HTMLResponse("<p class='muted'>Fill in the form to see the assessment.</p>")
        return templates.TemplateResponse(request, "_preview.html", {"a": a, "steps": STEPS.get(a.level, [])})

    # ----- submissions -----
    @app.get("/submissions", response_class=HTMLResponse)
    def submissions(request: Request) -> HTMLResponse:
        me = need(request)
        rows = conn.execute("SELECT s.*, u.name AS requester FROM submissions s JOIN users u ON u.id = s.requester_id ORDER BY s.created_at DESC").fetchall()
        waiting = [r for r in rows if r["status"] == "in_review" and can_decide(conn, me, r["id"]) is None]
        return page(request, "submissions.html", rows=rows, waiting=waiting)

    @app.get("/submissions/{sub_id}", response_class=HTMLResponse)
    def submission(request: Request, sub_id: int) -> HTMLResponse:
        me = need(request)
        s = conn.execute("SELECT s.*, u.name AS requester FROM submissions s JOIN users u ON u.id = s.requester_id WHERE s.id = ?", (sub_id,)).fetchone()
        if s is None:
            raise HTTPException(404)
        steps = conn.execute("SELECT a.*, u.name AS approver FROM approvals a LEFT JOIN users u ON u.id = a.approver_id WHERE submission_id = ? ORDER BY step", (sub_id,)).fetchall()
        ctrls = conn.execute("SELECT c.*, u.name AS done_by_name FROM controls c LEFT JOIN users u ON u.id = c.done_by WHERE submission_id = ? ORDER BY required DESC, name", (sub_id,)).fetchall()
        log = conn.execute(
            "SELECT * FROM audit_log WHERE (entity = 'submission' AND entity_id = ?) OR (entity = 'approval' AND entity_id IN (SELECT id FROM approvals WHERE submission_id = ?)) ORDER BY id",
            (sub_id, sub_id),
        ).fetchall()
        reg = conn.execute("SELECT id FROM register WHERE submission_id = ?", (sub_id,)).fetchone()
        return page(
            request, "submission.html", s=s, a=json.loads(s["assessment"]), it=json.loads(s["intake"]), steps=steps, ctrls=ctrls, log=log,
            why_not=can_decide(conn, me, sub_id), step=next_step(conn, sub_id), reg=reg, prefilled=json.loads(s["prefilled"]),
        )  # fmt: skip

    @app.post("/submissions/{sub_id}/decide")
    def submission_decide(request: Request, sub_id: int, decision: str = Form(...), comment: str = Form("")) -> Response:
        me = need(request)
        try:
            status = decide(conn, me, sub_id, decision == "approve", comment, now())
        except PermissionDenied as e:
            return back(f"/submissions/{sub_id}", f"Not allowed: {e}")
        return back(f"/submissions/{sub_id}", f"Recorded. Status: {status.replace('_', ' ')}.")

    @app.post("/submissions/{sub_id}/controls/{control_id}")
    def submission_control(request: Request, sub_id: int, control_id: str, done: str = Form("0"), evidence: str = Form("")) -> Response:
        me = need(request)
        try:
            set_control(conn, me, sub_id, control_id, done == "1", evidence, now())
        except PermissionDenied as e:
            return back(f"/submissions/{sub_id}", f"Not allowed: {e}")
        return back(f"/submissions/{sub_id}", "Control updated.")

    # ----- register -----
    @app.get("/register", response_class=HTMLResponse)
    def register(request: Request) -> HTMLResponse:
        need(request)
        rows = conn.execute("SELECT r.*, u.name AS owner FROM register r JOIN users u ON u.id = r.owner_id ORDER BY r.status = 'retired', r.review_due").fetchall()
        return page(request, "register.html", rows=rows)

    @app.get("/register/{tool_id}", response_class=HTMLResponse)
    def tool(request: Request, tool_id: int) -> HTMLResponse:
        need(request)
        r = conn.execute("SELECT r.*, u.name AS owner FROM register r JOIN users u ON u.id = r.owner_id WHERE r.id = ?", (tool_id,)).fetchone()
        if r is None:
            raise HTTPException(404)
        tv = next((t for t in tool_values(conn) if t.id == tool_id), None)
        ctrls = conn.execute("SELECT * FROM controls WHERE submission_id = ? ORDER BY required DESC, name", (r["submission_id"],)).fetchall()
        guides = conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM training_done d WHERE d.training_id = t.id) AS done, (SELECT COUNT(*) FROM eligible e WHERE e.tool_id = t.tool_id) AS eligible FROM training t WHERE tool_id = ?",
            (tool_id,),
        ).fetchall()
        incidents = conn.execute("SELECT * FROM incidents WHERE tool_id = ? ORDER BY happened_on DESC", (tool_id,)).fetchall()
        svg = charts.line(tv.weekly_active, "weekly active users") if tv else ""
        return page(request, "tool.html", r=r, tv=tv, ctrls=ctrls, guides=guides, incidents=incidents, svg=svg)

    @app.post("/register/{tool_id}/review")
    def tool_review(request: Request, tool_id: int, note: str = Form("")) -> Response:
        me = need(request)
        try:
            due = record_review(conn, me, tool_id, note, now())
        except PermissionDenied as e:
            return back(f"/register/{tool_id}", f"Not allowed: {e}")
        return back(f"/register/{tool_id}", f"Review recorded. Next review due {due}.")

    @app.post("/register/{tool_id}/status")
    def tool_status(request: Request, tool_id: int, status: str = Form(...)) -> Response:
        me = need(request)
        try:
            set_tool_status(conn, me, tool_id, status, now())
        except PermissionDenied as e:
            return back(f"/register/{tool_id}", f"Not allowed: {e}")
        return back(f"/register/{tool_id}", f"Status set to {status}.")

    @app.post("/register/{tool_id}/incident")
    def tool_incident(request: Request, tool_id: int, severity: str = Form(...), summary: str = Form(...)) -> Response:
        me = need(request)
        try:
            report_incident(conn, me, tool_id, severity, summary.strip()[:500], now()[:10], now())
        except PermissionDenied as e:
            return back(f"/register/{tool_id}", f"Not allowed: {e}")
        return back(f"/register/{tool_id}", "Incident logged.")

    # ----- training, audit, report -----
    @app.get("/training", response_class=HTMLResponse)
    def training(request: Request) -> HTMLResponse:
        need(request)
        tools = tool_values(conn)
        guides = conn.execute(
            "SELECT t.*, r.name AS tool, (SELECT COUNT(*) FROM training_done d WHERE d.training_id = t.id) AS done, "
            "(SELECT COUNT(*) FROM eligible e WHERE e.tool_id = t.tool_id) AS eligible FROM training t JOIN register r ON r.id = t.tool_id ORDER BY r.name, t.id"
        ).fetchall()
        live = [t for t in tools if t.status != "retired"]
        return page(request, "training.html", guides=guides, tools=live, eff=training_effect(conn, tools),
                    svg=charts.scatter([(t.name, t.trained_share, t.adoption) for t in live], "Staff who finished the training", "Weekly active staff"))  # fmt: skip

    @app.get("/audit", response_class=HTMLResponse)
    def audit_page(request: Request) -> HTMLResponse:
        need(request)
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall()
        ok, n = verify_chain(conn)
        return page(request, "audit.html", rows=rows, chain_ok=ok, chain_n=n)

    @app.get("/audit.csv")
    def audit_export(request: Request) -> PlainTextResponse:
        need(request)
        return PlainTextResponse(audit_csv(conn), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-log.csv"})

    @app.get("/report", response_class=HTMLResponse)
    def report(request: Request, month: str = "") -> HTMLResponse:
        need(request)
        r = build_report(conn, month or None)
        return page(request, "report.html", r=r, months=full_months(conn))

    return app
