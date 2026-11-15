"""Model factory. The only place that turns a node name into a chat model.

Why: no model names in Python. Switching profile (open, open_hosted, paid) is a config
or MODEL_PROFILE change, never a code change.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import SecretStr

from agent.config import NODE_NAMES, AppConfig, NodeModelConfig, get_config

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


class UnknownNodeError(KeyError):
    """Raised when a node name is not one of the configured agent nodes."""


def resolve_model(
    node_name: str, *, config: AppConfig | None = None, fallback: bool = False
) -> NodeModelConfig | None:
    """Return the model settings for a node under the active profile.

    With fallback=True returns the fallback model, or None if the node has none.
    """
    if node_name not in NODE_NAMES:
        raise UnknownNodeError(node_name)
    cfg = config or get_config()
    profile = cfg.models.profile
    if fallback:
        return cfg.models.fallback_models.get(profile, {}).get(node_name)
    return cfg.models.profiles[profile][node_name]


def _build(model_cfg: NodeModelConfig, cfg: AppConfig) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    provider = cfg.models.providers[model_cfg.provider]
    base_url = (
        os.environ.get(provider.base_url_env, provider.default_base_url)
        if provider.base_url_env
        else provider.default_base_url
    )
    # A local model server ignores the key, but the client requires a non empty value.
    api_key = os.environ.get(provider.api_key_env, "") if provider.api_key_env else "not-needed"
    return ChatOpenAI(
        model=model_cfg.model,
        base_url=base_url,
        api_key=SecretStr(api_key or "missing-key"),
        temperature=model_cfg.temperature,
        max_completion_tokens=model_cfg.max_tokens,
        timeout=cfg.budgets.node_timeout_seconds,
        max_retries=cfg.budgets.node_max_retries,
    )


def get_llm(node_name: str, *, config: AppConfig | None = None) -> BaseChatModel:
    """Chat model for a node, wrapped with its fallback model when one is configured."""
    cfg = config or get_config()
    primary_cfg = resolve_model(node_name, config=cfg)
    assert primary_cfg is not None
    primary = _build(primary_cfg, cfg)
    fallback_cfg = resolve_model(node_name, config=cfg, fallback=True)
    if fallback_cfg is None:
        return primary
    return primary.with_fallbacks([_build(fallback_cfg, cfg)])  # type: ignore[return-value]
