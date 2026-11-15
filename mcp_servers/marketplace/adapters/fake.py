"""In memory marketplace for unit tests, CI and offline development.

Why: lets the graph and the port contract be tested without GigSim or the network.
It follows the same rules as the real adapters: idempotent writes, dry_run with zero
side effects, Connects spent once.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

from agent.config import get_config
from agent.marketplace_port import (
    ClientHistory,
    ConnectsBalance,
    InsufficientConnects,
    InvalidRequest,
    Job,
    MarketplacePort,
    Message,
    ProposalPayload,
    WriteResult,
)


class FakeMarketplace(MarketplacePort):
    def __init__(
        self,
        jobs: list[Job] | None = None,
        clients: list[ClientHistory] | None = None,
        balance: int = 60,
        connects_cost: int | None = None,
    ) -> None:
        self.jobs = {j.job_id: j for j in (jobs or _default_jobs())}
        self.clients = {c.client_id: c for c in (clients or _default_clients())}
        self.balance = balance
        self.connects_cost = (
            connects_cost
            if connects_cost is not None
            else get_config().platform_rules.connects.cost_per_proposal
        )
        self.drafts: dict[str, ProposalPayload] = {}
        self.submitted: dict[str, str] = {}  # draft_id -> job_id
        self.messages: list[Message] = []
        self._results: dict[tuple[str, str], WriteResult] = {}
        self._ids = itertools.count(1)

    # ---------------------------------------------------------------- reads
    async def search_jobs(
        self, query: str = "", *, limit: int = 20, since: datetime | None = None
    ) -> list[Job]:
        q = query.lower().strip()
        out = [
            j
            for j in self.jobs.values()
            if (not q or q in j.title.lower() or q in j.description.lower())
            and (since is None or (j.posted_at is not None and j.posted_at >= since))
        ]
        return out[:limit]

    async def get_job(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise InvalidRequest(f"unknown job {job_id}")
        return self.jobs[job_id]

    async def get_client_history(self, client_id: str) -> ClientHistory:
        if client_id not in self.clients:
            raise InvalidRequest(f"unknown client {client_id}")
        return self.clients[client_id]

    async def get_connects_balance(self) -> ConnectsBalance:
        return ConnectsBalance(balance=self.balance)

    async def list_messages(self, thread_id: str | None = None) -> list[Message]:
        return [m for m in self.messages if thread_id is None or m.thread_id == thread_id]

    # --------------------------------------------------------------- writes
    def _replay(self, tool: str, key: str) -> WriteResult | None:
        prior = self._results.get((tool, key))
        return prior.model_copy(update={"replayed": True}) if prior else None

    async def create_proposal_draft(
        self, payload: ProposalPayload, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult:
        if payload.job_id not in self.jobs:
            raise InvalidRequest(f"unknown job {payload.job_id}")
        if dry_run:
            return WriteResult(
                ok=True, dry_run=True, idempotency_key=idempotency_key,
                preview=payload.model_dump(),
            )
        if prior := self._replay("create_proposal_draft", idempotency_key):
            return prior
        draft_id = f"draft-{next(self._ids)}"
        self.drafts[draft_id] = payload
        result = WriteResult(
            ok=True, dry_run=False, idempotency_key=idempotency_key, resource_id=draft_id
        )
        self._results[("create_proposal_draft", idempotency_key)] = result
        return result

    async def submit_proposal(
        self, draft_id: str, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult:
        if prior := self._replay("submit_proposal", idempotency_key):
            return prior
        if draft_id not in self.drafts:
            raise InvalidRequest(f"unknown draft {draft_id}")
        cost = self.connects_cost
        preview: dict[str, Any] = {"draft_id": draft_id, **self.drafts[draft_id].model_dump()}
        if dry_run:
            return WriteResult(
                ok=True, dry_run=True, idempotency_key=idempotency_key, connects_cost=cost,
                connects_balance_after=self.balance - cost, preview=preview,
            )
        if draft_id in self.submitted:
            raise InvalidRequest(f"draft {draft_id} already submitted")
        if self.balance < cost:
            raise InsufficientConnects(f"need {cost} Connects, have {self.balance}")
        self.balance -= cost
        self.submitted[draft_id] = self.drafts[draft_id].job_id
        result = WriteResult(
            ok=True, dry_run=False, idempotency_key=idempotency_key, resource_id=draft_id,
            connects_cost=cost, connects_balance_after=self.balance,
        )
        self._results[("submit_proposal", idempotency_key)] = result
        return result

    async def send_message(
        self, thread_id: str, text: str, *, idempotency_key: str, dry_run: bool = False
    ) -> WriteResult:
        if not text.strip():
            raise InvalidRequest("empty message")
        if dry_run:
            return WriteResult(
                ok=True, dry_run=True, idempotency_key=idempotency_key,
                preview={"thread_id": thread_id, "text": text},
            )
        if prior := self._replay("send_message", idempotency_key):
            return prior
        msg = Message(
            message_id=f"msg-{next(self._ids)}", thread_id=thread_id, sender="freelancer",
            text=text, sent_at=datetime.now(UTC),
        )
        self.messages.append(msg)
        result = WriteResult(
            ok=True, dry_run=False, idempotency_key=idempotency_key, resource_id=msg.message_id
        )
        self._results[("send_message", idempotency_key)] = result
        return result


def _default_jobs() -> list[Job]:
    return [
        Job(
            job_id="fake-job-1", title="Build a RAG chatbot over PDFs",
            description="Need a Python developer to build a retrieval chatbot with LangChain.",
            skills=["python", "langchain", "rag"], category="AI/ML", budget_type="fixed",
            budget_min=500, budget_max=1500, client_id="fake-client-1", provenance="synthetic",
        ),
        Job(
            job_id="fake-job-2", title="Dashboard in Power BI",
            description="Create a sales dashboard from Excel data.",
            skills=["power bi", "excel"], category="Data Analysis", budget_type="hourly",
            budget_min=20, budget_max=40, client_id="fake-client-2", provenance="synthetic",
        ),
    ]


def _default_clients() -> list[ClientHistory]:
    return [
        ClientHistory(
            client_id="fake-client-1", completed_projects=12, rating=4.8, total_spend=15000,
            payment_verified=True,
        ),
        ClientHistory(
            client_id="fake-client-2", completed_projects=0, rating=None, total_spend=0,
            payment_verified=False,
        ),
    ]
