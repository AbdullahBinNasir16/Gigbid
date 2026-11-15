# GigSim API

GigSim is a **student built** marketplace simulator for GigBid. This file is the only source
of endpoint facts for the marketplace MCP server (`mcp_servers/marketplace/adapters/gigsim.py`).

Base URL: `http://localhost:8081` (compose service `gigsim`). All times are UTC, ISO 8601,
in **simulated time** (see Clock).

## Auth and headers

| Header | Where | Meaning |
|---|---|---|
| `Authorization: Bearer <GIGSIM_API_TOKEN>` | every non admin endpoint except `/health` | missing or wrong token gives `401` |
| `X-GigSim-User: <user id>` | optional, default `default` | which freelancer account the call acts for. Connects, proposals and threads are scoped to it. |
| `Idempotency-Key: <8 to 200 chars>` | **required** on `POST /proposals`, `POST /proposals/{id}/submit`, `POST /threads/{id}/messages` | missing key gives `400`. A retry with the same key (same user, same route) returns the stored response with header `Idempotent-Replayed: true` and never repeats the side effect or the Connects spend. Error outcomes (402, 409, 422) are stored too. Keys survive a restart when `GIGSIM_STATE_FILE` is set. |
| `Authorization: Bearer <GIGSIM_ADMIN_TOKEN>` | `/admin/*` | admin endpoints only |

## Limits and errors

* **Rate limit:** token bucket per user. Default 120 requests per minute with a burst of 30
  (`gigsim/config.yaml` → `limits`). When empty: `429` with `Retry-After: <seconds>` and body
  `{"error": "rate_limited", "retry_after": <float>}`. Admin and `/health` are exempt.
  Clients should stay under 2 requests per second per user.
* **Simulated outages:** with `chaos.error_rate > 0` a seeded share of requests gets
  `503 {"error": "service_unavailable"}`. Default 0. Change it live with `POST /admin/chaos`.
* **Error body:** `{"error": "<message>", "detail": <object or null>}`.

| Code | When |
|---|---|
| 400 | missing or invalid Idempotency-Key |
| 401 | missing or wrong token |
| 402 | not enough Connects (`detail.needed`, `detail.balance`) |
| 404 | unknown job, client, proposal or thread, or one owned by another user |
| 409 | proposal already submitted, or this user already submitted for this job |
| 422 | validation error, banned phrase in letter or message (`detail.banned`), letter over the word limit |
| 429 | rate limited |
| 503 | simulated outage |

## Clock

Simulated time runs `clock.speed` times faster than real time (default 60: one real second is
one simulated minute). `POST /admin/advance?minutes=N` jumps forward. Outcomes and client
messages appear when simulated time passes their scheduled time.

## Public endpoints

### `GET /health`
`200 {"status": "ok", "service": "gigsim", "jobs": <int>, "sim_time": "<iso>"}`. No auth.

### `GET /jobs`
Query: `q` (all words must appear in title, description or skills; case insensitive),
`category`, `since`, `until` (ISO datetimes on `posted_at`), `limit` (1 to 100, default 20),
`offset` (default 0). Newest first. Only jobs with `posted_at <= sim_time`.

`200 {"total": <int>, "items": [Job, ...]}`

**Job:** `job_id`, `title`, `description`, `skills[]`, `category`, `budget_type`
(`fixed` | `hourly` | `unknown`), `budget_min`, `budget_max` (USD; hourly values are rates),
`posted_at`, `client_id`, `connects_cost` (current policy), `experience_level`, `applicants`
(bucket text, e.g. `"5 to 10"`), `provenance` (`real` | `synthetic`), `source_dataset`.
Planted labels (scam, injection, duplicate) are **never** returned.

### `GET /jobs/{job_id}` → `200 Job` or `404`

### `GET /clients/{client_id}` → `200 Client` or `404`
**Client:** `client_id`, `completed_projects`, `rating` (0 to 5 or null), `total_spend`,
`payment_verified`, `country`, `member_since` (date), `reviews[]`, `provenance`.
Hidden preferences (must have skills, budget ceiling, dislike of generic openings, scam flag)
are **never** returned.

### `GET /connects`
`200 {"user_id", "balance", "weekly_budget", "spent_this_week", "cost_per_proposal"}`.
New users start with `connects.starting_balance` (default 120).

### `POST /proposals` (create draft, idempotent)
Body: `{"job_id": str, "cover_letter": str (1 to 10000 chars), "amount": float > 0,
"budget_type": "fixed" | "hourly", "screening_answers": [str] (max 10)}`. Unknown fields: `422`.
`201 Proposal` in state `draft`. No Connects are spent.

### `POST /proposals/{proposal_id}/submit` (idempotent)
Spends Connects at the **current** policy cost and schedules the client's reaction.
`200 {"proposal": Proposal, "connects_spent": int, "balance_after": int}`.
Errors: `402`, `404`, `409` (already submitted, or another proposal for the same job by this
user), `422` (banned phrase, too long).

**Proposal:** `proposal_id`, `user_id`, `job_id`, `client_id`, `cover_letter`, `amount`,
`budget_type`, `state` (`draft`, `submitted`, `viewed`, `replied`, `interview`, `hired`,
`lost`), `connects_cost`, `created_at`, `submitted_at`, `events[]` (`{state, at}` revealed so
far), `thread_id` (set once the client has written).

### `GET /proposals?state=<state>` → `200 [Proposal]` (this user only)
### `GET /proposals/{proposal_id}` → `200 Proposal` or `404`

### `GET /threads` → `200 [Thread]`
**Thread:** `thread_id`, `user_id`, `client_id`, `job_id`, `proposal_id`, `last_message_at`,
`message_count`. A thread exists once the client replies to a proposal.

### `GET /threads/{thread_id}/messages` → `200 [Message]`
**Message:** `message_id`, `thread_id`, `sender` (`client` | `freelancer` | `system`), `text`,
`sent_at`. Client messages include questions, negotiation, interview requests and, for scam
clients, scam signals (off platform payment, requests for personal data, free work).

### `POST /threads/{thread_id}/messages` (idempotent)
Body `{"text": str (1 to 5000)}`. `201 Message`. `422` on banned phrases.

## Admin endpoints (Bearer GIGSIM_ADMIN_TOKEN)

| Endpoint | Purpose |
|---|---|
| `POST /admin/reset?seed=<int>` | rebuild the world from data with a seed (clears proposals, threads, users) |
| `POST /admin/jobs?replace=<bool>` | body: JSON list of jobs (same fields as Job; optional `client_id`, `is_scam`, `planted`, `injected`, `duplicate_of`). Used to plug in a hidden test set. |
| `POST /admin/clients` | body: JSON list of clients; optional `hidden: {dislikes_generic, is_scam}` per client |
| `GET /admin/policy` | current Connects and policy settings with change history |
| `POST /admin/policy` | policy update: `cost_per_proposal` (replaces tiers unless `cost_by_budget_usd` is also given), `cost_by_budget_usd`, `weekly_budget`, `banned_phrases`, `add_banned_phrases`, `max_cover_letter_words`, `note`. Applies to the next submit. |
| `POST /admin/chaos` | `{"error_rate": 0..1, "requests_per_minute": int, "burst": int}` |
| `POST /admin/advance?minutes=N` | move simulated time forward |
| `POST /admin/live/tick?n=N` | add N live jobs now (fresh reposts, near duplicates, scams, injected posts) |

## Connects cost rule

Default: tiers on job size from `connects.cost_by_budget_usd` (0 → 4, 500 → 6, 2000 → 10;
for hourly jobs size = max rate × 40 hours). Without matching tiers, `cost_per_proposal`
(default 6). The real 60k dataset shows 1 to 8 Connects per job (later doubled on the real
site), so these defaults sit in the real range.

## Client behaviour (summary)

See `gigsim/README.md` for the full rule. In short: base reply rate from competition
(real applicant counts), multiplied by `exp(sum of weighted features)`: naming the client's
hidden must have skills, citing concrete past work, no generic opening, mirroring the
problem, price under the hidden ceiling, and a sensible length. Seeded per (user, job,
client), so outcomes are repeatable.
