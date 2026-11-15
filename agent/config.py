"""Typed loader for agent/config.yaml.

Why: every model, threshold, budget and platform rule must come from one validated
place, so a policy change is a config edit and a typo fails at startup, not mid run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_PATH = Path(__file__).with_name("config.yaml")

NODE_NAMES: tuple[str, ...] = (
    "scout",
    "analyst",
    "risk",
    "matcher",
    "pricing",
    "writer",
    "verifier",
    "critic",
    "compliance",
    "liaison",
    "intent_classifier",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetryConfig(_Strict):
    max_attempts: int = Field(ge=1, le=10)
    base_delay_seconds: float = Field(gt=0)
    max_delay_seconds: float = Field(gt=0)


class BreakerConfig(_Strict):
    failure_threshold: int = Field(ge=1)
    cooldown_seconds: float = Field(gt=0)


class MarketplaceConfig(_Strict):
    mode: Literal["gigsim", "upwork_live", "fake"]
    max_requests_per_minute: int = Field(ge=1)
    polling_interval_seconds: int = Field(ge=10)
    live_polling_interval_seconds: int = Field(ge=300)
    adapters: dict[str, str]
    request_timeout_seconds: float = Field(gt=0)
    retry: RetryConfig
    circuit_breaker: BreakerConfig

    @model_validator(mode="after")
    def _mode_has_adapter(self) -> MarketplaceConfig:
        if self.mode not in self.adapters:
            raise ValueError(f"marketplace.mode '{self.mode}' has no entry in marketplace.adapters")
        return self


class ProviderConfig(_Strict):
    kind: Literal["openai_compatible"]
    base_url_env: str | None = None
    default_base_url: str
    api_key_env: str | None = None


class NodeModelConfig(_Strict):
    provider: str
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(ge=16, le=32768)


class EmbeddingsConfig(_Strict):
    model: str
    dimension: int = Field(ge=8)
    query_prefix: str = ""
    document_prefix: str = ""


class RerankerConfig(_Strict):
    model: str
    top_n: int = Field(ge=1, le=200)


class ModelsConfig(_Strict):
    profile: str
    providers: dict[str, ProviderConfig]
    profiles: dict[str, dict[str, NodeModelConfig]]
    fallback_models: dict[str, dict[str, NodeModelConfig]] = Field(default_factory=dict)
    embeddings: EmbeddingsConfig
    reranker: RerankerConfig

    @model_validator(mode="after")
    def _profiles_complete(self) -> ModelsConfig:
        if "open" not in self.profiles:
            raise ValueError("models.profiles.open is required")
        if self.profile not in self.profiles:
            raise ValueError(f"models.profile '{self.profile}' is not defined in models.profiles")
        for name, nodes in self.profiles.items():
            missing = set(NODE_NAMES) - set(nodes)
            if missing:
                raise ValueError(f"profile '{name}' is missing nodes: {sorted(missing)}")
            for node, cfg in nodes.items():
                if cfg.provider not in self.providers:
                    raise ValueError(f"{name}.{node} uses unknown provider '{cfg.provider}'")
        for name, nodes in self.fallback_models.items():
            for node, cfg in nodes.items():
                if node not in NODE_NAMES:
                    raise ValueError(f"fallback_models.{name} has unknown node '{node}'")
                if cfg.provider not in self.providers:
                    raise ValueError(f"fallback {name}.{node} uses unknown provider")
        return self


class LatencyTargets(_Strict):
    job_analysed: float = Field(gt=0)
    proposal: float = Field(gt=0)


class BudgetsConfig(_Strict):
    max_graph_steps: int = Field(ge=1)
    max_revisions: int = Field(ge=0)
    max_tokens_per_job: int = Field(ge=100)
    max_steps_per_thread: int = Field(ge=1)
    max_tokens_per_thread: int = Field(ge=100)
    critic_max_loops: int = Field(ge=0, le=5)
    node_timeout_seconds: float = Field(gt=0)
    node_max_retries: int = Field(ge=0, le=5)
    p95_latency_seconds: LatencyTargets
    cost_usd: LatencyTargets


class FitThresholds(_Strict):
    bid: float = Field(ge=0, le=1)
    watch: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> FitThresholds:
        if self.watch > self.bid:
            raise ValueError("thresholds.fit.watch must be <= thresholds.fit.bid")
        return self


class PriceThresholds(_Strict):
    floor_hourly_usd: float = Field(ge=0)
    floor_fixed_usd: float = Field(ge=0)
    band_low_percentile: Literal["p10", "p25", "p50"]
    band_high_percentile: Literal["p50", "p75", "p90"]
    min_expected_value_per_connect_usd: float = Field(ge=0)


class AutonomyThresholds(_Strict):
    auto_skip_below_fit: float = Field(ge=0, le=1)


class ThresholdsConfig(_Strict):
    minimum_fit_score: float = Field(ge=0, le=1)
    maximum_risk_score: float = Field(ge=0, le=1)
    fit: FitThresholds
    scam_risk: float = Field(ge=0, le=1)
    price: PriceThresholds
    autonomy: AutonomyThresholds


class ConnectsTier(_Strict):
    min_budget: float = Field(ge=0)
    cost: int = Field(ge=0)


class ConnectsRules(_Strict):
    cost_per_proposal: int = Field(ge=0)
    cost_by_budget_usd: list[ConnectsTier] = Field(default_factory=list)
    weekly_budget: int = Field(ge=0)


class FeeRules(_Strict):
    service_fee_percent: float = Field(ge=0, le=100)


class PlatformRules(_Strict):
    connects: ConnectsRules
    fees: FeeRules
    policy_pack_dir: str
    banned_phrases_file: str
    off_platform_terms: list[str]


class StyleMemoryConfig(_Strict):
    min_edits_to_promote: int = Field(ge=1)
    max_items: int = Field(ge=1)


class OutcomeMemoryConfig(_Strict):
    min_samples_to_promote: int = Field(ge=1)
    min_reply_rate_delta: float = Field(ge=0, le=1)


class MemoryConfig(_Strict):
    style: StyleMemoryConfig
    outcome: OutcomeMemoryConfig


class LiaisonAllowlist(_Strict):
    read: list[str]
    after_approval: list[str]


class ToolAllowlists(_Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scout: list[str]
    risk: list[str]
    pricing: list[str]
    matcher: list[str]
    writer: list[str]
    critic: list[str]
    analyst: list[str]
    compliance: list[str]
    liaison: LiaisonAllowlist
    submitter: list[str] = Field(default_factory=list)  # runs only after human approval


class RetrievalConfig(_Strict):
    variant: str
    compose: list[str] = Field(default_factory=list)
    outcome_boost_weight: float = Field(ge=0, le=1)
    corrective_max_requeries: int = Field(ge=0, le=5)
    min_evidence_score: float = Field(ge=0, le=1)


class SeedsConfig(_Strict):
    global_: int = Field(alias="global")


class AppConfig(_Strict):
    marketplace: MarketplaceConfig
    models: ModelsConfig
    budgets: BudgetsConfig
    thresholds: ThresholdsConfig
    platform_rules: PlatformRules
    memory: MemoryConfig
    tool_allowlists: ToolAllowlists
    retrieval: RetrievalConfig
    seeds: SeedsConfig
    # Rule tables kept in config so a policy update is a YAML edit, not a code change.
    risk_rules: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)

    def connects_cost_for(self, budget_usd: float | None) -> int:
        """Connects cost for a job, from config tiers (falls back to the flat cost)."""
        rules = self.platform_rules.connects
        if budget_usd is None or not rules.cost_by_budget_usd:
            return rules.cost_per_proposal
        matching = [t for t in rules.cost_by_budget_usd if budget_usd >= t.min_budget]
        if not matching:
            return rules.cost_per_proposal
        return max(matching, key=lambda t: t.min_budget).cost


class EnvOverrides(BaseSettings):
    """Env vars that may override config. Only switches, never secrets."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_profile: str | None = Field(default=None, alias="MODEL_PROFILE")
    marketplace_mode: str | None = Field(default=None, alias="MARKETPLACE_MODE")


def load_config(path: Path | str | None = None, *, apply_env: bool = True) -> AppConfig:
    """Read and validate the YAML config, applying env switches."""
    raw = yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    if apply_env:
        env = EnvOverrides()
        if env.model_profile:
            raw["models"]["profile"] = env.model_profile
        if env.marketplace_mode:
            raw["marketplace"]["mode"] = env.marketplace_mode
    return AppConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Process wide cached config. Call get_config.cache_clear() after editing in tests."""
    return load_config()
