"""MCP client setup and per-agent tool allowlists.

Agents never import GigSim, the portfolio files or the calendar. They call MCP tools through
`ToolBox`, which only exposes the tools named for that agent in config.tool_allowlists.

Transports (MCP_TRANSPORT):
* memory (default): servers run in-process over in-memory MCP streams; no ports, used by
  tests, evals and single-container deployment.
* http: MultiServerMCPClient over Streamable HTTP to the compose services, with bearer
  tokens from env (MCP_<SERVER>_URL, MCP_<SERVER>_BEARER_TOKEN).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from agent.config import get_config

SERVERS = ("marketplace", "portfolio", "workspace")
TOOL_SERVER = {
    "search_jobs": "marketplace", "get_job": "marketplace", "get_client_history": "marketplace",
    "get_connects_balance": "marketplace", "list_messages": "marketplace",
    "create_proposal_draft": "marketplace", "submit_proposal": "marketplace",
    "send_message": "marketplace",
    "search_evidence": "portfolio", "get_case_study": "portfolio", "list_skills": "portfolio",
    "get_free_slots": "workspace", "create_tentative_hold": "workspace",
    "create_email_draft": "workspace",
}


class ToolNotAllowed(PermissionError):
    pass


class ToolError(RuntimeError):
    """An MCP tool returned an error (validation, marketplace failure, outage)."""


def allowlist(agent: str, *, approved: bool = False) -> set[str]:
    al = get_config().tool_allowlists
    entry = getattr(al, agent, None)
    if entry is None:
        return set()
    if hasattr(entry, "read"):  # liaison: read tools, plus writes only after approval
        return set(entry.read) | (set(entry.after_approval) if approved else set())
    return set(entry)


def _server_module(server: str) -> Any:
    if server == "marketplace":
        from mcp_servers.marketplace import server as m
    elif server == "portfolio":
        from mcp_servers.portfolio import server as m
    else:
        from mcp_servers.workspace import server as m
    return m


async def _call_memory(server: str, tool: str, args: dict[str, Any]) -> Any:
    from mcp.shared.memory import create_connected_server_and_client_session

    mod = _server_module(server)
    async with create_connected_server_and_client_session(mod.mcp._mcp_server) as session:
        result = await session.call_tool(tool, args)
    if result.isError:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise ToolError(f"{tool}: {text[:500]}")
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text) if result.content else None


_http_client: Any = None


async def _call_http(server: str, tool: str, args: dict[str, Any]) -> Any:
    global _http_client
    if _http_client is None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        conns = {}
        for s in SERVERS:
            url = os.environ.get(f"MCP_{s.upper()}_URL", f"http://{s}-mcp:81{SERVERS.index(s)+1:02d}/mcp")
            token = os.environ.get(f"MCP_{s.upper()}_BEARER_TOKEN", "")
            conns[s] = {"transport": "streamable_http", "url": url,
                        "headers": {"Authorization": f"Bearer {token}"} if token else {}}
        _http_client = MultiServerMCPClient(conns)
    async with _http_client.session(server) as session:
        result = await session.call_tool(tool, args)
    if result.isError:
        raise ToolError(f"{tool}: {' '.join(getattr(c, 'text', '') for c in result.content)}")
    return result.structuredContent


class ToolBox:
    """The tools one agent may call, with timeout and a trace record per call."""

    def __init__(self, agent: str, *, trace_id: str | None = None, approved: bool = False,
                 transport: str | None = None) -> None:
        self.agent = agent
        self.allowed = allowlist(agent, approved=approved)
        self.trace_id = trace_id
        self.transport = transport or os.environ.get("MCP_TRANSPORT", "memory")
        self.calls: list[dict[str, Any]] = []
        self.timeout = get_config().budgets.node_timeout_seconds

    async def call(self, tool: str, **args: Any) -> Any:
        if tool not in self.allowed:
            raise ToolNotAllowed(f"agent '{self.agent}' may not call '{tool}'")
        server = TOOL_SERVER[tool]
        if self.trace_id and tool not in ("get_case_study", "list_skills", "get_free_slots"):
            args.setdefault("trace_id", self.trace_id)
        fn = _call_memory if self.transport == "memory" else _call_http
        t = time.perf_counter()
        err = None
        try:
            return await asyncio.wait_for(fn(server, tool, args), timeout=self.timeout)
        except Exception as exc:
            err = f"{exc.__class__.__name__}: {exc}"
            raise
        finally:
            self.calls.append({"tool": tool, "arguments": {k: v for k, v in args.items()
                                                           if k != "cover_letter"},
                               "duration_ms": round((time.perf_counter() - t) * 1000, 1),
                               "error": err})
