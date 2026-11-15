"""Typed handoffs between agents.

Why: later steps decide on these objects, so they must be validated structures,
never free text. Kit models (JobSpec, RiskReport, FitReport, ProposalDraft) keep
their original fields; new fields have safe defaults.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(min_length=1, max_length=128, strip_whitespace=True)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Score = Annotated[float, Field(ge=0, le=1)]
Money = Annotated[float, Field(ge=0, le=1_000_000)]


class _Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Provenance(StrEnum):
    real = "real"
    synthetic = "synthetic"


class EvidenceType(StrEnum):
    cv = "cv"
    case_study = "case_study"
    repo = "repo"
    code = "code"
    review = "review"
    proposal = "proposal"


class Outcome(StrEnum):
    won = "won"
    replied = "replied"
    ignored = "ignored"


class Evidence(_Handoff):
    """One retrieved portfolio item that can justify a claim."""

    id: Id
    type: EvidenceType
    source: ShortText
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    score: float = Field(ge=-1e6, le=1e6, default=0.0)
    project: str | None = None
    date: str | None = None
    outcome: Outcome | None = None
    skills: list[str] = Field(default_factory=list, max_length=50)


# ---------------------------------------------------------------- analysis


class Requirement(_Handoff):
    text: ShortText
    kind: Literal["skill", "deliverable", "constraint", "question"] = "skill"
    must_have: bool = True


class JobSpec(_Handoff):
    """What the Job Analyst extracted from an (untrusted) job post."""

    job_id: Id
    title: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    deliverables: list[str] = Field(default_factory=list, max_length=30)
    required_skills: list[str] = Field(default_factory=list, max_length=40)
    budget_min: Money | None = None
    budget_max: Money | None = None
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    category: str | None = Field(default=None, max_length=120)
    client_id: str | None = Field(default=None, max_length=128)
    requirements: list[Requirement] = Field(default_factory=list, max_length=30)
    screening_questions: list[str] = Field(default_factory=list, max_length=10)
    is_vague: bool = False
    injection_suspected: bool = False

    @model_validator(mode="after")
    def _budget_order(self) -> JobSpec:
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min must be <= budget_max")
        return self


class RiskFlag(StrEnum):
    scam = "scam"
    free_work = "free_work"
    off_platform_payment = "off_platform_payment"
    personal_data_request = "personal_data_request"
    prompt_injection = "prompt_injection"
    unverified_payment = "unverified_payment"
    low_client_rating = "low_client_rating"
    duplicate = "duplicate"
    vague = "vague"


class SuspiciousSpan(_Handoff):
    text: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    flag: RiskFlag
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)


class RiskReport(_Handoff):
    score: Score
    flags: list[str] = Field(default_factory=list)  # kit field: RiskFlag values
    explanation: str
    is_scam: bool = False
    injection_detected: bool = False
    suspicious_spans: list[SuspiciousSpan] = Field(default_factory=list, max_length=20)


class RequirementMatch(_Handoff):
    """Links one job requirement to the evidence that proves it."""

    requirement: ShortText
    evidence_ids: list[Id] = Field(default_factory=list, max_length=10)
    strength: Score = 0.0


class FitReport(_Handoff):
    score: Score
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    requirement_matches: list[RequirementMatch] = Field(default_factory=list, max_length=30)


# ---------------------------------------------------------------- decisions


class BidDecision(_Handoff):
    decision: Literal["skip", "watch", "bid"]
    reasons: list[ShortText] = Field(min_length=1, max_length=10)
    fit_score: Score
    risk_score: Score
    auto: bool = False  # True when the autonomy setting auto skipped it


class PriceQuote(_Handoff):
    amount: Money = Field(gt=0)
    currency: Literal["USD"] = "USD"
    budget_type: Literal["fixed", "hourly"]
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=1500)]
    band_low: Money | None = None
    band_high: Money | None = None
    connects_cost: int = Field(ge=0, le=100)
    worth_it: bool


# ---------------------------------------------------------------- writing


class ClaimSupport(StrEnum):
    supported = "supported"
    partly_supported = "partly_supported"
    unsupported = "unsupported"
    unchecked = "unchecked"


class Claim(_Handoff):
    text: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    evidence_ids: list[Id] = Field(default_factory=list, max_length=10)
    support: ClaimSupport = ClaimSupport.unchecked
    paragraph_index: int | None = Field(default=None, ge=0)


class ProposalDraft(_Handoff):
    job_id: Id
    cover_letter: str = ""  # kit field; joined paragraphs when empty
    screening_answers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal[
        "pending_review", "verified", "blocked", "approved", "rejected", "submitted"
    ] = "pending_review"
    paragraphs: list[Annotated[str, StringConstraints(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=12
    )
    claims: list[Claim] = Field(default_factory=list, max_length=40)
    revision: int = Field(default=0, ge=0, le=10)
    strategy: str | None = None

    @model_validator(mode="after")
    def _fill_cover_letter(self) -> ProposalDraft:
        if not self.cover_letter and self.paragraphs:
            object.__setattr__(self, "cover_letter", "\n\n".join(self.paragraphs))
        if not self.cover_letter:
            raise ValueError("a draft needs cover_letter or paragraphs")
        return self


class CritiqueIssue(_Handoff):
    kind: Literal[
        "generic_opening", "unsupported_claim", "not_personalised", "too_long",
        "missing_requirement", "tone", "other",
    ]
    detail: ShortText
    paragraph_index: int | None = Field(default=None, ge=0)


class Critique(_Handoff):
    verdict: Literal["accept", "revise"]
    score: Annotated[float, Field(ge=0, le=10)]
    issues: list[CritiqueIssue] = Field(default_factory=list, max_length=20)
    instructions: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _revise_needs_issue(self) -> Critique:
        if self.verdict == "revise" and not self.issues:
            raise ValueError("a revise verdict must list at least one issue")
        return self


class ComplianceVerdict(_Handoff):
    verdict: Literal["pass", "block"]
    reasons: list[ShortText] = Field(default_factory=list, max_length=20)
    removed_items: list[ShortText] = Field(default_factory=list, max_length=40)
    cleaned_text: str | None = None

    @model_validator(mode="after")
    def _block_needs_reason(self) -> ComplianceVerdict:
        if self.verdict == "block" and not self.reasons:
            raise ValueError("a block verdict must give a reason")
        return self


# ---------------------------------------------------------------- approval


class DryRunPreview(_Handoff):
    action: Literal["submit_proposal", "send_message", "create_tentative_hold"]
    payload: dict[str, object]
    connects_cost: int = Field(ge=0)
    connects_balance_after: int | None = None


class ApprovalPayload(_Handoff):
    """Everything a human needs to approve, edit or reject before anything is sent."""

    thread_id: Id
    kind: Literal["proposal", "message"]
    draft: ProposalDraft | None = None
    message_text: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    risk: RiskReport | None = None
    price: PriceQuote | None = None
    compliance: ComplianceVerdict | None = None
    preview: DryRunPreview

    @model_validator(mode="after")
    def _has_content(self) -> ApprovalPayload:
        if self.kind == "proposal" and self.draft is None:
            raise ValueError("a proposal approval needs a draft")
        if self.kind == "message" and not self.message_text:
            raise ValueError("a message approval needs message_text")
        return self


class ApprovalDecision(_Handoff):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = Field(default=None, max_length=1000)
    user_id: Id

    @model_validator(mode="after")
    def _rules(self) -> ApprovalDecision:
        if self.action == "reject" and not (self.reason and self.reason.strip()):
            raise ValueError("reject requires a reason")
        if self.action == "edit" and not (self.edited_text and self.edited_text.strip()):
            raise ValueError("edit requires edited_text")
        return self


class OutcomeEvent(_Handoff):
    """A marketplace outcome for a submitted proposal."""

    proposal_id: Id
    job_id: Id
    state: Literal["submitted", "viewed", "replied", "interview", "hired", "lost"]
    at: datetime
