"""Check every extracted item against the source text before it can reach the brief.

Two checks per item:
  1. Quote check  - the source_quote exists verbatim (after whitespace/punctuation
                    normalisation) in one of the source documents.
  2. Number check - every numeric field (low, high, value, yoy_change_pct) matches a
                    number written in that quote, of a compatible kind ($ vs %).
                    A $24,500 million / $24.5 billion scale difference is accepted;
                    any other mismatch rejects the item.
Rejected items are kept, with reasons, for the audit log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import Check, Extraction, GuidanceItem, ReportedMetric, ToneSignal, ValidatedExtraction

_TRANSLATE = str.maketrans({
    "\u2011": "-", "\u2010": "-", "\u202f": " ",  # non-breaking hyphen / narrow nbsp (IR sites)
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


def normalize(text: str) -> str:
    text = text.translate(_TRANSLATE).lower()
    text = text.replace("|", " ")  # table cell separators from HTML->text
    return re.sub(r"\s+", " ", text).strip()


def find_quote(quote: str, sources: dict[str, str]) -> str | None:
    """Return the name of the document containing the quote, else None.
    '...' splits the quote into pieces that must appear in order, close together."""
    pieces = [normalize(p) for p in re.split(r"\.\.\.|…", quote) if normalize(p)]
    if not pieces:
        return None
    for name, text in sources.items():
        doc = normalize(text)
        pos, ok, start = 0, True, None
        for p in pieces:
            i = doc.find(p, pos)
            if i == -1 or (start is not None and i - pos > 600):
                ok = False
                break
            start = i if start is None else start
            pos = i + len(p)
        if ok:
            return name
    return None


@dataclass(frozen=True)
class NumToken:
    value: float
    kind: str  # "pct", "usd", or "plain"


_NUM = re.compile(
    r"(?P<dollar>\$\s*)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<after>\s*(?:%|percent|percentage points?|points?|billion|million|bn|mm|m\b|b\b))?",
    re.I,
)


def numbers_in(text: str) -> list[NumToken]:
    out = []
    for m in _NUM.finditer(text.translate(_TRANSLATE)):
        v = float(m.group("num").replace(",", ""))
        after = (m.group("after") or "").strip().lower()
        if after.startswith(("%", "percent", "percentage", "point")):
            kind = "pct"
        elif m.group("dollar") or after in ("billion", "million", "bn", "mm", "m", "b"):
            kind = "usd"
        else:
            kind = "plain"
        out.append(NumToken(v, kind))
    return out


_COMPATIBLE = {
    "percent": {"pct", "plain"},
    "usd_billions": {"usd", "plain"},
    "usd_millions": {"usd", "plain"},
    "usd_per_share": {"usd", "plain"},
    "other": {"pct", "usd", "plain"},
}


def number_supported(value: float, unit: str, tokens: list[NumToken], allow_scale: bool = True) -> bool:
    kinds = _COMPATIBLE.get(unit, {"pct", "usd", "plain"})
    target = abs(value)
    scales = (1, 1000, 0.001) if allow_scale and unit in ("usd_billions", "usd_millions") else (1,)
    for t in tokens:
        if t.kind not in kinds:
            continue
        for s in scales:
            if abs(t.value * s - target) < 1e-6 * max(1.0, target):
                return True
    return False


def _check(item, fields: list[tuple[str, str]], sources: dict[str, str]) -> Check:
    reasons = []
    doc = find_quote(item.source_quote, sources)
    if doc is None:
        reasons.append("source_quote not found verbatim in any source document")
    tokens = numbers_in(item.source_quote)
    for field, unit in fields:
        v = getattr(item, field)
        if v is None:
            continue
        if not number_supported(v, unit, tokens):
            reasons.append(f"{field}={v:g} ({unit}) does not appear in source_quote")
    if isinstance(item, GuidanceItem):
        if item.low is None and item.high is None and not item.qualitative:
            reasons.append("guidance has neither a number nor a qualitative description")
        if item.low is not None and item.high is not None and item.low > item.high:
            reasons.append("low is greater than high")
    return Check(status="rejected" if reasons else "verified", source_doc=doc, reasons=reasons)


def validate(ex: Extraction, sources: dict[str, str], model: str | None = None) -> ValidatedExtraction:
    g = [(i, _check(i, [("low", i.unit), ("high", i.unit)], sources)) for i in ex.guidance]
    r = [(i, _check(i, [("value", i.unit), ("yoy_change_pct", "percent")], sources)) for i in ex.reported]
    t = [(i, _check(i, [], sources)) for i in ex.tone]
    return ValidatedExtraction(company=ex.company, ticker=ex.ticker, quarter=ex.quarter, model=model,
                               guidance=g, reported=r, tone=t)
