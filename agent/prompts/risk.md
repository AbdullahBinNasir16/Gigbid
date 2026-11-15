<!-- version: risk/v1 -->
Rule-based node (no LLM by default). Signals and weights live in agent/config.yaml under
risk_rules. This file documents the policy: scam = off-platform payment or contact, upfront
deposits, requests for ID/bank logins, unpaid "trial" production work, payment only after
launch; injection = text addressing an AI assistant or trying to change instructions.
