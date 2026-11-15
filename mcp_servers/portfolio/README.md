# GigBid Portfolio MCP server

A read-only MCP server that lets any MCP host (Claude Desktop, Cursor, MCP Inspector) answer
"what have I actually done?" from a freelancer's portfolio: CV, case studies, repos and code,
client reviews and past proposals with outcomes. Built with the official MCP Python SDK.

## Tools

| Tool | What it returns |
|---|---|
| `search_evidence(requirement, k=5, filters?)` | evidence items (type, source, date, project, outcome) for one requirement, ranked by the retrieval design chosen in `agent/config.yaml` (outcome-aware by default) |
| `get_case_study(id)` | the full case study (by `case:<persona>:<slug>` or slug) |
| `list_skills()` | profile skills and which projects evidence each one |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://cv`.
Prompts: "Answer a screening question from my portfolio", "Which of my projects prove this
requirement?", "Draft an opening line for this job".

## Install and run

From a clone of the repo:
```bash
pip install -e .
python -m mcp_servers.portfolio.server --stdio          # stdio, for desktop hosts
python -m mcp_servers.portfolio.server                  # Streamable HTTP on :8102/mcp
```
With uv, without installing anything globally (set `PORTFOLIO_DIR` to your portfolio folder;
the example personas live only in the repo):
```bash
uvx --from git+https://github.com/AbdullahBinNasir16/Gigbid gigbid-portfolio-mcp --stdio
```
With Docker:
```bash
docker build -f infra/docker/Dockerfile.mcp_portfolio -t gigbid-portfolio-mcp .
docker run -p 8102:8102 -e PORTFOLIO_PERSONA=ai_ml gigbid-portfolio-mcp
```

Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"gigbid-portfolio": {"command": "uvx",
  "args": ["--from", "git+https://github.com/AbdullahBinNasir16/Gigbid", "gigbid-portfolio-mcp", "--stdio"],
  "env": {"PORTFOLIO_PERSONA": "ai_ml"}}}}
```

## Use your own portfolio

Point `PORTFOLIO_DIR` at a folder with the same layout as `data/personas/ai_ml/`:
`profile.json`, `cv.md`, `case_studies/*.md` (YAML front matter: id, project, title, skills,
date, client_industry), optional `repos/<name>/README.md` and code, `reviews.json`, and
`proposals.jsonl` (with `outcome`: won, replied or ignored).

## Security

Read-only (every tool is annotated `readOnlyHint`). Over HTTP it requires
`Authorization: Bearer $MCP_PORTFOLIO_BEARER_TOKEN`; every call is appended to an audit log
with PII masked.
