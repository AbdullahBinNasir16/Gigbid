"""Typed graph state for the bid graph and the conversation graph.

Why the split:
* decision fields hold only what this thread needs now;
* `trace` is a separate append only list of tool calls and node events, for audit;
* long term memory is NOT here, it lives in agent/memory and is written only by
  promotion rules.
Parallel branches (Analyst, Risk, Matcher via Send) write through reducers so they
never overwrite each other.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from agent.handoffs import (
    ApprovalDecision,
    ApprovalPayload,
    BidDecision,
    ComplianceVerdict,
    Critique,
    Evidence,
    FitReport,
    JobSpec,
    OutcomeEvent,
    PriceQuote,
    ProposalDraft,
    RiskReport,
)


class Status(StrEnum):
    running = "running"
    awaiting_approval = "awaiting_approval"
    needs_attention = "needs_attention"
    dead_letter = "dead_letter"
    done = "done"


class Counters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    steps: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    critic_loops: int = Field(default=0, ge=0)
    writer_calls: int = Field(default=0, ge=0)


class TraceEvent(BaseModel):
    """One audit record: a node run or a tool call. Never fed to memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str
    node: str
    kind: Literal["node_start", "node_end", "tool_call", "error", "interrupt", "resume"]
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    result_summary: str | None = None
    tokens: int = 0
    duration_ms: float | None = None


class Analyses(TypedDict, total=False):
    job_spec: JobSpec
    risk: RiskReport
    fit: FitReport


# ------------------------------------------------------------------ reducers


def add_counters(left: Counters | None, right: Counters | None) -> Counters:
    """Sum counters, so parallel nodes each add their own step and token use."""
    left = left or Counters()
    if right is None:
        return left
    return Counters(
        steps=left.steps + right.steps,
        tokens=left.tokens + right.tokens,
        critic_loops=left.critic_loops + right.critic_loops,
        writer_calls=left.writer_calls + right.writer_calls,
    )


def merge_analyses(left: Analyses | None, right: Analyses | None) -> Analyses:
    """Each parallel branch fills its own key; later writes win per key."""
    merged: Analyses = dict(left or {})  # type: ignore[assignment]
    merged.update(right or {})  # type: ignore[typeddict-item]
    return merged


def merge_evidence(left: list[Evidence] | None, right: list[Evidence] | None) -> list[Evidence]:
    """Union by evidence id, keeping the highest score for duplicates. Order: score desc."""
    by_id: dict[str, Evidence] = {}
    for item in [*(left or []), *(right or [])]:
        current = by_id.get(item.id)
        if current is None or item.score > current.score:
            by_id[item.id] = item
    return sorted(by_id.values(), key=lambda e: e.score, reverse=True)


def last_value(left: Any, right: Any) -> Any:
    """Explicit replace semantics for sequential fields."""
    return right if right is not None else left


# --------------------------------------------------------------------- states


class BidState(TypedDict, total=False):
    # identity
    thread_id: str
    user_id: str
    trace_id: str
    persona: str
    # input (job text is untrusted)
    job: dict[str, Any]
    client: dict[str, Any]
    duplicate_of: str | None
    # parallel analyses (Analyst, Risk, Matcher)
    analyses: Annotated[Analyses, merge_analyses]
    evidence: Annotated[list[Evidence], merge_evidence]
    # decisions
    decision: BidDecision
    price: PriceQuote
    drafts: Annotated[list[ProposalDraft], operator.add]
    critiques: Annotated[list[Critique], operator.add]
    verification: dict[str, Any]
    compliance: ComplianceVerdict
    approval_request: ApprovalPayload
    approvals: Annotated[list[ApprovalDecision], operator.add]
    final_text: str
    outcomes: Annotated[list[OutcomeEvent], operator.add]
    # exactly once submission
    submitted: bool
    proposal_id: str
    # control
    counters: Annotated[Counters, add_counters]
    # No reducer on purpose: only sequential nodes set status. If two parallel
    # branches wrote it in one step, LangGraph raises InvalidUpdateError.
    status: Status
    status_reason: Annotated[str | None, last_value]
    errors: Annotated[list[str], operator.add]
    # audit, separate from decision fields
    trace: Annotated[list[TraceEvent], operator.add]


MessageIntent = Literal["question", "negotiation", "interview_request", "scam_signal", "other"]


class ConversationState(TypedDict, total=False):
    thread_id: str
    user_id: str
    trace_id: str
    client_id: str
    job_id: str
    new_messages: list[dict[str, Any]]
    intent: MessageIntent
    proposed_slots: list[dict[str, Any]]
    reply_draft: str
    compliance: ComplianceVerdict
    approval_request: ApprovalPayload
    approvals: Annotated[list[ApprovalDecision], operator.add]
    sent_message_ids: Annotated[list[str], operator.add]
    counters: Annotated[Counters, add_counters]
    # No reducer on purpose: only sequential nodes set status. If two parallel
    # branches wrote it in one step, LangGraph raises InvalidUpdateError.
    status: Status
    status_reason: Annotated[str | None, last_value]
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[TraceEvent], operator.add]


def step(tokens: int = 0, *, critic_loop: bool = False, writer_call: bool = False) -> Counters:
    """Counter delta for one node run; nodes return {'counters': step(...)}."""
    return Counters(
        steps=1, tokens=tokens, critic_loops=int(critic_loop), writer_calls=int(writer_call)
    )
