"""A small, safe condition language for the YAML rules.

A condition is a mapping; all of its keys must hold (AND). Keys:

    always: true                     always holds
    use_area: [a, b]                 the use area is one of these
    decision_mode: [a, b]            the decision mode is one of these
    flag: name                       this yes/no question was answered yes
    flags_all: [a, b] / flags_any    all / any of these flags
    data_any: [a, b]                 any of these data categories is involved
    affected_any: [a, b]             any of these groups is affected
    personal: true|false             information about people is involved (or not)
    vendor: true|false               an outside vendor or model is named
    tier: [a, b]                     the EU AI Act tier already worked out is one of these
    transfer: true|false             personal information is processed outside the region being checked
    text_any: [phrase, ...]          the title or purpose mentions one of these phrases
    any: [cond, ...]                 at least one holds
    all: [cond, ...]                 every one holds
    not: cond                        the condition does not hold

There is no eval and no code in the YAML, so a rules file can be reviewed by someone who does not program.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intake import Intake

KEYS = {
    "always", "use_area", "decision_mode", "flag", "flags_all", "flags_any", "data_any", "affected_any",
    "personal", "vendor", "tier", "transfer", "text_any", "any", "all", "not",
}  # fmt: skip


class RuleError(ValueError):
    """A rules file uses a key or value the language does not know."""


@dataclass
class Context:
    intake: Intake
    tier: str = "minimal"
    region: str | None = None  # the privacy region being checked, for "transfer"
    people_regions_with_law: tuple[str, ...] = ()


def _transfer(ctx: Context) -> bool:
    it = ctx.intake
    if not it.personal():
        return False
    if ctx.region is not None:
        return it.processing_region != ctx.region
    return any(r != it.processing_region for r in ctx.people_regions_with_law)


def holds(cond: dict[str, Any], ctx: Context) -> bool:
    if not isinstance(cond, dict) or not cond:
        raise RuleError(f"a condition must be a non-empty mapping, got {cond!r}")
    it = ctx.intake
    for key, val in cond.items():
        if key not in KEYS:
            raise RuleError(f"unknown condition key {key!r}")
        if key == "always":
            ok = bool(val)
        elif key == "use_area":
            ok = it.use_area in val
        elif key == "decision_mode":
            ok = it.decision_mode in val
        elif key == "flag":
            ok = it.has(val)
        elif key == "flags_all":
            ok = all(it.has(f) for f in val)
        elif key == "flags_any":
            ok = any(it.has(f) for f in val)
        elif key == "data_any":
            ok = any(c in it.data_categories for c in val)
        elif key == "affected_any":
            ok = any(a in it.affected for a in val)
        elif key == "personal":
            ok = it.personal() == bool(val)
        elif key == "vendor":
            ok = bool(it.vendor.strip() or it.model.strip()) == bool(val)
        elif key == "tier":
            ok = ctx.tier in val
        elif key == "transfer":
            ok = _transfer(ctx) == bool(val)
        elif key == "text_any":
            text = f"{it.title} {it.purpose}".lower()
            ok = any(p.lower() in text for p in val)
        elif key == "any":
            ok = any(holds(c, ctx) for c in val)
        elif key == "all":
            ok = all(holds(c, ctx) for c in val)
        else:  # not
            ok = not holds(val, ctx)
        if not ok:
            return False
    return True
