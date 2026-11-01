from pathlib import Path

from guidance_tracker.extract import load_fixture
from guidance_tracker.schema import GuidanceItem, ReportedMetric
from guidance_tracker.validate import _check, find_quote, numbers_in, number_supported, validate

SRC = {"transcript": "We expect total revenue of $19.4 to $19.8 billion, which represents growth of 13% to 15%.\n"
                     "Revenue in Devices was $4,300 million and increased 3%. Pricing — it held up."}


def g(**kw):
    base = dict(metric="Rev", period="Q2", unit="usd_billions", direction="initiated",
                source_quote="We expect total revenue of $19.4 to $19.8 billion")
    base.update(kw)
    return GuidanceItem(**base)


def test_exact_quote_and_numbers_pass():
    assert _check(g(low=19.4, high=19.8), [("low", "usd_billions"), ("high", "usd_billions")], SRC).status == "verified"


def test_hallucinated_number_rejected():
    c = _check(g(low=19.4, high=20.1), [("low", "usd_billions"), ("high", "usd_billions")], SRC)
    assert c.status == "rejected" and "high=20.1" in c.reasons[0]


def test_paraphrased_quote_rejected():
    c = _check(g(low=19.4, high=19.8, source_quote="Revenue expected at $19.4-19.8B"), [("low", "usd_billions")], SRC)
    assert any("not found" in r for r in c.reasons)


def test_whitespace_case_and_dash_normalisation():
    assert find_quote("PRICING - it   held up.", SRC) == "transcript"


def test_ellipsis_pieces_must_be_in_order():
    assert find_quote("We expect total revenue ... growth of 13% to 15%", SRC) == "transcript"
    assert find_quote("growth of 13% to 15% ... We expect total revenue", SRC) is None


def test_scale_millions_to_billions():
    m = ReportedMetric(metric="Devices", period="Q1", value=4.3, unit="usd_billions", yoy_change_pct=3,
                       source_quote="Revenue in Devices was $4,300 million and increased 3%")
    assert _check(m, [("value", "usd_billions"), ("yoy_change_pct", "percent")], SRC).status == "verified"


def test_percent_cannot_be_matched_by_dollar_figure():
    toks = numbers_in("Revenue was $14 billion and increased 9%")
    assert not number_supported(14, "percent", toks)
    assert number_supported(9, "percent", toks)
    assert not number_supported(9, "usd_billions", toks)


def test_qualitative_guidance_needs_text():
    c = _check(g(source_quote="We expect total revenue"), [("low", "usd_billions")], SRC)
    assert c.status == "rejected"


def test_sample_fixture_catches_the_three_planted_errors():
    root = Path(__file__).resolve().parents[1] / "samples" / "NWSC"
    sources = {"press_release": (root / "press_release.txt").read_text(),
               "transcript": (root / "transcript.txt").read_text()}
    v = validate(load_fixture(root / "extraction.json"), sources)
    rejected = {(i.metric if hasattr(i, "metric") else i.topic) for i, c in v.guidance + v.reported + v.tone
                if c.status == "rejected"}
    assert rejected == {"Business Applications revenue", "Net income", "Bookings"}
