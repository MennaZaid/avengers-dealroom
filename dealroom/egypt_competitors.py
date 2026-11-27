"""Egypt-first competitor check: searches Egyptian/MENA competitors for each startup and appends cited findings
to data/research/<Startup>.json (topic "competition_egypt"). Usage: python -m dealroom.egypt_competitors [Startup ...]"""
import json, sys
import yaml
from dealroom.research import ask_json, JUDGE_PROMPT, RES, DATA
from dealroom.search import searxng_search
from dealroom import registry

PROMPT = """You are a VC analyst. Startup: {name}. Sector: {sector}. It operates in Egypt.
Write 3 English web search queries to find its direct COMPETITORS IN EGYPT (and, if few, in the MENA region):
name real Egyptian or MENA companies you know in this space, and search for them and their funding.
Return JSON: {{"queries": ["...", "...", "..."]}}"""


def main():
    ev = yaml.safe_load((DATA / "evidence.yaml").read_text(encoding="utf-8"))
    for n in sys.argv[1:] or ["Modeeri", "IGNOT", "Finalyze", "REE", "Blaze", "Matbakh", "Motion+", "Hylix"]:
        e = ev[n]
        try:
            qs = ask_json(PROMPT.format(name=n, sector=e["sector"])).get("queries", [])[:3]
        except Exception as x:
            print("FAILED plan", n, x); continue
        new = []
        for q in qs:
            hits = [h for h in searxng_search(q, limit=6) if "://" in h.url]
            if not hits:
                continue
            listing = "\n".join(f"[{i+1}] {h.url}\n{h.title}\n{h.snippet}" for i, h in enumerate(hits))
            try:
                j = ask_json(JUDGE_PROMPT.format(topic="competitors in Egypt/MENA (name them)", name=n, sector=e["sector"], claim="", hits=listing))
            except Exception:
                continue
            allowed = {h.url for h in hits}
            j["sources"] = [u for u in j.get("sources", []) if u in allowed]
            if not j["sources"]:
                continue
            j["source_tiers"] = {u: registry.tier_of(u) for u in j["sources"]}
            new.append({"topic": "competition_egypt", "claim": "", "query": q, **j})
            print(f"{n} | {q} | {j.get('finding','')[:160]}")
        f = RES / f"{n}.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["findings"] = [x for x in d["findings"] if x.get("topic") != "competition_egypt"] + new
        f.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {n}: {len(new)} Egypt competitor findings saved")


if __name__ == "__main__":
    main()
