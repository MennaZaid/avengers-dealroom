"""Phase 4 Commercial: sourced prices only, break-even in code, draft policies, go/repeat/pivot/stop. No model."""

import os
from pathlib import Path

import pytest

from venture_os import commercial_stage as cs
from venture_os import evidence
from venture_os.agents import commercial_pricing as cp
from venture_os.agents import policy_drafter as pd
from venture_os.decision_log import read_log
from venture_os.guardrails import check_output
from venture_os.onboarding.briefs import ConfirmedBrief

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "briefs"


def _brief(name="pharmastock_v1.json", **fields):
    b = ConfirmedBrief.from_file(FIX / name)
    for k, v in fields.items():
        b.fields[k] = {"value": v, "status": "answered"}
    return b


def _price(n, text, url="https://example.org/p", date="2026-11-10", label="evidenced"):
    return {"id": f"E{n}", "kind": "price", "text": text, "label": label, "sources": [url] if url else [],
            "date": date}


THREE = [_price(1, "App A: $10 per month"), _price(2, "App B: $20 per month"), _price(3, "App C: $30 per month")]


def _out(name):
    return (Path(os.environ["OUTPUTS_DIR"]) / name).read_text(encoding="utf-8")


def _run(brief=None, items=THREE):
    brief = brief or _brief()
    return cs.run_commercial_stage(brief.brief_id, brief.version, brief=brief, items=items)


def test_contract_and_files():
    r = _run()
    assert r.decision.phase == 4 and r.decision.gate == "commercial" and r.stubbed == []
    assert r.files == list(cs.FILES.values())
    for f in r.files:
        assert "Brief id: " in _out(f) and _brief().brief_id in _out(f), f
        assert check_output(_out(f)) == []
    log = read_log()
    assert log[0]["action"] == "set_gate_thresholds"  # thresholds logged before step 1
    assert all(e.get("brief_id") == _brief().brief_id for e in log)


def test_no_price_without_url_or_date():
    rows, skipped = cp.research_prices([_price(1, "$10", url=None), _price(2, "$12", date=None),
                                        _price(3, "$14", label="assumption"), _price(4, "$15")])
    assert [r.item_id for r in rows] == ["E4"] and skipped == 3


def test_fewer_than_three_prices_is_repeat():
    assert _run(items=THREE[:2]).decision.outcome == "repeat"


def test_break_even_on_fixed_numbers():
    # pharmastock: budget 3,000 USD, "for 6 months"; median of 10/20/30 = 20 -> 150 customer-months -> 25 a month
    s = cp.set_price(cp.research_prices(THREE)[0], _brief())
    assert (s.min, s.median, s.max, s.customer_months, s.months, s.per_month) == (10, 20, 30, 150, 6, 25)
    md = _out("phase4_step2_price.md") if _run() else ""
    assert "ESTIMATE" in md and "| 150 (ESTIMATE) |" in md


def test_go_pivot_stop():
    assert _run().decision.outcome == "go"
    cheap = [_price(i, f"App {i}: $0.50 per month") for i in range(1, 4)]  # 6,000 customer-months -> 1,000 a month
    assert _run(items=cheap).decision.outcome == "pivot"
    free = [_price(i, f"App {i} is free") for i in range(1, 4)]
    assert _run(items=free).decision.outcome == "stop"
    excluded = _brief()
    excluded.product_check = {"status": "excluded", "categories": ["financial"]}
    assert _run(brief=excluded).decision.outcome == "stop"
    assert "phase4_gate_commercial.md" in _run().files


def test_income_promise_in_a_source_is_blocked():
    items = THREE + [_price(4, "Guaranteed income of $500 with this $40 app")]
    r = _run(items=items)
    assert "Guaranteed income" not in _out("phase4_step1_pricing_research.md")
    assert r.decision.actual == 3


def test_policies_draft_label_fallback_and_refund(monkeypatch):
    monkeypatch.setattr(pd, "legal_sources", lambda cc: [])  # the registry has no legal source for the country
    _run()
    for f in ("phase4_step3_terms.md", "phase4_step4_privacy.md", "phase4_step5_refund_policy.md"):
        md = _out(f)
        assert md.splitlines()[2] == f"**{pd.DRAFT_LABEL}**", f  # right after the Brief id line
        assert "No verified official source found for Kenya" in md
    assert "An approved refund revokes access to the product" in _out("phase4_step5_refund_policy.md")


def test_official_sources_are_cited_when_the_registry_has_them(monkeypatch):
    monkeypatch.setattr(pd, "legal_sources", lambda cc: [{"id": "KE-1", "source_name": "Kenya Law",
                                                          "url": "https://kenyalaw.org"}])
    _run()
    md = _out("phase4_step3_terms.md")
    assert "Kenya Law: https://kenyalaw.org" in md and "No verified official source" not in md


def test_phase4_evidence_items_for_phase5():
    b = _brief()
    _run(brief=b)
    stored = evidence.load(b.brief_id)
    assert [i.label for i in stored if i.phase == 4] == ["evidenced", "evidenced", "evidenced", "inferred", "inferred"]
    assert stored[-1].text.startswith("Phase 4 commercial gate: go")


@pytest.mark.parametrize("text,amount,cur", [("$9.99/month", 9.99, "USD"), ("150 EGP", 150, "EGP"),
                                             ("KES 1,499 per month", 1499, "KES"), ("Free", 0, "")])
def test_parse_price(text, amount, cur):
    assert cp.parse_price(text) == (amount, cur)
