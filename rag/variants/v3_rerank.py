"""V3: cross-encoder reranking of the top candidates (model and top_n in config)."""

from rag.variants.base import Flags, Pipeline


class V3Rerank(Pipeline):
    name = "v3_rerank"
    flags = Flags(rerank=True)
