"""Workspace MCP server: slots, idempotent holds and drafts."""

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace import server


async def test_hold_is_idempotent_and_blocks_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "STORE", tmp_path / "ws.json")
    monkeypatch.setattr("mcp_servers.common.AUDIT_DIR", tmp_path)
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as c:
        slots = (await c.call_tool("get_free_slots", {})).structuredContent["slots"]
        args = {"start": slots[0]["start"], "duration_minutes": 30, "title": "Interview",
                "idempotency_key": "hold-key-0001"}
        a = (await c.call_tool("create_tentative_hold", args)).structuredContent
        b = (await c.call_tool("create_tentative_hold", args)).structuredContent
        again = (await c.call_tool("get_free_slots", {})).structuredContent["slots"]
    assert a["hold_id"] == b["hold_id"] and b["replayed"] is True
    assert slots[0]["start"] not in [s["start"] for s in again]
