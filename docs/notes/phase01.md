# Phase 1 notes: config, handoffs, state, port

## Which file does what
- agent/config.yaml: every model (per node, per profile), budget, threshold, Connects rule, memory threshold, tool allowlist and retrieval choice. Kit keys are kept.
- agent/config.py: Pydantic models that validate the YAML at startup. MODEL_PROFILE and MARKETPLACE_MODE env vars override the profile and mode. `connects_cost_for()` turns a budget into a Connects cost using the config tiers.
- agent/llm.py: `get_llm(node)` is the only place a node name becomes a chat model. One OpenAI-compatible client reaches the local model server, a hosted open-weight provider or a paid provider. Cheap nodes get a fallback model.
- agent/handoffs.py: the Pydantic objects agents exchange (JobSpec, RiskReport, FitReport, BidDecision, PriceQuote, ProposalDraft, Critique, ComplianceVerdict, Evidence, ApprovalPayload, ApprovalDecision, OutcomeEvent). Extra fields are forbidden, so injected keys are rejected.
- agent/state.py: BidState and ConversationState. Reducers merge parallel writes (analyses, evidence, counters, trace). `trace` is a separate append-only audit list. Long-term memory is not in state.
- agent/marketplace_port.py: the abstract port, its typed errors (RateLimited, Unavailable, AuthFailed, InvalidRequest) and a factory that loads the adapter named by `marketplace.mode` through an import string.
- mcp_servers/marketplace/adapters/fake.py: an in-memory adapter for tests and offline work. It follows the same idempotency and dry_run rules as the real adapters.

## Three ways it could break
1. A node returns the whole state instead of a partial dict. Reducers would then double-count counters and duplicate trace events.
2. A new adapter path in config.yaml has a typo. The factory only fails when that mode is first used, not at startup.
3. The fake adapter keeps idempotency results in memory. The real marketplace server must store them in Postgres or Redis (Phase 2), or a restart breaks exactly-once submission.
