"""Schema snapshot: fails CI when an MCP tool signature changes unintentionally.

To accept an intended change: UPDATE_SNAPSHOTS=1 pytest tests/contract
"""

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace import server as marketplace
from mcp_servers.portfolio import server as portfolio
from mcp_servers.workspace import server as workspace

SNAP = Path(__file__).parent / "tool_schemas.json"


async def _schemas():
    out = {}
    for name, mod in (("marketplace", marketplace), ("portfolio", portfolio),
                      ("workspace", workspace)):
        async with create_connected_server_and_client_session(mod.mcp._mcp_server) as c:
            for t in (await c.list_tools()).tools:
                out[f"{name}.{t.name}"] = {
                    "input": t.inputSchema, "output": t.outputSchema,
                    "annotations": t.annotations.model_dump(exclude_none=True)
                    if t.annotations else None}
    return out


async def test_tool_schemas_match_snapshot():
    current = await _schemas()
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAP.exists():
        SNAP.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
        if not os.environ.get("UPDATE_SNAPSHOTS"):
            pytest.skip("snapshot created")
    assert current == json.loads(SNAP.read_text(encoding="utf-8")), (
        "MCP tool schema changed; if intended run UPDATE_SNAPSHOTS=1 pytest tests/contract")
