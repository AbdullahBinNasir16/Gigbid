"""Portfolio MCP server through an in-memory MCP client."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio import server


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml")
    monkeypatch.setattr("mcp_servers.common.AUDIT_DIR", tmp_path)


async def test_search_evidence_finds_matching_project():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
        r = await c.call_tool("search_evidence", {"requirement": "RAG chatbot over help-centre "
                                                  "articles with Pinecone", "k": 5})
    items = r.structuredContent["items"]
    assert items and items[0]["project"] == "support-rag-bot"
    assert {"type", "source", "date", "outcome"} <= set(items[0])


async def test_case_study_resource_and_prompts():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
        res = await c.read_resource("portfolio://case/support-rag-bot")
        prompts = [p.name for p in (await c.list_prompts()).prompts]
        skills = await c.call_tool("list_skills", {})
    assert "Customer support RAG chatbot" in res.contents[0].text
    assert "answer_screening_question" in prompts
    assert "RAG" in skills.structuredContent["skills"]
