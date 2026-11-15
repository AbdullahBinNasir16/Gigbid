"""Port contract: every adapter must pass these. Phase 2 and 3 adapters reuse it."""

import pytest

from agent.config import load_config
from agent.marketplace_port import (
    InsufficientConnects,
    InvalidRequest,
    MarketplacePort,
    ProposalPayload,
    get_marketplace,
)
from mcp_servers.marketplace.adapters.fake import FakeMarketplace


@pytest.fixture
def port() -> MarketplacePort:
    return FakeMarketplace(balance=20, connects_cost=6)


def _payload(job_id: str = "fake-job-1") -> ProposalPayload:
    return ProposalPayload(job_id=job_id, cover_letter="Hi", amount=900, budget_type="fixed")


async def test_reads(port: MarketplacePort) -> None:
    jobs = await port.search_jobs("rag")
    assert jobs and jobs[0].job_id == "fake-job-1"
    job = await port.get_job("fake-job-1")
    assert job.client_id
    history = await port.get_client_history(job.client_id)
    assert not hasattr(history, "hidden_preferences")
    assert (await port.get_connects_balance()).balance == 20
    assert await port.list_messages() == []
    with pytest.raises(InvalidRequest):
        await port.get_job("missing")


async def test_dry_run_has_no_side_effects(port: MarketplacePort) -> None:
    preview = await port.create_proposal_draft(_payload(), idempotency_key="key-dry-0001", dry_run=True)
    assert preview.dry_run and preview.resource_id is None
    draft = await port.create_proposal_draft(_payload(), idempotency_key="key-draft-001")
    sub_preview = await port.submit_proposal(
        draft.resource_id or "", idempotency_key="key-sub-0001", dry_run=True
    )
    assert sub_preview.connects_cost == 6
    assert sub_preview.connects_balance_after == 14
    assert (await port.get_connects_balance()).balance == 20


async def test_retry_with_same_key_never_spends_twice(port: MarketplacePort) -> None:
    draft = await port.create_proposal_draft(_payload(), idempotency_key="key-draft-001")
    again = await port.create_proposal_draft(_payload(), idempotency_key="key-draft-001")
    assert again.resource_id == draft.resource_id and again.replayed
    first = await port.submit_proposal(draft.resource_id or "", idempotency_key="key-sub-0001")
    second = await port.submit_proposal(draft.resource_id or "", idempotency_key="key-sub-0001")
    assert first.resource_id == second.resource_id
    assert second.replayed and not first.replayed
    assert (await port.get_connects_balance()).balance == 14


async def test_new_key_cannot_resubmit_same_draft(port: MarketplacePort) -> None:
    draft = await port.create_proposal_draft(_payload(), idempotency_key="key-draft-001")
    await port.submit_proposal(draft.resource_id or "", idempotency_key="key-sub-0001")
    with pytest.raises(InvalidRequest):
        await port.submit_proposal(draft.resource_id or "", idempotency_key="key-sub-0002")


async def test_insufficient_connects() -> None:
    port = FakeMarketplace(balance=2, connects_cost=6)
    draft = await port.create_proposal_draft(_payload(), idempotency_key="key-draft-001")
    with pytest.raises(InsufficientConnects):
        await port.submit_proposal(draft.resource_id or "", idempotency_key="key-sub-0001")


async def test_send_message_idempotent(port: MarketplacePort) -> None:
    a = await port.send_message("th1", "Thanks!", idempotency_key="key-msg-0001")
    b = await port.send_message("th1", "Thanks!", idempotency_key="key-msg-0001")
    assert a.resource_id == b.resource_id
    assert len(await port.list_messages("th1")) == 1


def test_factory_picks_adapter_from_config() -> None:
    cfg = load_config(apply_env=False)
    assert isinstance(get_marketplace(cfg, mode="fake"), FakeMarketplace)
    with pytest.raises(InvalidRequest):
        get_marketplace(cfg, mode="nope")
