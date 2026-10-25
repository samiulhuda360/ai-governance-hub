"""The explainable risk assessment: intake answers in, tier, privacy duties, NIST checks, level and controls out.

Every finding carries the plain-words reason and the clause it comes from. No model is involved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .conditions import Context, holds
from .intake import REGIONS, Intake

RULES_DIR = Path(__file__).resolve().parent / "rules"
LEVELS = ["low", "medium", "high", "prohibited"]


@dataclass
class Finding:
    id: str
    title: str
    explain: str
    source: str


@dataclass
class RegimeResult:
    id: str
    name: str
    law: str
    obligations: list[Finding]
    transfer_note: str = ""


@dataclass
class Driver:
    id: str
    points: int
    reason: str
    source: str
    at_least: str = ""


@dataclass
class Control:
    id: str
    name: str
    required: bool
    source: str


@dataclass
class Assessment:
    tier: str
    annex_area: str | None
    annex_point: str | None
    level: str
    score: int
    prohibited: list[Finding] = field(default_factory=list)
    high_risk: list[Finding] = field(default_factory=list)
    exception: Finding | None = None
    transparency: list[Finding] = field(default_factory=list)
    duties: list[Finding] = field(default_factory=list)
    nist: dict[str, list[Finding]] = field(default_factory=dict)
    regimes: list[RegimeResult] = field(default_factory=list)
    drivers: list[Driver] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)

    @property
    def regime_ids(self) -> list[str]:
        return [r.id for r in self.regimes]

    @property
    def required_controls(self) -> list[Control]:
        return [c for c in self.controls if c.required]

    def summary(self) -> str:
        """One plain-words sentence for lists and the audit log."""
        if self.tier == "prohibited":
            return f"Blocked: {self.prohibited[0].title.lower()} is banned by {self.prohibited[0].source}."
        tier_words = {
            "high": f"EU AI Act high-risk ({self.annex_point})",
            "limited": "EU AI Act transparency duties",
            "minimal": "EU AI Act minimal risk",
        }[self.tier]
        laws = ", ".join(r.name for r in self.regimes) or "no privacy law triggered"
        return f"{self.level.capitalize()} risk ({self.score} points). {tier_words}. Privacy: {laws}."

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["summary"] = self.summary()
        return d


@lru_cache(maxsize=1)
def load_rules(rules_dir: str = str(RULES_DIR)) -> dict[str, Any]:
    base = Path(rules_dir)
    return {name: yaml.safe_load((base / f"{name}.yaml").read_text(encoding="utf-8")) for name in ("eu_ai_act", "nist_rmf", "privacy", "risk")}


def _finding(rule: dict[str, Any], source: str | None = None) -> Finding:
    return Finding(rule["id"], rule["title"], " ".join(str(rule["explain"]).split()), source or rule["source"])


def _eu_tier(it: Intake, eu: dict[str, Any], a: Assessment) -> None:
    ctx = Context(it)
    a.prohibited = [_finding(r) for r in eu["prohibited"] if holds(r["when"], ctx)]
    if a.prohibited:
        a.tier = "prohibited"
        return
    exc = eu["exception_6_3"]
    remaining: list[tuple[dict[str, Any], Finding]] = []
    for r in eu["high_risk"]:
        if not holds(r["when"], ctx):
            continue
        f = _finding(r, f"EU AI Act {r['point']}")
        annex_iii = r["area"] != "product_safety"
        if annex_iii and it.has("profiling"):
            f.explain += " " + " ".join(exc["profiling_note"].split())
        elif annex_iii and holds(exc["when"], ctx):
            a.exception = Finding("art6_3", f"Article 6(3) exception for {r['point']}", " ".join(exc["explain"].split()), exc["source"])
            continue
        remaining.append((r, f))
    if remaining:
        a.tier = "high"
        a.annex_area = remaining[0][0]["area"]
        a.annex_point = remaining[0][0]["point"]
        a.high_risk = [f for _r, f in remaining]
    a.transparency = [_finding(r) for r in eu["transparency"] if holds(r["when"], ctx)]
    if a.tier != "high":
        a.tier = "limited" if a.transparency else "minimal"
    duties = eu["deployer_duties"]
    a.duties = [_finding(r) for r in duties["all"]]
    if a.tier == "high":
        a.duties += [_finding(r) for r in duties["high"]]
        if it.has("workplace_or_education") or "staff" in it.affected or a.annex_area == "employment":
            a.duties += [_finding(r) for r in duties["high_workplace"]]
        if it.has("public_service_deployer") or a.annex_point in ("Annex III 5(b)", "Annex III 5(c)"):
            a.duties += [_finding(r) for r in duties["high_fria"]]


def _regions_with_law(it: Intake) -> list[str]:
    if not it.personal():
        return []
    return [r for r in REGIONS if r != "other" and (r in it.people_regions or r in it.org_regions)]


def assess(it: Intake) -> Assessment:
    rules = load_rules()
    a = Assessment(tier="minimal", annex_area=None, annex_point=None, level="low", score=0)
    _eu_tier(it, rules["eu_ai_act"], a)
    ctx = Context(it, tier=a.tier)

    for chk in rules["nist_rmf"]["checks"]:
        if holds(chk["when"], ctx):
            a.nist.setdefault(chk["function"], []).append(Finding(chk["id"], chk["check"], "", chk["source"]))

    law_regions = _regions_with_law(it)
    for rid, reg in rules["privacy"]["regimes"].items():
        if reg["region"] not in law_regions:
            continue
        rctx = Context(it, tier=a.tier, region=reg["region"])
        obligations = [_finding(o) for o in reg["obligations"] if holds(o["when"], rctx)]
        note = ""
        if it.processing_region != reg["region"]:
            ok = it.processing_region in reg.get("adequate", [])
            note = (f"Processed in {REGIONS[it.processing_region]}: " + ("covered by an adequacy decision. " if ok else "")) + " ".join(reg["adequacy_note"].split())
        a.regimes.append(RegimeResult(rid, reg["name"], reg["law"], obligations, note))

    risk = rules["risk"]
    dctx = Context(it, tier=a.tier, people_regions_with_law=tuple(law_regions))
    floor = "low"
    for d in risk["drivers"]:
        if holds(d["when"], dctx):
            a.drivers.append(Driver(d["id"], int(d["points"]), d["reason"], d["source"], d.get("at_least", "")))
            if d.get("at_least") and LEVELS.index(d["at_least"]) > LEVELS.index(floor):
                floor = d["at_least"]
    a.score = sum(d.points for d in a.drivers)
    bands = risk["bands"]
    banded = "high" if a.score >= bands["high"] else "medium" if a.score >= bands["medium"] else "low"
    level = max(banded, floor, key=LEVELS.index)
    if a.tier == "high":
        a.drivers.insert(0, Driver("eu_high_risk", 0, f"EU AI Act high-risk use ({a.annex_point}).", f"EU AI Act {a.annex_point}", "high"))
        level = "high"
    if a.tier == "prohibited":
        a.drivers.insert(0, Driver("eu_prohibited", 0, a.prohibited[0].title + ".", a.prohibited[0].source, "prohibited"))
        level = "prohibited"
    a.level = level

    if level != "prohibited":
        rank = LEVELS.index(level)
        for c in risk["controls"]:
            if holds(c["when"], ctx):
                a.controls.append(Control(c["id"], c["name"], rank >= LEVELS.index(c["required_at"]), c["source"]))
    return a


def review_months(level: str) -> int:
    months: dict[str, int] = load_rules()["risk"]["review_months"]
    return months.get(level, 12)
