"""Render the one-page brief (HTML + Markdown) and the audit log of rejected items."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .schema import ValidatedExtraction

_env = Environment(loader=PackageLoader("guidance_tracker", "templates"), autoescape=select_autoescape(["html"]))


def fmt(v, unit):
    if v is None:
        return ""
    if unit == "usd_billions":
        return "$" + f"{v:,.2f}".rstrip("0").rstrip(".") + "B"
    if unit == "usd_millions":
        return f"${v:,.0f}M" if v >= 100 else f"${v:,.1f}M"
    if unit == "usd_per_share":
        return f"${v:,.2f}"
    if unit == "percent":
        return f"{v:g}%"
    return f"{v:g}"


def fmt_range(item):
    if item.low is None and item.high is None:
        return item.qualitative or ""
    if item.low == item.high or item.high is None:
        return fmt(item.low, item.unit)
    return f"{fmt(item.low, item.unit)} – {fmt(item.high, item.unit)}"


_env.filters["fmt"] = fmt
_env.filters["fmt_range"] = fmt_range

DOC_TAGS = {"press_release": "8-K", "transcript": "Call"}


def _ctx(v: ValidatedExtraction) -> dict:
    ok = lambda pairs: [(i, c) for i, c in pairs if c.status == "verified"]
    return {
        "v": v,
        "guidance": ok(v.guidance),
        "reported": ok(v.reported),
        "tone": ok(v.tone),
        "counts": v.counts(),
        "tag": lambda c: DOC_TAGS.get(c.source_doc, c.source_doc or ""),
        "today": date.today().isoformat(),
    }


def render(v: ValidatedExtraction, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{v.ticker}_{v.quarter}"
    ctx = _ctx(v)
    paths = {
        "html": out_dir / f"{stem}_brief.html",
        "md": out_dir / f"{stem}_brief.md",
        "audit": out_dir / f"{stem}_audit.md",
    }
    paths["html"].write_text(_env.get_template("brief.html").render(**ctx), encoding="utf-8")
    paths["md"].write_text(_env.get_template("brief.md").render(**ctx), encoding="utf-8")
    paths["audit"].write_text(_env.get_template("audit.md").render(**ctx), encoding="utf-8")
    return paths
