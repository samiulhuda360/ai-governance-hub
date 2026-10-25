"""Evaluate the rules engine and the optional model pre-fill against the hand-labelled cases.

    python eval/run_eval.py            # rules + pre-fill (uses recorded model replies; live only if a key is set)
    python eval/run_eval.py --check    # offline replay; fails if any reply is missing or a number changed

Part 1 runs the rules on the intake answers a careful person gave for each case.
Part 2 lets the model read only the plain-words description, fill the form, and runs the same rules on that.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from governance_hub.engine import LEVELS, Assessment, assess  # noqa: E402
from governance_hub.intake import Intake  # noqa: E402
from governance_hub.llm import LLM  # noqa: E402
from governance_hub.prefill import CHOICE_FIELDS, LIST_FIELDS, prefill, to_intake  # noqa: E402

EVAL = ROOT / "eval"
REGIMES = ["eu_gdpr", "uk_gdpr", "au_app", "nz_ipp", "us_state"]


def load_cases() -> list[dict[str, Any]]:
    return json.loads((EVAL / "cases_dev.json").read_text(encoding="utf-8")) + json.loads((EVAL / "cases_holdout.json").read_text(encoding="utf-8"))


def pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def score(cases: list[dict[str, Any]], preds: list[Assessment]) -> dict[str, Any]:
    n = len(cases)
    tier_ok = sum(a.tier == c["labels"]["tier"] for c, a in zip(cases, preds, strict=True))
    high = [(c, a) for c, a in zip(cases, preds, strict=True) if c["labels"]["tier"] == "high"]
    pred_high = [(c, a) for c, a in zip(cases, preds, strict=True) if a.tier == "high"]
    proh = [(c, a) for c, a in zip(cases, preds, strict=True) if c["labels"]["tier"] == "prohibited"]
    pred_proh = [(c, a) for c, a in zip(cases, preds, strict=True) if a.tier == "prohibited"]
    tp = fp = fn = 0
    per: dict[str, Counter[str]] = {r: Counter() for r in REGIMES}
    for c, a in zip(cases, preds, strict=True):
        gold, got = set(c["labels"]["regimes"]), set(a.regime_ids)
        tp += len(gold & got)
        fp += len(got - gold)
        fn += len(gold - got)
        for r in REGIMES:
            per[r]["tp"] += r in gold and r in got
            per[r]["fp"] += r not in gold and r in got
            per[r]["fn"] += r in gold and r not in got
    lvl_ok = sum(a.level == c["labels"]["risk_level"] for c, a in zip(cases, preds, strict=True))
    under = sum(LEVELS.index(a.level) < LEVELS.index(c["labels"]["risk_level"]) for c, a in zip(cases, preds, strict=True))
    misses = [
        {"id": c["id"], "label": c["labels"]["tier"], "got": a.tier, "label_level": c["labels"]["risk_level"], "got_level": a.level}
        for c, a in zip(cases, preds, strict=True)
        if a.tier != c["labels"]["tier"] or a.level != c["labels"]["risk_level"]
    ]
    return {
        "cases": n,
        "tier_accuracy": pct(tier_ok, n),
        "high_risk_recall": pct(sum(a.tier == "high" for _c, a in high), len(high)),
        "high_risk_precision": pct(sum(c["labels"]["tier"] == "high" for c, _a in pred_high), len(pred_high)),
        "high_risk_missed": sum(a.tier != "high" for _c, a in high),
        "annex_area_accuracy_on_high": pct(sum(a.annex_area == c["labels"]["annex_area"] for c, a in high), len(high)),
        "prohibited_recall": pct(sum(a.tier == "prohibited" for _c, a in proh), len(proh)),
        "prohibited_precision": pct(sum(c["labels"]["tier"] == "prohibited" for c, _a in pred_proh), len(pred_proh)),
        "regime_precision": pct(tp, tp + fp),
        "regime_recall": pct(tp, tp + fn),
        "regime_counts": {r: per[r]["tp"] + per[r]["fn"] for r in REGIMES},
        "risk_level_accuracy": pct(lvl_ok, n),
        "risk_level_under_rated": under,
        "misses": misses,
    }


def field_accuracy(cases: list[dict[str, Any]], filled: list[Intake]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in CHOICE_FIELDS + LIST_FIELDS:
        ok = 0
        for c, it in zip(cases, filled, strict=True):
            gold, got = c["intake"].get(f), getattr(it, f)
            ok += (set(gold or []) == set(got)) if f in LIST_FIELDS else (gold == got)
        out[f] = pct(ok, len(cases))
    tp = fp = fn = 0
    for c, it in zip(cases, filled, strict=True):
        gold, got = set(c["intake"].get("flags") or []), set(it.flags)
        tp, fp, fn = tp + len(gold & got), fp + len(got - gold), fn + len(gold - got)
    out["flags_precision"] = pct(tp, tp + fp)
    out["flags_recall"] = pct(tp, tp + fn)
    return out


def run() -> dict[str, Any]:
    cases = load_cases()
    by_split = {"dev": [c for c in cases if c["split"] == "dev"], "holdout": [c for c in cases if c["split"] == "holdout"]}
    res: dict[str, Any] = {"rules": {}, "prefill": {}}
    for name, cs in [*by_split.items(), ("all", cases)]:
        res["rules"][name] = score(cs, [assess(Intake(**c["intake"])) for c in cs])

    llm = LLM()
    filled: list[Intake] = []
    hits = failed = 0
    for c in cases:
        p = prefill(c["text"], llm)
        if p.error.startswith("Pre-fill needs"):
            raise SystemExit(f"{c['id']}: {p.error}")
        failed += bool(p.error)  # an unreadable reply counts as an empty form
        hits += p.cache_hit
        filled.append(to_intake(p, c["intake"]["title"]))
    for name, cs in [*by_split.items(), ("all", cases)]:
        idx = [i for i, c in enumerate(cases) if c in cs]
        sub_cases, sub_filled = [cases[i] for i in idx], [filled[i] for i in idx]
        res["prefill"][name] = {
            "fields": field_accuracy(sub_cases, sub_filled),
            "end_to_end": score(sub_cases, [assess(it) for it in sub_filled]),
        }
    res["model"] = llm.model
    res["recorded_replies"] = len(cases)
    res["unreadable_replies"] = failed
    res["replayed_from_cache_this_run"] = hits
    return res


def stable(res: dict[str, Any]) -> dict[str, Any]:
    r = json.loads(json.dumps(res))
    r.pop("replayed_from_cache_this_run", None)
    return r


def write_md(res: dict[str, Any]) -> None:
    def row(label: str, key: str, block: str = "rules") -> str:
        vals = []
        for s in ("dev", "holdout", "all"):
            v = res[block][s][key] if block == "rules" else res["prefill"][s]["end_to_end"][key]
            vals.append("n/a" if v is None else (f"{v}%" if isinstance(v, float) else str(v)))
        return f"| {label} | " + " | ".join(vals) + " |"

    r = res["rules"]
    lines = [
        "# Evaluation results",
        "",
        f"{r['all']['cases']} AI use cases written in plain words and labelled by hand from the published texts "
        f"({r['dev']['cases']} development cases used while writing the rules, {r['holdout']['cases']} held-out cases written separately "
        "and run once after the rules were committed). Labelling conventions: [labelling-guide.md](labelling-guide.md). "
        "Reproduce with `python eval/run_eval.py --check` (offline, replays the recorded model replies).",
        "",
        "## 1. Rules engine on the hand-filled intake answers",
        "",
        "| Measure | Development | Held-out | All |",
        "|---|---|---|---|",
        row("Cases", "cases"),
        row("EU AI Act tier accuracy", "tier_accuracy"),
        row("High-risk recall", "high_risk_recall"),
        row("High-risk cases missed", "high_risk_missed"),
        row("High-risk precision", "high_risk_precision"),
        row("Annex III area correct (high-risk cases)", "annex_area_accuracy_on_high"),
        row("Prohibited recall", "prohibited_recall"),
        row("Prohibited precision", "prohibited_precision"),
        row("Privacy-regime precision", "regime_precision"),
        row("Privacy-regime recall", "regime_recall"),
        row("Overall risk-level accuracy", "risk_level_accuracy"),
        row("Risk level rated lower than the label", "risk_level_under_rated"),
        "",
        "Privacy-regime labels in the set: " + ", ".join(f"{k} {v}" for k, v in r["all"]["regime_counts"].items()) + ".",
        "",
        "## 2. Model pre-fill: the model reads only the description",
        "",
        f"Model: `{res['model']}`, temperature 0, one recorded reply per case ({res['recorded_replies']} replies).",
        "",
        "Field accuracy against the hand-filled answers (lists count as correct only when the whole set matches):",
        "",
        "| Field | Development | Held-out | All |",
        "|---|---|---|---|",
    ]
    for f in res["prefill"]["all"]["fields"]:
        vals = [res["prefill"][s]["fields"][f] for s in ("dev", "holdout", "all")]
        lines.append(f"| {f} | " + " | ".join("n/a" if v is None else f"{v}%" for v in vals) + " |")
    lines += [
        "",
        "End to end, with no person checking the model's answers (the hub always asks a person to confirm each one):",
        "",
        "| Measure | Development | Held-out | All |",
        "|---|---|---|---|",
        row("EU AI Act tier accuracy", "tier_accuracy", "prefill"),
        row("High-risk recall", "high_risk_recall", "prefill"),
        row("High-risk cases missed", "high_risk_missed", "prefill"),
        row("Prohibited recall", "prohibited_recall", "prefill"),
        row("Privacy-regime precision", "regime_precision", "prefill"),
        row("Privacy-regime recall", "regime_recall", "prefill"),
        row("Overall risk-level accuracy", "risk_level_accuracy", "prefill"),
        row("Risk level rated lower than the label", "risk_level_under_rated", "prefill"),
        "",
        "## Cases the end-to-end run got wrong",
        "",
        "| Case | Tier label | Got | Level label | Got |",
        "|---|---|---|---|---|",
    ]
    for m in res["prefill"]["all"]["end_to_end"]["misses"]:
        lines.append(f"| {m['id']} | {m['label']} | {m['got']} | {m['label_level']} | {m['got_level']} |")
    if r["all"]["misses"]:
        lines += ["", "## Cases the rules got wrong on hand-filled answers", "", "| Case | Tier label | Got | Level label | Got |", "|---|---|---|---|---|"]
        lines += [f"| {m['id']} | {m['label']} | {m['got']} | {m['label_level']} | {m['got_level']} |" for m in r["all"]["misses"]]
    (EVAL / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="offline replay; fail on a missing reply or a changed result")
    args = ap.parse_args()
    if args.check:
        import os

        os.environ["HUB_OFFLINE"] = "1"
    res = run()
    out = EVAL / "results.json"
    if args.check:
        saved = json.loads(out.read_text(encoding="utf-8"))
        if stable(saved) != stable(res):
            print("results differ from eval/results.json")
            return 1
        print(f"replay ok: {res['rules']['all']['cases']} cases, {res['replayed_from_cache_this_run']} model replies from cache")
        return 0
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    write_md(res)
    print(json.dumps({k: res["rules"][k]["tier_accuracy"] for k in res["rules"]}), json.dumps(res["prefill"]["all"]["end_to_end"]["tier_accuracy"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
