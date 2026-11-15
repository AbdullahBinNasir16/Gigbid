"""Fit Matcher: map every requirement to portfolio evidence and score fit, with reasons.

Uses only the Portfolio MCP tools (search_evidence, list_skills). Fit combines:
* skill coverage: share of the job's listed skills the portfolio evidences;
* evidence strength: cross-encoder grade of the best evidence against the job;
* category match: the job is in one of the persona's categories.
Weights live in config.generation.fit_weights.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent.config import get_config
from agent.handoffs import Evidence, FitReport, RequirementMatch
from agent.mcp_client import ToolBox
from agent.nodes._common import event, timed, tool_events
from agent.state import step
from rag.index.store import tokenize
from rag.variants.base import decompose, job_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = {"skills": 0.4, "evidence": 0.4, "category": 0.2}


@lru_cache(maxsize=8)
def persona_profile(persona: str) -> dict[str, Any]:
    path = ROOT / "data" / "personas" / persona / "profile.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _norm(s: str) -> str:
    return " ".join(tokenize(s))


def match_requirements(reqs: list[str], evidence: list[Evidence]) -> list[RequirementMatch]:
    out = []
    for r in reqs[:30]:
        rt = set(tokenize(r))
        scored = []
        for e in evidence:
            et = set(tokenize(e.text + " " + " ".join(e.skills)))
            ov = len(rt & et) / max(1, len(rt))
            if ov > 0:
                scored.append((ov, e.id))
        scored.sort(reverse=True)
        out.append(RequirementMatch(requirement=r[:500],
                                    evidence_ids=[i for _, i in scored[:3]],
                                    strength=round(scored[0][0], 3) if scored else 0.0))
    return out


def score_fit(job: dict[str, Any], evidence: list[Evidence], skills: list[str],
              persona: str) -> FitReport:
    weights = get_config().generation.get("fit_weights") or DEFAULT_WEIGHTS
    have = {_norm(s) for s in skills}
    ev_text = " " + _norm(" ".join(e.text + " " + " ".join(e.skills) for e in evidence)) + " "
    job_skills = [s for s in (job.get("skills") or []) if s]
    matched = [s for s in job_skills if _norm(s) in have or f" {_norm(s)} " in ev_text]
    missing = [s for s in job_skills if s not in matched]
    if job_skills:
        coverage = len(matched) / len(job_skills)
    else:  # no listed skills: use how many persona skills the post mentions
        jt = " " + _norm(job_text(job)) + " "
        coverage = min(1.0, sum(f" {h} " in jt for h in have if len(h) > 2) / 4)
    strength = 0.0
    if evidence:
        from rag.verify import _scores

        grades = _scores([(job_text(job)[:1500], e.text[:1500]) for e in evidence[:6]])
        strength = max(grades) if grades else 0.0
    cats = persona_profile(persona).get("categories", [])
    category = 1.0 if job.get("category") in cats else 0.0
    score = (weights["skills"] * coverage + weights["evidence"] * strength
             + weights["category"] * category)
    reqs = decompose(job)
    return FitReport(score=round(min(1.0, score), 3), matched_skills=matched[:40],
                     missing_skills=missing[:40], evidence_ids=[e.id for e in evidence],
                     requirement_matches=match_requirements(reqs, evidence))


async def fit_matcher(state: dict) -> dict:
    job, persona = state["job"], state.get("persona", "ai_ml")
    tb = ToolBox("matcher", trace_id=state.get("trace_id"))
    k = int(get_config().generation.get("evidence_k", 6))
    with timed() as t:
        res = await tb.call("search_evidence", requirement=job_text(job)[:2000], k=k,
                            persona_id=persona)
        evidence = [Evidence.model_validate(e) for e in res["items"]]
        skills = (await tb.call("list_skills", persona_id=persona))["skills"]
        import asyncio

        report = await asyncio.to_thread(score_fit, job, evidence, skills, persona)
    return {"analyses": {"fit": report}, "evidence": evidence, "counters": step(),
            "trace": [*tool_events(state, "matcher", tb.calls),
                      event(state, "matcher", duration_ms=t["ms"],
                            result_summary=f"fit={report.score} evidence={len(evidence)}")]}
