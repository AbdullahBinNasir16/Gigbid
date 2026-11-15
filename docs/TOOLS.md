# Tools

Every capability an agent uses is an MCP tool with a schema, an owner and a test. Agents
reach them only through `agent/mcp_client.py`, which filters by the per-agent allowlist in
`agent/config.yaml` (`tool_allowlists`). Schemas are frozen by
`tests/contract/test_tool_schemas.py` (snapshot in `tests/contract/tool_schemas.json`).

Auth: over HTTP every server requires `Authorization: Bearer <MCP_<SERVER>_BEARER_TOKEN>`
(`mcp_servers/common.py`, `BearerAuthMiddleware`); in-process (`MCP_TRANSPORT=memory`) there
is no network surface. Every call is appended to `data/processed/audit/<server>.jsonl`
(user, tool, masked arguments, result summary, trace id).

## Our servers

| Tool | Server | Read / write | Annotations | Idempotency / dry run | Auth | Allowed agents |
|---|---|---|---|---|---|---|
| `search_jobs` | marketplace | read | readOnly, idempotent, openWorld | n/a | bearer | scout |
| `get_job` | marketplace | read | readOnly, idempotent, openWorld | n/a | bearer | scout, risk, pricing |
| `get_client_history` | marketplace | read | readOnly, idempotent, openWorld | n/a | bearer | scout, risk, pricing, liaison |
| `get_connects_balance` | marketplace | read | readOnly, idempotent, openWorld | n/a | bearer | scout, pricing, submitter |
| `list_messages` | marketplace | read | readOnly, idempotent, openWorld | n/a | bearer | liaison |
| `create_proposal_draft` | marketplace | write | not readOnly, not destructive, idempotent | `idempotency_key` (8–200 chars) required; `dry_run` defaults to true | bearer | submitter (after approval) |
| `submit_proposal` | marketplace | write, spends Connects | destructive, idempotent | key required; `dry_run` default true returns cost and balance after | bearer | submitter (after approval) |
| `send_message` | marketplace | write | destructive, idempotent | key required; `dry_run` default true | bearer | liaison (after approval) |
| `search_evidence` | portfolio | read | readOnly, idempotent, closed world | n/a | bearer | matcher, writer, critic |
| `get_case_study` | portfolio | read | readOnly, idempotent | n/a | bearer | matcher, writer, critic |
| `list_skills` | portfolio | read | readOnly, idempotent | n/a | bearer | matcher, writer, critic |
| `get_free_slots` | workspace | read | readOnly, idempotent | n/a | bearer | liaison |
| `create_tentative_hold` | workspace | write | not destructive, idempotent | key required | bearer | liaison (after approval) |
| `create_email_draft` | workspace | write (draft only) | not destructive, idempotent | key required | bearer | liaison (after approval) |

Portfolio resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://cv`.
Portfolio prompts: "Answer a screening question from my portfolio", "Which of my projects
prove this requirement?", "Draft an opening line for this job".

The workspace server is a documented local mock (`data/processed/workspace.json`); swapping in
Google Calendar and Gmail changes only `mcp_servers/workspace/server.py`.

## Third-party servers

| Server | Used for | Tools we call | Trust rationale |
|---|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1) | live mode behind the same port (`mcp_servers/marketplace/adapters/upwork_live.py`) | job search, job details, proposal draft, message draft | Run by the platform itself; OAuth scopes are granted by the user; every write is a draft the user confirms on Upwork, and GigBid adds its own approval before that. |
| GitHub official MCP (`https://api.githubcopilot.com/mcp/`) | repo ingestion for the portfolio (`rag/ingest/github.py`) | `get_file_contents` only | Maintained by GitHub; used with a fine-grained read-only token, and only a read tool is called, so the worst case is reading a repo the token can already see. |

## Running the servers for an external host

```bash
python -m mcp_servers.portfolio.server --stdio            # Claude Desktop / Cursor
python -m mcp_servers.marketplace.server                  # Streamable HTTP on :8101/mcp
npx @modelcontextprotocol/inspector                       # then connect to http://localhost:8101/mcp
```
Claude Desktop entry for the portfolio server:
```json
{"mcpServers": {"gigbid-portfolio": {"command": "python",
  "args": ["-m", "mcp_servers.portfolio.server", "--stdio"],
  "env": {"PORTFOLIO_PERSONA": "ai_ml"}}}}
```
