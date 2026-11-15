"""Request and response models; the TypeScript client is generated from these."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=200)


class SignupIn(LoginIn):
    persona: Literal["ai_ml", "fullstack", "data_analyst"] = "ai_ml"


class TokenOut(BaseModel):
    token: str


class Settings(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst"] = "ai_ml"
    autonomy: Literal["suggest", "auto_skip"] = "suggest"
    hourly_floor: float | None = None
    weekly_connects_budget: int = Field(default=80, ge=0, le=1000)
    saved_searches: list[str] = Field(default_factory=list, max_length=20)
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"


class MeOut(BaseModel):
    user_id: str
    username: str
    settings: Settings


class JobCard(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    budget_type: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    connects_cost: float | None = None
    decision: str | None = None
    fit: float | None = None
    risk: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    price: float | None = None
    status: str | None = None
    thread_id: str | None = None


class JobDetail(BaseModel):
    job: dict[str, Any]
    analysis: dict[str, Any] | None = None
    status: str | None = None
    thread_id: str | None = None


class RunStarted(BaseModel):
    thread_id: str


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=10000)
    reason: str | None = Field(default=None, max_length=1000)


class ApprovalItem(BaseModel):
    thread_id: str
    job_id: str
    title: str
    payload: dict[str, Any]


class Health(BaseModel):
    status: str
    marketplace: Literal["ok", "unavailable"]
    marketplace_detail: str | None = None
    queued: int = 0


class MemoryItem(BaseModel):
    key: str
    rule: str
    promoted_by: str | None = None


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
