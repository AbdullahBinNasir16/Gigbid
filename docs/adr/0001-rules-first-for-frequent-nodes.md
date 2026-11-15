# ADR 0001: Rules before LLMs for frequent nodes

Status: accepted (15 Nov 2026)

**Context.** Scout, Risk, Analyst, Pricing and Compliance run on every job. On the target laptop a 3B model generates about 1.2 tokens/s (evals/results/llm_speed.json) and 7B does not fit in RAM next to the stack.

**Decision.** These nodes are deterministic rules whose tables live in agent/config.yaml (risk signals, thresholds, Connects tiers, banned phrases). LLMs are used where text must be generated or judged: writer, critic, liaison, and optionally the analyst (generation.analyst_mode).

**Consequences.** A job is analysed in about 2 s at zero model cost (evals/results/decisions.json), the change request is a YAML edit, and decisions are explainable. Rules miss semantic matches; the analyst can be switched to LLM mode when a hosted model is available.
