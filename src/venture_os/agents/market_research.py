"""Market Research agent (Discover): market size, customer pain, pricing, regulation and the open questions
from onboarding. Works through its topics with store_search, web_search and fetch (see agents/base.py)."""

from venture_os.agents.base import ResearchAgent


class MarketResearchAgent(ResearchAgent):
    name = "market_research"
