"""Year-5 forecast and runway for the proposed portfolio (base case and downside).
Equity % = cheque / post-money; post-money = pre-money + the whole round."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load():
    return yaml.safe_load((DATA / "forecast.yaml").read_text(encoding="utf-8"))


def forecast(vals: dict, alloc: dict, rules: dict) -> dict:
    f = load()
    keep_b, keep_d = f["dilution"]["base_keep"], f["dilution"]["downside_keep"]
    rows = []
    for n, cheque in alloc.items():
        p = f.get(n)
        if not p:
            continue
        pre = p.get("premoney_override") or vals[n]["blended_premoney"]  # the price on the table, if the startup states one
        rnd = max(p["round_usd"], cheque)
        post = pre + rnd
        stake = cheque / post
        rows.append({
            "startup": n, "cheque": cheque, "pre_money": pre, "round": rnd, "post_money": post, "stake_now": stake,
            "runway_months": rnd / p["monthly_burn_usd"], "our_cheque_months": cheque / p["monthly_burn_usd"],
            "milestone": p["milestone"],
            "stake_y5_base": stake * keep_b, "value_y5_base": stake * keep_b * p["y5_base"],
            "value_y5_down": stake * keep_d * p["y5_downside"],
            "y5_base_company": p["y5_base"], "y5_down_company": p["y5_downside"]})
    reserve = rules["fund_usd"] - sum(alloc.values())
    base = sum(r["value_y5_base"] for r in rows) + reserve   # reserve kept as cash (ASSUMPTION: no return)
    down = sum(r["value_y5_down"] for r in rows) + reserve
    fund = rules["fund_usd"]
    best = max(rows, key=lambda r: r["value_y5_base"]) if rows else None
    return {"rows": rows, "reserve": reserve, "base": base, "down": down,
            "moic_base": base / fund, "moic_down": down / fund,
            "best": best and best["startup"], "best_returns_fund": bool(best and best["value_y5_base"] >= fund),
            "keep_base": keep_b, "keep_down": keep_d}


def markdown(fc: dict) -> str:
    m = lambda x: f"${x:,.0f}"
    L = ["## Year-5 forecast (base case and downside)", "",
         f"Dilution ASSUMPTION: we keep {fc['keep_base']:.0%} of our stake in the base case, {fc['keep_down']:.0%} in the downside. "
         "Company values at year 5 are ASSUMPTIONS in data/forecast.yaml.", "",
         "| Startup | Cheque | Post-money | Stake now | Runway (whole round) | Milestone it funds | Y5 value base | Y5 value downside |",
         "|---|---|---|---|---|---|---|---|"]
    for r in fc["rows"]:
        L.append(f"| {r['startup']} | {m(r['cheque'])} | {m(r['post_money'])} | {r['stake_now']:.1%} | "
                 f"{r['runway_months']:.0f} months | {r['milestone']} | {m(r['value_y5_base'])} | {m(r['value_y5_down'])} |")
    L += ["", f"Reserve (cash): {m(fc['reserve'])}.",
          f"**Fund at year 5: base {m(fc['base'])} ({fc['moic_base']:.1f}x), downside {m(fc['down'])} ({fc['moic_down']:.2f}x).**",
          f"Best pick in base case: {fc['best']} - " + ("returns the whole fund on its own." if fc["best_returns_fund"] else "does not return the whole fund on its own.")]
    return "\n".join(L) + "\n"
