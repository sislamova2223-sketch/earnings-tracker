"""LLM structured extraction via the Anthropic API (forced tool call -> JSON).

The prompt is written so the model's job is copying, not computing: every
number must be lifted verbatim from a quoted sentence. The validator enforces it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import Extraction

DEFAULT_MODEL = os.environ.get("TRACKER_MODEL") or "claude-sonnet-5-5"

SYSTEM = """You are an equity research associate extracting facts from an earnings release and call transcript.

Rules (strict):
1. source_quote must be copied character-for-character from the documents. Never paraphrase inside source_quote. Use '...' only to join two verbatim pieces from the same passage.
2. Every number you put in low, high, value or yoy_change_pct must appear literally in that item's source_quote. Do not convert units, annualise, add, or compute anything. If the quote says "$24.5 billion", write 24.5 with unit usd_billions. If it says "$24,500 million", write 24500 with unit usd_millions.
3. For a range like "$24.0 to $24.5 billion" use low=24.0, high=24.5. For a point estimate set low=high.
4. If guidance has no number ("low double-digit growth"), leave low/high null and fill qualitative.
5. direction reflects only what management said about their prior outlook ("raising", "reiterating"). If they did not say, use "unclear" (or "initiated" for a first-time outlook).
6. Guidance = forward-looking outlook only. Reported = actual results for the quarter just ended. Cover total company and each reported segment.
7. Tone: 3-6 signals that an analyst would care about (demand, pricing, capacity, margins, macro, capital spending). Prefer prepared remarks from the CFO/CEO and Q&A answers over boilerplate.
8. Skip safe-harbor language."""


MAX_DOC_CHARS = 150_000  # keeps one call well inside the context window


def build_documents(sources: dict[str, str]) -> str:
    return "\n\n".join(f'<document name="{name}">\n{text[:MAX_DOC_CHARS]}\n</document>' for name, text in sources.items())


def extract_with_llm(sources: dict[str, str], company: str, ticker: str, quarter: str, model: str = DEFAULT_MODEL) -> Extraction:
    import anthropic  # imported here so the offline/fixture path needs no API package

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    tool = {
        "name": "record_extraction",
        "description": "Record the structured extraction.",
        "input_schema": Extraction.model_json_schema(),
    }
    msg = client.messages.create(
        model=model,
        max_tokens=8000,
        temperature=0,
        system=SYSTEM,
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_extraction"},
        messages=[{
            "role": "user",
            "content": f"{build_documents(sources)}\n\nCompany: {company} ({ticker}). Quarter: {quarter}. Extract guidance, reported metrics, and tone.",
        }],
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    data = dict(block.input)
    data.update(company=company, ticker=ticker, quarter=quarter)
    return Extraction.model_validate(data)


def load_fixture(path: Path) -> Extraction:
    """Load a saved extraction (for offline runs, tests, or re-validating a past run)."""
    return Extraction.model_validate(json.loads(Path(path).read_text()))
