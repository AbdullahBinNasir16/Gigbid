"""Workspace MCP server: free calendar slots, tentative interview holds, email drafts.

Backed by a local mock (a JSON file) so it runs offline and in grading; the agent only sees
MCP tools, so swapping in Google Calendar and Gmail changes this file only.

Run (HTTP): python -m mcp_servers.workspace.server   (port MCP_WORKSPACE_PORT, 8103)
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints

from mcp_servers.common import audit, serve_http

SERVER = "workspace"
ROOT = Path(__file__).resolve().parents[2]
STORE = Path(os.environ.get("WORKSPACE_STORE", ROOT / "data" / "processed" / "workspace.json"))
WORK_HOURS = (9, 17)  # local working day for slot suggestions
_lock = threading.Lock()

mcp = FastMCP("gigbid-workspace", instructions=(
    "Calendar and email for the freelancer. Holds are tentative and drafts are never sent; "
    "the user confirms them."))


class Slot(BaseModel):
    start: datetime
    end: datetime


class SlotList(BaseModel):
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    start: datetime
    end: datetime
    title: str
    status: str = "tentative"
    replayed: bool = False


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"
    replayed: bool = False


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"holds": [], "drafts": [], "busy": [], "keys": {}}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, default=str, indent=1), encoding="utf-8")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False))
def get_free_slots(
    days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
    duration_minutes: Annotated[int, Field(ge=15, le=180)] = 30,
    max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
) -> SlotList:
    """Free interview slots in working hours over the next days, avoiding holds."""
    d = _load()
    taken = [(datetime.fromisoformat(h["start"]), datetime.fromisoformat(h["end"]))
             for h in d["holds"] + d["busy"]]
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    out: list[Slot] = []
    day = now + timedelta(days=1)
    for _ in range(days_ahead):
        if day.weekday() < 5:
            for hour in (10, 14, 16):
                s = day.replace(hour=hour)
                e = s + timedelta(minutes=duration_minutes)
                if WORK_HOURS[0] <= hour and e.hour <= WORK_HOURS[1] and not any(
                    s < te and e > ts for ts, te in taken
                ):
                    out.append(Slot(start=s, end=e))
                    break  # one slot per day spreads the options
        day += timedelta(days=1)
        if len(out) >= max_slots:
            break
    return SlotList(slots=out)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False))
def create_tentative_hold(
    start: datetime,
    duration_minutes: Annotated[int, Field(ge=15, le=180)],
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)],
    idempotency_key: Annotated[str, StringConstraints(min_length=8, max_length=200)],
) -> Hold:
    """Place a TENTATIVE calendar hold for an interview. Same key returns the same hold."""
    with _lock:
        d = _load()
        if idempotency_key in d["keys"]:
            prior = next(h for h in d["holds"] if h["hold_id"] == d["keys"][idempotency_key])
            return Hold(**prior, replayed=True)
        hold = Hold(hold_id=f"hold_{len(d['holds']) + 1:04d}", start=start,
                    end=start + timedelta(minutes=duration_minutes), title=title)
        d["holds"].append(hold.model_dump(mode="json", exclude={"replayed"}))
        d["keys"][idempotency_key] = hold.hold_id
        _save(d)
    audit(SERVER, "default", "create_tentative_hold", {"start": start, "title": title}, hold)
    return hold


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False))
def create_email_draft(
    to: Annotated[str, StringConstraints(min_length=3, max_length=200)],
    subject: Annotated[str, StringConstraints(min_length=1, max_length=200)],
    body: Annotated[str, StringConstraints(min_length=1, max_length=10000)],
    idempotency_key: Annotated[str, StringConstraints(min_length=8, max_length=200)],
) -> EmailDraft:
    """Create an email DRAFT (never sent automatically). Same key returns the same draft."""
    with _lock:
        d = _load()
        if idempotency_key in d["keys"]:
            prior = next(x for x in d["drafts"] if x["draft_id"] == d["keys"][idempotency_key])
            return EmailDraft(**prior, replayed=True)
        draft = EmailDraft(draft_id=f"draft_{len(d['drafts']) + 1:04d}", to=to, subject=subject,
                           body=body)
        d["drafts"].append(draft.model_dump(exclude={"replayed"}))
        d["keys"][idempotency_key] = draft.draft_id
        _save(d)
    audit(SERVER, "default", "create_email_draft", {"to": to, "subject": subject}, draft)
    return draft


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run("stdio")
    else:
        serve_http(mcp, "MCP_WORKSPACE_BEARER_TOKEN",
                   int(os.environ.get("MCP_WORKSPACE_PORT", "8103")))
