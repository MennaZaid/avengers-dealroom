"""Builds the data room: one dossier per startup plus outputs/dealroom/data_room.md that holds everything.
Inputs: data/evidence.yaml, scores.yaml, rules.yaml, research/*.json, and the portfolio computed by dealroom.run."""
import json
from pathlib import Path
import yaml
from dealroom import run as pipeline

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs" / "dealroom"
CRITERIA = ["team", "market", "product", "competition", "sales", "funding_need", "other"]


def load():
    y = lambda f: yaml.safe_load((DATA / f).read_text(encoding="utf-8"))
    evidence, scores, rules = y("evidence.yaml"), y("scores.yaml"), y("rules.yaml")
    research = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (DATA / "research").glob("*.json")}
    vals = pipeline.value(scores, rules)
    alloc = pipeline.allocate(vals, evidence, rules)
    return evidence, scores, rules, research, vals, alloc


def money(x):
    return f"${x:,.0f}" if x else "not stated"


def dossier(name, e, s, v, a, research, ver):
    L = [f"## {name}", "",
         f"**Sector:** {e['sector']}  ", f"**Stage:** {e['stage']}  ",
         f"**Their ask:** {money(e.get('ask_usd'))} ({e['ask_note']})  ",
         f"**Our proposed ticket:** {money(a) if a else 'PASS'}" + (f" (~{a / (v['blended_premoney'] + max(e.get('ask_usd') or 0, a)):.1%} stake = cheque / post-money)" if a else ""), "",
         f"**Score:** {v['weighted']} / 5 - Scorecard pre-money {money(v['scorecard_premoney'])}, Berkus {money(v['berkus_premoney'])}, "
         f"blended {money(v['blended_premoney'])}", "",
         "| " + " | ".join(CRITERIA) + " |", "|" + "---|" * len(CRITERIA), "| " + " | ".join(str(s[c]) for c in CRITERIA) + " |", "",
         f"**Team's reasoning:** {s['why']}", "", "### Founder claims (verified against deck/video text)", ""]
    for r in ver.get(name, []):
        L.append(f"- [{r['source'].upper()}, {r['status']}] \"{r['quote']}\"")
    L += ["", "### Independent research (web, cited)", ""]
    fs = research.get(name, {}).get("findings", [])
    if not fs:
        L.append("_Not researched yet: run `python -m dealroom.research " + name + "`._")
    for f in fs:
        src = ", ".join(f.get("sources", [])) or "no source"
        L.append(f"- **{f.get('topic', '').upper()} - {f.get('verdict', '').upper()}** (query: _{f.get('query')}_): {f.get('finding', '')} Sources: {src}")
        if f.get("risk_flag"):
            L.append(f"  - Risk: {f['risk_flag']}")
    return "\n".join(L) + "\n"


def build():
    evidence, scores, rules, research, vals, alloc = load()
    ver = pipeline.verify(evidence)
    OUT.mkdir(parents=True, exist_ok=True)
    order = sorted(vals, key=lambda n: -vals[n]["weighted"])
    head = ["# DealRoom data room", "",
            f"Fund {money(rules['fund_usd'])}, reserve {money(rules['reserve_usd'])}, max ticket {money(rules['max_ticket_usd'])}, "
            f"investment bar: weighted score >= {rules['min_weighted_score']}. Proposed deployment {money(sum(alloc.values()))}.",
            "Labels: DECK/VIDEO = founder claim; web findings cite URLs; base pre-money in rules.yaml is an ASSUMPTION.", "",
            "| Startup | Score | Blended pre-money | Ask | Ticket |", "|---|---|---|---|---|"]
    for n in order:
        head.append(f"| {n} | {vals[n]['weighted']} | {money(vals[n]['blended_premoney'])} | {money(evidence[n].get('ask_usd'))} | {money(alloc.get(n)) if alloc.get(n) else 'PASS'} |")
    parts = []
    for n in order:
        d = dossier(n, evidence[n], scores[n], vals[n], alloc.get(n, 0), research, ver)
        (OUT / f"dossier_{n}.md").write_text(d, encoding="utf-8")
        parts.append(d)
    from dealroom import forecast
    fc_md = forecast.markdown(forecast.forecast(vals, alloc, rules))
    text = "\n".join(head) + "\n\n" + fc_md + "\n" + "\n".join(parts)
    (OUT / "data_room.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(build()[:1500])
