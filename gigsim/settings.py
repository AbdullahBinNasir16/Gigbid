"""GigSim settings: YAML config plus secrets from env.

GigSim is independent of the agent code on purpose (it stands in for a third party
marketplace), so it has its own small config loader instead of importing agent.config.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

PKG = Path(__file__).resolve().parent
CONFIG_PATH = PKG / "config.yaml"
TEMPLATES_PATH = PKG / "templates.yaml"


def data_dir() -> Path:
    return Path(os.environ.get("GIGSIM_DATA_DIR", PKG.parent / "data"))


def load_config(path: Path | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def load_templates() -> dict[str, Any]:
    return yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def api_token() -> str:
    """Bearer token clients (our marketplace MCP adapter) must send."""
    return os.environ.get("GIGSIM_API_TOKEN", "dev-gigsim-token")


def admin_token() -> str:
    return os.environ.get("GIGSIM_ADMIN_TOKEN", "dev-gigsim-admin")
