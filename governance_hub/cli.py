"""Command line: build the demo data, run the web app, assess a use case from a JSON file, or write the report.

hub seed                      rebuild data/hub.db with the Acme Logistics demo
hub serve [--port 8060]       run the web app (builds the demo first if there is no database)
hub assess examples/cv.json   print the assessment for one intake form
hub report --month 2026-09    write the monthly report as HTML
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import DEFAULT_DB


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub", description="AI governance hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="rebuild the demo database")
    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8060)
    a = sub.add_parser("assess", help="assess an intake form saved as JSON")
    a.add_argument("file")
    r = sub.add_parser("report", help="write the monthly report as HTML")
    r.add_argument("--month", default=None)
    r.add_argument("--out", default="report.html")
    args = ap.parse_args(argv)

    if args.cmd == "seed":
        from .seed import build

        conn = build(DEFAULT_DB)
        n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        print(f"built {DEFAULT_DB} ({n} audit entries)")
        return 0
    if args.cmd == "serve":
        import uvicorn

        if not Path(DEFAULT_DB).exists():
            from .seed import build

            build(DEFAULT_DB).close()
        from .web import create_app

        uvicorn.run(create_app(DEFAULT_DB), host=args.host, port=args.port, log_level="warning")
        return 0
    if args.cmd == "assess":
        from .engine import assess
        from .intake import Intake, validate_choices

        it = Intake(**json.loads(Path(args.file).read_text(encoding="utf-8")))
        problems = validate_choices(it)
        if problems:
            print("; ".join(problems), file=sys.stderr)
            return 2
        res = assess(it)
        print(res.summary())
        print(json.dumps(res.to_dict(), indent=1))
        return 0
    if args.cmd == "report":
        from fastapi.testclient import TestClient

        from .web import create_app

        client = TestClient(create_app(DEFAULT_DB))
        gov = client.app.state.conn.execute("SELECT id FROM users WHERE role = 'governance_lead'").fetchone()[0]  # type: ignore[attr-defined]
        client.post(f"/demo/signin/{gov}")
        html = client.get("/report", params={"month": args.month or ""}).text
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
