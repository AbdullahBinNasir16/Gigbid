"""V8: corrective RAG loop as a small LangGraph StateGraph.

retrieve -> grade -> (good: done | weak: rewrite query and retrieve again | still weak after
max requeries: refuse). Grading always uses the cross-encoder probability, so the threshold
(retrieval.min_evidence_score) means the same thing whatever the base pipeline is.
Refusing returns no evidence, which makes the writer say nothing rather than invent a claim,
and pushes the bid decision towards skip.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from rag.variants.base import Flags, Pipeline, decompose, job_text


class CragState(TypedDict, total=False):
    job: Any
    query: Any
    k: int
    attempt: int
    ranked: list[tuple[str, float]]
    graded: list[tuple[str, float]]
    refused: bool


def _build(pipeline: Pipeline):
    def retrieve(state: CragState) -> CragState:
        return {"ranked": pipeline.rank(state["query"], max(state["k"] * 2, 10))}

    def grade(state: CragState) -> CragState:
        ids = [cid for cid, _ in state["ranked"]]
        graded = pipeline.index.rerank(job_text(state["job"]), ids)
        keep = [(cid, s) for cid, s in graded if s >= pipeline.min_score]
        return {"graded": keep}

    def route(state: CragState) -> str:
        if len(state["graded"]) >= min(2, state["k"]):
            return "done"
        if state.get("attempt", 0) >= pipeline.max_requeries:
            return "refuse"
        return "rewrite"

    def rewrite(state: CragState) -> CragState:
        attempt = state.get("attempt", 0) + 1
        job = state["job"]
        reqs = decompose(job)
        # attempt 1: requirements only (drops boilerplate); attempt 2: skills only
        if attempt == 1:
            query = " ".join(reqs)
        else:
            skills = job.get("skills") if isinstance(job, dict) else None
            query = ", ".join(skills) if skills else reqs[0]
        return {"query": query, "attempt": attempt}

    def refuse(state: CragState) -> CragState:
        return {"graded": [], "refused": True}

    g = StateGraph(CragState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("rewrite", rewrite)
    g.add_node("refuse", refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, {"done": END, "rewrite": "rewrite",
                                             "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("refuse", END)
    return g.compile()


def corrective_rank(pipeline: Pipeline, job: Any, k: int) -> list[tuple[str, float]]:
    base = Pipeline(pipeline.index, Flags(**{**pipeline.flags.__dict__, "corrective": False}))
    graph = _build(base)
    out = graph.invoke({"job": job, "query": job, "k": k, "attempt": 0})
    graded = out.get("graded", [])
    if base.flags.multivector:
        graded = base._group(graded)
    return graded[:k]


class V8Corrective(Pipeline):
    name = "v8_corrective"
    flags = Flags(corrective=True)
