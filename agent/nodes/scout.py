"""Scout: run saved searches, deduplicate, queue new jobs (Marketplace read via MCP).

Dedup uses a normalised title+description fingerprint, so reposts ("URGENT: ...",
"(Updated) ...") and near duplicates map to the first job seen.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from agent.mcp_client import ToolBox

_PREFIX = re.compile(r"^\s*(urgent|reposting|updated|\(updated\)|re-?post)\s*[:!-]*\s*", re.I)


def fingerprint(job: dict[str, Any]) -> str:
    title = _PREFIX.sub("", job.get("title", "")).lower()
    title = re.sub(r"\W+", " ", title).strip()
    desc = re.sub(r"\W+", " ", (job.get("description") or "").lower())[:300]
    return hashlib.sha1(f"{title}|{desc}".encode()).hexdigest()[:16]


def dedupe(jobs: list[dict[str, Any]], seen: dict[str, str]) -> list[dict[str, Any]]:
    """Return jobs with `duplicate_of` set for repeats; `seen` maps fingerprint -> job_id."""
    out = []
    for j in jobs:
        fp = fingerprint(j)
        dup = seen.get(fp)
        if dup is None:
            seen[fp] = j["job_id"]
        out.append(j | {"duplicate_of": dup if dup and dup != j["job_id"] else None})
    return out


async def scout(saved_searches: list[str], seen: dict[str, str], *, limit: int = 20,
                trace_id: str | None = None) -> tuple[list[dict[str, Any]], list[dict]]:
    tb = ToolBox("scout", trace_id=trace_id)
    found: dict[str, dict[str, Any]] = {}
    for q in saved_searches or [""]:
        res = await tb.call("search_jobs", query=q, limit=limit)
        for j in res["items"]:
            found.setdefault(j["job_id"], j)
    jobs = dedupe(list(found.values()), seen)
    return [j for j in jobs if not j["duplicate_of"]], tb.calls
