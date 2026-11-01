"""Structured output the LLM must return, plus the validated wrappers.

Every extracted item carries a verbatim `source_quote`. The validator uses that
quote to prove the item exists in the source and that every number in the item
appears in the quote. Nothing reaches the brief without passing that check.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Unit = Literal["usd_billions", "usd_millions", "usd_per_share", "percent", "other"]


class GuidanceItem(BaseModel):
    metric: str = Field(description="What is being guided, e.g. 'Total revenue', 'Intelligent Cloud revenue', 'Operating margin', 'Capex'.")
    period: str = Field(description="Period the guidance covers, e.g. 'FY26 Q2', 'FY26'.")
    low: Optional[float] = Field(None, description="Low end of the range exactly as written in the quote. Null if qualitative.")
    high: Optional[float] = Field(None, description="High end of the range exactly as written. Equal to low for a point estimate. Null if qualitative.")
    unit: Unit
    basis: Optional[str] = Field(None, description="Qualifier such as 'constant currency', 'y/y growth', 'non-GAAP'.")
    qualitative: Optional[str] = Field(None, description="Use when guidance has no number, e.g. 'low double-digit growth', 'sequentially higher'.")
    direction: Literal["raised", "lowered", "maintained", "initiated", "unclear"] = Field(
        description="How management characterised this guidance versus their prior outlook, based only on what they said.")
    source_quote: str = Field(description="Exact sentence(s) copied verbatim from the source. Use '...' only to skip text between two verbatim pieces.")


class ReportedMetric(BaseModel):
    metric: str
    period: str
    value: float = Field(description="Value exactly as written in the quote. Do not convert units or compute.")
    unit: Unit
    yoy_change_pct: Optional[float] = Field(None, description="Year-over-year change in percent, only if stated in the quote.")
    source_quote: str


class ToneSignal(BaseModel):
    topic: str = Field(description="e.g. 'AI demand', 'Capacity constraints', 'Enterprise spending', 'FX'.")
    signal: Literal["positive", "cautious", "negative", "neutral"]
    summary: str = Field(description="One short sentence in your own words.")
    source_quote: str


class Extraction(BaseModel):
    company: str
    ticker: str
    quarter: str
    guidance: list[GuidanceItem] = []
    reported: list[ReportedMetric] = []
    tone: list[ToneSignal] = []


class Check(BaseModel):
    status: Literal["verified", "rejected"]
    source_doc: Optional[str] = None  # which document the quote was found in
    reasons: list[str] = []


class ValidatedExtraction(BaseModel):
    company: str
    ticker: str
    quarter: str
    model: Optional[str] = None
    guidance: list[tuple[GuidanceItem, Check]] = []
    reported: list[tuple[ReportedMetric, Check]] = []
    tone: list[tuple[ToneSignal, Check]] = []

    def counts(self) -> dict:
        allc = [c for _, c in self.guidance + self.reported + self.tone]
        v = sum(c.status == "verified" for c in allc)
        return {"total": len(allc), "verified": v, "rejected": len(allc) - v}
