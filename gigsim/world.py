"""The simulated marketplace state.

One World holds jobs, clients (with hidden preferences), users and their Connects,
proposals, outcome events, message threads and idempotency records. All public reads
return copies without hidden fields. Outcomes are decided at submit time with a seeded
RNG and revealed over simulated time, so the same proposal always gets the same result.
"""

from __future__ import annotations

import itertools
import json
import math
import threading
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gigsim.decisions import HiddenPrefs, decide, seeded_rng
from gigsim.settings import data_dir, load_templates

PUBLIC_JOB_FIELDS = (
    "job_id", "title", "description", "skills", "category", "budget_type", "budget_min",
    "budget_max", "experience_level", "applicants", "provenance", "source_dataset",
)


class SimError(Exception):
    status = 400

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.detail = detail


class NotFound(SimError):
    status = 404


class Conflict(SimError):
    status = 409


class Unprocessable(SimError):
    status = 422


class PaymentRequired(SimError):
    status = 402  # not enough Connects


# ---------------------------------------------------------------- loading


def _clean(v: Any) -> Any:
    """Turn pandas/numpy values into plain JSON values."""
    if v is None:
        return None
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def load_job_records(cfg: dict[str, Any], base: Path | None = None) -> list[dict[str, Any]]:
    base = base or data_dir()
    for rel in cfg["data"]["job_stream"]:
        path = base / rel
        if not path.exists():
            continue
        if path.suffix == ".parquet":
            import pandas as pd

            rows = pd.read_parquet(path).to_dict(orient="records")
        else:
            rows = json.loads(path.read_text(encoding="utf-8"))
        return [{k: _clean(v) for k, v in r.items()} for r in rows]
    return []


def load_priors(cfg: dict[str, Any], base: Path | None = None) -> dict[str, Any]:
    path = (base or data_dir()) / cfg["data"]["outcome_priors"]
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _from_quantiles(q: dict[str, Any] | None, u: float, default: float) -> float:
    """Inverse CDF by linear interpolation between stored percentiles."""
    if not q:
        return default
    pts = [(p, q[f"p{p}"]) for p in (10, 25, 50, 75, 90) if f"p{p}" in q]
    if not pts:
        return default
    xs = [p / 100 for p, _ in pts]
    ys = [y for _, y in pts]
    if u <= xs[0]:
        return ys[0] * (u / xs[0]) if xs[0] else ys[0]
    if u >= xs[-1]:
        return ys[-1] * (1 + (u - xs[-1]) * 2)
    i = bisect_right(xs, u)
    t = (u - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[i - 1] + t * (ys[i] - ys[i - 1])


# ---------------------------------------------------------------- records


@dataclass
class Proposal:
    proposal_id: str
    user_id: str
    job_id: str
    client_id: str
    cover_letter: str
    amount: float
    budget_type: str
    connects_cost: int
    created_at: datetime
    submitted_at: datetime | None = None
    # (state, at) pairs revealed when sim time passes `at`
    schedule: list[tuple[str, datetime]] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)  # internal, never served
    thread_id: str | None = None


@dataclass
class Message:
    message_id: str
    thread_id: str
    sender: str
    text: str
    sent_at: datetime


@dataclass
class Thread:
    thread_id: str
    user_id: str
    client_id: str
    job_id: str
    proposal_id: str
    pending: list[tuple[datetime, str, str]] = field(default_factory=list)  # (at, sender, text)


class World:
    def __init__(self, cfg: dict[str, Any], *, jobs: list[dict[str, Any]] | None = None,
                 priors: dict[str, Any] | None = None, state_file: Path | None = None) -> None:
        self.cfg = cfg
        self.templates = load_templates()
        self.lock = threading.RLock()
        self.state_file = state_file
        self.priors = priors if priors is not None else load_priors(cfg)
        self._raw_jobs = jobs if jobs is not None else load_job_records(cfg)
        self.reset(seed=cfg["seed"])
        if state_file and state_file.exists():
            self._load_state()

    # ------------------------------------------------------------ clock
    def now(self) -> datetime:
        elapsed = (datetime.now(UTC) - self.real_start).total_seconds()
        return self.sim_start + timedelta(seconds=elapsed * self.cfg["clock"]["speed"]) + self.offset

    def advance(self, minutes: float) -> datetime:
        with self.lock:
            self.offset += timedelta(minutes=minutes)
            self._save()
            return self.now()

    # ------------------------------------------------------------ setup
    def reset(self, seed: int | None = None) -> None:
        with self.lock:
            self.seed = int(seed if seed is not None else self.cfg["seed"])
            self.real_start = datetime.now(UTC)
            self.sim_start = self.real_start
            self.offset = timedelta(0)
            self.ids = itertools.count(1)
            self.jobs: dict[str, dict[str, Any]] = {}
            self.hidden: dict[str, HiddenPrefs] = {}  # job_id -> hidden preferences
            self.job_meta: dict[str, dict[str, Any]] = {}  # planted labels, never served
            self.clients: dict[str, dict[str, Any]] = {}
            self.client_hidden: dict[str, dict[str, Any]] = {}
            self.users: dict[str, dict[str, Any]] = {}
            self.proposals: dict[str, Proposal] = {}
            self.threads: dict[str, Thread] = {}
            self.messages: dict[str, list[Message]] = {}
            self.idempotency: dict[str, dict[str, Any]] = {}
            self.policy_log: list[dict[str, Any]] = []
            self.live_counter = 0
            self._build_clients()
            self._add_jobs(self._raw_jobs, historical=True)

    def _build_clients(self) -> None:
        rng = seeded_rng(self.seed, "clients")
        pop = self.priors.get("client_population", {})
        ccfg = self.cfg["clients"]
        countries = list((pop.get("top_countries") or {"United States": 1.0}).items())
        for i in range(ccfg["count"]):
            cid = f"cl_{i:04d}"
            verified = rng.random() < pop.get("payment_verified_rate", 0.65)
            zero = rng.random() < pop.get("share_zero_spend", 0.4)
            spend = 0.0 if zero else round(_from_quantiles(pop.get("spend_usd"), rng.random(), 2000), 2)
            unrated = zero or rng.random() < pop.get("share_unrated", 0.4)
            rating = None if unrated else round(min(5.0, _from_quantiles(pop.get("rating_if_rated"), rng.random(), 4.8)), 2)
            completed = 0 if unrated else max(1, int(_from_quantiles(pop.get("feedback_count"), rng.random(), 5)))
            is_scam = rng.random() < ccfg["scam_client_share"]
            if is_scam:  # scam accounts look new and unverified more often
                verified, spend, rating, completed = rng.random() < 0.2, 0.0, None, 0
            country = rng.choices([c for c, _ in countries], weights=[w for _, w in countries])[0]
            self.clients[cid] = {
                "client_id": cid, "completed_projects": completed, "rating": rating,
                "total_spend": spend, "payment_verified": verified, "country": country,
                "member_since": (self.sim_start - timedelta(days=rng.randint(10, 2500))).date().isoformat(),
                "reviews": self._reviews(rating, completed, rng), "provenance": "synthetic",
            }
            self.client_hidden[cid] = {
                "dislikes_generic": rng.random() < ccfg["dislike_generic_share"],
                "is_scam": is_scam,
            }

    def _reviews(self, rating: float | None, completed: int, rng: Any) -> list[str]:
        if not rating or not completed:
            return []
        pool = self.templates.get("client_reviews", {})
        key = "positive" if rating >= 4.5 else "mixed" if rating >= 3.5 else "negative"
        options = pool.get(key, [])
        return rng.sample(options, k=min(len(options), min(3, completed))) if options else []

    def _add_jobs(self, rows: list[dict[str, Any]], *, historical: bool,
                  meta: dict[str, Any] | None = None) -> list[str]:
        added = []
        rng = seeded_rng(self.seed, "jobs", len(self.jobs))
        days = self.cfg["data"]["history_days"]
        client_ids = list(self.clients)
        for row in rows:
            job = {k: row.get(k) for k in PUBLIC_JOB_FIELDS}
            if not job["job_id"] or not job["title"]:
                continue
            job["skills"] = list(job.get("skills") or [])
            job["budget_type"] = job.get("budget_type") or "unknown"
            job["provenance"] = row.get("provenance") or "synthetic"
            if historical:
                job["posted_at"] = self.sim_start - timedelta(minutes=rng.uniform(0, days * 1440))
            else:
                job["posted_at"] = self.now()
            cid = row.get("client_id")
            if cid not in self.clients:
                cid = rng.choice(client_ids)
            job["client_id"] = cid
            self.jobs[job["job_id"]] = job
            self.hidden[job["job_id"]] = self._hidden_for(job, rng)
            m = dict(meta or {})
            for key in ("is_scam", "planted", "injected", "duplicate_of"):
                if row.get(key) is not None:
                    m[key] = row[key]
            if m:
                self.job_meta[job["job_id"]] = m
            added.append(job["job_id"])
        return added

    def _hidden_for(self, job: dict[str, Any], rng: Any) -> HiddenPrefs:
        lo, hi = self.cfg["clients"]["must_have_skills"]
        skills = job["skills"]
        k = min(len(skills), rng.randint(lo, hi))
        must = tuple(rng.sample(skills[: max(k, 5)], k=k)) if k else ()
        top = job.get("budget_max") or job.get("budget_min")
        ceiling = round(float(top) * rng.uniform(0.9, 1.3), 2) if top else None
        ch = self.client_hidden.get(job["client_id"], {})
        return HiddenPrefs(must, ceiling, bool(ch.get("dislikes_generic", True)),
                           bool(ch.get("is_scam", False)) or bool(job.get("is_scam")))

    # ------------------------------------------------------------ policy
    def connects_cost(self, job: dict[str, Any]) -> int:
        c = self.cfg["connects"]
        budget = job.get("budget_max") or job.get("budget_min")
        if budget and job.get("budget_type") == "hourly":
            budget = float(budget) * 40  # one week of work as a size proxy
        tiers = [t for t in c.get("cost_by_budget_usd") or [] if budget and budget >= t["min_budget"]]
        if tiers:
            return int(max(tiers, key=lambda t: t["min_budget"])["cost"])
        return int(c["cost_per_proposal"])

    def set_policy(self, update: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            c, p = self.cfg["connects"], self.cfg["policy"]
            if update.get("cost_per_proposal") is not None:
                c["cost_per_proposal"] = update["cost_per_proposal"]
                if update.get("cost_by_budget_usd") is None:
                    c["cost_by_budget_usd"] = []  # a flat cost change replaces tiers
            if update.get("cost_by_budget_usd") is not None:
                c["cost_by_budget_usd"] = update["cost_by_budget_usd"]
            if update.get("weekly_budget") is not None:
                c["weekly_budget"] = update["weekly_budget"]
            if update.get("banned_phrases") is not None:
                p["banned_phrases"] = list(update["banned_phrases"])
            if update.get("add_banned_phrases"):
                p["banned_phrases"] = sorted(set(p["banned_phrases"]) | set(update["add_banned_phrases"]))
            if update.get("max_cover_letter_words") is not None:
                p["max_cover_letter_words"] = update["max_cover_letter_words"]
            entry = {"at": self.now().isoformat(), "update": update}
            self.policy_log.append(entry)
            self._save()
            return self.policy()

    def policy(self) -> dict[str, Any]:
        return {"connects": self.cfg["connects"], "policy": self.cfg["policy"],
                "history": self.policy_log}

    # ------------------------------------------------------------ users
    def user(self, user_id: str) -> dict[str, Any]:
        if user_id not in self.users:
            self.users[user_id] = {"balance": self.cfg["connects"]["starting_balance"], "spent": []}
        return self.users[user_id]

    def connects(self, user_id: str) -> dict[str, Any]:
        with self.lock:
            u = self.user(user_id)
            week_ago = self.now() - timedelta(days=7)
            spent = sum(n for at, n in u["spent"] if datetime.fromisoformat(at) >= week_ago)
            return {"user_id": user_id, "balance": u["balance"],
                    "weekly_budget": self.cfg["connects"]["weekly_budget"],
                    "spent_this_week": spent,
                    "cost_per_proposal": self.cfg["connects"]["cost_per_proposal"]}

    # ------------------------------------------------------------ reads
    def search_jobs(self, q: str = "", since: datetime | None = None, until: datetime | None = None,
                    category: str | None = None, limit: int = 20, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
        with self.lock:
            terms = [t for t in q.lower().split() if t]
            now = self.now()
            hits = []
            for job in self.jobs.values():
                if job["posted_at"] > now:
                    continue
                if since and job["posted_at"] < since or until and job["posted_at"] > until:
                    continue
                if category and job.get("category") != category:
                    continue
                if terms:
                    hay = (job["title"] + " " + job["description"] + " " + " ".join(job["skills"])).lower()
                    if not all(t in hay for t in terms):
                        continue
                hits.append(job)
            hits.sort(key=lambda j: j["posted_at"], reverse=True)
            return len(hits), [self.public_job(j) for j in hits[offset: offset + limit]]

    def public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        out = dict(job)
        out["connects_cost"] = self.connects_cost(job)
        return out

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            if job_id not in self.jobs:
                raise NotFound(f"job {job_id} not found")
            return self.public_job(self.jobs[job_id])

    def get_client(self, client_id: str) -> dict[str, Any]:
        with self.lock:
            if client_id not in self.clients:
                raise NotFound(f"client {client_id} not found")
            return dict(self.clients[client_id])

    # ------------------------------------------------------------ idempotency
    def idem_get(self, user_id: str, route: str, key: str) -> dict[str, Any] | None:
        return self.idempotency.get(f"{user_id}|{route}|{key}")

    def idem_put(self, user_id: str, route: str, key: str, status: int, body: Any) -> None:
        self.idempotency[f"{user_id}|{route}|{key}"] = {"status": status, "body": body}
        self._save()

    # ------------------------------------------------------------ proposals
    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self.ids):06d}"

    def create_draft(self, user_id: str, data: dict[str, Any]) -> Proposal:
        with self.lock:
            job = self.jobs.get(data["job_id"])
            if job is None:
                raise NotFound(f"job {data['job_id']} not found")
            p = Proposal(
                proposal_id=self._new_id("prop"), user_id=user_id, job_id=job["job_id"],
                client_id=job["client_id"], cover_letter=data["cover_letter"],
                amount=float(data["amount"]), budget_type=data["budget_type"],
                connects_cost=self.connects_cost(job), created_at=self.now(),
            )
            self.proposals[p.proposal_id] = p
            self._save()
            return p

    def submit(self, user_id: str, proposal_id: str) -> tuple[Proposal, int, int]:
        with self.lock:
            p = self.proposals.get(proposal_id)
            if p is None or p.user_id != user_id:
                raise NotFound(f"proposal {proposal_id} not found")
            if p.submitted_at is not None:
                raise Conflict("proposal already submitted", {"proposal_id": proposal_id})
            if any(o.user_id == user_id and o.job_id == p.job_id and o.submitted_at
                   for o in self.proposals.values()):
                raise Conflict("you already submitted a proposal for this job", {"job_id": p.job_id})
            low = p.cover_letter.lower()
            banned = [b for b in self.cfg["policy"]["banned_phrases"] if b.lower() in low]
            if banned:
                raise Unprocessable("cover letter contains banned phrases", {"banned": banned})
            if len(low.split()) > self.cfg["policy"]["max_cover_letter_words"]:
                raise Unprocessable("cover letter too long")
            job = self.jobs[p.job_id]
            cost = self.connects_cost(job)  # current policy at submit time
            u = self.user(user_id)
            if u["balance"] < cost:
                raise PaymentRequired("not enough Connects", {"needed": cost, "balance": u["balance"]})
            u["balance"] -= cost
            now = self.now()
            u["spent"].append((now.isoformat(), cost))
            p.connects_cost, p.submitted_at = cost, now
            self._schedule(p, job)
            self._save()
            return p, cost, u["balance"]

    def _schedule(self, p: Proposal, job: dict[str, Any]) -> None:
        rng = seeded_rng(self.seed, p.user_id, p.job_id, p.client_id)
        prefs = self.hidden[p.job_id]
        d = decide(letter=p.cover_letter, amount=p.amount, job=job, prefs=prefs,
                   priors=self.priors, cfg=self.cfg, rng=rng, seed=self.seed)
        t = self.cfg["decision"]["timing_minutes"]
        at = p.submitted_at or self.now()

        def later(key: str, after: datetime) -> datetime:
            lo, hi = t[key]
            return after + timedelta(minutes=rng.uniform(lo, hi))

        sched: list[tuple[str, datetime]] = [("submitted", at)]
        if d.viewed:
            sched.append(("viewed", later("viewed", at)))
        if d.replied:
            sched.append(("replied", later("replied", sched[-1][1])))
        if d.interview:
            sched.append(("interview", later("interview", sched[-1][1])))
        if d.hired:
            sched.append(("hired", later("hired", sched[-1][1])))
        else:
            sched.append(("lost", max(later("lost", at), sched[-1][1] + timedelta(minutes=60))))
        p.schedule = sched
        p.decision = asdict(d) | {"prefs_scam": prefs.is_scam}
        if d.replied:
            self._plan_thread(p, sched, rng, prefs.is_scam)

    def _plan_thread(self, p: Proposal, sched: list[tuple[str, datetime]], rng: Any, scam: bool) -> None:
        msgs = self.templates["client_messages"]
        thread = Thread(self._new_id("th"), p.user_id, p.client_id, p.job_id, p.proposal_id)
        times = dict(sched)
        if scam:
            thread.pending.append((times["replied"], "client", rng.choice(msgs["scam_signal"])))
        else:
            kind = rng.choice(["question", "question", "negotiation"])
            thread.pending.append((times["replied"], "client", rng.choice(msgs[kind])))
            if "interview" in times:
                thread.pending.append((times["interview"], "client", rng.choice(msgs["interview_request"])))
            if "hired" in times:
                thread.pending.append((times["hired"], "client", rng.choice(msgs["hired"])))
            elif "lost" in times:
                thread.pending.append((times["lost"], "client", rng.choice(msgs["lost"])))
        p.thread_id = thread.thread_id
        self.threads[thread.thread_id] = thread
        self.messages[thread.thread_id] = []

    def state_of(self, p: Proposal) -> tuple[str, list[dict[str, Any]]]:
        if p.submitted_at is None:
            return "draft", []
        now = self.now()
        visible = [(s, at) for s, at in p.schedule if at <= now]
        state = visible[-1][0] if visible else "submitted"
        return state, [{"state": s, "at": at} for s, at in visible]

    def public_proposal(self, p: Proposal) -> dict[str, Any]:
        state, events = self.state_of(p)
        visible_thread = p.thread_id if p.thread_id and self._thread_started(p.thread_id) else None
        return {
            "proposal_id": p.proposal_id, "user_id": p.user_id, "job_id": p.job_id,
            "client_id": p.client_id, "cover_letter": p.cover_letter, "amount": p.amount,
            "budget_type": p.budget_type, "state": state, "connects_cost": p.connects_cost,
            "created_at": p.created_at, "submitted_at": p.submitted_at, "events": events,
            "thread_id": visible_thread,
        }

    def list_proposals(self, user_id: str, state: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            out = [self.public_proposal(p) for p in self.proposals.values() if p.user_id == user_id]
            return [o for o in out if state is None or o["state"] == state]

    def get_proposal(self, user_id: str, proposal_id: str) -> dict[str, Any]:
        with self.lock:
            p = self.proposals.get(proposal_id)
            if p is None or p.user_id != user_id:
                raise NotFound(f"proposal {proposal_id} not found")
            return self.public_proposal(p)

    # ------------------------------------------------------------ messages
    def _thread_started(self, thread_id: str) -> bool:
        self._deliver(thread_id)
        return bool(self.messages.get(thread_id))

    def _deliver(self, thread_id: str) -> None:
        th = self.threads[thread_id]
        now = self.now()
        due = [m for m in th.pending if m[0] <= now]
        th.pending = [m for m in th.pending if m[0] > now]
        for at, sender, text in sorted(due):
            self.messages[thread_id].append(Message(self._new_id("msg"), thread_id, sender, text, at))
        if due:
            self._save()

    def list_threads(self, user_id: str) -> list[dict[str, Any]]:
        with self.lock:
            out = []
            for th in self.threads.values():
                if th.user_id != user_id or not self._thread_started(th.thread_id):
                    continue
                msgs = self.messages[th.thread_id]
                out.append({"thread_id": th.thread_id, "user_id": th.user_id,
                            "client_id": th.client_id, "job_id": th.job_id,
                            "proposal_id": th.proposal_id, "last_message_at": msgs[-1].sent_at,
                            "message_count": len(msgs)})
            return sorted(out, key=lambda t: t["last_message_at"], reverse=True)

    def list_messages(self, user_id: str, thread_id: str) -> list[dict[str, Any]]:
        with self.lock:
            th = self.threads.get(thread_id)
            if th is None or th.user_id != user_id or not self._thread_started(thread_id):
                raise NotFound(f"thread {thread_id} not found")
            return [asdict(m) for m in self.messages[thread_id]]

    def send_message(self, user_id: str, thread_id: str, text: str) -> dict[str, Any]:
        with self.lock:
            th = self.threads.get(thread_id)
            if th is None or th.user_id != user_id or not self._thread_started(thread_id):
                raise NotFound(f"thread {thread_id} not found")
            low = text.lower()
            banned = [b for b in self.cfg["policy"]["banned_phrases"] if b.lower() in low]
            if banned:
                raise Unprocessable("message contains banned phrases", {"banned": banned})
            msg = Message(self._new_id("msg"), thread_id, "freelancer", text, self.now())
            self.messages[thread_id].append(msg)
            # A simple follow up from the client after a reply, unless the thread is closed.
            rng = seeded_rng(self.seed, thread_id, len(self.messages[thread_id]))
            if not self.client_hidden.get(th.client_id, {}).get("is_scam") and rng.random() < 0.5:
                follow = rng.choice(self.templates["client_messages"]["question"])
                th.pending.append((self.now() + timedelta(minutes=rng.uniform(30, 600)), "client", follow))
            self._save()
            return asdict(msg)

    # ------------------------------------------------------------ live stream
    def live_tick(self, n: int = 1) -> list[str]:
        """Add n live jobs: fresh reposts, near duplicates, scams and injected posts."""
        with self.lock:
            added: list[str] = []
            mix = self.cfg["live"]["mix"]
            kinds, weights = list(mix), list(mix.values())
            base_jobs = [j for j in self.jobs.values() if not self.job_meta.get(j["job_id"], {}).get("planted")]
            for _ in range(n):
                self.live_counter += 1
                rng = seeded_rng(self.seed, "live", self.live_counter)
                kind = rng.choices(kinds, weights=weights)[0]
                src = dict(rng.choice(base_jobs)) if base_jobs else {}
                row: dict[str, Any] = {**src, "job_id": f"live_{self.live_counter:05d}", "client_id": None}
                if kind == "duplicate" and src:
                    prefix = rng.choice(self.templates["duplicate_title_prefixes"])
                    row |= {"title": prefix + src["title"], "duplicate_of": src["job_id"], "planted": "duplicate",
                            "provenance": "synthetic"}
                elif kind == "scam":
                    t = rng.choice(self.templates["scam_jobs"])
                    row |= {"title": t["title"], "description": t["description"], "skills": [],
                            "category": "other", "budget_type": "fixed", "budget_min": 500.0,
                            "budget_max": 500.0, "is_scam": True, "planted": "scam", "provenance": "synthetic"}
                elif kind == "injection" and src:
                    row |= {"description": src["description"] + rng.choice(self.templates["injection_suffixes"]),
                            "injected": True, "planted": "injection", "provenance": "synthetic"}
                added += self._add_jobs([row], historical=False)
            self._save()
            return added

    def load_jobs(self, rows: list[dict[str, Any]], replace: bool = False) -> list[str]:
        with self.lock:
            if replace:
                self.jobs.clear()
                self.hidden.clear()
                self.job_meta.clear()
            ids = self._add_jobs(rows, historical=True)
            self._save()
            return ids

    def load_clients(self, rows: list[dict[str, Any]]) -> list[str]:
        """Load clients from JSON. Optional `hidden` dict per row sets hidden preferences."""
        with self.lock:
            ids = []
            for r in rows:
                cid = r["client_id"]
                hidden = r.pop("hidden", {}) or {}
                base: dict[str, Any] = {"completed_projects": 0, "rating": None, "total_spend": 0.0,
                        "payment_verified": False, "country": None,
                        "member_since": self.sim_start.date().isoformat(), "reviews": [],
                        "provenance": "synthetic"}
                self.clients[cid] = base | r
                self.client_hidden[cid] = {"dislikes_generic": bool(hidden.get("dislikes_generic", True)),
                                           "is_scam": bool(hidden.get("is_scam", False))}
                ids.append(cid)
            self._save()
            return ids

    # ------------------------------------------------------------ persistence
    def _save(self) -> None:
        """Persist the mutable state so a restart keeps proposals, spend and idempotency."""
        if not self.state_file:
            return
        next_id = next(self.ids)
        state: dict[str, Any] = {
            "seed": self.seed, "offset_s": self.offset.total_seconds(),
            "sim_start": self.sim_start.isoformat(), "real_start": self.real_start.isoformat(),
            "next_id": next_id, "users": self.users, "idempotency": self.idempotency,
            "proposals": [asdict(p) for p in self.proposals.values()],
            "threads": [asdict(t) for t in self.threads.values()],
            "messages": {k: [asdict(m) for m in v] for k, v in self.messages.items()},
            "policy": {"connects": self.cfg["connects"], "policy": self.cfg["policy"], "log": self.policy_log},
            "live_counter": self.live_counter,
        }
        # next(self.ids) consumed one id; rebuild the counter from it
        self.ids = itertools.count(next_id)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str), encoding="utf-8")
        tmp.replace(self.state_file)

    def _load_state(self) -> None:
        assert self.state_file is not None
        s = json.loads(self.state_file.read_text(encoding="utf-8"))
        if s.get("seed") != self.seed:
            self.reset(seed=s["seed"])
        dt = datetime.fromisoformat
        self.offset = timedelta(seconds=s["offset_s"])
        self.sim_start, self.real_start = dt(s["sim_start"]), dt(s["real_start"])
        self.ids = itertools.count(s["next_id"])
        self.users = s["users"]
        self.idempotency = s["idempotency"]
        self.cfg["connects"], self.cfg["policy"] = s["policy"]["connects"], s["policy"]["policy"]
        self.policy_log = s["policy"]["log"]
        self.live_counter = s["live_counter"]
        for p in s["proposals"]:
            p["created_at"] = dt(p["created_at"])
            p["submitted_at"] = dt(p["submitted_at"]) if p["submitted_at"] else None
            p["schedule"] = [(st, dt(at)) for st, at in p["schedule"]]
            self.proposals[p["proposal_id"]] = Proposal(**p)
        for t in s["threads"]:
            t["pending"] = [(dt(at), sender, text) for at, sender, text in t["pending"]]
            self.threads[t["thread_id"]] = Thread(**t)
        for k, msgs in s["messages"].items():
            self.messages[k] = [Message(**(m | {"sent_at": dt(m["sent_at"])})) for m in msgs]
        if self.live_counter:  # re-create live jobs deterministically
            n, self.live_counter = self.live_counter, 0
            self.live_tick(n)
