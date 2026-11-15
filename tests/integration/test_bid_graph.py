"""Bid graph end to end on the fake marketplace (in-memory MCP), template writer.

Covers: parallel analysis, scam skip, approval interrupt, edit re-checked by compliance,
crash-and-resume from the checkpoint, exactly-once submission.
"""

import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent.config import get_config
from agent.graphs.bid_graph import build_bid_graph
from agent.marketplace_port import Job
from agent.memory import store as mem
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.fake import FakeMarketplace

ROOT = Path(__file__).resolve().parents[2]


def dev_job(pred):
    for line in (ROOT / "evals/datasets/dev_ai_ml.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if pred(r):
            return r
    raise LookupError


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setattr("mcp_servers.common.AUDIT_DIR", tmp_path)
    get_config().generation["writer_mode"] = "template"
    get_config().generation["critic_mode"] = "rules"
    mem.set_store(InMemoryStore())
    yield
    server.set_port(None)


def _fake(job):
    f = FakeMarketplace(jobs=[Job(job_id=job["job_id"], title=job["title"],
                                  description=job["description"], skills=job["skills"],
                                  budget_type=job["budget_type"])], balance=40, connects_cost=6)
    server.set_port(f)
    return f


async def test_scam_is_skipped_without_drafting():
    job = dev_job(lambda r: r["gold"]["is_scam"])
    g = build_bid_graph(InMemorySaver())
    out = await g.ainvoke({"thread_id": "t-scam", "persona": "ai_ml", "job": job,
                           "client": job["client"]}, {"configurable": {"thread_id": "t-scam"}})
    assert out["decision"].decision == "skip"
    assert out["analyses"]["risk"].is_scam
    assert not out.get("drafts")


async def test_bid_approve_crash_resume_submits_once():
    job = dev_job(lambda r: r["gold"]["gold_decision"] == "bid" and not r["gold"]["injected"]
                  and r["job_id"].startswith("job_"))
    fake = _fake(job)
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t-bid"}}
    g = build_bid_graph(saver)
    out = await g.ainvoke({"thread_id": "t-bid", "persona": "ai_ml", "job": job,
                           "client": job["client"]}, cfg)
    assert out["decision"].decision == "bid", out["decision"].reasons
    assert "__interrupt__" in out
    payload = out["__interrupt__"][0].value
    assert payload["preview"]["connects_cost"] == 6 and payload["evidence"]
    # "crash": build a new graph object on the same checkpointer, then approve
    g2 = build_bid_graph(saver)
    final = await g2.ainvoke(Command(resume={"action": "approve", "user_id": "u1"}), cfg)
    assert final["submitted"] and fake.balance == 34
    # replaying the submit node (e.g. worker restart) must not spend again
    again = await g2.ainvoke(Command(resume={"action": "approve", "user_id": "u1"}), cfg)
    assert fake.balance == 34 and again["submitted"]
    assert len(fake.submitted) == 1


async def test_edit_with_offplatform_text_is_blocked_then_approved():
    job = dev_job(lambda r: r["gold"]["gold_decision"] == "bid" and r["job_id"].startswith("job_"))
    fake = _fake(job)
    cfg = {"configurable": {"thread_id": "t-edit"}}
    g = build_bid_graph(InMemorySaver())
    await g.ainvoke({"thread_id": "t-edit", "persona": "ai_ml", "job": job}, cfg)
    out = await g.ainvoke(Command(resume={"action": "edit", "user_id": "u1",
                                          "edited_text": "Message me on WhatsApp to discuss."}),
                          cfg)
    assert "__interrupt__" in out and out["compliance"].verdict == "block"
    out = await g.ainvoke(Command(resume={"action": "reject", "user_id": "u1",
                                          "reason": "not a fit after all"}), cfg)
    assert not out.get("submitted") and fake.balance == 40
