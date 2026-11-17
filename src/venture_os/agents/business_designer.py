"""Phase 2 Validate, core step "Design the business": a Lean Canvas where every entry says where it comes from.

    from venture_os.agents import business_designer
    canvas = business_designer.run(brief_id)        # -> outputs/phase2_step1_lean_canvas.md + one log entry

Basis of every entry:
- FOUNDER: the founder's own words, quoted from a confirmed brief field (brief.known(...)).
- EVIDENCED: a Phase 1 evidence item with a source URL and a date (cited by its id).
- ASSUMPTION: anything else, including everything the model suggests without a real evidence id.
- UNKNOWN: the brief field is unknown; it stays "unknown" and is never filled in.

Rules first (works with no model). The model, when on, may only add short entries; a cited evidence id that
does not exist (or has no URL and date) is relabelled ASSUMPTION; text that fails guardrails.check_output() or
states expected income is dropped. Bad JSON -> one retry -> rules only, and the output says so.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from venture_os.decision_log import log_action
from venture_os.guardrails import check_output
from venture_os.outputs import write_output
from venture_os.prompts import load_prompt

Basis = Literal["FOUNDER", "EVIDENCED", "ASSUMPTION", "UNKNOWN"]
Chat = Callable[[list[dict]], str]

BOXES: dict[str, str] = {
    "problem": "Problem",
    "customer_segments": "Customer segments",
    "unique_value_proposition": "Unique value proposition",
    "solution": "Solution",
    "channels": "Channels",
    "revenue_streams": "Revenue streams",
    "cost_structure": "Cost structure",
    "key_metrics": "Key metrics",
    "unfair_advantage": "Unfair advantage",
}

# Which brief fields fill which box (quoted as FOUNDER). A required box with no known field shows UNKNOWN.
FOUNDER_FIELDS: dict[str, list[tuple[str, str]]] = {
    "problem": [("problem", ""), ("known_competitors", "Existing alternatives: ")],
    "customer_segments": [("target_customer", ""), ("city", "Where: "), ("country", "Country: ")],
    "unique_value_proposition": [],
    "solution": [("idea", ""), ("technical_preferences", "Form: ")],
    "channels": [],
    "revenue_streams": [("business_model", "")],
    "cost_structure": [("budget", "Budget as stated: "), ("time_available", "Founder time: ")],
    "key_metrics": [],
    "unfair_advantage": [("founder_skills", "Founder skills: "), ("values", "Values: ")],
}
# Boxes that must show "unknown" when nothing fills them (others get an ASSUMPTION from the rules).
UNKNOWN_IF_EMPTY = {"problem", "customer_segments", "solution", "revenue_streams", "cost_structure"}

# Evidence item kind -> box (Phase 1 writes kinds such as pain, competitor, price, customer, channel).
KIND_TO_BOX = {
    "pain": "problem", "problem": "problem", "competitor": "problem", "alternative": "problem",
    "customer": "customer_segments", "segment": "customer_segments", "audience": "customer_segments",
    "market_size": "customer_segments", "price": "revenue_streams", "competitor_price": "revenue_streams",
    "channel": "channels", "market": "customer_segments", "supply": "customer_segments",
    "revenue": "revenue_streams", "demand": "key_metrics",
}

# Expected income is never stated (revenue streams describe how money would come in, not how much).
INCOME_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    (r"\b(expected|projected|estimated|potential|guaranteed)\s+(monthly\s+|annual\s+|yearly\s+)?"
     r"(income|revenue|profit|earnings|sales)\b"),
    r"\b(earn|make|generate|bring in)\s+(up to\s+|over\s+|around\s+)?[$€£]?\s?\d",
    (r"\d[\d,.]*\s*(k|m|usd|egp|kes|\$|dollars|pounds)?\s*(per|a|/)\s*(month|year|week)\s+(in\s+)?"
     r"(income|revenue|profit|earnings)"),
    r"(دخل|أرباح|ربح|إيرادات)\s+(متوقع|متوقعة|شهري|شهرية|سنوي|سنوية)",
)]
MAX_TEXT = 200


class Entry(BaseModel):
    text: str
    basis: Basis
    field: str | None = None  # FOUNDER: the brief field quoted
    evidence_id: str | None = None  # EVIDENCED: the evidence item cited
    url: str | None = None
    date: str | None = None
    note: str = ""  # e.g. "model cited unknown evidence id E9"
    by: str = "rules"  # rules | model id


class LeanCanvas(BaseModel):
    brief_id: str
    brief_version: int | None = None
    boxes: dict[str, list[Entry]]
    riskiest_assumption: str
    riskiest_by: str = "rules"
    built_by: str  # "rules" or "rules + <model>"
    model: str | None = None
    notes: list[str] = []
    dropped: list[str] = []  # model text removed by guardrails (rule names only, never the text)


def run(brief_id: str, *, brief: Any = None, evidence_items: list | None = None,
        chat: Chat | None | Literal["auto"] = "auto") -> LeanCanvas:
    """Build the Lean Canvas for a confirmed brief, write it to outputs/ and log the action."""
    notes: list[str] = []
    if brief is None:
        from venture_os.onboarding.briefs import load_brief
        brief = load_brief(brief_id)
    if evidence_items is None:
        evidence_items, note = _load_evidence(brief_id)
        if note:
            notes.append(note)
    evidence = _index_evidence(evidence_items)
    if not evidence:
        notes.append("No Phase 1 evidence items: no entry is EVIDENCED; market statements are ASSUMPTION.")

    boxes = _rule_boxes(brief, evidence)
    riskiest, riskiest_by = _rule_riskiest(brief, boxes), "rules"

    model_name, cost, dropped = None, 0.0, []
    if chat == "auto":
        chat, model_name = _default_chat()
    if chat is None:
        notes.append("Built by rules only: no model is configured (LLM_MODE=replay or no endpoint).")
    else:
        from venture_os.llm.client import usage_mark, usage_summary
        mark = usage_mark()
        raw = _ask_model(chat, brief, evidence)
        cost = usage_summary(since=mark)["cost_usd"]
        if raw is None:
            notes.append("The model returned no valid JSON after one retry: built by rules only.")
            model_name = None
        else:
            model_name = model_name or "model"
            added, dropped, model_riskiest = _merge_model(raw, boxes, evidence, model_name)
            if model_riskiest:
                riskiest, riskiest_by = model_riskiest, model_name
            notes.append(f"The model ({model_name}) added {added} entries; every one is ASSUMPTION unless it "
                         "cites a real evidence id.")

    canvas = LeanCanvas(brief_id=str(brief_id), brief_version=getattr(brief, "version", None), boxes=boxes,
                        riskiest_assumption=riskiest, riskiest_by=riskiest_by, model=model_name,
                        built_by=f"rules + {model_name}" if model_name else "rules", notes=notes, dropped=dropped)
    md = to_markdown(canvas)
    if check_output(md):  # last line of defence: never write text that breaks a must-never rule
        raise RuntimeError(f"lean canvas failed the output guardrail: {check_output(md)}")
    write_output(2, 1, "lean_canvas", md)
    sources = sorted({e.url for es in boxes.values() for e in es if e.basis == "EVIDENCED" and e.url})
    log_action("business_designer", "design_lean_canvas", sources=sources, model=model_name, cost=cost,
               approved_by=None, brief_id=str(brief_id), brief_version=canvas.brief_version,
               built_by=canvas.built_by, riskiest_assumption=riskiest,
               counts={b: sum(1 for es in boxes.values() for e in es if e.basis == b)
                       for b in ("FOUNDER", "EVIDENCED", "ASSUMPTION", "UNKNOWN")})
    return canvas


# ---------- evidence ----------

def _load_evidence(brief_id: str) -> tuple[list, str | None]:
    try:
        from venture_os import evidence  # Menna's module (evidence.add / evidence.load)
    except ImportError:
        return [], "Evidence store (venture_os.evidence) is not available yet: Phase 1 evidence was not read."
    if not hasattr(evidence, "load"):
        return [], "venture_os.evidence has no load(): Phase 1 evidence was not read."
    try:
        return list(evidence.load(brief_id) or []), None
    except Exception as e:  # noqa: BLE001 - the canvas still works; the gap is reported, not hidden
        return [], f"Phase 1 evidence could not be read ({type(e).__name__})."


def _get(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def _index_evidence(items: list) -> dict[str, dict]:
    """id -> {text, kind, label, url, date, quote}. Items without an id get E1, E2... in load order."""
    out: dict[str, dict] = {}
    for i, it in enumerate(items or [], start=1):
        sources = _get(it, "sources") or []
        url = next((u for u in sources if isinstance(u, str) and u.startswith(("http://", "https://"))), None)
        eid = str(_get(it, "id") or f"E{i}")
        out[eid] = {"text": str(_get(it, "text") or "").strip(), "kind": str(_get(it, "kind") or ""),
                    "label": str(_get(it, "label") or ""), "url": url, "date": _get(it, "date"),
                    "quote": _get(it, "quote")}
    return out


def _is_evidenced(ev: dict) -> bool:
    return ev["label"] == "evidenced" and bool(ev["url"]) and bool(ev["date"])


# ---------- rules ----------

def _rule_boxes(brief: Any, evidence: dict[str, dict]) -> dict[str, list[Entry]]:
    boxes: dict[str, list[Entry]] = {k: [] for k in BOXES}
    for box, fields in FOUNDER_FIELDS.items():
        for i, (field, prefix) in enumerate(fields):
            value = brief.known(field)
            if value:
                boxes[box].append(Entry(text=f"{prefix}{value}"[:MAX_TEXT * 2], basis="FOUNDER", field=field))
            elif i == 0:  # the box's main brief field is unknown: say so, never fill it in
                boxes[box].append(Entry(text="unknown", basis="UNKNOWN", field=field,
                                        note=f"brief field `{field}` is unknown"))
    for eid, ev in evidence.items():
        box = KIND_TO_BOX.get(ev["kind"])
        if not box or not ev["text"]:
            continue
        if _is_evidenced(ev):
            boxes[box].append(Entry(text=ev["text"][:MAX_TEXT], basis="EVIDENCED", evidence_id=eid, url=ev["url"],
                                    date=str(ev["date"])))
        else:
            why = "no source URL and date" if ev["label"] == "evidenced" else f"labelled {ev['label'] or 'unlabelled'}"
            boxes[box].append(Entry(text=ev["text"][:MAX_TEXT], basis="ASSUMPTION", evidence_id=eid,
                                    note=f"Phase 1 item {eid}: {why}"))
    idea, customer = brief.known("idea"), brief.known("target_customer")
    if idea and customer:
        boxes["unique_value_proposition"].append(Entry(
            text=f"{idea}, for {customer}"[:MAX_TEXT * 2], basis="ASSUMPTION",
            note="Composed from the founder's idea and customer; not tested yet"))
    boxes["channels"].append(Entry(text="Landing page with a waitlist (the Phase 2 demand test)",
                                   basis="ASSUMPTION", note="First channel to test; reach is not known yet"))
    boxes["key_metrics"].append(Entry(text="Waitlist sign-ups against the target fixed before the demand test",
                                      basis="ASSUMPTION", note="Measured in Phase 2; the result is entered later"))
    for box in UNKNOWN_IF_EMPTY:
        if not boxes[box]:
            boxes[box].append(Entry(text="unknown", basis="UNKNOWN", note="Not in the confirmed brief"))
    for box in BOXES:
        if not boxes[box]:
            boxes[box].append(Entry(text="unknown", basis="UNKNOWN"))
    return boxes


def _rule_riskiest(brief: Any, boxes: dict[str, list[Entry]]) -> str:
    customer = brief.known("target_customer") or "the target customers"
    idea = brief.known("idea") or "this product"
    evidenced_problem = any(e.basis == "EVIDENCED" for e in boxes["problem"])
    base = f"{customer} want {idea} enough to join a waitlist"
    return base if evidenced_problem else f"{base} (the problem itself has no sourced evidence yet)"


# ---------- model ----------

def _default_chat() -> tuple[Chat | None, str | None]:
    from venture_os.llm.client import chat_json, live_enabled, model_for
    if not live_enabled():
        return None, None
    return (lambda messages: chat_json(messages, profile="reasoning")), model_for("reasoning")


def _language(brief: Any) -> str:
    langs = brief.tag("languages") if hasattr(brief, "tag") else []
    first = langs[0] if isinstance(langs, list) and langs else langs
    return "Arabic" if first == "ar" else "English"


def _ask_model(chat: Chat, brief: Any, evidence: dict[str, dict]) -> dict | None:
    fields = {n: brief.known(n) or "unknown" for n in getattr(brief, "fields", {})}
    items = [{"id": k, "kind": v["kind"], "text": v["text"], "has_source": _is_evidenced(v)}
             for k, v in evidence.items()]
    messages = [
        {"role": "system", "content": load_prompt("business_designer", language=_language(brief))},
        {"role": "user", "content": "<untrusted>\n" + json.dumps({"brief": fields, "evidence": items},
                                                                 ensure_ascii=False)[:20000] + "\n</untrusted>"},
    ]
    for _ in range(2):  # one retry, then rules
        try:
            data = json.loads(chat(messages))
        except Exception:  # noqa: BLE001 - bad JSON, timeout, model down: retry once, then rules
            data = None
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    return None


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _repeats(text: str, entries: list[Entry]) -> bool:
    t = _norm(text)
    return any(t == _norm(e.text) or (len(t) > 15 and t in _norm(e.text)) for e in entries)


def _blocked(text: str) -> str | None:
    rules = check_output(text)
    if rules:
        return rules[0]
    if any(p.search(text) for p in INCOME_PATTERNS):
        return "income_statement"
    return None


def _merge_model(raw: dict, boxes: dict[str, list[Entry]], evidence: dict[str, dict],
                 model: str) -> tuple[int, list[str], str | None]:
    added, dropped = 0, []
    per_box: dict[str, int] = {}
    for item in raw.get("entries", [])[:30]:
        if not isinstance(item, dict):
            continue
        box, text = item.get("box"), str(item.get("text") or "").strip()
        if box not in BOXES or not text or per_box.get(box, 0) >= 2:
            continue
        text = text[:MAX_TEXT]
        if _repeats(text, boxes[box]):  # the model often echoes the founder's words; keep the FOUNDER row only
            continue
        if why := _blocked(text):
            dropped.append(f"{box}: {why}")
            continue
        eid = item.get("evidence_id")
        eid = str(eid) if eid not in (None, "", "null") else None
        ev = evidence.get(eid) if eid else None
        if ev and _is_evidenced(ev):
            entry = Entry(text=text, basis="EVIDENCED", evidence_id=eid, url=ev["url"], date=str(ev["date"]), by=model)
        elif eid:
            reason = "does not exist" if ev is None else "has no source URL and date"
            entry = Entry(text=text, basis="ASSUMPTION", by=model,
                          note=f"model cited evidence id {eid}, which {reason}: relabelled ASSUMPTION")
        else:
            entry = Entry(text=text, basis="ASSUMPTION", by=model)
        # a suggestion never hides an unknown brief field (only the generic "unknown" placeholder goes)
        boxes[box] = [e for e in boxes[box] if e.basis != "UNKNOWN" or e.field] + [entry]
        per_box[box] = per_box.get(box, 0) + 1
        added += 1
    riskiest = str(raw.get("riskiest_assumption") or "").strip()[:300]
    if riskiest and (why := _blocked(riskiest)):
        dropped.append(f"riskiest_assumption: {why}")
        riskiest = ""
    return added, dropped, riskiest or None


# ---------- output ----------

def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _source(e: Entry) -> str:
    if e.basis == "FOUNDER":
        return f"brief field `{e.field}`"
    if e.basis == "EVIDENCED":
        return f"{e.evidence_id}: {e.url} ({e.date})"
    return _cell(e.note) if e.note else ("model suggestion" if e.by != "rules" else "")


def to_markdown(c: LeanCanvas) -> str:
    lines = [f"Brief id: {c.brief_id}", "", "# Phase 2, step 1: Lean Canvas", "",
             (f"Brief version: {c.brief_version if c.brief_version is not None else 'unknown'} · "
              f"Built by: {c.built_by}"), "",
             ("Basis: **FOUNDER** = the founder's words from the confirmed brief (not market facts); "
              "**EVIDENCED** = a Phase 1 source with URL and date; **ASSUMPTION** = not verified yet; "
              "**UNKNOWN** = not in the brief, left unknown."), "",
             "| Box | Entry | Basis | Source |", "|---|---|---|---|"]
    for key, title in BOXES.items():
        for e in c.boxes[key]:
            lines.append(f"| {title} | {_cell(e.text)} | {e.basis} | {_source(e)} |")
    lines += ["", "## Riskiest assumption", "",
              f"ASSUMPTION: {_cell(c.riskiest_assumption)}", "",
              ("The Phase 2 demand test (a landing-page waitlist with a target fixed before it starts) checks "
               "this assumption."), ""]
    if c.notes or c.dropped:
        lines += ["## Notes", ""] + [f"- {_cell(n)}" for n in c.notes]
        lines += [f"- Removed model text that broke a rule ({d})." for d in c.dropped]
        lines.append("")
    lines.append("Revenue streams describe how money would come in; no expected income is stated.")
    return "\n".join(lines) + "\n"
