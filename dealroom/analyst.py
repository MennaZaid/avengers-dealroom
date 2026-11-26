"""Analyst chatbot: answers questions using only the data room (scores, valuations, claims, web research)
plus the full deck/transcript text of any startup named in the question."""
from pathlib import Path
from dealroom.research import ask_json

ROOT = Path(__file__).resolve().parent.parent
STARTUPS = ROOT / "data" / "startups"
ROOM = ROOT / "outputs" / "dealroom" / "data_room.md"

SYSTEM = """You are the investment analyst of a student VC team in The DealRoom competition (simulated USD 1,000,000 fund, Egypt/MENA pre-seed).
Answer using ONLY the data room and source excerpts below. Cite where each fact comes from (DECK, VIDEO, or the URL).
Say clearly when the data room doesn't contain the answer. Separate founder claims from independent evidence.
Give a direct recommendation when asked, with the main risk. Be concise. English only.

DATA ROOM:
{room}

SOURCE EXCERPTS:
{sources}"""


def compact_room(focus: str = "") -> str:
    """Short version of the data room that fits free-tier model limits (~5k tokens)."""
    from dealroom import dossier
    evidence, scores, rules, research, vals, alloc = dossier.load()
    L = [f"Fund ${rules['fund_usd']:,}; reserve ${rules['reserve_usd']:,}; bar {rules['min_weighted_score']}; "
         "base pre-money is an ASSUMPTION."]
    for n in sorted(vals, key=lambda n: -vals[n]["weighted"]):
        e, v, a = evidence[n], vals[n], alloc.get(n, 0)
        L.append(f"## {n} | {e['sector']} | {e['stage']} | ask {e.get('ask_usd')} ({e['ask_note']}) | "
                 f"score {v['weighted']} | blended pre-money ${v['blended_premoney']:,.0f} | our ticket {a or 'PASS'}")
        L.append("Team view: " + scores[n]["why"])
        named = [m for m in vals if m.lower() in focus.lower()]
        if named and n not in named:
            continue  # other startups: headline line only, keeps the prompt inside free-tier limits
        L.append("Claims: " + " / ".join(f"[{c['source']}] {c['quote']}" for c in e["claims"]))
        for f in research.get(n, {}).get("findings", []):
            L.append(f"- WEB {f.get('topic')} {str(f.get('verdict')).upper()}: {str(f.get('finding'))[:220]} "
                     f"({(f.get('sources') or ['no source'])[0]})")
    from dealroom import forecast
    L.append(forecast.markdown(forecast.forecast(vals, alloc, rules)))
    return chr(10).join(L)


def sources_for(question: str, limit: int = 2500) -> str:
    out = []
    for d in STARTUPS.iterdir():
        if d.is_dir() and d.name.lower() in question.lower():
            for f in ("deck.txt", "video_transcript.txt"):
                p = d / f
                if p.exists():
                    out.append(f"--- {d.name} {f} ---\n" + p.read_text(encoding="utf-8")[:limit])
    return "\n".join(out) or "(none: name a startup in the question to load its deck and transcript)"


def answer(question: str, history: list[dict] | None = None) -> str:
    convo = "".join(f"\n{m['role'].upper()}: {m['content']}" for m in (history or [])[-6:])
    room = compact_room(question + convo)
    prompt = SYSTEM.format(room=room, sources=sources_for(question + convo)) + \
        f"\n\nCONVERSATION SO FAR:{convo}\n\nQUESTION: {question}\n" + 'Return JSON: {"answer": "<markdown answer>"}'
    return ask_json(prompt).get("answer", "")


if __name__ == "__main__":
    import sys
    print(answer(" ".join(sys.argv[1:]) or "Which startup should get our biggest ticket and why?"))
