"""Orchestration: find each covered company's latest earnings call, analyze it, publish it to the site.

  coverage.json         companies to track
  docs/data/calls/*.json one validated analysis per call (what the website reads)
  docs/data/index.json  list of calls + last update time
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from . import edgar
from .extract import DEFAULT_MODEL, extract_with_llm
from .quarters import fiscal_quarter, quarter_end_before
from .schema import ValidatedExtraction
from .transcripts import find_transcript, slugify
from .validate import validate

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / "coverage.json"
DATA = ROOT / "docs" / "data"


def load_coverage() -> list[dict]:
    return json.loads(COVERAGE.read_text())["companies"]


def save_coverage(companies: list[dict]) -> None:
    companies.sort(key=lambda c: c["ticker"])
    COVERAGE.write_text(json.dumps({"companies": companies}, indent=2) + "\n")


def add_company(ticker: str) -> dict:
    """Add a ticker to coverage using SEC data. Returns the coverage entry."""
    ticker = ticker.upper().strip()
    companies = load_coverage()
    for c in companies:
        if c["ticker"] == ticker:
            return c
    info = edgar.lookup(ticker)
    name = info["sec_name"].title() if info["sec_name"].isupper() else info["sec_name"]
    entry = {"ticker": ticker, "company": name, "cik": info["cik"], "exchange": info["exchange"],
             "fy_end_month": info["fy_end_month"],
             "transcript": "fool", "fool_slug": f"{slugify(name)}-{ticker.lower()}"}
    companies.append(entry)
    save_coverage(companies)
    return entry


def existing_calls() -> dict[str, dict]:
    out = {}
    for p in (DATA / "calls").glob("*.json"):
        d = json.loads(p.read_text())
        out[d["id"]] = d
    return out


def to_site_doc(v: ValidatedExtraction, meta: dict) -> dict:
    def pack(pairs):
        rows = []
        for item, check in pairs:
            row = {k: val for k, val in item.model_dump().items() if val is not None}
            c = {"status": check.status, "source_doc": check.source_doc}
            if check.reasons:
                c["reasons"] = check.reasons
            row["check"] = c
            rows.append(row)
        return rows
    return {**meta, "guidance": pack(v.guidance), "reported": pack(v.reported), "tone": pack(v.tone),
            "counts": v.counts()}


def rebuild_index() -> None:
    calls = sorted(existing_calls().values(), key=lambda c: (c["ticker"], c.get("call_date", "")))
    index = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "calls": [{"id": c["id"], "ticker": c["ticker"], "company": c["company"], "quarter": c["quarter"],
                        "call_date": c.get("call_date"), "file": f"calls/{c['id']}.json"} for c in calls]}
    (DATA / "index.json").write_text(json.dumps(index, indent=2) + "\n")


def update_company(company: dict, force: bool = False, model: str = DEFAULT_MODEL, log=print) -> str:
    """Analyze the company's latest earnings call if it isn't on the site yet. Returns a status line."""
    t = company["ticker"]
    info = edgar.lookup(t, company.get("cik"))
    filing = edgar.latest_earnings_8k(info["cik"])
    done = [c for c in existing_calls().values() if c["ticker"] == t and c.get("accession") == filing["accession"]]
    if done and not force:
        return f"{t}: up to date ({done[0]['quarter']})"

    filed = date.fromisoformat(filing["filing_date"])
    q = fiscal_quarter(quarter_end_before(filed), company.get("fy_end_month", info["fy_end_month"]))
    log(f"{t}: new earnings 8-K {filing['accession']} filed {filed} -> {q['label']}")

    pr_text, pr_url = edgar.fetch_press_release(info["cik"], filing["accession"])
    sources = {"press_release": pr_text}
    links = []
    found = find_transcript({**company, "exchange": company.get("exchange") or info["exchange"]}, q, filed)
    if found:
        text, url, label = found
        sources["transcript"] = text
        links.append({"label": f"Call transcript ({label})", "url": url})
        log(f"{t}: transcript from {url}")
    else:
        log(f"{t}: no transcript found, analyzing the press release only")
    links.append({"label": "Press release (SEC 8-K)", "url": pr_url})

    ex = extract_with_llm(sources, company["company"], t, q["label"], model)
    v = validate(ex, sources, model=model)
    call_id = f"{t}-{q['label'].replace(' ', '_')}"
    doc = to_site_doc(v, {
        "id": call_id, "ticker": t, "company": company["company"], "quarter": q["label"],
        "call_date": filing["filing_date"], "accession": filing["accession"], "links": links,
        "transcript_found": bool(found), "model": model,
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    (DATA / "calls").mkdir(parents=True, exist_ok=True)
    (DATA / "calls" / f"{call_id}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    rebuild_index()
    c = v.counts()
    return f"{t}: analyzed {q['label']} - {c['verified']}/{c['total']} items verified, {c['rejected']} rejected"
