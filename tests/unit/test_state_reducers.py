"""Reducers must merge parallel writes from Analyst, Risk and Matcher without loss."""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.handoffs import Evidence, FitReport, JobSpec, RiskReport
from agent.state import (
    BidState,
    Counters,
    Status,
    TraceEvent,
    add_counters,
    merge_analyses,
    merge_evidence,
    step,
)


def _ev(i: str, score: float) -> Evidence:
    return Evidence(id=i, type="case_study", source="s", text="t", score=score)


def test_add_counters_sums() -> None:
    total = add_counters(step(10), step(5, critic_loop=True))
    assert total == Counters(steps=2, tokens=15, critic_loops=1)
    assert add_counters(None, None) == Counters()


def test_merge_evidence_dedupes_and_keeps_best_score() -> None:
    merged = merge_evidence([_ev("a", 0.2), _ev("b", 0.5)], [_ev("a", 0.9)])
    assert [e.id for e in merged] == ["a", "b"]
    assert merged[0].score == 0.9


def test_merge_analyses_keeps_each_branch() -> None:
    spec = JobSpec(job_id="j", title="t")
    risk = RiskReport(score=0.1, explanation="ok")
    assert set(merge_analyses({"job_spec": spec}, {"risk": risk})) == {"job_spec", "risk"}


def _graph():  # type: ignore[no-untyped-def]
    def fan_out(state: BidState) -> list[Send]:
        return [Send(n, state) for n in ("analyst", "risk", "matcher")]

    def analyst(state: BidState) -> dict:
        return {
            "analyses": {"job_spec": JobSpec(job_id="j", title="t")},
            "counters": step(100),
            "trace": [TraceEvent(trace_id="tr", node="analyst", kind="node_end")],
        }

    def risk(state: BidState) -> dict:
        return {
            "analyses": {"risk": RiskReport(score=0.2, explanation="fine")},
            "counters": step(50),
            "trace": [TraceEvent(trace_id="tr", node="risk", kind="node_end")],
        }

    def matcher(state: BidState) -> dict:
        return {
            "analyses": {"fit": FitReport(score=0.8, evidence_ids=["a"])},
            "evidence": [_ev("a", 0.7), _ev("b", 0.4)],
            "counters": step(70),
            "trace": [TraceEvent(trace_id="tr", node="matcher", kind="node_end")],
        }

    def decide(state: BidState) -> dict:
        return {"status": Status.done, "counters": step()}

    g = StateGraph(BidState)
    for name, fn in (("analyst", analyst), ("risk", risk), ("matcher", matcher), ("decide", decide)):
        g.add_node(name, fn)
    g.add_conditional_edges(START, fan_out, ["analyst", "risk", "matcher"])
    for n in ("analyst", "risk", "matcher"):
        g.add_edge(n, "decide")
    g.add_edge("decide", END)
    return g.compile()


def test_parallel_branches_merge_through_reducers() -> None:
    out = _graph().invoke({"thread_id": "t", "job": {"job_id": "j"}})
    assert set(out["analyses"]) == {"job_spec", "risk", "fit"}
    assert out["counters"] == Counters(steps=4, tokens=220)
    assert {e.node for e in out["trace"]} == {"analyst", "risk", "matcher"}
    assert [e.id for e in out["evidence"]] == ["a", "b"]
    assert out["status"] == Status.done
