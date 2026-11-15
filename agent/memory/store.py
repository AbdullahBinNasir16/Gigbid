"""Long-term memory on a LangGraph store.

Namespaces (per user):
  ("candidates", user, "style")   raw edit patterns observed, with the proposals they came from
  ("memory", user, "style")       PROMOTED style rules the writer sees
  ("candidates", user, "outcome") outcome tallies per job category
  ("memory", user, "outcome")     PROMOTED outcome lessons
Only agent/memory/promotion_rules.py moves items from candidates to memory. Raw tool output
never goes into memory.

Backend: PostgresStore when DATABASE_URL is a postgres URL, else SqliteStore in
data/processed/memory.sqlite (both persist across restarts).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_store: Any = None


def get_store() -> Any:
    global _store
    if _store is not None:
        return _store
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.store.postgres import PostgresStore
        from psycopg import Connection

        conn = Connection.connect(url.replace("postgresql+psycopg", "postgresql"), autocommit=True)
        _store = PostgresStore(conn)
    else:
        from langgraph.store.sqlite import SqliteStore

        path = Path(os.environ.get("MEMORY_DB", ROOT / "data" / "processed" / "memory.sqlite"))
        path.parent.mkdir(parents=True, exist_ok=True)
        _store = SqliteStore(sqlite3.connect(str(path), check_same_thread=False,
                                             isolation_level=None))
    _store.setup()
    return _store


def set_store(store: Any) -> None:
    """Tests inject an InMemoryStore."""
    global _store
    _store = store


def list_memory(user: str, kind: str) -> list[dict[str, Any]]:
    return [{"key": i.key, **i.value} for i in get_store().search(("memory", user, kind),
                                                                  limit=200)]


def delete_memory(user: str, kind: str, key: str) -> None:
    get_store().delete(("memory", user, kind), key)
    # forget the evidence too, so it is not promoted straight back
    get_store().delete(("candidates", user, kind), key)


def style_rules_text(user: str) -> str:
    try:
        rules = list_memory(user, "style")
    except Exception:  # noqa: BLE001 - memory is optional for drafting
        return ""
    if not rules:
        return ""
    return "Style rules learned from this freelancer's edits (follow them):\n" + "\n".join(
        f"- {r['rule']}" for r in rules[:20])
