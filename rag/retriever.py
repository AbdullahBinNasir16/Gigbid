"""Retriever factory: the variant (or composition) is chosen by config, never in code.

retrieval.variant names the base variant; retrieval.compose lists variants whose flags are
OR-ed together, e.g. [v1_decomposition, v2_hybrid, v3_rerank] is decomposition + hybrid +
rerank in one pipeline.
"""

from __future__ import annotations

from agent.config import get_config
from rag.index.store import get_index
from rag.variants.base import Flags, Pipeline
from rag.variants.v0_naive import V0Naive
from rag.variants.v1_decomposition import V1Decomposition
from rag.variants.v2_hybrid import V2Hybrid
from rag.variants.v3_rerank import V3Rerank
from rag.variants.v4_outcome_aware import V4OutcomeAware
from rag.variants.v5_multivector import V5MultiVector
from rag.variants.v8_corrective import V8Corrective

VARIANTS: dict[str, type[Pipeline]] = {
    v.name: v
    for v in (V0Naive, V1Decomposition, V2Hybrid, V3Rerank, V4OutcomeAware, V5MultiVector,
              V8Corrective)
}


def flags_for(names: list[str]) -> Flags:
    flags = Flags()
    for n in names:
        if n not in VARIANTS:
            raise KeyError(f"unknown retrieval variant '{n}'; known: {sorted(VARIANTS)}")
        flags = flags | VARIANTS[n].flags
    return flags


def get_retriever(persona: str, variant: str | None = None,
                  compose: list[str] | None = None) -> Pipeline:
    cfg = get_config().retrieval
    names = [variant or cfg.variant, *(cfg.compose if compose is None else compose)]
    p = Pipeline(get_index(persona), flags_for(names))
    p.name = "+".join(names)
    return p
