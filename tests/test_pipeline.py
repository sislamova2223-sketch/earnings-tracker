import json
from datetime import date
from pathlib import Path

from guidance_tracker.edgar import _EX991, html_to_text
from guidance_tracker.quarters import fiscal_quarter, quarter_end_before
from guidance_tracker.transcripts import slugify
from guidance_tracker.validate import find_quote, numbers_in, number_supported

ROOT = Path(__file__).resolve().parents[1]


def test_quarter_labels():
    assert fiscal_quarter(quarter_end_before(date(2026, 10, 28)), 6)["label"] == "FY27 Q1"   # Microsoft
    assert fiscal_quarter(quarter_end_before(date(2026, 10, 22)), 12)["label"] == "Q3 2026"  # Bloom
    assert fiscal_quarter(quarter_end_before(date(2026, 2, 4)), 12)["label"] == "Q4 2025"    # January/February reports
    assert fiscal_quarter(quarter_end_before(date(2026, 7, 29)), 6)["label"] == "FY26 Q4"


def test_exhibit_names():
    for name in ["msft-ex99_1.htm", "googexhibit991q32026.htm", "ex991_q326financialresults.htm", "d291965dex991.htm"]:
        assert _EX991.search(name), name


def test_slug():
    assert slugify("Bloom Energy Corp") == "bloom-energy"
    assert slugify("NVIDIA CORP") == "nvidia"


def test_non_breaking_hyphen_from_ir_sites():
    src = {"transcript": "our full‑year 2026 CapEx guidance range of $195‑$205 billion remain unchanged."}
    q = "our full-year 2026 CapEx guidance range of $195-$205 billion remain unchanged."
    assert find_quote(q, src) == "transcript"
    assert number_supported(205, "usd_billions", numbers_in(q))


def test_html_to_text_keeps_table_cells_apart():
    assert "Rev | 18,600" in html_to_text("<table><tr><td>Rev</td><td>18,600</td></tr></table>")


def test_site_data_is_consistent():
    index = json.loads((ROOT / "docs/data/index.json").read_text())
    for entry in index["calls"]:
        doc = json.loads((ROOT / "docs/data" / entry["file"]).read_text())
        items = doc["guidance"] + doc["reported"] + doc["tone"]
        assert doc["counts"]["total"] == len(items)
        assert doc["counts"]["verified"] == sum(i["check"]["status"] == "verified" for i in items)
        for i in items:  # every published number is backed by its quote
            if i["check"]["status"] != "verified":
                continue
            toks = numbers_in(i["source_quote"])
            for f in ("low", "high", "value"):
                if i.get(f) is not None:
                    assert number_supported(i[f], i["unit"], toks), (doc["id"], i)
