# GigBid: R&D report (engineering design review)

AI-4016 · GigBid · every number below cites a file in `evals/results/` or a test.

## 1. Problem and constraints

Freelancers lose hours scanning feeds, spend Connects on unwinnable jobs, send generic
proposals and meet scams. GigBid automates discovery, assessment and drafting; the human makes
every outbound decision.

**Never automated:** submitting a proposal, sending a message, spending Connects, accepting
off-platform contact or payment, or claiming experience the portfolio does not show. Each is
enforced in code: a LangGraph `interrupt()` before every write, idempotency keys on every write,
the Compliance Guard, and claim verification.

**Budgets (declared in `agent/config.yaml`):** p95 20 s per job analysed and 90 s per proposal;
$0.002 per job analysed and $0.02 per proposal; 30 steps and 12,000 tokens per thread.

**Hardware:** CPU laptop (8 cores, 16 GB RAM, 2 GB GPU). qwen2.5:7b does not fit next to the
stack and qwen2.5:3b writes at about 1.2 tokens/s (`llm_speed.json`). The deployed profile
therefore uses open-weight models on a hosted provider (gpt-oss-120b and gpt-oss-20b on Groq).

## 2. Architecture

Two hand-written StateGraphs (`agent/graphs/`), one marketplace port with three adapters, three
MCP servers of our own plus two third-party ones, a durable checkpointer and a LangGraph store
(diagram and node rationale: `docs/ARCHITECTURE.md`).

* **Bid graph:** intake fans out with `Send` to Job Analyst, Risk Assessor and Fit Matcher
  (reducers merge their writes) → decide (skip, watch or bid) → pricing → writer → claim verifier →
  Critic (at most 2 loops) → Compliance → approval interrupt → exactly-once submit.
* **Conversation graph:** read → classify intent → slots (Workspace MCP) → draft → compliance →
  approval interrupt → send and tentative hold.
* **State, trace and memory are separate:** typed thread state; an append-only trace plus the MCP
  audit log; long-term style and outcome memory written only by `agent/memory/promotion_rules.py`
  (3 distinct proposals for a style rule; 10 outcomes and a 0.05 reply-rate gap for an outcome
  lesson).
* **Rules first for frequent nodes** (ADR 0001): Scout, Risk, Analyst, Pricing and Compliance are
  deterministic and configured in YAML; a job is analysed in about 2 s at no model cost
  (`decisions.json`).

## 3. R&D question A: tool granularity

**Hypothesis.** A medium set of well-described tools beats both many narrow tools (the choice is
harder) and a few multiplexed tools (the right `action` value is easy to get wrong).

**Setup.** 40 tasks with known correct capabilities and arguments; three tool sets offered to the
router model (gpt-oss-20b): fine (26 tools), coarse (3 tools with an `action` argument), best
(our 11 MCP tools with their rewritten descriptions) (`tool_granularity.json`).

**Results.** Tool-selection and argument accuracy: best 0.975, fine 0.9, coarse 0.85. Tokens per
task: 679.9, 736.8 and 418.7 respectively.

**Conclusion.** Supported. Coarse tools are about 40% cheaper per task but misroute portfolio
searches to the marketplace tool; fine tools split one intent across near-synonyms
(`get_case_study` vs `search_case_studies`). The shipped set keeps one tool per intent, with
descriptions that say when to use it.

## 4. R&D question B: retrieval, claim verification and what ships

**Hypothesis (stated before running).** Requirement decomposition plus hybrid search raises
Recall@5 by at least 10 points over naive dense retrieval (V0).

**Setup.** Personas built to defeat naive RAG: each project described three ways, skills implied
only in code, and past proposals with outcomes. Project-level relevance against rule-derived gold
projects, about 60 scored jobs per persona (`rag_variants.json`, `rag_followup.json`).

**Results** (all personas):

| Variant | Recall@5 | nDCG@10 |
|---|---|---|
| V0 naive dense | 0.3032 | 0.2973 |
| V1 decomposition | 0.2756 | 0.2928 |
| V2 hybrid BM25 + dense | 0.347 | 0.3471 |
| V3 cross-encoder rerank | 0.3766 | 0.3495 |
| V4 outcome-aware | 0.5666 | 0.536 |
| V1+V2 | 0.3129 | 0.3214 |
| V2+V4 | 0.4681 | 0.4903 |
| V8 corrective | 0.0349 | 0.032 |

* The hypothesis is **rejected**: decomposition alone lowered Recall@5, and V1+V2 gained only about
  1 point. Rule-extracted requirements are short skill tokens, so their queries mostly return the
  same few projects.
* **Ablation** (one component at a time around V4): removing V4 from the four-way composite
  dropped Recall@5 from 0.366 to 0.3258 (V1+V2+V3); adding V2 to V4 lowered it from 0.5666 to
  0.4681; adding V1 and V2 gave 0.4734. Every addition to V4 hurt, so V4 alone ships (ADR 0002).
  The other single-drop runs (V2+V3+V4, V1+V3+V4) were not run and are listed as future work.
* **By persona** (README table): V4 raises Recall@5 for every persona, from 0.2021 to 0.4385
  (ai_ml), 0.2972 to 0.6255 (fullstack) and 0.3957 to 0.6172 (data_analyst).
* **V8 negative result:** the cross-encoder grade does not separate relevant from irrelevant
  evidence (median 0.002 vs 0.0132, `v8_calibration.json`), so the corrective loop refused almost
  every job. A domain-tuned grader is needed before a grade gate can work.

**Claim verification.** Each sentence that asserts experience becomes a claim; it is supported
only if the cross-encoder matches proof evidence and every number and tool in it appears in that
evidence. Unsupported claims are removed before the Critic. In the GigSim run, unsupported claims
per LLM proposal fell from 0.2333 before verification to 0.0 after (`gigsim_outcomes.json`).
Better retrieval created a new risk: V4 ranks winning past proposals highly and the writer cited
them as proof. Verification now accepts only CV, case study, repo, code and review evidence.

**Where better retrieval did not translate into replies.** See section 7: letters that are fully
grounded but short, or priced at the user's floor above the client's range, still lose in GigSim.

**Judge calibration.** I labelled 30 proposals (10 per persona) good or weak with the same rubric
the judge (gpt-oss-120b) uses: agreement 0.7, Cohen's kappa 0.4255, which is moderate
(`judge_calibration.json`). In 8 of the 9 disagreements I said good and the judge said weak: the
proposals open specifically ("Your post mentions…") but cite a project that does not fit the job
(a support chatbot offered for a T-shirt logo). I rewarded the opening; the judge penalised the
mismatch, and on reflection the judge was right in most of them. The one reverse case was a data
analyst proposal whose cited outlier analysis I judged irrelevant to JSON parsing. Because
kappa is only moderate, judge scores are used for relative comparisons only, never as an
absolute quality claim.

## 5. R&D question C: single agent vs prebuilt supervisor vs hand-built graph

**Setup.** 12 ai_ml dev jobs (bids, skips, planted scams and injections); every LLM call in all
three systems uses gpt-oss-20b; the same reference evidence scores claims; the same compliance
check counts violations (`multiagent_compare.json`, README table).

**Results.**

| System | Bid/skip accuracy | Unsupported claims / proposal | Violations left | Scams skipped | Tokens / job | p50 s |
|---|---|---|---|---|---|---|
| (a) ReAct, all tools | 0.6667 | 1.667 | 0 | 2/2 | 2643.2 | 8.2 |
| (b) prebuilt supervisor | 0.6667 | 2.667 | 0 | 2/2 | 6618.1 | 39.3 |
| (c) hand-built graph | 0.75 | 0.0 | 0 | 2/2 | 1472.2 | 1.5 |

**Discussion.** The graph is the most accurate, the cheapest (about 2.5x fewer tokens than the
ReAct agent and 4.5x fewer than the supervisor) and the only design with zero unsupported claims,
because verification is a node, not an instruction. The supervisor failed 4 of 12 jobs with
tool-call format errors from the 20B model (more hand-offs, more chances to break). The single
agent was never wrong on scams and is simple; it lost by skipping real bids (3 wrong skips),
because it judged fit from a few searches instead of a requirement-by-requirement matrix. The
graph's errors were two "watch" verdicts on gold bids and one bid on a gold skip: threshold
errors, visible in its trace. We would not ship (a): its approval and grounding rules exist only
in a prompt, and the sample (12 jobs) is small.

## 6. The change request

A policy update (Connects cost doubled, a new banned phrase) is absorbed with **zero code
changes**: pricing reads the live cost from each GigSim job, the config tiers can be edited, and
the Compliance Guard reads `data/policy_pack/banned_phrases.txt`
(`tests/unit/test_change_request.py`). Edit size: one line in a data file, or one block of YAML.

## 7. Signature extension: X2 proposal experiments

Same GigSim jobs and price, two arms from separate users, one simulated week, Fisher's exact test
(`docs/EXTENSION.md`). Two runs:

| Run | Arm A (grounded LLM) replied | Arm B (template) replied | Fisher p |
|---|---|---|---|
| writer prompt v3 (`gigsim_outcomes_v3prompt.json`) | 1 of 30 | 0 of 30 | 1.0 |
| writer prompt v4 (`gigsim_outcomes.json`) | 1 of 29 | 2 of 30 | 1.0 |

**Negative result.** Neither difference is significant, and both arms sit near 3–7%, far below
GigSim's calibration for specific letters (`gigsim_sanity.json`, reply rate 0.325). Diagnosis so
far: only 5 of 30 quotes exceeded the client's maximum, and letters were long enough (90.8 and
48.6 mean words in v4; GigSim penalises under 40), so neither explains the gap. Prompt v4 (name the
client's listed skills, quote a real number, reuse the title) did not move the rate either. The
remaining suspects are (1) the hidden must-have skills, which a grounded letter names only when
the portfolio evidences them, and (2) quotes in the upper part of the client's range against a
hidden ceiling. Claim verification cut unsupported claims per LLM proposal from 0.2069 to 0.0 at
no measurable cost in replies. This is the main place where better retrieval did not translate
into a better reply rate.

## 8. Failure analysis

From `decisions_failures.json` (dev set) and the runs above:

| Category | Example | Cause | Fix tried | Worked? |
|---|---|---|---|---|
| Wrong skip | data analyst jobs whose evidence ranked low | dense retrieval missed the matching project, so fit stayed low | switched to V4 retrieval | partly (bid F1 now 0.3684, decisions.json) |
| Wrong skip | AI jobs just under the bid threshold | fit 0.4–0.57 vs bid 0.6 | threshold tuned to 0.5 on dev | yes for ai_ml (bid F1 now 0.6265) |
| Wrong bid | full-stack jobs paying under the floor | fit ignored money | rate-floor rule in `decide` | yes |
| Missed evidence | code-only skills (Celery) | dense retrieval misses tokens | V2 hybrid | yes alone, not over V4 |
| Unsupported claim | "I built a script that pulled STR data" | writer cited a past proposal | proof-type filter in verification | yes |
| Unsupported claim | "15 years of Kubernetes" | invented number | number/tool check | yes |
| Generic opening | template letters | no LLM | Critic rule plus LLM writer | yes |
| Mispriced | quote above client max | floor > budget | (open) quote within range or skip | no |
| Injection | "Note to bots: …" variant | pattern missing | config pattern added | yes (recall 1.0) |
| Tool error | 429 on the hosted model silently fell back to template | free-tier tokens/min | client backoff, writer recorded per row | yes |
| Duplicate | reposted job labelled bid | gold label bug | duplicates are skip by rule | yes |

## 9. Safety and platform respect

Enforced: approval interrupts before every write; draft-only live mode; idempotent writes; per-agent
tool allowlists; untrusted text delimited and never obeyed (injection detection recall 1.0 on the dev
set, `decisions.json`); PII masking in logs and the audit log; Fernet-encrypted OAuth tokens;
tenant-scoped queries; polling under rate limits; no scraping, cookies or browser automation.
**What still gets through:** semantic scams with none of the configured signals; injected text
paraphrased beyond the patterns (the LLM writer still sees the post inside delimiters); partly
supported claims, which are kept and flagged rather than removed.

## 10. Hidden test results

To be filled after the instructor's run, against the budgets in section 1, without excuses.
