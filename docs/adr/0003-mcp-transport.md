# ADR 0003: In-process MCP by default, HTTP for external hosts

Status: accepted (15 Nov 2026)

**Context.** Agents must only use MCP tools. Free hosts give one container; compose can run each server separately.

**Decision.** agent/mcp_client.py talks MCP to the same server objects either over in-memory streams (MCP_TRANSPORT=memory, default) or over Streamable HTTP with bearer tokens via MultiServerMCPClient (MCP_TRANSPORT=http). The servers also run standalone for Claude Desktop, Cursor and MCP Inspector.

**Consequences.** Same schemas, validation, annotations and audit log on both paths; tests use the in-memory client. The single-container deploy has no internal network surface. Per-agent allowlists are enforced in the client in both modes.
