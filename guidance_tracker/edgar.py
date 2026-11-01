"""SEC EDGAR access: company lookup and the earnings press release (8-K, Item 2.02, Exhibit 99.1).

SEC asks every client to send a descriptive User-Agent with contact details. Set SEC_USER_AGENT
(the GitHub workflow reads it from a repository variable).
"""
from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from html.parser import HTMLParser

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
DEFAULT_UA = "EarningsTracker sislamova2223-sketch@users.noreply.github.com"  # override with SEC_USER_AGENT


@lru_cache(maxsize=1)
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": os.environ.get("SEC_USER_AGENT") or DEFAULT_UA,
                      "Accept-Encoding": "gzip, deflate"})
    return s


class SECThrottled(RuntimeError):
    """SEC is rate-limiting this machine's IP (common on shared CI runners). Try again later."""


RETRY_WAITS = (20, 60, 120)  # seconds; SEC lifts most throttles within ~10 minutes


def _get(url: str) -> requests.Response:
    for wait in (*RETRY_WAITS, None):
        time.sleep(0.15)  # stay well under SEC's 10 requests/second limit
        r = _session().get(url, timeout=30)
        throttled = r.status_code == 429 or (r.status_code == 403 and "Rate Threshold" in r.text)
        if not throttled:
            if r.status_code == 403:
                raise RuntimeError(f"SEC refused {url} (403). Check SEC_USER_AGENT is 'Name email@domain'.")
            r.raise_for_status()
            return r
        if wait is None:
            raise SECThrottled(f"SEC is rate-limiting this runner ({url}); will retry on the next run")
        print(f"  SEC throttled this runner, waiting {wait}s...", flush=True)
        time.sleep(wait)


@lru_cache(maxsize=1)
def _tickers() -> dict:
    return _get(TICKERS_URL).json()


def lookup(ticker: str, cik: int | None = None) -> dict:
    """CIK, SEC company name and fiscal-year-end month for a ticker.
    Pass a known CIK to skip downloading SEC's full ticker list."""
    if cik:
        sub = submissions(int(cik))
        return {"cik": int(cik), "sec_name": sub.get("name", ticker), "exchange": _exchange(sub),
                "fy_end_month": int((sub.get("fiscalYearEnd") or "1231")[:2])}
    for row in _tickers().values():
        if row["ticker"].upper() == ticker.upper():
            cik = int(row["cik_str"])
            sub = submissions(cik)
            fye = sub.get("fiscalYearEnd") or "1231"
            return {"cik": cik, "sec_name": row["title"], "exchange": _exchange(sub), "fy_end_month": int(fye[:2])}
    raise ValueError(f"Ticker {ticker} not found on SEC EDGAR")


def _exchange(sub: dict) -> str:
    ex = [e.lower() for e in (sub.get("exchanges") or []) if e]
    return "nasdaq" if any("nasdaq" in e for e in ex) else (ex[0] if ex else "nyse")


@lru_cache(maxsize=64)
def submissions(cik: int) -> dict:
    return _get(SUBMISSIONS_URL.format(cik=cik)).json()


def latest_earnings_8k(cik: int) -> dict:
    """Newest 8-K that includes Item 2.02 (Results of Operations and Financial Condition)."""
    recent = submissions(cik)["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "8-K" and "2.02" in (recent["items"][i] or ""):
            return {"accession": recent["accessionNumber"][i], "filing_date": recent["filingDate"][i]}
    raise ValueError(f"No Item 2.02 8-K found for CIK {cik}")


_EX991 = re.compile(r"(ex|exhibit|dex)[-_]?99[-_.]?0?1", re.I)


def fetch_press_release(cik: int, accession: str) -> tuple[str, str]:
    """Return (text, url) of Exhibit 99.1 for a filing."""
    base = ARCHIVE_URL.format(cik=cik, acc=accession.replace("-", ""))
    names = [it["name"] for it in _get(base + "index.json").json()["directory"]["item"]]
    htm = [n for n in names if n.lower().endswith((".htm", ".html")) and "index" not in n.lower()]
    ex = next((n for n in htm if _EX991.search(n)), None) or next((n for n in htm if "99" in n), None)
    if not ex:
        raise ValueError(f"No Exhibit 99.1 in filing {accession}: {names}")
    return html_to_text(_get(base + ex).text), base + ex


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "table", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()
