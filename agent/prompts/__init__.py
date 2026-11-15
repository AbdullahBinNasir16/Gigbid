"""Prompt loader. Every prompt lives in agent/prompts/<node>.md, never inline in code."""

from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    text = (DIR / f"{name}.md").read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.startswith("<!--")).strip()


def prompt_version(name: str) -> str:
    first = (DIR / f"{name}.md").read_text(encoding="utf-8").splitlines()[0]
    return first.replace("<!-- version:", "").replace("-->", "").strip()
