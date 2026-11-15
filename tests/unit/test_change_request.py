"""Change request readiness: a platform policy update is absorbed by config and data only.

Scenario (mirrors GigSim's POST /admin/policy): Connects cost doubles and a new phrase is
banned. GigBid needs zero code changes: pricing uses the cost carried by each job (or the
config tiers), and the Compliance Guard reads the banned phrases file.
"""

from agent.config import get_config
from agent.nodes import compliance
from agent.nodes.pricing import quote


def test_doubled_connects_cost_flows_from_job_into_quote():
    job = {"job_id": "j1", "title": "RAG bot", "category": "ai_ml", "budget_type": "fixed",
           "budget_min": 800, "budget_max": 1200, "connects_cost": 12}
    assert quote(job, 0.7, "ai_ml").connects_cost == 12
    assert quote(job | {"connects_cost": 24}, 0.7, "ai_ml").connects_cost == 24


def _with_rules(**changes):
    cfg = get_config()
    return cfg.model_copy(update={"platform_rules": cfg.platform_rules.model_copy(update=changes)})


def test_config_tiers_change_without_code():
    rules = get_config().platform_rules.connects
    doubled = rules.model_copy(update={"cost_by_budget_usd": [
        t.model_copy(update={"cost": t.cost * 2}) for t in rules.cost_by_budget_usd]})
    assert get_config().connects_cost_for(600) == 6
    assert _with_rules(connects=doubled).connects_cost_for(600) == 12


def test_new_banned_phrase_is_enforced_from_the_data_file(tmp_path, monkeypatch):
    f = tmp_path / "banned.txt"
    f.write_text("instant results\n", encoding="utf-8")
    new_cfg = _with_rules(banned_phrases_file=str(f))
    monkeypatch.setattr(compliance, "get_config", lambda: new_cfg)
    compliance.banned_phrases.cache_clear()
    v = compliance.check("I deliver instant results for every client. Happy to discuss scope.")
    assert "instant results" not in (v.cleaned_text or "").lower()
    compliance.banned_phrases.cache_clear()
