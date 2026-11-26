"""Three lenses on every startup: HUMAN judgment (team meeting), DATA analysis (models, scorecard, valuation,
forecast) and AGENT research (verified quotes, cited web findings). The final decision is the team's; the tool
only shows where the lenses agree and where they disagree, so every override has a stated reason."""
from pathlib import Path
import yaml
from dealroom import dossier, run, forecast as fc_mod

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEAM = DATA / "team_view.yaml"


def load_team() -> dict:
    return yaml.safe_load(TEAM.read_text(encoding="utf-8")) if TEAM.exists() else {}


def save_team(team: dict) -> None:
    head = [l for l in TEAM.read_text(encoding="utf-8").splitlines() if l.startswith("#")] if TEAM.exists() else []
    TEAM.write_text("\n".join(head) + "\n" + yaml.safe_dump(team, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")


def build() -> dict:
    evidence, scores, rules, research, vals, alloc = dossier.load()
    team = load_team()
    fyaml = fc_mod.load()
    ver = run.verify(evidence)
    out = {}
    for n in sorted(vals, key=lambda n: -vals[n]["weighted"]):
        v, e, t, f = vals[n], evidence[n], team.get(n) or {}, fyaml.get(n) or {}
        votes = {k: x for k, x in (t.get("conviction") or {}).items() if isinstance(x, (int, float))}
        avg = round(sum(votes.values()) / len(votes), 2) if votes else None
        fs = research.get(n, {}).get("findings", [])
        verdicts = {k: sum(1 for x in fs if x.get("verdict") == k) for k in ("supported", "contradicted", "context", "unverified")}
        tiers = [tr for x in fs for tr in (x.get("source_tiers") or {}).values() if tr]
        tool_call = "invest" if n in alloc else "pass"
        human_call = t.get("decision") or "undecided"
        flags = []
        if human_call in ("invest", "pass") and human_call != tool_call:
            flags.append(f"Team says {human_call.upper()}, tool says {tool_call.upper()}")
        if avg is not None and abs(avg - v["weighted"]) >= 1:
            flags.append(f"Team conviction {avg} vs data score {v['weighted']}")
        if verdicts["contradicted"]:
            flags.append(f"Agents found {verdicts['contradicted']} contradicted claim(s)")
        out[n] = {
            "human": {"votes": votes, "avg": avg, "decision": human_call, "open_day": t.get("open_day", ""),
                      "gut": t.get("gut_feeling", ""), "concerns": t.get("concerns", ""),
                      "final_cheque": t.get("final_cheque_usd"), "override_reason": t.get("override_reason", "")},
            "data": {"score": v["weighted"], "premoney_ours": v["blended_premoney"], "price_stated": f.get("premoney_override"),
                     "ask": e.get("ask_usd"), "tool_cheque": alloc.get(n, 0), "runway_m": (f["round_usd"] / f["monthly_burn_usd"]) if f else None,
                     "y5_base": f.get("y5_base"), "y5_down": f.get("y5_downside"), "milestone": f.get("milestone", ""), "why": v["why"]},
            "agents": {"quotes": len(ver.get(n, [])), "quotes_ok": sum(r["status"] != "NOT FOUND" for r in ver.get(n, [])),
                       "verdicts": verdicts, "trusted_sources": sum(1 for x in tiers if x in ("A", "B")),
                       "risks": [x["risk_flag"] for x in fs if x.get("risk_flag")][:3]},
            "tool_call": tool_call, "flags": flags,
            "agree": not flags and human_call in ("invest", "pass"),
        }
    return out


def final_portfolio(lenses: dict) -> dict:
    """The team's cheques where set; the tool's proposal elsewhere (marked)."""
    res = {}
    for n, L in lenses.items():
        h = L["human"]
        if h["final_cheque"] is not None:
            res[n] = (int(h["final_cheque"]), "team")
        elif h["decision"] == "pass":
            res[n] = (0, "team")
        elif L["data"]["tool_cheque"]:
            res[n] = (L["data"]["tool_cheque"], "tool proposal")
    return {n: x for n, x in res.items() if x[0] > 0}


def worksheet() -> str:
    """Printable sheet for the team meeting: the data and agent lenses filled in, the human lens left blank."""
    L = build()
    team = load_team()
    members = team.get("members") or ["Member 1", "Member 2", "Member 3"]
    m = lambda x: f"${x:,.0f}" if x else "-"
    out = ["# Team meeting worksheet: three lenses", "",
           "For each startup: read the DATA and AGENT lenses, then fill in the HUMAN lens together.",
           "Where the team disagrees with the tool, write **why**. That reason becomes a pitch line.", ""]
    for n, x in L.items():
        d, a = x["data"], x["agents"]
        out += [f"## {n}  (tool proposes: {x['tool_call'].upper()} {m(d['tool_cheque'])})", "",
                f"**DATA:** score {d['score']}/5 · our pre-money {m(d['premoney_ours'])}"
                + (f" · their price {m(d['price_stated'])}" if d['price_stated'] else "")
                + f" · ask {m(d['ask'])} · runway {d['runway_m']:.0f} months" if d['runway_m'] else "",
                f"Y5 company value: base {m(d['y5_base'])}, downside {m(d['y5_down'])}. Milestone: {d['milestone']}", "",
                f"**AGENTS:** {a['quotes_ok']}/{a['quotes']} founder quotes verified · web findings: "
                + ", ".join(f"{k} {v}" for k, v in a["verdicts"].items() if v)
                + (f" · top risks: {'; '.join(a['risks'])}" if a["risks"] else ""), "",
                "**HUMAN:**", "",
                "| " + " | ".join(members) + " | Average |", "|" + "---|" * (len(members) + 1),
                "| " + " | ".join("  /5" for _ in members) + " |  |", "",
                "- What we saw at the Open Day: ______________________________________________",
                "- Gut feeling about the founder(s): __________________________________________",
                "- Biggest concern: ___________________________________________________________",
                "- Decision:  INVEST  /  PASS  /  WATCH        Our cheque: $__________",
                "- If we disagree with the tool, why: _________________________________________", ""]
    return "\n".join(out)
