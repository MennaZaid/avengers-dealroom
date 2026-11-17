"""Competitor Intelligence agent (Discover): finds the brief's known competitors online, and candidate
competitors and alternatives from search results, each with a link."""

import re

from venture_os.agents.base import ResearchAgent
from venture_os.agents.research_planner import Topic
from venture_os.tools.search import SearchHit


class CompetitorIntelligenceAgent(ResearchAgent):
    """Also builds the competitor list: brief competitors matched to a result, and candidates from results."""
    name = "competitor_intelligence"

    def __init__(self, *args, known: list[str] | None = None, **kw):
        super().__init__(*args, **kw)
        self.known = known or []
        self._names: dict[str, dict] = {}

    def on_hits(self, topic: Topic, query: str, hits: list[SearchHit]) -> None:
        for name in self.known:
            if not query.lower().startswith(name.lower()) or name.lower() in self._names:
                continue
            token = re.sub(r"\W+", "", name.lower())
            match = next((h for h in hits if token and token in re.sub(r"\W+", "", (h.title + h.url).lower())),
                         None)
            entry = {"name": name, "from_brief": True, "url": match.url if match else None,
                     "title": match.title if match else None,
                     "status": "found online" if match else "not found in search results",
                     "evidence": "search result" if match else None}
            self._names[name.lower()] = entry
            self.result.competitors.append(entry)
        if not any(query.lower().startswith(n.lower()) for n in self.known):
            for h in hits[:5]:
                key = h.url.lower()
                if key in self._names:
                    continue
                self._names[key] = {"name": h.title[:120] or h.url, "from_brief": False, "url": h.url,
                                    "title": h.title, "status": "candidate from search (unverified)",
                                    "evidence": "search result"}
                self.result.competitors.append(self._names[key])
