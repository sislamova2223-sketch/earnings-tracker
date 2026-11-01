# Earnings Call Tracker

**Live site:** https://sislamova2223-sketch.github.io/earnings-tracker/

A searchable website that tracks what management says on earnings calls. Every weekday a GitHub Action checks
SEC EDGAR for each covered company's newest earnings release. When a new one appears, the Action pulls the call
transcript and has Claude extract **forward guidance, reported results and management tone**. Before anything is
published, Python code **checks every figure against the source documents**.

Current coverage: **Bloom Energy (BE), Microsoft (MSFT), Alphabet (GOOGL)**. Anyone with access can add a company
from the website.

---

## Why it exists

Reading three or four transcripts in an earnings week is slow, and LLM summaries can't be trusted on numbers.
This project uses the LLM only for what it's good at, which is finding and structuring the relevant statements. A
deterministic check then decides whether each figure is published. If a number doesn't appear word for word in
the company's own words, it doesn't reach the site.

## How it works

```
SEC EDGAR (8-K, Item 2.02, Ex. 99.1) ─┐
                                      ├─► Claude: structured extraction ─► validator ─► docs/data/*.json ─► website
Investor relations transcript ────────┘     (every item carries a           (quote + number
  or Motley Fool fallback                     verbatim source quote)          checks)
```

1. **Detect.** `edgar.py` finds the company's latest 8-K with Item 2.02 (Results of Operations). If that filing
   is already on the site, nothing happens, so the daily run costs nothing on quiet days.
2. **Fetch.** It downloads the press release (Exhibit 99.1) from EDGAR. `transcripts.py` then looks for the call
   transcript, first on the company's investor relations site (Microsoft and Alphabet publish theirs), then at a
   transcript URL pinned in `coverage.json`, then on the Motley Fool's free transcript page. If none is found,
   the call is analyzed from the press release alone and marked as such on the site.
3. **Extract.** `extract.py` sends both documents to Claude with a forced tool call, so the reply is JSON that
   matches the schema in `schema.py`. The prompt makes the model **copy, not compute**: every item must include
   the exact sentence it came from, and every number must appear in that sentence.
4. **Validate.** `validate.py` checks each item twice:
   - **Quote check:** the quote must appear verbatim in the press release or transcript. Case, whitespace, curly
     quotes and the special hyphens investor relations sites use are ignored.
   - **Number check:** every number in the item (low, high, value, y/y %) must appear in that quote, and of the
     right kind, so a `%` can't be matched by a `$` figure. `$1.03 billion` = `1,030` million is allowed.
   Items that fail are kept out of the main view and listed, with the reason, in each company's **audit log** on
   the site.
5. **Publish.** One JSON file per call goes to `docs/data/calls/`. GitHub Pages serves `docs/` as a static site
   with search across tickers, companies and the full text of every quote.

## Using the site

- **Search** by ticker, company or topic: `capex`, `Azure`, `margin`, `TPU`.
- **Open a company** to see its guidance table (range, basis, and whether management raised, lowered or
  maintained it), reported results, tone signals with the supporting quote, links to the transcript and SEC
  filing, and the audit log.
- **Request a company:** type a ticker and click *Request analysis*. This opens a GitHub issue titled `Add NVDA`.
  The `request.yml` workflow adds the company, analyzes its latest call, comments on the issue with the result,
  and closes it. Only the repo owner's requests run, so strangers can't spend the API credit.

## Setup (one time)

1. **API key:** create a key at [console.anthropic.com](https://console.anthropic.com) and add a few dollars of
   credit. Each call analyzed costs roughly $0.05–0.20.
2. **Add it to GitHub:** in the repo, go to **Settings → Secrets and variables → Actions → New repository secret**,
   name `ANTHROPIC_API_KEY`.
3. **SEC contact (recommended):** in the same place, on the **Variables** tab, add `SEC_USER_AGENT` with your name
   and email, e.g. `Jane Doe jane@example.com`. SEC asks automated clients to identify themselves.
4. **Turn on the website:** go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **First run:** go to **Actions → Update earnings calls → Run workflow**. After that it runs on its own every weekday
   evening, around 6–7 pm ET.

Optional: set a `TRACKER_MODEL` variable to use a different Claude model (default `claude-sonnet-5-5`).

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # never commit this
export SEC_USER_AGENT="Your Name you@example.com"

python -m guidance_tracker update            # all companies in coverage.json
python -m guidance_tracker update MSFT       # one company
python -m guidance_tracker update BE --force # re-analyze even if already on the site
python -m guidance_tracker add NVDA          # add a company and analyze its latest call
pytest -q                                    # tests (no network or API key needed)

cd docs && python -m http.server             # preview the site at http://localhost:8000
```

Offline demo of the validator on a fictional company, with three planted errors it catches:

```bash
python -m guidance_tracker run NWSC --quarter "Q1 FY26" \
  --press-release samples/NWSC/press_release.txt --transcript samples/NWSC/transcript.txt \
  --extraction samples/NWSC/extraction.json --out samples/output
```

## Adding or fixing a company by hand

`coverage.json` controls what's tracked:

```json
{ "ticker": "MSFT", "company": "Microsoft", "fy_end_month": 6, "transcript": "microsoft", "fool_slug": "microsoft-msft" }
```

- `fy_end_month` sets quarter labels: June year end → `FY27 Q1`, December → `Q3 2026`. `add` fills this from SEC.
- `transcript` picks an investor relations finder (`microsoft`, `alphabet`), or `fool` to go straight to the
  Motley Fool. To support another company's investor relations site, add a function in `transcripts.py`.
- If a transcript can't be found automatically, pin it: `"transcript_urls": {"Q3 2026": "https://..."}`, then run
  `update TICKER --force`.

## Project layout

| Path | Purpose |
|---|---|
| `guidance_tracker/edgar.py` | Ticker → CIK, latest earnings 8-K, Exhibit 99.1 text |
| `guidance_tracker/transcripts.py` | Transcript finders (investor relations sites, pinned URL, Motley Fool) |
| `guidance_tracker/quarters.py` | Fiscal quarter labels from filing dates |
| `guidance_tracker/extract.py` | Claude API call with forced structured output |
| `guidance_tracker/validate.py` | Quote and number checks |
| `guidance_tracker/update.py` | Orchestration; writes `docs/data` |
| `guidance_tracker/brief.py` | Optional one-page HTML/Markdown brief for a single call |
| `docs/` | The website (static HTML + JSON data) |
| `.github/workflows/` | `update` (daily), `request` (issue-driven), `pages` (deploy), `tests` |

## Limitations

- **Transcripts.** Not every company posts its transcript. The Motley Fool fallback depends on its URL pattern and
  on the site allowing automated requests. When both fail, the site shows the analysis is press-release-only. A
  pinned URL fixes that.
- **Copyright.** The site publishes analysis plus short supporting quotes and links out to the full transcript. It
  never republishes full transcripts.
- **Tone is judgment.** Guidance and results are checked mechanically. Tone labels (positive, cautious, negative)
  are the model's reading, but the quote behind each one is still checked against the source.
- **Not investment advice.** This is a research and learning project.

## Roadmap

- [ ] Quarter-over-quarter diff: flag guidance raised, lowered or dropped versus the prior call
- [ ] Energy names (XOM, CVX, COP) with sector-specific fields: production, realized prices, buybacks
- [ ] Email digest when a covered company reports

---

Built by Sabina Islamova · Finance, The Ohio State University Fisher College of Business
