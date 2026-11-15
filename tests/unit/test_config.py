from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agent.config import CONFIG_PATH, NODE_NAMES, load_config
from agent.llm import UnknownNodeError, get_llm, resolve_model


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_PROFILE", raising=False)
    monkeypatch.delenv("MARKETPLACE_MODE", raising=False)


def _raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, raw: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_config_loads_and_keeps_kit_keys() -> None:
    cfg = load_config(apply_env=False)
    assert cfg.marketplace.mode == "gigsim"
    assert cfg.budgets.critic_max_loops == 2
    assert cfg.thresholds.minimum_fit_score == pytest.approx(0.60)


def test_every_profile_covers_every_node() -> None:
    cfg = load_config(apply_env=False)
    for name in ("open", "paid"):
        assert set(cfg.models.profiles[name]) >= set(NODE_NAMES)


def test_env_switches_profile_and_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROFILE", "paid")
    monkeypatch.setenv("MARKETPLACE_MODE", "fake")
    cfg = load_config()
    assert cfg.models.profile == "paid"
    assert cfg.marketplace.mode == "fake"


def test_profile_switch_changes_model_without_code_change(tmp_path: Path) -> None:
    raw = _raw()
    open_cfg = load_config(_write(tmp_path, raw), apply_env=False)
    raw["models"]["profile"] = "paid"
    paid_cfg = load_config(_write(tmp_path, raw), apply_env=False)
    open_writer = resolve_model("writer", config=open_cfg)
    paid_writer = resolve_model("writer", config=paid_cfg)
    assert open_writer is not None and paid_writer is not None
    assert open_writer.model != paid_writer.model
    assert get_llm("writer", config=paid_cfg).model_name == paid_writer.model  # type: ignore[attr-defined]


def test_cheap_node_has_fallback_and_writer_does_not() -> None:
    cfg = load_config(apply_env=False)
    assert resolve_model("scout", config=cfg, fallback=True) is not None
    assert resolve_model("writer", config=cfg, fallback=True) is None


def test_unknown_node_rejected() -> None:
    with pytest.raises(UnknownNodeError):
        resolve_model("not_a_node")


def test_missing_node_in_profile_fails_validation(tmp_path: Path) -> None:
    raw = _raw()
    del raw["models"]["profiles"]["paid"]["critic"]
    with pytest.raises(ValidationError, match="critic"):
        load_config(_write(tmp_path, raw), apply_env=False)


def test_unknown_profile_fails_validation(tmp_path: Path) -> None:
    raw = _raw()
    raw["models"]["profile"] = "nope"
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, raw), apply_env=False)


def test_unordered_fit_thresholds_rejected(tmp_path: Path) -> None:
    raw = _raw()
    raw["thresholds"]["fit"] = {"bid": 0.3, "watch": 0.5}
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, raw), apply_env=False)


def test_connects_cost_is_config_driven(tmp_path: Path) -> None:
    cfg = load_config(apply_env=False)
    assert cfg.connects_cost_for(None) == cfg.platform_rules.connects.cost_per_proposal
    assert cfg.connects_cost_for(100) == 4
    assert cfg.connects_cost_for(5000) == 10
    raw = _raw()
    raw["platform_rules"]["connects"]["cost_by_budget_usd"] = []
    raw["platform_rules"]["connects"]["cost_per_proposal"] = 9
    assert load_config(_write(tmp_path, raw), apply_env=False).connects_cost_for(5000) == 9
