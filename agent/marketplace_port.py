"""The one marketplace port.

Why: graph code depends only on this interface. Adapters (GigSim, live Upwork, fake)
are chosen by `marketplace.mode` in config and loaded by import string, so the graph
never imports a specific adapter and switching marketplace is a config edit.

Every write takes an idempotency_key (a retry must never submit or spend twice) and
dry_run (return exactly what would happen, with no side effects).
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agent.config import AppConfig, get_config

IdempotencyKey = Annotated[str, StringConstraints(min_length=8, max_length=200)]


# ------------------------------------------------------------------ errors


class MarketplaceError(Exception):
    """Base for every typed marketplace failure."""


class RateLimited(MarketplaceError):
    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class Unavailable(MarketplaceError):
    """Server down, timeout, 5xx or open circuit breaker."""


class AuthFailed(MarketplaceError):
    pass


class InvalidRequest(MarketplaceError):
    pass


class InsufficientConnects(InvalidRequest):
    pass


# ------------------------------------------------------------------ models


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Job(_Model):
    job_id: str
    title: str
    description: str
    skills: list[str] = Field(default_factory=list)
    category: str | None = None
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    posted_at: datetime | None = None
    client_id: str | None = None
    connects_cost: int | None = None
    provenance: Literal["real", "synthetic"] | None = None


class ClientHistory(_Model):
    """Public history only. Hidden simulator preferences are never exposed."""

    client_id: str
    completed_projects: int = Field(ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    total_spend: float = Field(default=0, ge=0)
    payment_verified: bool
    country: str | None = None
    reviews: list[str] = Field(default_factory=list)


class ConnectsBalance(_Model):
    balance: int = Field(ge=0)
    weekly_budget: int | None = None
    spent_this_week: int = Field(default=0, ge=0)


class Message(_Model):
    message_id: str
    thread_id: str
    sender: Literal["client", "freelancer", "system"]
    text: str
    sent_at: datetime


class ProposalPayload(_Model):
    job_id: str
    cover_letter: str = Field(min_length=1, max_length=10000)
    amount: float = Field(gt=0)
    budget_type: Literal["fixed", "hourly"]
    screening_answers: list[str] = Field(default_factory=list)


class WriteResult(_Model):
    """Result of any write. With dry_run=True nothing happened and `preview` says what would."""

    ok: bool
    dry_run: bool
    idempotency_key: str
    replayed: bool = False  # True when an earlier result was returned for the same key
    resource_id: str | None = None
    connects_cost: int = 0
    connects_balance_after: int | None = None
    preview: dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------------- port


class MarketplacePort(ABC):
    @abstractmethod
    async def search_jobs(
        self, query: str = "", *, limit: int = 20, since: datetime | None = None
    ) -> list[Job]: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Job: ...

    @abstractmethod
    async def get_client_history(self, client_id: str) -> ClientHistory: ...

    @abstractmethod
    async def get_connects_balance(self) -> ConnectsBalance: ...

    @abstractmethod
    async def list_messages(self, thread_id: str | None = None) -> list[Message]: ...

    @abstractmethod
    async def create_proposal_draft(
        self, payload: ProposalPayload, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult: ...

    @abstractmethod
    async def submit_proposal(
        self, draft_id: str, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult: ...

    @abstractmethod
    async def send_message(
        self, thread_id: str, text: str, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult: ...


def _load(path: str) -> type[MarketplacePort]:
    module_name, _, class_name = path.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    if not (isinstance(cls, type) and issubclass(cls, MarketplacePort)):
        raise TypeError(f"{path} does not implement MarketplacePort")
    return cls


def get_marketplace(
    config: AppConfig | None = None, mode: str | None = None, **kwargs: Any
) -> MarketplacePort:
    """Build the adapter named by marketplace.mode (or an explicit mode)."""
    cfg = config or get_config()
    chosen = mode or cfg.marketplace.mode
    try:
        path = cfg.marketplace.adapters[chosen]
    except KeyError as exc:
        raise InvalidRequest(f"no adapter configured for marketplace mode '{chosen}'") from exc
    return _load(path)(**kwargs)
