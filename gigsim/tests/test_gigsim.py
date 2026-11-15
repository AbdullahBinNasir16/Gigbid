"""GigSim endpoint, idempotency, rate limit, 5xx, policy and determinism tests."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gigsim.app import create_app
from gigsim.decisions import HiddenPrefs, rule_decide, seeded_rng
from gigsim.settings import load_config
from gigsim.world import World

TOKEN = {"Authorization": "Bearer dev-gigsim-token"}
ADMIN = {"Authorization": "Bearer dev-gigsim-admin"}

JOBS = [
    {"job_id": f"j{i}", "title": title, "description": desc, "skills": skills,
     "category": cat, "budget_type": "fixed", "budget_min": 800.0, "budget_max": 1200.0,
     "applicants": "5 to 10", "provenance": "real", "source_dataset": "test"}
    for i, (title, desc, skills, cat) in enumerate([
        ("RAG chatbot over PDFs", "Need LangChain and Qdrant experience.", ["LangChain", "Python", "Qdrant"], "ai_ml"),
        ("Power BI sales dashboard", "Build a dashboard from Excel data.", ["Power BI", "Excel", "SQL"], "data_analytics"),
        ("Next.js marketing site", "Landing page with a CMS.", ["Next.js", "React", "TypeScript"], "web_dev"),
    ])
]
PRIORS: dict[str, Any] = {"applicant_midpoints": {"5 to 10": 7.5}}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIGSIM_API_TOKEN", raising=False)
    monkeypatch.delenv("GIGSIM_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("GIGSIM_STATE_FILE", raising=False)


def make(overrides: dict[str, Any] | None = None, state_file: Path | None = None) -> tuple[TestClient, World]:
    cfg = load_config()
    for k, v in (overrides or {}).items():
        cfg[k] = {**cfg[k], **v}
    world = World(copy.deepcopy(cfg), jobs=copy.deepcopy(JOBS), priors=PRIORS, state_file=state_file)
    return TestClient(create_app(world.cfg, world)), world


def headers(key: str | None = None, user: str = "alice") -> dict[str, str]:
    h = {**TOKEN, "X-GigSim-User": user}
    if key:
        h["Idempotency-Key"] = key
    return h


def draft(client: TestClient, job_id: str = "j0", letter: str = "Hello", key: str = "draft-key-1",
          amount: float = 900, user: str = "alice") -> dict[str, Any]:
    r = client.post("/proposals", headers=headers(key, user),
                    json={"job_id": job_id, "cover_letter": letter, "amount": amount, "budget_type": "fixed"})
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_auth() -> None:
    client, _ = make()
    assert client.get("/health").status_code == 200
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_search_get_job_and_client_history_hide_preferences() -> None:
    client, _ = make()
    page = client.get("/jobs", params={"q": "dashboard"}, headers=headers()).json()
    assert page["total"] == 1 and page["items"][0]["job_id"] == "j1"
    job = client.get("/jobs/j0", headers=headers()).json()
    assert job["connects_cost"] == 6  # 1200 budget -> 500+ tier
    hist = client.get(f"/clients/{job['client_id']}", headers=headers()).json()
    forbidden = {"must_have_skills", "budget_ceiling", "dislikes_generic", "is_scam", "hidden"}
    assert not forbidden & set(hist)
    assert not forbidden & set(job)
    assert client.get("/jobs/nope", headers=headers()).status_code == 404


def test_submit_twice_same_key_spends_once() -> None:
    client, world = make()
    p = draft(client)
    before = client.get("/connects", headers=headers()).json()["balance"]
    r1 = client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1"))
    r2 = client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1"))
    assert r1.status_code == r2.status_code == 200
    assert r2.headers.get("Idempotent-Replayed") == "true"
    assert r1.json() == r2.json()
    after = client.get("/connects", headers=headers()).json()["balance"]
    assert before - after == r1.json()["connects_spent"] == 6
    assert sum(1 for x in world.proposals.values() if x.submitted_at) == 1


def test_new_key_cannot_double_submit_same_job() -> None:
    client, _ = make()
    p = draft(client)
    client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1"))
    r = client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-2"))
    assert r.status_code == 409
    p2 = draft(client, key="draft-key-2")
    assert client.post(f"/proposals/{p2['proposal_id']}/submit", headers=headers("submit-key-3")).status_code == 409


def test_writes_require_idempotency_key() -> None:
    client, _ = make()
    r = client.post("/proposals", headers=headers(),
                    json={"job_id": "j0", "cover_letter": "x", "amount": 1, "budget_type": "fixed"})
    assert r.status_code == 400


def test_draft_retry_returns_same_draft() -> None:
    client, world = make()
    a = draft(client, key="same-draft-key")
    b = draft(client, key="same-draft-key")
    assert a["proposal_id"] == b["proposal_id"] and len(world.proposals) == 1


def test_rate_limit_returns_429_with_retry_after() -> None:
    client, _ = make({"limits": {"requests_per_minute": 60, "burst": 5}})
    codes = [client.get("/jobs", headers=headers()) for _ in range(20)]
    limited = [r for r in codes if r.status_code == 429]
    assert limited and int(limited[0].headers["Retry-After"]) >= 1
    # Another user has their own bucket.
    assert client.get("/jobs", headers=headers(user="bob")).status_code == 200


def test_5xx_injection_and_recovery() -> None:
    client, _ = make()
    assert client.post("/admin/chaos", headers=ADMIN, json={"error_rate": 0.5}).status_code == 200
    codes = [client.get("/jobs", headers=headers(user=f"u{i}")).status_code for i in range(40)]
    assert 503 in codes and 200 in codes
    client.post("/admin/chaos", headers=ADMIN, json={"error_rate": 0.0})
    assert all(client.get("/jobs", headers=headers(user=f"v{i}")).status_code == 200 for i in range(10))


def test_admin_requires_token_and_policy_update_applies_to_next_submit() -> None:
    client, _ = make()
    assert client.post("/admin/policy", json={"cost_per_proposal": 9}).status_code == 401
    r = client.post("/admin/policy", headers=ADMIN, json={"cost_per_proposal": 9, "add_banned_phrases": ["guaranteed"]})
    assert r.status_code == 200
    assert client.get("/jobs/j0", headers=headers()).json()["connects_cost"] == 9
    p = draft(client)
    assert client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-9")).json()["connects_spent"] == 9
    bad = draft(client, job_id="j1", letter="Guaranteed results!", key="draft-key-b")
    r = client.post(f"/proposals/{bad['proposal_id']}/submit", headers=headers("submit-key-b"))
    assert r.status_code == 422 and "guaranteed" in r.json()["detail"]["banned"]


def test_not_enough_connects() -> None:
    client, _ = make({"connects": {"starting_balance": 3}})
    p = draft(client)
    assert client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1")).status_code == 402


def test_outcomes_revealed_over_time_and_threads() -> None:
    client, _ = make({"decision": {"reply_scale": 100.0, "max_reply_probability": 1.0}})  # reply certain
    letter = ("I built a RAG chatbot with LangChain, Python and Qdrant for a legal client that "
              "answers questions over 3,000 PDFs with 92% accuracy. Happy to share the repo.")
    p = draft(client, letter=letter)
    client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1"))
    assert client.get(f"/proposals/{p['proposal_id']}", headers=headers()).json()["state"] == "submitted"
    client.post("/admin/advance", headers=ADMIN, params={"minutes": 60 * 24 * 10})
    final = client.get(f"/proposals/{p['proposal_id']}", headers=headers()).json()
    assert final["state"] in {"replied", "interview", "hired", "lost"}
    assert [e["state"] for e in final["events"]][:2] == ["submitted", "viewed"]
    threads = client.get("/threads", headers=headers()).json()
    assert threads and threads[0]["proposal_id"] == p["proposal_id"]
    tid = threads[0]["thread_id"]
    msgs = client.get(f"/threads/{tid}/messages", headers=headers()).json()
    assert msgs[0]["sender"] == "client"
    sent = client.post(f"/threads/{tid}/messages", headers=headers("msg-key-0001"), json={"text": "Thanks!"})
    again = client.post(f"/threads/{tid}/messages", headers=headers("msg-key-0001"), json={"text": "Thanks!"})
    assert sent.status_code == 201 and sent.json() == again.json()
    # Another user cannot read this thread.
    assert client.get(f"/threads/{tid}/messages", headers=headers(user="mallory")).status_code == 404


def test_live_tick_adds_planted_jobs_without_exposing_labels() -> None:
    client, world = make()
    added = client.post("/admin/live/tick", headers=ADMIN, params={"n": 30}).json()["added"]
    assert len(added) == 30
    kinds = {world.job_meta.get(j, {}).get("planted") for j in added}
    assert {"scam", "duplicate", "injection"} & kinds
    job = client.get(f"/jobs/{added[0]}", headers=headers()).json()
    assert "planted" not in job and "is_scam" not in job


def test_load_jobs_and_clients_from_json() -> None:
    client, _ = make()
    r = client.post("/admin/clients", headers=ADMIN, json=[{"client_id": "hc1", "rating": 4.9,
                    "hidden": {"is_scam": False}}])
    assert r.json()["loaded"] == ["hc1"]
    r = client.post("/admin/jobs", headers=ADMIN, json=[{**JOBS[0], "job_id": "hidden-1", "client_id": "hc1"}])
    assert r.json()["loaded"] == ["hidden-1"]
    assert client.get("/jobs/hidden-1", headers=headers()).json()["client_id"] == "hc1"


def test_state_survives_restart(tmp_path: Path) -> None:
    state = tmp_path / "gigsim_state.json"
    client, _ = make(state_file=state)
    p = draft(client)
    first = client.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1")).json()
    client2, _ = make(state_file=state)
    replay = client2.post(f"/proposals/{p['proposal_id']}/submit", headers=headers("submit-key-1"))
    assert replay.headers.get("Idempotent-Replayed") == "true" and replay.json() == first
    assert client2.get("/connects", headers=headers()).json()["balance"] == first["balance_after"]


# ------------------------------------------------------------ decision rule


def _decide(letter: str, seed: int, prefs: HiddenPrefs, amount: float = 900) -> Any:
    cfg = load_config()
    return rule_decide(letter=letter, amount=amount, job=JOBS[0], prefs=prefs, priors=PRIORS,
                       cfg=cfg, rng=seeded_rng(seed))


SPECIFIC = ("Your RAG chatbot needs reliable retrieval. I built a LangChain and Qdrant assistant "
            "for a legal firm that answers over 3,000 PDFs, cutting search time by 60%. "
            "I can start with an ingestion prototype this week.")
GENERIC = ("Dear hiring manager, I am writing to apply for your job. I am a hard working and "
           "passionate developer with many skills. I can do this job very well and on time.")
PREFS = HiddenPrefs(("LangChain", "Qdrant"), 1300.0, True)


def test_rule_is_deterministic() -> None:
    a, b = _decide(SPECIFIC, 7, PREFS), _decide(SPECIFIC, 7, PREFS)
    assert (a.viewed, a.replied, a.interview, a.hired) == (b.viewed, b.replied, b.interview, b.hired)


def test_specific_beats_generic_on_average() -> None:
    spec = sum(_decide(SPECIFIC, s, PREFS).replied for s in range(400))
    gen = sum(_decide(GENERIC, s, PREFS).replied for s in range(400))
    assert spec > 2 * gen
    assert spec < 400  # not a guaranteed win


def test_long_padding_does_not_game_the_client() -> None:
    padded = GENERIC + " " + " ".join(["I am very reliable and committed to quality."] * 60)
    assert _decide(padded, 1, PREFS).p_reply <= _decide(GENERIC, 1, PREFS).p_reply


def test_over_budget_lowers_reply_probability() -> None:
    assert _decide(SPECIFIC, 1, PREFS, amount=3000).p_reply < _decide(SPECIFIC, 1, PREFS).p_reply
