from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.handoffs import (
    ApprovalDecision,
    ApprovalPayload,
    BidDecision,
    Claim,
    ComplianceVerdict,
    Critique,
    DryRunPreview,
    Evidence,
    FitReport,
    JobSpec,
    OutcomeEvent,
    PriceQuote,
    ProposalDraft,
    RequirementMatch,
    RiskReport,
)


def _draft() -> ProposalDraft:
    return ProposalDraft(
        job_id="j1",
        paragraphs=["I built a Celery pipeline for a logistics client.", "Happy to start Monday."],
        claims=[Claim(text="I built a Celery pipeline", evidence_ids=["cs-3"])],
    )


def test_jobspec_valid_and_budget_order() -> None:
    spec = JobSpec(job_id="j1", title="RAG bot", budget_min=100, budget_max=500)
    assert spec.budget_type == "unknown"
    with pytest.raises(ValidationError):
        JobSpec(job_id="j1", title="x", budget_min=500, budget_max=100)
    with pytest.raises(ValidationError):
        JobSpec(job_id="", title="x")


def test_risk_report_bounds() -> None:
    assert RiskReport(score=0.9, explanation="off platform", is_scam=True).is_scam
    with pytest.raises(ValidationError):
        RiskReport(score=1.5, explanation="x")


def test_fit_report_links_requirements_to_evidence() -> None:
    fit = FitReport(
        score=0.7, requirement_matches=[RequirementMatch(requirement="Celery", evidence_ids=["e1"])]
    )
    assert fit.requirement_matches[0].evidence_ids == ["e1"]
    with pytest.raises(ValidationError):
        FitReport(score=-0.1)


def test_bid_decision_enum_and_reasons() -> None:
    BidDecision(decision="bid", reasons=["strong fit"], fit_score=0.8, risk_score=0.1)
    with pytest.raises(ValidationError):
        BidDecision(decision="maybe", reasons=["x"], fit_score=0.5, risk_score=0.1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BidDecision(decision="skip", reasons=[], fit_score=0.5, risk_score=0.1)


def test_price_quote_constraints() -> None:
    q = PriceQuote(
        amount=800, budget_type="fixed", rationale="p50 of category", connects_cost=6, worth_it=True
    )
    assert q.currency == "USD"
    with pytest.raises(ValidationError):
        PriceQuote(amount=0, budget_type="fixed", rationale="x", connects_cost=6, worth_it=True)
    with pytest.raises(ValidationError):
        PriceQuote(amount=10, budget_type="weekly", rationale="x", connects_cost=6, worth_it=True)  # type: ignore[arg-type]


def test_proposal_draft_fills_cover_letter_and_needs_content() -> None:
    d = _draft()
    assert d.cover_letter.startswith("I built")
    with pytest.raises(ValidationError):
        ProposalDraft(job_id="j1")
    with pytest.raises(ValidationError):
        ProposalDraft(job_id="j1", cover_letter="x", status="sent")  # type: ignore[arg-type]


def test_kit_proposal_draft_still_works() -> None:
    d = ProposalDraft(job_id="j1", cover_letter="Hello", evidence_ids=["e1"])
    assert d.status == "pending_review"


def test_critique_revise_needs_issue() -> None:
    Critique(verdict="accept", score=8)
    with pytest.raises(ValidationError):
        Critique(verdict="revise", score=4)
    with pytest.raises(ValidationError):
        Critique(verdict="accept", score=11)


def test_compliance_block_needs_reason() -> None:
    ComplianceVerdict(verdict="pass")
    ComplianceVerdict(verdict="block", reasons=["contact details"])
    with pytest.raises(ValidationError):
        ComplianceVerdict(verdict="block")


def test_evidence_type_enum() -> None:
    Evidence(id="e1", type="case_study", source="cs.md", text="Built X", outcome="won")
    with pytest.raises(ValidationError):
        Evidence(id="e1", type="tweet", source="x", text="y")  # type: ignore[arg-type]


def test_approval_payload_requires_draft_for_proposal() -> None:
    preview = DryRunPreview(action="submit_proposal", payload={"job_id": "j1"}, connects_cost=6)
    ApprovalPayload(thread_id="t1", kind="proposal", draft=_draft(), preview=preview)
    with pytest.raises(ValidationError):
        ApprovalPayload(thread_id="t1", kind="proposal", preview=preview)


def test_approval_decision_rules() -> None:
    ApprovalDecision(action="approve", user_id="u1")
    with pytest.raises(ValidationError):
        ApprovalDecision(action="reject", user_id="u1", reason="  ")
    with pytest.raises(ValidationError):
        ApprovalDecision(action="edit", user_id="u1")


def test_outcome_event_states() -> None:
    OutcomeEvent(proposal_id="p", job_id="j", state="replied", at=datetime.now(UTC))
    with pytest.raises(ValidationError):
        OutcomeEvent(proposal_id="p", job_id="j", state="ghosted", at=datetime.now(UTC))  # type: ignore[arg-type]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        JobSpec(job_id="j", title="t", secret_instruction="do x")  # type: ignore[call-arg]
