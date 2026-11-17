"""Phase 1 (Discover) orchestration. Starts once the founder has confirmed the brief; ends at the gate.

  thresholds  -> decision_log "set_gate_thresholds" BEFORE any research
  step 0  research_planner     topics, AR/EN queries, registry sources (product_scope digital|any)
  step 1  brief_analyzer       the six brief fields + product type        -> phase1_step1_brief.md/.json
  step 2  opportunity_finder   pain quotes + sharpened idea + alternatives -> phase1_step2_opportunities.md/.json
  step 3  idea_scorer          weighted matrix, totals in plain code       -> phase1_step3_idea_scores.md/.json
  step 4  market_definer       beachhead, competitors, TAM/SAM/SOM         -> phase1_step4_market.md/.json
  step 5  interview_designer   Mom Test plan, linted script                -> phase1_step5_interview_plan.md/.json
  step 6  research_critic      rules + a different-family judge model      -> appended to the gate file
  gate    gates.evaluate_discover (plain code) -> recommendation; the founder decides (approval.py)
                                                                          -> phase1_gate_decision.md/.json
Every agent action goes to decision_log.json. Every page read goes to Postgres (documents/chunks), every claim
to `claims`. Nothing is published, sent or spent.
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from venture_os import discover_report, gates
from venture_os.agents import (
    brief_analyzer,
    idea_scorer,
    interview_designer,
    market_definer,
    opportunity_finder,
    research_critic,
)
from venture_os.agents.base import Budget, Toolbox, Trace
from venture_os.agents.competitor_intelligence import CompetitorIntelligenceAgent
from venture_os.agents.market_research import MarketResearchAgent
from venture_os.agents.research_planner import ResearchPlan, lang_of, split_competitors
from venture_os.agents.schemas import Claim, Competitor, IdeaScore
from venture_os.decision_log import log_action, log_actions
from venture_os.evidence.extract import model_claims, rule_claims, terms
from venture_os.evidence.store import EvidenceStore, StoredChunk
from venture_os.evidence.validate import claim_flags, run_report
from venture_os.guardrails import check_request
from venture_os.llm import profiles
from venture_os.tools import apis as free_apis
from venture_os.tools.fetch import Page, fetch_page
from venture_os.tools.search import SearchError, SearchHit, searxng_search

MAX_CLAIMS_PER_TOPIC = 10
IGNORED: list[dict] = []  # injected instructions found in fetched pages during the current run
# Words that show someone describing a problem (EN + Egyptian/MSA Arabic). Marketing copy and generic text
# that merely shares the query's words do not count as pain evidence.
PAIN_MARKER = re.compile(
    r"\b(problem|issue|frustrat\w*|annoy\w*|hate|struggl\w*|wast\w*|lost|lose|losing|can'?t|cannot|couldn'?t|"
    r"never|no way|wish|hard|difficult|painful|pain|complain\w*|expensive|too much|time[- ]consuming|tedious|"
    r"broken|bug|fail\w*|missing|unreliable|late|stuck|confus\w*|manual(?:ly)?|slow)\b|"
    r"مشكل|صعب|بيضيع|ضاع|مش لاقي|مش عارف|تعبت|غالي|بيتأخر|اتأخر|مزعج|بطيء|معاناة|بنعاني|ناقص|متلخبط",
    re.IGNORECASE)
CHUNKS_PER_DOC = 3
MARKET_TOPICS = ("market_size", "pricing", "regulation")


class LiveToolbox:
    """Real tools: SearXNG, the web, free APIs, and the Postgres evidence store."""

    apis = free_apis

    def __init__(self, store: EvidenceStore | None = None):
        self.store = store or EvidenceStore()

    def search(self, query: str, language: str) -> list[SearchHit]:
        return searxng_search(query, language)

    def fetch(self, url: str) -> Page:
        return fetch_page(url)

    def save_page(self, page: Page) -> list[StoredChunk]:
        return self.store.save_page(page)

    def search_store(self, query: str) -> list[StoredChunk]:
        return self.store.search_chunks(query)

    def registry_match(self, url: str):
        return self.store.registry_match(url)


def registry_pages(plan: ResearchPlan, per_topic: int = 2) -> dict[str, list[SearchHit]]:
    """The country's registry sources, read directly by the agents (a page that blocks bots is skipped)."""
    if isinstance(plan.country_sources, str):
        return {}
    out: dict[str, list[SearchHit]] = {}
    for t in plan.topics:
        if t.kind != "standard":
            continue
        refs = [s for s in plan.country_sources if s.id in t.source_ids and s.crawl != "none" and s.url]
        refs.sort(key=lambda s: (s.tier, s.id))
        out[t.key] = [SearchHit(url=s.url, title=f"{s.id} {s.source_name}", snippet="", rank=0)
                      for s in refs[:per_topic]]
    return out


def _best_chunks(chunks: list[StoredChunk], query: str) -> list[StoredChunk]:
    want = terms(query)
    by_doc: dict[str, list[StoredChunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.document_id, []).append(c)
    out = []
    for doc_chunks in by_doc.values():
        ranked = sorted(doc_chunks, key=lambda c: -len(want & terms(c.text)))
        out.extend(c for c in ranked[:CHUNKS_PER_DOC] if want & terms(c.text))
    return out


def extract_claims(evidence, plan: ResearchPlan, chat, model_id: str | None, start: int = 1) -> list[Claim]:
    """Verbatim-quote claims from stored pages. Rules by default; a model's claim is kept only if its quote is
    found word for word in the page."""
    cc = plan.country_code if plan.country_code != "unknown" else None
    claims, seen, per_topic = [], set(), {}
    model_calls = int(os.environ.get("MODEL_EXTRACT_CALLS", "12"))  # bounds a run on a CPU-only laptop
    for ev in evidence:
        topic = "pain" if ev.topic in ("pain", "customer_pain") else ev.topic
        for chunk in _best_chunks(ev.chunks, ev.query):
            if per_topic.get(topic, 0) >= MAX_CLAIMS_PER_TOPIC:
                break
            found = rule_claims(chunk, topic, ev.query)
            if chat and found and model_calls > 0:  # the model reads only sections with a candidate sentence
                model_calls -= 1
                found = model_claims(chunk, topic, ev.query, chat)
            for c in found:
                hit = check_request(c["quote"])
                if hit and hit.rule == "instruction_injection":  # page text is data: an instruction is ignored
                    IGNORED.append({"url": chunk.url, "rule": hit.rule})
                    continue
                if topic == "pain" and not PAIN_MARKER.search(c["quote"]):
                    continue  # a pain claim must say something hurts, not just share the query's words
                key = " ".join(c["quote"].split()).lower()
                if key in seen or per_topic.get(topic, 0) >= MAX_CLAIMS_PER_TOPIC:
                    continue
                seen.add(key)
                per_topic[topic] = per_topic.get(topic, 0) + 1
                kind = _source_kind(chunk)
                claims.append(Claim(
                    id=f"C{start + len(claims)}", type="fact", topic=topic, text=c["text"], quote=c["quote"],
                    url=chunk.url, title=chunk.title, published_at=str(chunk.published_at) if chunk.published_at else None,
                    retrieved_at=chunk.retrieved_at.isoformat(timespec="seconds"), source_id=chunk.source_id,
                    source_kind=kind, tier=chunk.tier, language=lang_of(c["quote"]),
                    flags=claim_flags(c, chunk, topic, cc), extracted_by=model_id if c["extracted_by"] == "model" else "rules",
                    document_id=chunk.document_id, chunk_id=chunk.chunk_id))
    return claims


UGC_HOSTS = ("news.ycombinator.com", "stackexchange.com", "stackoverflow.com", "superuser.com", "github.com",
             "apps.apple.com")


def _source_kind(chunk: StoredChunk) -> str:
    if chunk.source_id:
        return "registry"
    return "api_ugc" if any(h in chunk.url for h in UGC_HOSTS) else "web"


def _claim_rows(claims: list[Claim]) -> list[dict]:
    return [{"topic": c.topic, "agent": "discover", "text": c.text, "type": c.type if c.type != "primary_founder_reported"
             else "fact", "document_id": c.document_id, "chunk_id": c.chunk_id, "quote": c.quote,
             "language": c.language, "flags": c.flags, "extracted_by": "rules" if c.extracted_by == "rules" else "model"}
            for c in claims if c.document_id]


def screen_brief(brief: dict, run_id: str) -> list[dict]:
    """Requests hidden in the brief that the system must refuse (fake reviews, income promises, posing as a
    customer, instructions...). Each refusal is logged; the run continues without acting on it."""
    refused = []
    for name, f in (brief.get("fields") or {}).items():
        text = (f or {}).get("value")
        if isinstance(text, str) and (hit := check_request(text)):
            refused.append({"field": name, "rule": hit.rule, "message": hit.message("en")})
            log_action("guardrails", "refuse_request", sources=[], model=None, cost=0.0, approved_by=None,
                       run_id=run_id, stage="discover", field=name, rule=hit.rule)
    return refused


def interview_summary(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        tagged = r.get("tagged") or []
        out.append({"person": r.get("person"), "describes_problem": r.get("describes_problem", True),
                    "counts": any(n.get("counts") for n in tagged),
                    "past_behaviour": any("past_behaviour" in n.get("tags", []) for n in tagged)})
    return out


def pain_statement(db) -> str:
    """Customer + pain, in the founder's words (falls back to the idea when the brief names no problem)."""
    who = db.optional.get("target_customer") or db.required.get("target_market") or ""
    what = db.optional.get("problem") or db.required.get("idea") or ""
    return f"{who} {what}".strip()


def relevance_filter(evidence: list, statement: str, cfg: dict, trace: Trace, embed=None) -> tuple[list, dict]:
    """Drop pain pages whose bge-m3 cosine similarity to the pain statement is under relevance.min_similarity.
    Runs only with live models (never in tests/CI); without an embedding model it is skipped, never a crash."""
    from venture_os.config import Settings

    if embed is None:
        if os.environ.get("LLM_MODE", Settings().llm_mode) != "live":
            return evidence, {"ran": False, "reason": "LLM_MODE is not live"}
        from venture_os.evidence.retrieval import embed
    min_sim = float((cfg.get("relevance") or {}).get("min_similarity", 0.35))
    pages = [e for e in evidence if e.chunks]
    if not statement or not pages:
        return evidence, {"ran": False, "reason": "no pain statement or no pages"}
    try:
        vecs = embed([statement] + [" ".join(c.text for c in e.chunks)[:2000] for e in pages])
    except Exception as e:  # noqa: BLE001 - no embedding model: keep every page, say so
        trace.add("relevance_filter", "skipped", reason=f"{type(e).__name__}: embedding model unavailable")
        return evidence, {"ran": False, "reason": "embedding model unavailable"}

    def cos(a, b):
        na, nb = sum(x * x for x in a) ** 0.5, sum(x * x for x in b) ** 0.5
        return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0

    kept, dropped = [], 0
    for e, v in zip(pages, vecs[1:], strict=True):
        sim = cos(vecs[0], v)
        if sim >= min_sim:
            kept.append(e)
        else:
            dropped += 1
            trace.add("relevance_filter", "drop_page", query=e.query, url=e.chunks[0].url,
                      similarity=round(sim, 3), threshold=min_sim)
    trace.add("relevance_filter", "done", kept=len(kept), dropped=dropped, threshold=min_sim)
    return kept + [e for e in evidence if not e.chunks], {"ran": True, "kept": len(kept), "dropped": dropped}


def run_discover(run_id: str, plan: ResearchPlan, brief: dict, toolbox: Toolbox, store: Any,
                 budget: Budget | None = None, write_files: bool = True) -> dict:
    cfg = gates.load_config()
    log_action("gate", "set_gate_thresholds", sources=[], model=None, cost=0.0, approved_by=None, run_id=run_id,
               stage="discover", thresholds=cfg["thresholds"], weights=cfg["scoring"]["weights"],
               stop_rules=cfg["stop_rules"])
    reasoning, judge = profiles.get_profile("reasoning"), profiles.get_profile("judge")
    extract = profiles.get_profile("extract")
    chat_r = reasoning.chat_json if reasoning else None
    chat_x = extract.chat_json if extract else None
    output: dict = {"plan": plan.model_dump(), "research": {"status": "researching", "trace": []}}
    last = [0.0]

    def progress(events: list[dict]) -> None:
        if time.monotonic() - last[0] > 2:
            last[0] = time.monotonic()
            output["research"]["trace"] = events
            try:
                store.update_run(run_id, output)
            except Exception:  # noqa: BLE001, S110 - progress is best effort
                pass

    trace = Trace(progress)
    budget = budget or Budget()
    steps: list[dict] = []  # one decision-log entry per step
    IGNORED.clear()
    refused = screen_brief(brief, run_id)
    try:
        db = brief_analyzer.analyze(brief, chat_x, extract.model if extract else None)
        by = db.product_type.decided_by
        steps.append({"agent": "brief_analyzer", "action": "classify_product_type", "sources": [],
                      "model": None if by in ("rules", "guardrails.check_product") else by,
                      "product_type": db.product_type.label, "group": db.product_type.group,
                      "trigger": db.product_type.trigger})
        research: dict = {"brief": db.model_dump()}
        if db.product_type.group == "excluded":
            gate = gates.evaluate_discover("excluded", db.product_type.label, [], [], [], [], cfg)
            research.update(status="done", claims=[], ideas=[], scores=[], market=None, interview_plan=None,
                            critic=None, gate=gate.model_dump(), interviews=[])
        else:
            pages = registry_pages(plan)
            known = split_competitors(db.optional.get("known_competitors"))
            market_t = [t for t in plan.topics if t.key in MARKET_TOPICS]
            comp_t = [t for t in plan.topics if t.key == "competitors"]
            market_agent = MarketResearchAgent(market_t, toolbox, budget, trace, chat_r, registry_pages=pages)
            comp_agent = CompetitorIntelligenceAgent(comp_t, toolbox, budget, trace, chat_r, known=known,
                                                     registry_pages=pages)
            with ThreadPoolExecutor(max_workers=3) as pool:
                f_pain = pool.submit(opportunity_finder.gather_pain, plan, db, toolbox, budget, trace, chat_r, pages)
                f_market = pool.submit(market_agent.run)
                f_comp = pool.submit(comp_agent.run)
                pain_ev, market_res, comp_res = f_pain.result(), f_market.result(), f_comp.result()
            api_found = market_definer.api_competitors(plan, db, toolbox, trace)
            pain_ev, relevance = relevance_filter(pain_ev, pain_statement(db), cfg, trace)
            claims = extract_claims(pain_ev + market_res.evidence + comp_res.evidence, plan, chat_x,
                                    extract.model if extract else None)
            reach = None
            apis = getattr(toolbox, "apis", None)
            if apis is not None and plan.country_code != "unknown":
                try:
                    item = apis.wdi_indicator(plan.country_code)
                    if item:
                        chunks = toolbox.save_page(opportunity_finder.item_page(item))
                        trace.add("market_definer", "api_call", api="wdi_indicator", sources=[item.url])
                        reach = Claim(id=f"C{len(claims) + 1}", type="fact", topic="digital_reach", text=item.text,
                                      quote=item.text, url=item.url, title=item.title,
                                      published_at=str(item.published),
                                      retrieved_at=(chunks[0].retrieved_at if chunks else datetime.now(UTC)).isoformat(
                                          timespec="seconds"), source_id="R-001",
                                      source_kind="api_statistic", tier="A",
                                      document_id=chunks[0].document_id if chunks else None,
                                      chunk_id=chunks[0].chunk_id if chunks else None)
                        claims.append(reach)
                except SearchError as e:
                    trace.add("market_definer", "api_failed", api="wdi_indicator", error=str(e)[:150])
            market, price_claims = market_definer.define_market(plan, db, comp_res.competitors, claims, api_found,
                                                                reach)
            claims += price_claims
            pain = [c for c in claims if c.topic == "pain" and "stale" not in c.flags]
            ideas = opportunity_finder.propose_ideas(db, pain, chat_r, reasoning.model if reasoning else None)
            scores = idea_scorer.score_ideas(ideas, db, claims, market.competitors, reach, chat_r,
                                             reasoning.model if reasoning else None)
            iplan = interview_designer.plan(db, pain, ideas[0].title if ideas else None)
            critic = research_critic.review(claims, ideas, judge.chat_json if judge else None,
                                            judge.model if judge else None, judge.family if judge else None,
                                            reasoning.family if reasoning else None,
                                            brief_text=" ".join(str(v) for v in (db.required | db.optional).values() if v))
            interviews = interview_summary(store.interviews(brief["brief_id"]) if hasattr(store, "interviews") else [])
            gate = gates.evaluate_discover(db.product_type.group, db.product_type.label, claims, market.competitors,
                                           scores, interviews, cfg, relevance=relevance)
            ids = store.save_claims(run_id, _claim_rows(claims))
            research.update(
                status="done", relevance=relevance, claims=[c.model_dump() for c in claims],
                ideas=[i.model_dump() for i in ideas],
                scores=[s.model_dump() for s in scores], market=market.model_dump(),
                interview_plan=iplan.model_dump(), critic=critic.model_dump(), gate=gate.model_dump(),
                interviews=interviews, report=run_report([c.model_dump() for c in claims if c.type == "fact"],
                                                         [t.key for t in plan.topics if t.queries]),
                stored_claims=len(ids), documents=len({c.document_id for c in claims if c.document_id}),
                models={"reasoning": reasoning.model if reasoning else None,
                        "extract": extract.model if extract else None, "judge": judge.model if judge else None},
                not_built=["Source Finder (new official sources for an uncovered country)"])
            urls = lambda cs: sorted({c.url for c in cs if c.url})
            steps += [
                {"agent": "research_planner", "action": "plan_research", "sources": [], "model": None,
                 "topics": [t.key for t in plan.topics]},
                {"agent": "opportunity_finder", "action": "find_opportunities", "sources": urls(pain)[:40],
                 "model": reasoning.model if reasoning else None, "ideas": [i.id for i in ideas]},
                {"agent": "idea_scorer", "action": "score_ideas", "sources": [], "model": reasoning.model if reasoning
                 else None, "totals": {s.idea_id: s.total for s in scores}},
                {"agent": "market_definer", "action": "define_market",
                 "sources": sorted({c.url for c in market.competitors})[:40] + ([reach.url] if reach else []),
                 "model": None},
                {"agent": "interview_designer", "action": "design_interviews", "sources": [], "model": None,
                 "rejected_questions": sum(1 for r in iplan.lint if not r.ok)},
                {"agent": "research_critic", "action": "review_research", "sources": [],
                 "model": critic.judge_model, "findings": len(critic.findings)},
            ]
        research["trace"] = trace.events
        research["refused_requests"] = refused
        research["ignored_injections"] = list(IGNORED)
        for ig in IGNORED:
            steps.append({"agent": "evidence_extractor", "action": "ignore_injected_instruction",
                          "sources": [ig["url"]], "model": None, "rule": ig["rule"]})
        steps.append({"agent": "gate", "action": "evaluate_discover_gate", "sources": [], "model": None,
                      "outcome": research["gate"]["recommendation"], "pivot_to": research["gate"].get("pivot_to")})
        output["research"] = research
        store.update_run(run_id, output, "awaiting_approval")
    except Exception as e:  # noqa: BLE001 - recorded on the run, never hidden
        output["research"].update(status="failed", error=f"{type(e).__name__}: {e}", trace=trace.events)
        store.update_run(run_id, output, "failed")
    _record(run_id, output, trace, steps, write_files)
    return output


def _record(run_id: str, output: dict, trace: Trace, steps: list[dict], write_files: bool) -> None:
    """decision_log.json: one entry per agent action (tool calls, then steps); outputs/: the step files."""
    try:
        calls = []
        for e in trace.events:
            detail = {k: v for k, v in e.items() if k not in ("at", "agent", "action", "url", "sources")}
            sources = list(e.get("sources") or ([e["url"]] if e.get("url") else []))
            calls.append({"timestamp": e["at"].replace("+00:00", "Z"), "agent": e["agent"], "action": e["action"],
                          "sources": sources, "model": None, "cost": 0.0, "approved_by": None, "run_id": run_id,
                          "stage": "discover", **detail})
        for s in steps:
            calls.append({"cost": 0.0, "approved_by": None, "run_id": run_id, "stage": "discover", **s})
        log_actions(calls)
        if write_files and output["research"].get("status") == "done":
            discover_report.write_all(run_id, output)
    except Exception as e:  # noqa: BLE001
        output["research"].setdefault("record_errors", []).append(f"{type(e).__name__}: {e}")


def regate(run: dict, interviews_rows: list[dict]) -> dict:
    """Re-evaluate the gate with the founder's current interviews (no new research). Returns the new gate."""
    research = (run.get("output") or {}).get("research") or {}
    brief = research.get("brief") or {}
    pt = brief.get("product_type") or {}
    claims = [Claim.model_validate(c) for c in research.get("claims") or []]
    comps = [Competitor.model_validate(c) for c in (research.get("market") or {}).get("competitors") or []]
    scores = [IdeaScore.model_validate(s) for s in research.get("scores") or []]
    interviews = interview_summary(interviews_rows)
    gate = gates.evaluate_discover(pt.get("group", "ambiguous"), pt.get("label", "?"), claims, comps, scores,
                                   interviews, relevance=research.get("relevance"))
    log_action("gate", "evaluate_discover_gate", sources=[], model=None, cost=0.0, approved_by=None,
               run_id=str(run["id"]), stage="discover", outcome=gate.recommendation, trigger="interviews updated",
               interviews=len(interviews))
    return {"gate": gate.model_dump(), "interviews": interviews}
