"""Research agent: checks each startup's claims and market against the open web (SearXNG) with an LLM.
Writes data/research/<Startup>.json. Every finding cites URLs that the search actually returned.
Usage: python -m dealroom.research [Startup ...]"""
import json, sys, datetime as dt
from pathlib import Path
import yaml
from dealroom.search import searxng_search
from dealroom.llm import chat_json as _chat, usage_mark, usage_summary
import re
from dealroom import registry


def ask_json(prompt: str) -> dict:
    """Call the model and parse its JSON, tolerating code fences or text around the object; one retry."""
    for _ in range(2):
        text = _chat([{"role": "user", "content": prompt + " Reply with the JSON object only."}], profile="reasoning")
        m = re.search(r"\{.*\}", text, re.S)
        try:
            return json.loads(m.group(0) if m else text)
        except ValueError:
            continue
    raise ValueError("model did not return JSON: " + text[:200])

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RES = DATA / "research"

PLAN_PROMPT = """You are a VC analyst doing due diligence on a pre-seed startup for a USD 1M fund in Egypt/MENA.
Startup: {name}. Sector: {sector}. Stage: {stage}. Ask: {ask}.
Founder claims (from their deck/video):
{claims}
Write 6 specific web search queries (English, include concrete company, report or regulator names; never just the startup's own name unless checking a named customer) that would let an investor independently check:
1) market size / growth for this sector in Egypt, MENA or globally,
2) the main competitors: name specific real companies you know in this space (global leaders and Egypt/MENA players) and search for their funding,
3) regulation or licensing that affects this business,
4-6) the most checkable founder claims (named customers, partners, data suppliers, market reports, regulations, competitor names).
Return JSON: {{"queries": [{{"topic": "market|competition|regulation|claim", "claim": "<claim being checked or empty>", "query": "<search query>"}}]}}"""

JUDGE_PROMPT = """You are a careful VC research analyst. Topic: {topic}. Startup: {name} ({sector}).
Founder claim being checked (may be empty): {claim}
Search results (only these may be cited):
{hits}
Write what these results say that matters to an investor. Do not invent numbers; use only what the snippets say.
verdict: "supported" (results confirm the claim), "contradicted" (results conflict with it), "context" (no claim, or results add market/competition/regulation facts), or "unverified" (results don't address it).
Return JSON: {{"verdict": "...", "finding": "<2-4 sentences with figures as stated in the snippets>", "sources": ["<urls from the results you relied on>"], "risk_flag": "<one short investor risk this suggests, or empty>"}}"""


TRUSTED_PROMPT = """You plan due-diligence searches restricted to trusted sources from our team's source registry.
Startup: {name}. Sector: {sector}. Stage: {stage}.
Registry of fact sources (domain [tier, coverage]: what it provides):
{catalogue}
Case-study sources (for analogies to similar businesses):
{cases}
Pick the 3 fact sources most useful for checking this startup's market size, regulation or customers in Egypt/MENA,
and 1 case-study source likely to hold a comparable business case. Write a short English query for each (no site: prefix).
Return JSON: {{"picks": [{{"domain": "<domain from the lists>", "topic": "market|regulation|competition|case_study", "query": "<query>"}}]}}"""


def trusted_queries(name: str, e: dict) -> list[dict]:
    """Up to 4 searches restricted (site:) to tier A/B registry sources picked for this startup."""
    try:
        plan = ask_json(TRUSTED_PROMPT.format(name=name, sector=e["sector"], stage=e["stage"],
                                              catalogue=registry.catalogue("fact"), cases=registry.catalogue("analogy", ("A", "B", "C"))))
    except Exception:
        return []
    known = {s["domain"] for s in registry.sources()}
    out = []
    for p in plan.get("picks", [])[:4]:
        d = str(p.get("domain", "")).lower().removeprefix("www.")
        if d in known and p.get("query"):
            out.append({"topic": p.get("topic", "market"), "claim": "", "site": d, "trusted": True,
                        "query": f"site:{d} {p['query']}"})
    return out


def research(name: str, e: dict, trusted_only: bool = False) -> dict:
    if trusted_only:
        queries = trusted_queries(name, e)
    else:
        claims = "\n".join(f"- [{c['source']}] {c['quote']}" for c in e.get("claims", []))
        plan = ask_json(PLAN_PROMPT.format(name=name, sector=e["sector"], stage=e["stage"], ask=e.get("ask_usd"), claims=claims))
        queries = plan.get("queries", [])[:6] + trusted_queries(name, e)
    findings = []
    for q in queries:
        hits = [h for h in searxng_search(q["query"], limit=6) if "://" in h.url and not h.url.startswith("http:///")]
        if q.get("site") and not hits:  # site: search found nothing; retry as a plain query naming the source
            hits = [h for h in searxng_search(q["query"].replace("site:" + q["site"], q["site"]), limit=6)
                    if "://" in h.url and not h.url.startswith("http:///")]
        if not hits:
            findings.append({**q, "verdict": "unverified", "finding": "No search results.", "sources": [], "risk_flag": ""})
            continue
        listing = "\n".join(f"[{i+1}] {h.url}\n{h.title}\n{h.snippet}" for i, h in enumerate(hits))
        j = ask_json(JUDGE_PROMPT.format(topic=q.get("topic"), name=name, sector=e["sector"], claim=q.get("claim") or "", hits=listing))
        allowed = {h.url for h in hits}
        j["sources"] = [u for u in j.get("sources", []) if u in allowed]  # drop any URL the model made up
        if not j["sources"] and j.get("verdict") in ("supported", "contradicted"):
            j["verdict"] = "unverified"
        j["source_tiers"] = {u: registry.tier_of(u) for u in j["sources"]}  # A/B/C from the team registry, None = not in it
        findings.append({**q, **j})
        print(f"  {name} | {q.get('topic')} | {j.get('verdict')} | tiers {list(j['source_tiers'].values())}")
    return {"startup": name, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "findings": findings}


def main():
    evidence = yaml.safe_load((DATA / "evidence.yaml").read_text(encoding="utf-8"))
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(evidence)
    RES.mkdir(parents=True, exist_ok=True)
    mark = usage_mark()
    for n in names:
        print("researching", n)
        trusted_only = "--trusted-only" in sys.argv
        try:
            out = research(n, evidence[n], trusted_only)
        except Exception as exc:  # keep going; one failure shouldn't lose the others
            print("  FAILED", n, exc); continue
        f = RES / f"{n}.json"
        if trusted_only:  # add the trusted-source findings that found something; keep all earlier findings
            if not f.exists():
                continue
            old = json.loads(f.read_text(encoding="utf-8"))
            new = [x for x in out["findings"] if x.get("sources")]
            old["findings"] = [x for x in old["findings"] if not (x.get("trusted") and not x.get("sources"))] + new
            f.write_text(json.dumps(old, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  added {len(new)} trusted-source findings for {n}")
            continue
        sourced = lambda d: sum(1 for x in d["findings"] if x.get("sources"))
        if f.exists() and "--force" not in sys.argv:
            old = json.loads(f.read_text(encoding="utf-8"))
            if sourced(out) < sourced(old):  # e.g. search engines blocked mid-run: keep the better earlier research
                print(f"  kept earlier research for {n} ({sourced(old)} sourced findings vs {sourced(out)} now)")
                continue
        f.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("usage:", usage_summary(mark))

if __name__ == "__main__":
    main()
