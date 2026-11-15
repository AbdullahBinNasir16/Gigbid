"""Job Analyst: untrusted job post -> JobSpec. No tools.

Default mode is rules (deterministic, free, fast); generation.analyst_mode=llm asks the
analyst model for requirements and screening questions, with the rules as fallback.
"""

from __future__ import annotations

import re
from typing import Any

from agent.config import get_config
from agent.handoffs import JobSpec, Requirement
from agent.nodes._common import call_llm, event, parse_json, timed, untrusted
from agent.nodes.risk_assessor import injection_spans
from agent.prompts import load_prompt
from agent.state import step
from rag.variants.base import decompose

_Q = re.compile(r"([^.?!\n]{8,200}\?)")


def rules_spec(job: dict[str, Any]) -> JobSpec:
    desc = job.get("description") or ""
    reqs = decompose(job)
    questions = [q.strip() for q in _Q.findall(desc)][:5]
    bt = job.get("budget_type") or "unknown"
    bmin, bmax = job.get("budget_min"), job.get("budget_max")
    if bmin is not None and bmax is not None and bmin > bmax:
        bmin, bmax = bmax, bmin
    return JobSpec(
        job_id=job["job_id"], title=(job.get("title") or "untitled")[:300],
        deliverables=[r[:300] for r in reqs if len(r) > 25][:8],
        required_skills=[str(s)[:80] for s in (job.get("skills") or [])][:40],
        budget_min=bmin, budget_max=bmax,
        budget_type=bt if bt in ("fixed", "hourly") else "unknown",
        category=job.get("category"), client_id=job.get("client_id"),
        requirements=[Requirement(text=r[:500], kind="skill" if len(r) < 40 else "deliverable")
                      for r in reqs[:30]],
        screening_questions=questions, is_vague=len(desc) < 150 and len(reqs) < 3,
        injection_suspected=bool(injection_spans(desc)),
    )


def analyst(state: dict) -> dict:
    job = state["job"]
    tokens = 0
    with timed() as t:
        spec = rules_spec(job)
        if get_config().generation.get("analyst_mode") == "llm":
            try:
                text, tokens = call_llm("analyst", load_prompt("analyst"),
                                        untrusted("job", f"{job['title']}\n{job['description']}"))
                data = parse_json(text) or {}
                reqs = [str(r)[:500] for r in data.get("requirements", []) if str(r).strip()]
                if reqs:
                    qs = [str(q)[:300] for q in data.get("screening_questions", [])][:10]
                    spec = spec.model_copy(update={
                        "requirements": [Requirement(text=r) for r in reqs[:30]],
                        "screening_questions": qs or spec.screening_questions})
            except Exception:  # noqa: BLE001 - the rules spec stays as the fallback
                pass
    return {"analyses": {"job_spec": spec}, "counters": step(tokens),
            "trace": [event(state, "analyst", tokens=tokens, duration_ms=t["ms"],
                            result_summary=f"{len(spec.requirements)} requirements")]}
