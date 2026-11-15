"""App database (users, settings, analysed jobs, runs, encrypted OAuth tokens).

SQLAlchemy Core so the same code runs on Postgres in compose (DATABASE_URL) and on SQLite
locally. Every query is scoped by user_id (tenant).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)

ROOT = Path(__file__).resolve().parents[2]
_url = os.environ.get("DATABASE_URL", "")
if not _url.startswith("postgres"):
    (ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    _url = f"sqlite:///{(ROOT / 'data' / 'processed' / 'app.sqlite').as_posix()}"
engine = create_engine(_url, future=True, pool_pre_ping=True)
meta = MetaData()

users = Table("users", meta,
              Column("user_id", String(64), primary_key=True),
              Column("username", String(120), unique=True, nullable=False),
              Column("pw_hash", String(300), nullable=False),
              Column("settings", Text, nullable=False, default="{}"),
              Column("created_at", DateTime(timezone=True)))
jobs = Table("jobs", meta,
             Column("user_id", String(64), primary_key=True),
             Column("job_id", String(128), primary_key=True),
             Column("data", Text, nullable=False),
             Column("analysis", Text),
             Column("decision", String(16)),
             Column("fit", Float),
             Column("risk", Float),
             Column("status", String(32), default="new"),
             Column("thread_id", String(200)),
             Column("updated_at", DateTime(timezone=True)))
runs = Table("runs", meta,
             Column("thread_id", String(200), primary_key=True),
             Column("user_id", String(64), nullable=False),
             Column("job_id", String(128)),
             Column("kind", String(16), default="bid"),
             Column("status", String(32)),
             Column("summary", Text),
             Column("metrics", Text, default="{}"),
             Column("updated_at", DateTime(timezone=True)))
tokens = Table("oauth_tokens", meta,
               Column("user_id", String(64), primary_key=True),
               Column("provider", String(32), primary_key=True),
               Column("ciphertext", Text, nullable=False),
               Column("updated_at", DateTime(timezone=True)))

meta.create_all(engine)


def now() -> datetime:
    return datetime.now(UTC)


def q(stmt: Any) -> list[dict[str, Any]]:
    with engine.begin() as c:
        res = c.execute(stmt)
        return [dict(r._mapping) for r in res] if res.returns_rows else []


def upsert_job(user_id: str, job_id: str, **fields: Any) -> None:
    for k in ("data", "analysis"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], default=str)
    fields["updated_at"] = now()
    with engine.begin() as c:
        hit = c.execute(select(jobs.c.job_id).where(jobs.c.user_id == user_id,
                                                    jobs.c.job_id == job_id)).first()
        if hit:
            c.execute(update(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id)
                      .values(**fields))
        else:
            c.execute(insert(jobs).values(user_id=user_id, job_id=job_id, **fields))


def upsert_run(thread_id: str, user_id: str, **fields: Any) -> None:
    if "metrics" in fields and not isinstance(fields["metrics"], str):
        fields["metrics"] = json.dumps(fields["metrics"], default=str)
    fields["updated_at"] = now()
    with engine.begin() as c:
        hit = c.execute(select(runs.c.thread_id).where(runs.c.thread_id == thread_id)).first()
        if hit:
            c.execute(update(runs).where(runs.c.thread_id == thread_id,
                                         runs.c.user_id == user_id).values(**fields))
        else:
            c.execute(insert(runs).values(thread_id=thread_id, user_id=user_id, **fields))


__all__ = [
    "delete",
    "engine",
    "insert",
    "jobs",
    "now",
    "q",
    "runs",
    "select",
    "tokens",
    "update",
    "upsert_job",
    "upsert_run",
    "users",
]
