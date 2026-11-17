"""Shared base for the Discover research agents (agents/market_research.py, agents/competitor_intelligence.py).

Each agent works through its topics of the ResearchPlan with three read-only tools:
  store_search (evidence already in Postgres from earlier runs), web_search (SearXNG), fetch (one page).
Fetched pages are saved in the evidence store (documents + chunks) and become evidence for the topic.

Two policies:
- rules (no model, zero cost; used in CI and when no model is configured): for each planned query, reuse fresh
  stored evidence if there is enough, otherwise search and fetch the best results (registry sources first).
- model: the model picks the next action as JSON. It may only fetch URLs that a search returned (links inside
  pages are never followed), and it has a step budget. Invalid answers fall back to the rules policy.

No tool here publishes, sends, or spends.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from venture_os.agents.research_planner import ResearchPlan, Topic
from venture_os.evidence.store import RegistryMatch, StoredChunk
from venture_os.prompts import load_prompt
from venture_os.tools.fetch import FetchError, Page
from venture_os.tools.search import SearchError, SearchHit

ChatFn = Callable[[list[dict]], str]
TIER_ORDER = {"A": 0, "B": 1, "C": 2, None: 3}


class Toolbox(Protocol):
    def search(self, query: str, language: str) -> list[SearchHit]: ...
    def fetch(self, url: str) -> Page: ...
    def save_page(self, page: Page) -> list[StoredChunk]: ...
    def search_store(self, query: str) -> list[StoredChunk]: ...
    def registry_match(self, url: str) -> RegistryMatch | None: ...


@dataclass
class Budget:
    """Shared across agents in one run so the whole run stays bounded."""
    fetches: int = 40  # pages that block bots or need JavaScript also use a fetch
    searches: int = 40
    pages: dict = field(default_factory=dict)  # url -> stored chunks, shared so two agents never fetch twice
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, kind: str) -> bool:
        with self._lock:
            left = getattr(self, kind)
            if left <= 0:
                return False
            setattr(self, kind, left - 1)
            return True


class Trace:
    """What each agent did, in order. Shown to the founder and kept in the run output."""

    def __init__(self, on_event: Callable[[list[dict]], None] | None = None):
        self.events: list[dict] = []
        self._lock = threading.Lock()
        self._on_event = on_event

    def add(self, agent: str, action: str, **detail) -> None:
        with self._lock:
            self.events.append({"at": datetime.now(UTC).isoformat(timespec="seconds"), "agent": agent,
                                "action": action, **detail})
            snapshot = list(self.events)
        if self._on_event:
            self._on_event(snapshot)


@dataclass
class Evidence:
    topic: str
    query: str
    agent: str
    chunks: list[StoredChunk]


@dataclass
class AgentResult:
    agent: str
    mode: str  # rules | model
    evidence: list[Evidence] = field(default_factory=list)
    competitors: list[dict] = field(default_factory=list)


class ResearchAgent:
    name = "research"
    fetch_per_query = 2

    def __init__(self, topics: list[Topic], toolbox: Toolbox, budget: Budget, trace: Trace,
                 model: ChatFn | None = None, max_model_steps: int = 12,
                 registry_pages: dict[str, list[SearchHit]] | None = None):
        self.topics = topics
        # Country registry sources to read directly for each topic (official sources first), from the plan.
        self.registry_pages = registry_pages or {}
        self.started = datetime.now(UTC)
        self.tools = toolbox
        self.budget = budget
        self.trace = trace
        self.model = model
        self.max_model_steps = max_model_steps
        self.result = AgentResult(agent=self.name, mode="model" if model else "rules")
        self._fetched: dict[str, list[StoredChunk]] = budget.pages  # url -> chunks (empty if unusable)

    # ---- tools, each traced ----
    def _store_search(self, topic: Topic, query: str) -> list[StoredChunk]:
        try:
            # only evidence stored by EARLIER runs counts as reuse; pages from this run are already evidence
            chunks = [c for c in self.tools.search_store(query) if c.retrieved_at < self.started]
        except Exception as e:  # noqa: BLE001 - the store being down must not stop web research
            self.trace.add(self.name, "store_search_failed", topic=topic.key, query=query, error=str(e)[:200])
            return []
        self.trace.add(self.name, "store_search", topic=topic.key, query=query, found=len(chunks))
        if chunks:
            self.result.evidence.append(Evidence(topic.key, query, self.name, chunks))
        return chunks

    def _search(self, topic: Topic, query: str, language: str) -> list[SearchHit]:
        if not self.budget.take("searches"):
            self.trace.add(self.name, "budget_exhausted", kind="searches")
            return []
        try:
            hits = self.tools.search(query, language)
        except SearchError as e:
            self.trace.add(self.name, "search_failed", topic=topic.key, query=query, error=str(e)[:200])
            return []
        self.trace.add(self.name, "search", topic=topic.key, query=query, language=language, results=len(hits))
        return hits

    def _fetch(self, topic: Topic, query: str, hit: SearchHit) -> list[StoredChunk]:
        if hit.url in self._fetched:  # fetched for another query: reuse it as evidence for this one too
            chunks = self._fetched[hit.url]
            if chunks:
                self.result.evidence.append(Evidence(topic.key, query, self.name, chunks))
            return chunks
        if not self.budget.take("fetches"):
            self.trace.add(self.name, "budget_exhausted", kind="fetches")
            return []
        self._fetched[hit.url] = []
        try:
            page = self.tools.fetch(hit.url)
            chunks = self.tools.save_page(page)
            self._fetched[hit.url] = chunks
        except FetchError as e:
            self.trace.add(self.name, "fetch_skipped", topic=topic.key, url=hit.url, reason=str(e)[:200])
            return []
        except Exception as e:  # noqa: BLE001 - one bad page must not stop the run
            self.trace.add(self.name, "fetch_failed", topic=topic.key, url=hit.url, error=str(e)[:200])
            return []
        reg = self.tools.registry_match(page.final_url)
        self.trace.add(self.name, "fetch", topic=topic.key, url=page.final_url, title=page.title[:150],
                       language=page.language, published=str(page.published_at or ""),
                       registry_source=reg.source_id if reg else None, chunks=len(chunks))
        self.result.evidence.append(Evidence(topic.key, query, self.name, chunks))
        return chunks

    def _rank(self, hits: list[SearchHit]) -> list[SearchHit]:
        def key(h: SearchHit):
            m = self.tools.registry_match(h.url)
            return (TIER_ORDER.get(m.tier if m else None, 3), h.rank)
        return sorted(hits, key=key)

    # ---- policies ----
    def run(self) -> AgentResult:
        self.trace.add(self.name, "start", mode=self.result.mode, topics=[t.key for t in self.topics])
        for topic in self.topics:
            if not topic.queries:
                self.trace.add(self.name, "topic_skipped", topic=topic.key, reason=topic.skipped_reason)
                continue
            done = self.model and self._model_topic(topic)
            if not done:
                self._rules_topic(topic)
        self.trace.add(self.name, "finish", evidence=sum(len(e.chunks) for e in self.result.evidence))
        return self.result

    def _read_registry(self, topic: Topic) -> None:
        """Read the topic's country registry sources (official, tier A/B) before searching the web."""
        for hit in self.registry_pages.get(topic.key, []):
            self.trace.add(self.name, "registry_source", topic=topic.key, url=hit.url, source=hit.title)
            self._fetch(topic, topic.queries[0].text if topic.queries else topic.title, hit)

    def _rules_topic(self, topic: Topic) -> None:
        self._read_registry(topic)
        for q in topic.queries:
            self._store_search(topic, q.text)  # earlier runs' evidence is added, never instead of searching
            hits = self._search(topic, q.text, q.language)
            self.on_hits(topic, q.text, hits)
            taken = 0
            for h in self._rank(hits):
                if taken >= self.fetch_per_query:
                    break
                if self._fetch(topic, q.text, h):
                    taken += 1

    def on_hits(self, topic: Topic, query: str, hits: list[SearchHit]) -> None:
        """Hook for agents that learn something from result lists themselves (competitors)."""

    _MODEL_SYSTEM = load_prompt("research_agent")

    def _model_topic(self, topic: Topic) -> bool:
        """Run the model loop for one topic. Returns False to fall back to rules."""
        seen: dict[str, tuple[SearchHit, str]] = {}  # url -> (hit, the query that found it)
        log: list[str] = []
        bad = 0
        planned = "\n".join(f"- [{q.language}] {q.text}" for q in topic.queries)
        for _step in range(self.max_model_steps):
            state = (f"Topic: {topic.title}\nPlanned queries:\n{planned}\nDone so far:\n" + ("\n".join(log) or "-"))
            try:
                action = json.loads(self.model([{"role": "system", "content": self._MODEL_SYSTEM},
                                                {"role": "user", "content": state}]))
                kind = action.get("action")
            except Exception:  # noqa: BLE001
                action, kind = {}, None
            if kind == "finish":
                self.trace.add(self.name, "model_finish", topic=topic.key)
                return True
            if kind == "store_search" and action.get("query"):
                found = self._store_search(topic, str(action["query"]))
                log.append(f"store_search {action['query']!r}: {len(found)} stored passages")
            elif kind == "web_search" and action.get("query"):
                lang = action.get("language") if action.get("language") in ("ar", "en") else "en"
                hits = self._search(topic, str(action["query"]), lang)
                self.on_hits(topic, str(action["query"]), hits)
                for h in hits:
                    seen.setdefault(h.url, (h, str(action["query"])))
                lines = []
                for h in self._rank(hits)[:8]:
                    m = self.tools.registry_match(h.url)
                    tier = f"tier {m.tier}" if m else "web"
                    lines.append(f"  {h.url} | {tier} | {h.title[:100]}")
                log.append(f"web_search {action['query']!r}:\n" + "\n".join(lines))
            elif kind == "fetch" and action.get("url") in seen:
                hit, query = seen[action["url"]]
                got = self._fetch(topic, query, hit)
                log.append(f"fetch {action['url']}: {'ok, ' + str(len(got)) + ' passages' if got else 'not usable'}")
            else:
                bad += 1
                self.trace.add(self.name, "model_invalid_action", topic=topic.key, proposed=str(action)[:200])
                log.append("invalid action (fetch only URLs from search results)")
                if bad >= 2:
                    self.trace.add(self.name, "fallback_to_rules", topic=topic.key)
                    return False
        self.trace.add(self.name, "model_step_limit", topic=topic.key)
        return True


def split_topics(plan: ResearchPlan) -> tuple[list[Topic], list[Topic]]:
    """Competitor topic -> Competitor Intelligence; everything else -> Market Research."""
    comp = [t for t in plan.topics if t.key == "competitors"]
    market = [t for t in plan.topics if t.key != "competitors"]
    return market, comp
