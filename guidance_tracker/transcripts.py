"""Find and download the earnings call transcript for a quarter.

Order of preference:
  1. The company's own investor relations site (finders below; add more as coverage grows).
  2. A transcript URL pinned by hand in coverage.json ("transcript_urls": {"FY27 Q1": "https://..."}).
  3. The Motley Fool's free transcript, whose URL follows a predictable pattern.
If nothing is found the call is analyzed from the press release alone and flagged on the site.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import requests

from .edgar import html_to_text

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
MIN_CHARS = 8000  # a real transcript is long; shorter pages are error pages or teasers


def _get_text(url: str) -> str | None:
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    text = html_to_text(r.text)
    return text if len(text) >= MIN_CHARS else None


def _microsoft(q: dict) -> tuple[str, str] | None:
    url = f"https://www.microsoft.com/en-us/investor/events/fy-{q['fy']}/earnings-fy-{q['fy']}-q{q['q']}"
    text = _get_text(url)
    return (text, url) if text and "Transcript" in text else None


def _alphabet(q: dict) -> tuple[str, str] | None:
    try:
        html = requests.get("https://abc.xyz/investor/", headers=BROWSER_HEADERS, timeout=30).text
    except requests.RequestException:
        return None
    m = re.search(rf'href="([^"]*{q["fy"]}-Q{q["q"]}-Earnings-Call[^"]*)"', html)
    if not m:
        return None
    url = m.group(1) if m.group(1).startswith("http") else "https://abc.xyz" + m.group(1)
    text = _get_text(url)
    return (text, url) if text else None


IR_FINDERS = {"microsoft": _microsoft, "alphabet": _alphabet}


def _fool(company: dict, q: dict, call_date: date) -> tuple[str, str] | None:
    slug = company.get("fool_slug")
    if not slug:
        return None
    for d in (call_date, call_date + timedelta(days=1), call_date - timedelta(days=1)):
        url = (f"https://www.fool.com/earnings/call-transcripts/{d:%Y/%m/%d}/"
               f"{slug}-q{q['q']}-{q['fy']}-earnings-call-transcript/")
        text = _get_text(url)
        if text:
            return text, url
    return None


def find_transcript(company: dict, q: dict, call_date: date) -> tuple[str, str, str] | None:
    """Return (text, url, source label) or None."""
    finder = IR_FINDERS.get(company.get("transcript", ""))
    if finder and (hit := finder(q)):
        return hit[0], hit[1], f"{company['company']} investor relations"
    pinned = (company.get("transcript_urls") or {}).get(q["label"])
    if pinned and (text := _get_text(pinned)):
        return text, pinned, "Transcript"
    if hit := _fool(company, q, call_date):
        return hit[0], hit[1], "Motley Fool"
    return None


def slugify(name: str) -> str:
    name = re.sub(r"\b(inc|corp|corporation|co|ltd|plc|holdings|group|company|the)\b\.?", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
