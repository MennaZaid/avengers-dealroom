"""DealRoom pipeline: verify quotes -> score + value -> allocate $1M -> human approval.
Usage: python -m dealroom.run [--approve]"""
import json, re, sys, datetime as dt
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs" / "dealroom"
LOG = OUT / "decision_log.json"
log = []

def note(agent, action, **kw):
    log.append({"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "agent": agent, "action": action, "sources": kw.pop("sources", []),
                "model": None, "cost": 0, "approved_by": kw.pop("approved_by", None), **kw})

def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()

def verify(evidence):
    res = {}
    for name, e in evidence.items():
        rows = []
        for c in e.get("claims", []):
            src = c["source"]
            if src in ("deck", "video"):
                f = DATA / "startups" / name / ("deck.txt" if src == "deck" else "video_transcript.txt")
                ok = f.exists() and norm(c["quote"]) in norm(f.read_text(encoding="utf-8"))
                status = "VERIFIED" if ok else "NOT FOUND"
            else:
                status = "MANUAL (image/URL)"
            rows.append({**c, "status": status})
        res[name] = rows
        note("verifier", "verify_quotes", startup=name,
             verified=sum(r["status"] == "VERIFIED" for r in rows),
             failed=sum(r["status"] == "NOT FOUND" for r in rows))
    return res

def value(scores, rules):
    w, out = rules["weights"], {}
    for name, s in scores.items():
        ws = sum(w[k] * s[k] for k in w)
        scorecard = rules["base_premoney_usd"] * ws / 3          # 3 = typical startup -> base
        berkus = sum(s[k] / 5 * 500000 for k in ("market", "product", "team", "other", "sales"))
        out[name] = {"weighted": round(ws, 2), "scorecard_premoney": round(scorecard, -4),
                     "berkus_premoney": round(berkus, -4),
                     "blended_premoney": round((scorecard + berkus) / 2, -4), "why": s["why"]}
        note("validator", "score_and_value", startup=name, **{k: out[name][k] for k in ("weighted", "blended_premoney")})
    return out

def allocate(vals, evidence, rules):
    budget = rules["fund_usd"] - rules["reserve_usd"]
    elig = {n: v for n, v in vals.items() if v["weighted"] >= rules["min_weighted_score"]}
    for n, v in vals.items():
        if n not in elig:
            note("gate", "investment_gate", startup=n, outcome="stop",
                 reason=f"weighted score {v['weighted']} < {rules['min_weighted_score']}")
    # weight by score above the bar; cap by max ticket and by what the round still needs
    cap = lambda n: min(rules["max_ticket_usd"], evidence[n].get("ask_usd") or rules["max_ticket_usd"])
    alloc, remaining, pool = {}, budget, dict(elig)
    while pool and remaining > 0:
        tot = sum(v["weighted"] - rules["min_weighted_score"] + 0.1 for v in pool.values())
        nxt = {}
        for n, v in pool.items():
            share = remaining * (v["weighted"] - rules["min_weighted_score"] + 0.1) / tot
            alloc[n] = alloc.get(n, 0) + share
        remaining = 0
        for n in list(pool):
            if alloc[n] > cap(n):
                remaining += alloc[n] - cap(n); alloc[n] = cap(n)
            else:
                nxt[n] = pool[n]
        pool = nxt if remaining > 0 else {}
    r = rules["round_to_usd"]
    alloc = {n: int(a // r * r) for n, a in alloc.items() if a >= rules["min_ticket_usd"]}
    return alloc

def approve(alloc, vals, interactive):
    final = {}
    for n, a in alloc.items():
        own = a / (vals[n]["blended_premoney"] + a)
        if interactive:
            ans = input(f"{n}: ${a:,} (~{own:.1%} post-money). [a]pprove / [r]eject / number to override: ").strip()
            if ans.lower().startswith("r"):
                note("portfolio", "allocate", startup=n, amount=0, approved_by="founder", outcome="rejected"); continue
            if ans.replace(",", "").isdigit():
                a = int(ans.replace(",", ""))
            note("portfolio", "allocate", startup=n, amount=a, approved_by="founder", outcome="approved")
            final[n] = a
        else:
            final[n] = a
            note("portfolio", "propose_allocation", startup=n, amount=a, outcome="pending_approval")
    return final

def report(ver, vals, alloc, evidence, rules, approved):
    L = ["# DealRoom portfolio proposal", "",
         f"Fund ${rules['fund_usd']:,}; reserve ${rules['reserve_usd']:,}; max ticket ${rules['max_ticket_usd']:,}; "
         f"invest only if weighted score >= {rules['min_weighted_score']}.",
         "Status: " + ("**approved by the team**" if approved else "**PROPOSAL - not yet approved** (run with `--approve`)"), "",
         "## Allocation", "", "| Startup | Score | Blended pre-money | Their ask | Ticket | ~Stake |", "|---|---|---|---|---|---|"]
    for n, v in sorted(vals.items(), key=lambda x: -x[1]["weighted"]):
        a = alloc.get(n, 0); ask = evidence[n].get("ask_usd")
        stake = f"{a / (v['blended_premoney'] + a):.1%}" if a else "-"
        L.append(f"| {n} | {v['weighted']} | ${v['blended_premoney']:,.0f} | {'$%s' % format(ask, ',') if ask else 'not stated'} | "
                 f"{'$%s' % format(a, ',') if a else 'STOP / pass'} | {stake} |")
    L += ["", f"Deployed ${sum(alloc.values()):,} of ${rules['fund_usd']:,}.", "",
          "Valuation: Scorecard method (base pre-money is an ASSUMPTION in data/rules.yaml) averaged with Berkus. "
          "Founders' own valuation, where stated, is in the evidence notes.", "", "## Why", ""]
    for n, v in sorted(vals.items(), key=lambda x: -x[1]["weighted"]):
        L.append(f"- **{n}** ({evidence[n]['stage']}): {v['why']}. _Ask note: {evidence[n]['ask_note']}_")
    L += ["", "## Evidence check", "", "| Startup | Source | Quote | Status |", "|---|---|---|---|"]
    for n, rows in ver.items():
        for r in rows:
            L.append(f"| {n} | {r['source'].upper()} | {r['quote'].replace('|', '/')} | {r['status']} |")
    return "\n".join(L) + "\n"

def main():
    interactive = "--approve" in sys.argv
    load = lambda f: yaml.safe_load((DATA / f).read_text(encoding="utf-8"))
    evidence, scores, rules = load("evidence.yaml"), load("scores.yaml"), load("rules.yaml")
    ver = verify(evidence)
    vals = value(scores, rules)
    alloc = approve(allocate(vals, evidence, rules), vals, interactive)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "portfolio.md").write_text(report(ver, vals, alloc, evidence, rules, interactive), encoding="utf-8")
    LOG.write_text("[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in log) + "\n]\n", encoding="utf-8")
    bad = [(n, r["quote"]) for n, rows in ver.items() for r in rows if r["status"] == "NOT FOUND"]
    print(f"wrote {OUT / 'portfolio.md'}; quotes not found: {len(bad)}")
    for b in bad: print("  NOT FOUND:", *b)

if __name__ == "__main__":
    main()
