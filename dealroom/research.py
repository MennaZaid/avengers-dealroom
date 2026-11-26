"""Research agent: checks each startup's claims and market against the open web (SearXNG) with an LLM.
Writes data/research/<Startup>.json. Every finding cites URLs that the search actually returned.
Usage: python -m dealroom.research [Startup ...]"""
import json, sys, datetime as dt
from pathlib import Path
import yaml
from dealroom.search import searxng_search
from dealroom.llm import chat_json as _chat, usage_mark, usage_summary
import re


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


def research(name: str, e: dict) -> dict:
    claims = "\n".join(f"- [{c['source']}] {c['quote']}" for c in e.get("claims", []))
    plan = ask_json(PLAN_PROMPT.format(name=name, sector=e["sector"], stage=e["stage"], ask=e.get("ask_usd"), claims=claims))
    findings = []
    for q in plan.get("queries", [])[:6]:
        hits = [h for h in searxng_search(q["query"], limit=6) if "://" in h.url and not h.url.startswith("http:///")]
        if not hits:
            findings.append({**q, "verdict": "unverified", "finding": "No search results.", "sources": [], "risk_flag": ""})
            continue
        listing = "\n".join(f"[{i+1}] {h.url}\n{h.title}\n{h.snippet}" for i, h in enumerate(hits))
        j = ask_json(JUDGE_PROMPT.format(topic=q.get("topic"), name=name, sector=e["sector"], claim=q.get("claim") or "", hits=listing))
        allowed = {h.url for h in hits}
        j["sources"] = [u for u in j.get("sources", []) if u in allowed]  # drop any URL the model made up
        if not j["sources"] and j.get("verdict") in ("supported", "contradicted"):
            j["verdict"] = "unverified"
        findings.append({**q, **j})
        print(f"  {name} | {q.get('topic')} | {j.get('verdict')}")
    return {"startup": name, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "findings": findings}


def main():
    evidence = yaml.safe_load((DATA / "evidence.yaml").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(evidence)
    RES.mkdir(parents=True, exist_ok=True)
    mark = usage_mark()
    for n in names:
        print("researching", n)
        try:
            out = research(n, evidence[n])
        except Exception as exc:  # keep going; one failure shouldn't lose the others
            print("  FAILED", n, exc); continue
        (RES / f"{n}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("usage:", usage_summary(mark))

if __name__ == "__main__":
    main()
