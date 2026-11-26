"""Smoke tests: every quote is found in its source, the portfolio respects the fund rules, the forecast is consistent."""
import yaml
from pathlib import Path
from dealroom import run, dossier, forecast

DATA = Path(__file__).resolve().parent.parent / "data"


def test_every_quote_is_found():
    ev = yaml.safe_load((DATA / "evidence.yaml").read_text(encoding="utf-8"))
    bad = [(n, r["quote"]) for n, rows in run.verify(ev).items() for r in rows if r["status"] == "NOT FOUND"]
    assert bad == []


def test_portfolio_respects_rules():
    evidence, scores, rules, res, vals, alloc = dossier.load()
    assert sum(alloc.values()) <= rules["fund_usd"] - rules["reserve_usd"]
    for n, a in alloc.items():
        assert rules["min_ticket_usd"] <= a <= rules["max_ticket_usd"]
        assert vals[n]["weighted"] >= rules["min_weighted_score"]
        if evidence[n].get("ask_usd"):
            assert a <= evidence[n]["ask_usd"]


def test_forecast_downside_below_base():
    evidence, scores, rules, res, vals, alloc = dossier.load()
    fc = forecast.forecast(vals, alloc, rules)
    assert 0 <= fc["down"] <= fc["base"]
    for r in fc["rows"]:
        assert abs(r["stake_now"] - r["cheque"] / r["post_money"]) < 1e-9
