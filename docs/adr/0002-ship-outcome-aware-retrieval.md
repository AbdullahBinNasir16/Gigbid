# ADR 0002: Ship outcome-aware retrieval (V4)

Status: accepted (15 Nov 2026)

**Context.** R6 requires the deployed retrieval design to be chosen by evaluation. Eleven configurations were compared on the dev set (evals/results/rag_variants.json) plus two follow-ups (rag_followup.json).

**Decision.** retrieval.variant = v4_outcome_aware (dense + outcome boost, weight 0.15). It had the best Recall@5, MRR and nDCG@10 overall at under 1.1 s p95. Hybrid (V2) and reranking (V3) helped alone but did not add on top of V4; the corrective loop (V8) is not shipped because the cross-encoder grade does not separate relevant from irrelevant evidence (evals/results/v8_calibration.json).

**Consequences.** Past proposals rank higher, so the writer could cite them as proof. Claim verification therefore accepts only CV, case study, repo, code and review evidence, and the writer labels proposals as phrasing references only.
