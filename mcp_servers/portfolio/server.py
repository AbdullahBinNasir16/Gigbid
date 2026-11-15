"""Portfolio MCP server (read-only): evidence search, case studies, skills.

Usable on its own from Claude Desktop or Cursor:
    {"command": "python", "args": ["-m", "mcp_servers.portfolio.server", "--stdio"],
     "env": {"PORTFOLIO_PERSONA": "ai_ml"}}
Point PORTFOLIO_DIR at your own folder (same layout as data/personas/<persona>) to use
your own portfolio.

Run (HTTP): python -m mcp_servers.portfolio.server   (port MCP_PORTFOLIO_PORT, 8102)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.handoffs import Evidence
from mcp_servers.common import audit, serve_http

SERVER = "portfolio"
ROOT = Path(__file__).resolve().parents[2]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                       openWorldHint=False)

mcp = FastMCP("gigbid-portfolio", instructions=(
    "Read-only access to a freelancer's portfolio: CV, case studies, repos, reviews and past "
    "proposals with outcomes. Use search_evidence to find proof for a job requirement; only "
    "claim what the returned evidence says."))


def persona() -> str:
    return os.environ.get("PORTFOLIO_PERSONA", "ai_ml")


def base_dir(p: str | None = None) -> Path:
    custom = os.environ.get("PORTFOLIO_DIR")
    return Path(custom) if custom else ROOT / "data" / "personas" / (p or persona())


class EvidenceFilters(BaseModel):
    types: list[Literal["cv", "case_study", "repo", "code", "review", "proposal"]] | None = None
    project: str | None = None
    outcome: Literal["won", "replied", "ignored"] | None = None
    since: str | None = Field(default=None, description="ISO date; keep items on or after it")


class EvidenceResult(BaseModel):
    persona: str
    variant: str
    items: list[Evidence]
    refused: bool = Field(default=False, description="True when no evidence passed the grade")


class CaseStudy(BaseModel):
    id: str
    project: str
    title: str
    skills: list[str]
    date: str | None
    client_industry: str | None
    text: str


class SkillList(BaseModel):
    persona: str
    skills: list[str]
    evidenced_by_projects: dict[str, list[str]]


@mcp.tool(annotations=READ)
async def search_evidence(
    requirement: Annotated[str, Field(min_length=2, max_length=2000,
                                      description="One job requirement or the job text")],
    k: Annotated[int, Field(ge=1, le=20)] = 5,
    filters: EvidenceFilters | None = None,
    persona_id: str | None = None,
    trace_id: str | None = None,
) -> EvidenceResult:
    """Find portfolio evidence for a requirement. Returns items with type, source, date,
    project and (for past proposals) outcome. Uses the retrieval design chosen in config."""
    import anyio

    from rag.retriever import get_retriever

    p = persona_id or persona()
    r = await anyio.to_thread.run_sync(get_retriever, p)
    items = await anyio.to_thread.run_sync(r.retrieve, requirement, k * 3 if filters else k)
    if filters:
        if filters.types:
            items = [e for e in items if e.type.value in filters.types]
        if filters.project:
            items = [e for e in items if e.project == filters.project]
        if filters.outcome:
            items = [e for e in items if e.outcome and e.outcome.value == filters.outcome]
        if filters.since:
            items = [e for e in items if e.date and e.date >= filters.since]
    out = EvidenceResult(persona=p, variant=r.name, items=items[:k],
                         refused=not items and r.flags.corrective)
    audit(SERVER, p, "search_evidence", {"requirement": requirement, "k": k,
                                         "trace_id": trace_id}, {"n": len(out.items)}, trace_id)
    return out


def _case(slug: str, p: str | None = None) -> CaseStudy:
    import yaml

    slug = slug.split(":")[-1].split("#")[0]
    path = base_dir(p) / "case_studies" / f"{slug}.md"
    if not path.exists():
        raise ValueError(f"unknown case study '{slug}'")
    _, fm, body = path.read_text(encoding="utf-8").split("---", 2)
    meta = yaml.safe_load(fm)
    return CaseStudy(id=meta["id"], project=meta["project"], title=meta["title"],
                     skills=meta.get("skills", []), date=str(meta.get("date")),
                     client_industry=meta.get("client_industry"), text=body.strip())


@mcp.tool(annotations=READ)
def get_case_study(id: Annotated[str, Field(min_length=1, max_length=200)],
                   persona_id: str | None = None) -> CaseStudy:
    """Full case study by id (e.g. 'case:ai_ml:support-rag-bot') or project slug."""
    return _case(id, persona_id)


@mcp.tool(annotations=READ)
def list_skills(persona_id: str | None = None) -> SkillList:
    """Skills in the profile, and which projects give evidence for each skill."""
    p = persona_id or persona()
    profile = json.loads((base_dir(p) / "profile.json").read_text(encoding="utf-8"))
    by_skill: dict[str, list[str]] = {}
    for path in sorted((base_dir(p) / "case_studies").glob("*.md")):
        c = _case(path.stem, p)
        for s in c.skills:
            by_skill.setdefault(s, []).append(c.project)
    skills = sorted(set(profile.get("core_skills", [])) | set(by_skill))
    return SkillList(persona=p, skills=skills, evidenced_by_projects=by_skill)


# --------------------------------------------------------------- resources
@mcp.resource("portfolio://case/{id}", mime_type="text/markdown")
def case_resource(id: str) -> str:
    """A full case study as Markdown."""
    c = _case(id)
    return f"# {c.title}\n\nSkills: {', '.join(c.skills)}\n\n{c.text}"


@mcp.resource("portfolio://proposal/{id}", mime_type="application/json")
def proposal_resource(id: str) -> str:
    """A past proposal with its outcome."""
    for line in (base_dir() / "proposals.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["id"] == id or r["id"].endswith(f":{id}"):
            return json.dumps(r, indent=2)
    raise ValueError(f"unknown proposal '{id}'")


@mcp.resource("portfolio://cv", mime_type="text/markdown")
def cv_resource() -> str:
    """The CV."""
    return (base_dir() / "cv.md").read_text(encoding="utf-8")


# ----------------------------------------------------------------- prompts
@mcp.prompt(title="Answer a screening question from my portfolio")
def answer_screening_question(question: str) -> str:
    return (f"Answer this client screening question in 2-4 sentences: \"{question}\"\n"
            "First call search_evidence with the question. Use only facts in the returned "
            "evidence and name the project each fact comes from. If nothing relevant comes "
            "back, say plainly that you have not done this before and what is closest.")


@mcp.prompt(title="Which of my projects prove this requirement?")
def prove_requirement(requirement: str) -> str:
    return (f"Call search_evidence for: \"{requirement}\". List the matching projects with one "
            "line each on what they prove, and say how strong the match is (direct, partial, "
            "none). Do not stretch weak matches.")


@mcp.prompt(title="Draft an opening line for this job")
def opening_line(job_summary: str) -> str:
    return (f"Job: {job_summary}\nWrite one opening sentence that mirrors the client's problem "
            "and cites one concrete past result from search_evidence. No greetings like 'Dear "
            "Sir', no 'I am passionate', no guarantees.")


def main() -> None:
    """Console entry point (`gigbid-portfolio-mcp [--stdio]`)."""
    if "--stdio" in sys.argv:
        mcp.run("stdio")
    else:
        serve_http(mcp, "MCP_PORTFOLIO_BEARER_TOKEN", int(os.environ.get("MCP_PORTFOLIO_PORT",
                                                                          "8102")))


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run("stdio")
    else:
        serve_http(mcp, "MCP_PORTFOLIO_BEARER_TOKEN", int(os.environ.get("MCP_PORTFOLIO_PORT",
                                                                          "8102")))
