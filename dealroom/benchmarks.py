"""Benchmark agent: finds cited numbers for the forecast (dilution per round, revenue multiples, MENA valuations).
Writes data/benchmarks.json. Every number must come from a search result snippet; URLs are checked against the results.
Usage: python -m dealroom.benchmarks"""
import json, datetime as dt
from pathlib import Path
from venture_os.tools.search import searxng_search
from dealroom.research import ask_json

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "benchmarks.json"

QUESTIONS = [
    ("dilution", "Median founder dilution in a seed round", "Carta median dilution seed round 2026"),
    ("dilution", "Median dilution in a Series A round", "Carta median dilution Series A 2026"),
    ("dilution", "Typical dilution per funding round (rule of thumb)", "typical startup dilution per funding round seed series A percent"),
    ("valuation", "Median pre-seed / seed valuation in MENA or Egypt", "MAGNiTT median seed valuation MENA Egypt startups 2026"),
    ("valuation", "Egypt startup funding 2026 totals and typical round sizes", "Egypt startup funding 2026 report pre-seed seed round size"),
    ("multiple", "Revenue multiples by industry (Damodaran)", "Damodaran EV/Sales by industry emerging markets 2026"),
    ("multiple", "Private SaaS / vertical SaaS revenue multiples", "private SaaS company valuation revenue multiple 2026"),
    ("multiple", "Fintech revenue multiples", "fintech startup valuation revenue multiple 2026"),
    ("multiple", "Proptech / real-estate platform revenue multiples", "proptech valuation revenue multiple 2026"),
    ("multiple", "Sports tech valuation multiples", "sports technology company valuation revenue multiple"),
    ("comparable", "Fawry valuation and revenue (EGX-listed fintech)", "Fawry market capitalization revenue 2026"),
    ("comparable", "Nawy Series A (Egypt proptech)", "Nawy Series A 75 million valuation"),
    ("comparable", "Foodics funding (MENA restaurant POS)", "Foodics Series C funding valuation"),
    ("outcomes", "Share of seed startups that fail or return nothing", "percentage of seed stage startups fail return zero venture capital power law"),
]

PROMPT = """You extract benchmark numbers for a VC team's 5-year forecast.
Question: {q}
Search results (only these may be cited):
{hits}
Report only numbers that appear in the snippets. If none answer the question, say so.
Return JSON: {{"answer": "<1-3 sentences with the numbers exactly as stated, incl. year/region>", "value": "<the key figure, e.g. '20%' or '6.5x', or empty>", "sources": ["<urls you used>"], "confidence": "high|medium|low"}}"""


def main():
    rows = []
    for kind, q, query in QUESTIONS:
        hits = [h for h in searxng_search(query, limit=6) if not h.url.startswith("http:///")]
        if not hits:
            rows.append({"kind": kind, "question": q, "query": query, "answer": "No search results.", "value": "", "sources": [], "confidence": "low"})
            continue
        listing = "\n".join(f"[{i+1}] {h.url}\n{h.title}\n{h.snippet}" for i, h in enumerate(hits))
        try:
            j = ask_json(PROMPT.format(q=q, hits=listing))
        except Exception as exc:
            j = {"answer": f"Model error: {exc}", "value": "", "sources": [], "confidence": "low"}
        allowed = {h.url for h in hits}
        j["sources"] = [u for u in j.get("sources", []) if u in allowed]
        if not j["sources"]:
            j["confidence"] = "low"
        rows.append({"kind": kind, "question": q, "query": query, **j})
        print(f"{kind} | {q} | {j.get('value')} | {j.get('confidence')}", flush=True)
    OUT.write_text(json.dumps({"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "rows": rows},
                              indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
