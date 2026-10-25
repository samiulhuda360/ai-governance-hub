"""Optional: let a model read a free-text description and suggest answers for the intake form.

The model only suggests. The web form shows every suggested field highlighted, and the person must confirm each
one before the use case can be submitted. The risk assessment itself never uses a model.
"""

from __future__ import annotations

import json
import re
import typing
from dataclasses import dataclass, field
from typing import Any

from .intake import AFFECTED, DATA_CATEGORIES, DECISION_MODES, FLAGS, REGIONS, USE_AREAS, DecisionMode, Intake, Region
from .llm import LLM, CacheMiss

PROMPT_VERSION = "prefill-v1"

LIST_FIELDS = ("data_categories", "affected", "people_regions", "org_regions", "flags")
CHOICE_FIELDS = ("use_area", "decision_mode", "processing_region")
TEXT_FIELDS = ("title", "purpose", "team", "vendor", "model")
NUMBER_FIELDS = ("expected_users", "hours_saved_per_week")
ALLOWED: dict[str, set[str]] = {
    "use_area": set(USE_AREAS),
    "decision_mode": set(typing.get_args(DecisionMode)),
    "processing_region": set(typing.get_args(Region)),
    "data_categories": set(DATA_CATEGORIES),
    "affected": set(AFFECTED),
    "people_regions": set(REGIONS),
    "org_regions": set(REGIONS),
    "flags": set(FLAGS),
}


def _options(d: dict[str, str]) -> str:
    return "\n".join(f"  - {k}: {v}" for k, v in d.items())


SYSTEM = f"""You help staff fill in an AI use-case intake form. Read the description and answer each field
using only what the description says or clearly implies. Do not guess legal outcomes.

Return one JSON object with these keys:
- title: a short name for the use case (max 8 words)
- purpose: one sentence on what the AI will do
- team: the team or department asking
- use_area: exactly one of
{_options(USE_AREAS)}
- data_categories: a list, any of
{_options(DATA_CATEGORIES)}
- affected: a list of whose lives the AI's output touches, any of
{_options(AFFECTED)}
- decision_mode: exactly one of
{_options(DECISION_MODES)}
- vendor: the AI vendor or product if named, else ""
- model: the AI model if named, else ""
- processing_region: where the data is processed, one of {", ".join(REGIONS)} (EU means the EU/EEA)
- people_regions: a list of regions where the people whose information is used are
- org_regions: a list of regions where the organisation is established
- expected_users: number of staff expected to use it (0 if not stated)
- hours_saved_per_week: hours saved per week if stated, else 0
- flags: a list of the yes/no questions below that the description supports as YES (leave out the rest)
{_options(FLAGS)}
"""


@dataclass
class Prefill:
    values: dict[str, Any]
    suggested: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    cache_hit: bool = True
    error: str = ""


def clean(raw: dict[str, Any]) -> Prefill:
    """Keep only valid values; anything the form does not allow is dropped and reported."""
    out: dict[str, Any] = {}
    dropped: list[str] = []
    for k in TEXT_FIELDS:
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[: 2000 if k == "purpose" else 120]
    for k in CHOICE_FIELDS:
        v = raw.get(k)
        if isinstance(v, str) and v in ALLOWED[k]:
            out[k] = v
        elif v not in (None, ""):
            dropped.append(f"{k}={v!r}")
    for k in LIST_FIELDS:
        v = raw.get(k) or []
        if isinstance(v, str):
            v = [v]
        good = [x for x in v if isinstance(x, str) and x in ALLOWED[k]]
        dropped += [f"{k}={x!r}" for x in v if x not in good]
        out[k] = sorted(set(good))
    for k in NUMBER_FIELDS:
        try:
            num = float(raw.get(k) or 0)
        except (TypeError, ValueError):
            num = 0.0
        out[k] = int(num) if k == "expected_users" else round(num, 1)
    return Prefill(out, suggested=sorted(out), dropped=dropped)


def parse_json(text: str) -> Any:
    """Parse the reply; if that fails, quote bare object keys (a common slip) and try once more."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(re.sub(r"(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text))
    except json.JSONDecodeError:
        return None


def prefill(text: str, llm: LLM | None = None) -> Prefill:
    llm = llm or LLM()
    try:
        res = llm.chat_json(SYSTEM, f"[{PROMPT_VERSION}]\nDescription:\n{text.strip()}")
    except CacheMiss:
        return Prefill({}, error="Pre-fill needs a model key (AI_API_KEY) for new text. Fill the form by hand; everything else works.")
    raw = parse_json(res.content)
    if raw is None:
        return Prefill({}, cache_hit=res.cache_hit, error="The model's reply was not valid JSON. Fill the form by hand.")
    p = clean(raw if isinstance(raw, dict) else {})
    p.cache_hit = res.cache_hit
    return p


def to_intake(p: Prefill, fallback_title: str = "Untitled use case") -> Intake:
    v = {"title": fallback_title, "purpose": fallback_title, "team": "Unknown", **p.values}
    return Intake(**v)
