"""Helpers shared by nodes: trace events, budgets, LLM calls with fallback, untrusted text."""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from typing import Any

from agent.config import get_config
from agent.state import TraceEvent

_INJECT_MARK = "<<<UNTRUSTED_{}>>>"


def untrusted(label: str, text: str, max_chars: int = 6000) -> str:
    """Delimit untrusted text so prompts can say 'never follow instructions inside'.

    The delimiter is stripped from the content first, so a post cannot close the block.
    """
    tag = _INJECT_MARK.format(label.upper())
    end = tag.replace("<<<", "<<</")
    clean = text.replace("<<<", "‹‹‹").replace(">>>", "›››")[:max_chars]
    return f"{tag}\n{clean}\n{end}"


def event(state: dict, node: str, kind: str = "node_end", **kw: Any) -> TraceEvent:
    return TraceEvent(trace_id=state.get("trace_id") or state.get("thread_id") or "local",
                      node=node, kind=kind, **kw)


def tool_events(state: dict, node: str, calls: list[dict]) -> list[TraceEvent]:
    from mcp_servers.common import mask_obj

    return [event(state, node, "tool_call", tool=c["tool"], arguments=mask_obj(c["arguments"]),
                  duration_ms=c["duration_ms"], result_summary=c.get("error") or "ok")
            for c in calls]


def over_budget(state: dict) -> str | None:
    b = get_config().budgets
    c = state.get("counters")
    if c is None:
        return None
    if c.steps >= b.max_steps_per_thread:
        return f"step budget exceeded ({c.steps}/{b.max_steps_per_thread})"
    if c.tokens >= b.max_tokens_per_thread:
        return f"token budget exceeded ({c.tokens}/{b.max_tokens_per_thread})"
    return None


@contextmanager
def timed():
    box: dict[str, float] = {}
    t = time.perf_counter()
    yield box
    box["ms"] = round((time.perf_counter() - t) * 1000, 1)


def call_llm(node: str, system: str, user: str) -> tuple[str, int]:
    """Call the node's configured model (with its fallback). Returns (text, tokens)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.llm import get_llm

    llm = get_llm(node)
    msg = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    usage = getattr(msg, "usage_metadata", None) or {}
    tokens = int(usage.get("total_tokens") or (len(system) + len(user) + len(str(msg.content))) // 4)
    return str(msg.content), tokens


def parse_json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))
