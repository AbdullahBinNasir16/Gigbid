"""Public API models of GigSim. Hidden client preferences are NOT part of any public model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProposalState = Literal["draft", "submitted", "viewed", "replied", "interview", "hired", "lost"]


class JobOut(BaseModel):
    job_id: str
    title: str
    description: str
    skills: list[str] = Field(default_factory=list)
    category: str | None = None
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    posted_at: datetime
    client_id: str
    connects_cost: int
    experience_level: str | None = None
    applicants: str | None = None
    provenance: Literal["real", "synthetic"]
    source_dataset: str | None = None


class JobPage(BaseModel):
    total: int
    items: list[JobOut]


class ClientOut(BaseModel):
    client_id: str
    completed_projects: int
    rating: float | None
    total_spend: float
    payment_verified: bool
    country: str | None
    member_since: str
    reviews: list[str]
    provenance: Literal["real", "synthetic"]


class ConnectsOut(BaseModel):
    user_id: str
    balance: int
    weekly_budget: int
    spent_this_week: int
    cost_per_proposal: int


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    cover_letter: str = Field(min_length=1, max_length=10000)
    amount: float = Field(gt=0, le=1_000_000)
    budget_type: Literal["fixed", "hourly"]
    screening_answers: list[str] = Field(default_factory=list, max_length=10)


class ProposalEvent(BaseModel):
    state: ProposalState
    at: datetime


class ProposalOut(BaseModel):
    proposal_id: str
    user_id: str
    job_id: str
    client_id: str
    cover_letter: str
    amount: float
    budget_type: Literal["fixed", "hourly"]
    state: ProposalState
    connects_cost: int
    created_at: datetime
    submitted_at: datetime | None = None
    events: list[ProposalEvent] = Field(default_factory=list)
    thread_id: str | None = None


class SubmitOut(BaseModel):
    proposal: ProposalOut
    connects_spent: int
    balance_after: int


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)


class MessageOut(BaseModel):
    message_id: str
    thread_id: str
    sender: Literal["client", "freelancer", "system"]
    text: str
    sent_at: datetime


class ThreadOut(BaseModel):
    thread_id: str
    user_id: str
    client_id: str
    job_id: str
    proposal_id: str
    last_message_at: datetime
    message_count: int


class PolicyIn(BaseModel):
    """Admin policy update, e.g. a Connects cost change or a new banned phrase."""

    model_config = ConfigDict(extra="forbid")

    cost_per_proposal: int | None = Field(default=None, ge=0, le=100)
    cost_by_budget_usd: list[dict[str, float]] | None = None
    weekly_budget: int | None = Field(default=None, ge=0)
    banned_phrases: list[str] | None = None
    add_banned_phrases: list[str] | None = None
    max_cover_letter_words: int | None = Field(default=None, ge=10)
    note: str | None = None


class ChaosIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_rate: float | None = Field(default=None, ge=0, le=1)
    requests_per_minute: int | None = Field(default=None, ge=1)
    burst: int | None = Field(default=None, ge=1)


class ErrorOut(BaseModel):
    error: str
    detail: Any = None
