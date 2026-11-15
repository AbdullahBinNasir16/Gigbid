"""Marketplace MCP server through an in-memory MCP client, backed by the fake adapter."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.fake import FakeMarketplace


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr("mcp_servers.common.AUDIT_DIR", tmp_path)
    f = FakeMarketplace(balance=20, connects_cost=6)
    server.set_port(f)
    yield f
    server.set_port(None)


async def _call(name, args):
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
        return await c.call_tool(name, args)


async def test_tools_listed_with_annotations(fake):
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert {"search_jobs", "get_job", "get_client_history", "get_connects_balance",
            "list_messages", "create_proposal_draft", "submit_proposal", "send_message"} <= set(tools)
    assert tools["get_job"].annotations.readOnlyHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["submit_proposal"].annotations.idempotentHint is True
    assert tools["submit_proposal"].outputSchema is not None


async def test_dry_run_has_no_side_effect_and_retry_spends_once(fake):
    job = next(iter(fake.jobs))
    letter = "I built a retrieval chatbot that cut response time from hours to seconds. " * 2
    r = await _call("create_proposal_draft", {"job_id": job, "cover_letter": letter,
                                              "amount": 500, "budget_type": "fixed",
                                              "idempotency_key": "key-draft-0001"})
    assert r.structuredContent["dry_run"] is True and not fake.drafts
    r = await _call("create_proposal_draft", {"job_id": job, "cover_letter": letter,
                                              "amount": 500, "budget_type": "fixed",
                                              "idempotency_key": "key-draft-0001",
                                              "dry_run": False})
    draft_id = r.structuredContent["resource_id"]
    preview = await _call("submit_proposal", {"proposal_id": draft_id,
                                              "idempotency_key": "key-submit-01"})
    assert preview.structuredContent["connects_balance_after"] == 14 and fake.balance == 20
    for _ in range(3):  # retries with the same key
        r = await _call("submit_proposal", {"proposal_id": draft_id, "dry_run": False,
                                            "idempotency_key": "key-submit-01"})
        assert not r.isError
    assert fake.balance == 14


async def test_schema_rejects_short_idempotency_key(fake):
    r = await _call("send_message", {"thread_id": "t1", "text": "hi", "idempotency_key": "x"})
    assert r.isError
