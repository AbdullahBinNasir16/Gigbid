"""Shared retrieval pipeline. Each variant file sets a few flags on it.

Why flags: V1 (decomposition), V2 (hybrid), V3 (rerank), V4 (outcome), V5 (multi-vector
grouping) and V8 (corrective loop) are independent components, so the shipped design is a
composition and the ablation turns one off at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from agent.config import get_config
from agent.handoffs import Evidence, EvidenceType, Outcome
from rag.index.store import PortfolioIndex

RRF_K = 60


@dataclass(frozen=True)
class Flags:
    decompose: bool = False
    hybrid: bool = False
    rerank: bool = False
    outcome: bool = False
    multivector: bool = False
    corrective: bool = False

    def __or__(self, other: Flags) -> Flags:
        return Flags(**{k: getattr(self, k) or getattr(other, k)
                        for k in self.__dataclass_fields__})


def job_text(job: dict[str, Any] | str) -> str:
    if isinstance(job, str):
        return job
    skills = ", ".join(job.get("skills") or [])
    return f"{job.get('title', '')}. {job.get('description', '')} Skills: {skills}"


_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|;\s*|•")
_NEED = re.compile(r"\b(need|build|create|develop|implement|experience|looking for|must|should|"
                   r"require|integrat|design|set up|automate|analy[sz]e|dashboard|model)\w*",
                   re.IGNORECASE)


def decompose(job: dict[str, Any] | str, max_reqs: int = 8) -> list[str]:
    """Rule-based requirement extraction: listed skills plus need-bearing sentences.

    Deterministic and free; the Job Analyst's LLM requirements replace it when present.
    """
    if isinstance(job, dict) and job.get("requirements"):
        return [str(r) for r in job["requirements"]][:max_reqs]
    reqs: list[str] = []
    if isinstance(job, dict):
        reqs.extend(job.get("skills") or [])
    text = job if isinstance(job, str) else job.get("description", "")
    for sent in _SPLIT.split(text):
        sent = sent.strip()
        if 15 < len(sent) < 300 and _NEED.search(sent):
            reqs.append(sent)
    seen, out = set(), []
    for r in reqs:
        if r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out[:max_reqs] or [job_text(job)[:500]]


def rrf(*rankings: list[tuple[str, float]], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (cid, _) in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


OUTCOME_WEIGHT = {"won": 1.0, "replied": 0.6, "ignored": -0.5}


class Pipeline:
    name = "custom"
    flags = Flags()

    def __init__(self, index: PortfolioIndex, flags: Flags | None = None) -> None:
        self.index = index
        self.flags = flags or self.flags
        cfg = get_config().retrieval
        self.outcome_weight = cfg.outcome_boost_weight
        self.min_score = cfg.min_evidence_score
        self.max_requeries = cfg.corrective_max_requeries
        self._project_outcomes = self._outcomes_by_project()

    def _outcomes_by_project(self) -> dict[str, float]:
        acc: dict[str, list[float]] = {}
        for c in self.index.chunks:
            if c.type == "proposal" and c.project and c.outcome:
                acc.setdefault(c.project, []).append(OUTCOME_WEIGHT[c.outcome])
        return {p: sum(v) / len(v) for p, v in acc.items()}

    # ----------------------------------------------------------- one query
    def _search(self, query: str, depth: int) -> list[tuple[str, float]]:
        dense = self.index.dense(query, depth)
        if not self.flags.hybrid:
            return dense
        return rrf(dense, self.index.sparse(query, depth))

    def _candidates(self, job: dict[str, Any] | str, depth: int) -> list[tuple[str, float]]:
        if not self.flags.decompose:
            return self._search(job_text(job), depth)
        rankings = [self._search(req, depth) for req in decompose(job)]
        # the whole post too, so global context is not lost
        rankings.append(self._search(job_text(job), depth))
        return rrf(*rankings)

    def _apply_outcome(self, ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
        out = []
        for cid, score in ranked:
            c = self.index.by_id[cid]
            boost = 0.0
            if c.type == "proposal" and c.outcome:
                boost = OUTCOME_WEIGHT[c.outcome]
            elif c.project in self._project_outcomes:
                boost = self._project_outcomes[c.project]
            out.append((cid, score * (1 + self.outcome_weight * boost)))
        return sorted(out, key=lambda x: -x[1])

    def _group(self, ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """Multi-vector: keep the best chunk per project, so one project fills one slot."""
        seen: set[str] = set()
        out = []
        for cid, score in ranked:
            proj = self.index.by_id[cid].project or cid
            if proj not in seen:
                seen.add(proj)
                out.append((cid, score))
        return out

    def rank(self, job: dict[str, Any] | str, k: int = 10) -> list[tuple[str, float]]:
        depth = max(30, k * 3)
        ranked = self._candidates(job, depth)
        if self.flags.rerank:
            ranked = self.index.rerank(job_text(job), [cid for cid, _ in ranked])
        if self.flags.outcome:
            ranked = self._apply_outcome(ranked)
        if self.flags.multivector:
            ranked = self._group(ranked)
        return ranked[:k]

    def retrieve(self, job: dict[str, Any] | str, k: int = 5) -> list[Evidence]:
        if self.flags.corrective:
            from rag.variants.v8_corrective import corrective_rank

            ranked = corrective_rank(self, job, k)
        else:
            ranked = self.rank(job, k)
        return [to_evidence(self.index, cid, score) for cid, score in ranked]


def to_evidence(index: PortfolioIndex, cid: str, score: float) -> Evidence:
    c = index.by_id[cid]
    return Evidence(
        id=c.id, type=EvidenceType(c.type), source=c.source, text=c.text[:4000],
        score=float(score), project=c.project, date=c.date,
        outcome=Outcome(c.outcome) if c.outcome else None, skills=c.skills[:50],
    )


def with_flags(p: Pipeline, **changes: bool) -> Pipeline:
    return Pipeline(p.index, replace(p.flags, **changes))
