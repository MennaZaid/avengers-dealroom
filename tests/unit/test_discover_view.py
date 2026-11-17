"""Discover page labels (ui/discover_view.py): replay mode, no Streamlit needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ui"))
import discover_view as dv


def test_run_status_says_what_the_run_did_not_the_gate():
    assert dv.run_label("awaiting_approval") == "Run: ✅ completed · waiting for your decision"
    assert dv.run_label("approved") == "Run: ✅ completed · you chose Go"
    assert "go" not in dv.run_label("awaiting_approval").lower().split("·")[0]
    assert dv.run_label("rejected", "ar").startswith("التشغيل")


def test_gate_recommendation_is_the_heading_coloured_by_outcome():
    el, md = dv.gate_banner({"recommendation": "stop", "reasons": ["founder fit fails"]})
    assert el == "error" and md.startswith("### Recommendation: STOP") and "founder fit fails" in md
    assert dv.gate_banner({"recommendation": "repeat"})[0] == "warning"
    assert dv.gate_banner({"recommendation": "pivot", "pivot_to": "I2"}) == ("warning", "### Recommendation: PIVOT → I2")
    assert dv.gate_banner({"recommendation": "go"})[0] == "success"


def test_unknown_market_size_is_one_honest_line_and_never_an_estimate():
    m = {"tam": [None, None], "sam": [None, None], "som": [None, None]}
    assert dv.market_size_line(m) == ("Market size unknown: no sourced figures found. The system doesn't "
                                      "estimate without sources.")
    assert dv.market_size_line({**m, "som": [100, 400]}) is None          # a sourced figure is shown, not hidden
    assert dv.market_size_line({}) is not None and dv.market_size_line(m, "ar").startswith("حجم السوق")


def test_competitors_without_a_price_say_so():
    assert dv.price_cell({"name": "X"}) == "no published price found"
    assert dv.price_cell({"name": "X", "price": None}) == "no published price found"
    assert dv.price_cell({"name": "X", "price": "$9/month"}) == "$9/month"


def test_no_zero_byte_exports():
    assert not dv.exportable([]) and not dv.exportable([{}])
    assert dv.exportable([{"name": "X"}])
    assert dv.nothing_to_export() == "nothing to export yet"
