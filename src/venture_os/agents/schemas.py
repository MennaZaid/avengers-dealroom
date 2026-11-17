"""Typed outputs of the Discover steps. Every step renders these to outputs/phase1_step<M>_<name>.md + .json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

ClaimType = Literal["fact", "assumption", "primary_founder_reported"]
Outcome = Literal["go", "repeat", "pivot", "stop"]


class Claim(BaseModel):
    """A market claim. A fact needs a URL, a retrieval date and a verbatim quote; anything else is an assumption."""
    id: str
    type: ClaimType
    topic: str                      # pain | competitor_price | market_size | competitors | ... | open_question_N
    text: str
    quote: str | None = None
    url: str | None = None
    title: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    source_id: str | None = None    # registry row
    source_kind: str = "web"        # web | registry | api_ugc | api_store | api_statistic | founder
    tier: str | None = None
    language: str | None = None
    flags: list[str] = []
    extracted_by: str = "rules"     # rules | model id
    document_id: str | None = None
    chunk_id: str | None = None

    @field_validator("url")
    @classmethod
    def _http(cls, v):
        if v is not None and not v.startswith(("https://", "http://")):
            raise ValueError("claim URL must be http(s)")
        return v

    def model_post_init(self, _ctx) -> None:
        if self.type == "fact" and not (self.url and self.retrieved_at and self.quote):
            raise ValueError(f"fact claim {self.id} needs url, retrieved_at and a verbatim quote")


class Idea(BaseModel):
    id: str                          # I0 = the founder's starting idea (sharpened), I1.. = alternatives
    title: str
    description: str
    product_type: str                # saas | mobile_app | template_or_asset | online_course | ...
    origin: Literal["starting_idea", "alternative"]
    built_by: str                    # model id or "rules"
    pain: str                        # the pain it solves, in one sentence
    pain_claim_ids: list[str] = []   # verbatim quotes from real people
    why_founder: str = ""            # skills / budget / time / values link
    assumptions: list[str] = []


class CriterionScore(BaseModel):
    criterion: str
    score: float
    evidence_ids: list[str] = []
    basis: Literal["evidenced", "ASSUMPTION"] = "evidenced"
    note: str = ""


class IdeaScore(BaseModel):
    idea_id: str
    criteria: list[CriterionScore]
    total: float                     # computed in plain code from config weights, never by the model
    proposed_by: str                 # model id or "rules"


class Competitor(BaseModel):
    name: str
    url: str
    kind: Literal["direct", "substitute", "open_source"] = "direct"
    price: str | None = None         # as published, e.g. "Free", "$9.99", "KES 1,499/month"
    pricing_model: str | None = None  # free | paid | subscription | freemium | unknown
    price_claim_id: str | None = None
    signal: str = ""                 # rating count, installs, stars ...
    source_id: str | None = None


class SizingInput(BaseModel):
    name: str
    low: float | None
    high: float | None
    unit: str
    claim_id: str | None = None      # sourced input
    basis: Literal["sourced", "ASSUMPTION"] = "ASSUMPTION"
    note: str = ""


class MarketDefinition(BaseModel):
    segment: str
    geography: str
    beachhead: str
    competitors: list[Competitor]
    inputs: list[SizingInput]
    formula: str
    tam: tuple[float | None, float | None]
    sam: tuple[float | None, float | None]
    som: tuple[float | None, float | None]
    currency: str
    notes: list[str] = []


class InterviewRecord(BaseModel):
    """Founder-entered only. The system never writes interview answers."""
    id: str
    person: str                      # anonymous label, e.g. "Freelance designer, Cairo"
    held_on: str
    past_behaviour: bool             # described a real past situation, not an opinion
    describes_problem: bool
    notes: str
    type: Literal["primary_founder_reported"] = "primary_founder_reported"


class GateResult(BaseModel):
    recommendation: Outcome
    reasons: list[str]
    checks: list[dict]               # {check, target, actual, passed}
    thresholds: dict
    pivot_to: str | None = None      # idea id when the recommendation is pivot
    collect_next: list[str] = []     # what to collect for a repeat
    note: str = "A recommendation only: the founder decides at the gate."
