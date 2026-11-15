"""Repo ingestion through the official GitHub MCP server (third-party, read-only use).

Run: GITHUB_TOKEN=... python -m rag.ingest.github <owner/repo> [persona]
Writes data/personas/<persona>/repos/<repo>/README.md and up to MAX_CODE_FILES source files,
then drops the cached index so the next search re-embeds (incremental re-index).

Server: https://api.githubcopilot.com/mcp/ (GitHub's hosted MCP server) over Streamable
HTTP with a fine-grained, read-only token. Only `get_file_contents` is called.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITHUB_MCP_URL = os.environ.get("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".sql", ".ipynb")
MAX_CODE_FILES = 5


async def _get(session, owner: str, repo: str, path: str) -> object:  # type: ignore[no-untyped-def]
    res = await session.call_tool("get_file_contents", {"owner": owner, "repo": repo,
                                                        "path": path})
    if res.isError:
        return None
    return res.structuredContent or "".join(getattr(c, "text", "") for c in res.content)


async def ingest(full_name: str, persona: str) -> list[str]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    owner, repo = full_name.split("/", 1)
    client = MultiServerMCPClient({"github": {
        "transport": "streamable_http", "url": GITHUB_MCP_URL,
        "headers": {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}}})
    out_dir = ROOT / "data/personas" / persona / "repos" / repo
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    async with client.session("github") as s:
        readme = await _get(s, owner, repo, "README.md")
        if isinstance(readme, str) and readme:
            (out_dir / "README.md").write_text(readme, encoding="utf-8")
            written.append("README.md")
        listing = await _get(s, owner, repo, "")
        entries = listing if isinstance(listing, list) else []
        for e in [e for e in entries if str(e.get("name", "")).endswith(CODE_SUFFIXES)][:MAX_CODE_FILES]:
            body = await _get(s, owner, repo, e["path"])
            if isinstance(body, str) and body:
                (out_dir / e["name"]).write_text(body[:20000], encoding="utf-8")
                written.append(e["name"])
    from rag.index.store import reset_index

    reset_index(persona)
    return written


if __name__ == "__main__":
    print(asyncio.run(ingest(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "ai_ml")))
