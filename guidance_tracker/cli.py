"""Command line.

  python -m guidance_tracker update            # every company in coverage.json
  python -m guidance_tracker update MSFT BE    # just these
  python -m guidance_tracker add NVDA          # add to coverage and analyze its latest call
  python -m guidance_tracker run ...           # one-off run on local files (see README)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .extract import DEFAULT_MODEL


def cmd_update(a):
    from .update import load_coverage, update_company
    cov = load_coverage()
    wanted = {t.upper() for t in a.tickers}
    targets = [c for c in cov if not wanted or c["ticker"] in wanted]
    missing = wanted - {c["ticker"] for c in cov}
    if missing:
        sys.exit(f"Not in coverage.json: {', '.join(sorted(missing))}. Use `add` first.")
    from .edgar import SECThrottled
    failures = 0
    for c in targets:
        try:
            print(update_company(c, force=a.force, model=a.model))
        except SECThrottled as e:  # not our bug; the next scheduled run gets a fresh runner IP
            print(f"{c['ticker']}: SKIPPED - {e}")
        except Exception as e:  # keep going so one bad company doesn't block the rest
            failures += 1
            print(f"{c['ticker']}: FAILED - {e}")
    if failures == len(targets) and targets:
        sys.exit(1)


def cmd_add(a):
    from .update import add_company, update_company
    for t in a.tickers:
        entry = add_company(t)
        print(f"{entry['ticker']}: in coverage as {entry['company']}")
        print(update_company(entry, force=a.force, model=a.model))


def cmd_run(a):
    from .brief import render
    from .extract import extract_with_llm, load_fixture
    from .validate import validate
    sources = {}
    if a.press_release:
        sources["press_release"] = Path(a.press_release).read_text(encoding="utf-8")
    if a.transcript:
        sources["transcript"] = Path(a.transcript).read_text(encoding="utf-8")
    if not sources:
        sys.exit("Give at least one of --press-release or --transcript")
    ex = load_fixture(Path(a.extraction)) if a.extraction else \
        extract_with_llm(sources, a.company or a.ticker, a.ticker, a.quarter, a.model)
    v = validate(ex, sources, model=None if a.extraction else a.model)
    for k, p in render(v, Path(a.out)).items():
        print(f"{k:5} -> {p}")
    c = v.counts()
    print(f"{c['verified']}/{c['total']} verified, {c['rejected']} rejected")


def main(argv=None):
    p = argparse.ArgumentParser(prog="guidance_tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("update", help="Analyze any new earnings calls for covered companies")
    u.add_argument("tickers", nargs="*")
    u.add_argument("--force", action="store_true", help="Re-analyze even if the latest call is on the site")
    u.add_argument("--model", default=DEFAULT_MODEL)
    u.set_defaults(func=cmd_update)

    ad = sub.add_parser("add", help="Add tickers to coverage and analyze their latest call")
    ad.add_argument("tickers", nargs="+")
    ad.add_argument("--force", action="store_true")
    ad.add_argument("--model", default=DEFAULT_MODEL)
    ad.set_defaults(func=cmd_add)

    r = sub.add_parser("run", help="One-off: analyze local files and write a one-page brief")
    r.add_argument("ticker")
    r.add_argument("--quarter", required=True)
    r.add_argument("--company")
    r.add_argument("--press-release")
    r.add_argument("--transcript")
    r.add_argument("--extraction", help="Saved extraction JSON instead of calling the LLM")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--out", default="briefs")
    r.set_defaults(func=cmd_run)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
