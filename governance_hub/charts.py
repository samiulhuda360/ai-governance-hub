"""Small server-rendered SVG charts. Colours come from CSS variables, so light and dark themes both work, and
every mark has a hover title. Pages show the same numbers in a table next to each chart."""

from __future__ import annotations

from html import escape


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


def line(points: list[tuple[str, float]], label: str, width: int = 640, height: int = 220) -> str:
    """One series over time (single series, so the title names it and no legend is needed)."""
    if not points:
        return ""
    pad_l, pad_r, pad_t, pad_b = 44, 12, 12, 28
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    top = max(v for _x, v in points) or 1
    top = _nice(top)
    n = len(points)

    def x(i: int) -> float:
        return pad_l + (w * i / (n - 1) if n > 1 else w / 2)

    def y(v: float) -> float:
        return pad_t + h - h * v / top

    grid = "".join(
        f'<line x1="{pad_l}" x2="{pad_l + w}" y1="{y(top * k / 4):.1f}" y2="{y(top * k / 4):.1f}" class="grid"/>'
        f'<text x="{pad_l - 6}" y="{y(top * k / 4) + 4:.1f}" class="tick" text-anchor="end">{_fmt(top * k / 4)}</text>'
        for k in range(5)
    )
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_d, v) in enumerate(points))
    ticks = "".join(f'<text x="{x(i):.1f}" y="{height - 8}" class="tick" text-anchor="middle">{escape(d[5:])}</text>' for i, (d, _v) in enumerate(points) if i % 4 == 0)
    hits = "".join(
        f'<g class="hit"><rect x="{x(i) - w / n / 2:.1f}" y="{pad_t}" width="{w / n:.1f}" height="{h}" fill="transparent"/>'
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" class="dot s1"/><title>Week of {escape(d)}: {_fmt(v)} {escape(label)}</title></g>'
        for i, (d, v) in enumerate(points)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{escape(label)} by week">{grid}'
        f'<path d="{path}" class="ln s1"/>{ticks}{hits}</svg>'
    )


def paired_bars(rows: list[tuple[str, float, float]], names: tuple[str, str], width: int = 640) -> str:
    """Two values per row (for example estimated vs measured hours), horizontal bars, legend on top."""
    if not rows:
        return ""
    bar, gap, label_w = 9, 2, 190
    row_h = bar * 2 + gap + 12
    height = 26 + row_h * len(rows)
    top = _nice(max(max(a, b) for _n, a, b in rows) or 1)
    w = width - label_w - 60
    legend = (
        f'<rect x="{label_w}" y="4" width="12" height="12" rx="2" class="s1f"/><text x="{label_w + 18}" y="14" class="tick">{escape(names[0])}</text>'
        f'<rect x="{label_w + 160}" y="4" width="12" height="12" rx="2" class="s2f"/><text x="{label_w + 178}" y="14" class="tick">{escape(names[1])}</text>'
    )
    out = []
    for i, (name, a, b) in enumerate(rows):
        y0 = 26 + i * row_h
        wa, wb = max(1.0, w * a / top), max(1.0, w * b / top)
        out.append(
            f'<text x="{label_w - 8}" y="{y0 + bar + 2}" class="tick lbl" text-anchor="end">{escape(name)}</text>'
            f'<g class="hit"><rect x="{label_w}" y="{y0}" width="{wa:.1f}" height="{bar}" rx="2" class="s1f"/><title>{escape(name)}: {_fmt(a)} {escape(names[0].lower())}</title></g>'
            f'<g class="hit"><rect x="{label_w}" y="{y0 + bar + gap}" width="{wb:.1f}" height="{bar}" rx="2" class="s2f"/><title>{escape(name)}: {_fmt(b)} {escape(names[1].lower())}</title></g>'
            f'<text x="{label_w + max(wa, wb) + 6:.1f}" y="{y0 + bar + 2}" class="tick">{_fmt(b)}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{escape(names[0])} and {escape(names[1])} per tool">{legend}{"".join(out)}</svg>'


def scatter(points: list[tuple[str, float, float]], xlabel: str, ylabel: str, width: int = 420, height: int = 300) -> str:
    """Share values (0..1) on both axes, one labelled dot per tool."""
    pad_l, pad_r, pad_t, pad_b = 44, 16, 12, 40
    w, h = width - pad_l - pad_r, height - pad_t - pad_b

    def x(v: float) -> float:
        return pad_l + w * v

    def y(v: float) -> float:
        return pad_t + h - h * v

    grid = "".join(
        f'<line x1="{pad_l}" x2="{pad_l + w}" y1="{y(k / 4):.1f}" y2="{y(k / 4):.1f}" class="grid"/>'
        f'<text x="{pad_l - 6}" y="{y(k / 4) + 4:.1f}" class="tick" text-anchor="end">{k * 25}%</text>'
        f'<text x="{x(k / 4):.1f}" y="{pad_t + h + 16}" class="tick" text-anchor="middle">{k * 25}%</text>'
        for k in range(5)
    )
    dots = "".join(
        f'<g class="hit"><circle cx="{x(a):.1f}" cy="{y(b):.1f}" r="10" fill="transparent"/><circle cx="{x(a):.1f}" cy="{y(b):.1f}" r="5" class="dot s1"/>'
        f"<title>{escape(n)}: {a:.0%} trained, {b:.0%} weekly active</title></g>"
        for n, a, b in points
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{escape(ylabel)} against {escape(xlabel)}">{grid}{dots}'
        f'<text x="{pad_l + w / 2}" y="{height - 4}" class="tick" text-anchor="middle">{escape(xlabel)}</text>'
        f'<text x="12" y="{pad_t + h / 2}" class="tick" text-anchor="middle" transform="rotate(-90 12 {pad_t + h / 2})">{escape(ylabel)}</text></svg>'
    )


def _nice(v: float) -> float:
    for step in (1, 2, 2.5, 5):
        for mag in (1, 10, 100, 1000, 10000, 100000, 1000000):
            if step * mag * 4 >= v:
                return step * mag * 4
    return v
