"""V2: BM25 plus dense with reciprocal rank fusion.

Targets exact tool names ("Celery", "dbt", "Pinecone") that embeddings blur.
"""

from rag.variants.base import Flags, Pipeline


class V2Hybrid(Pipeline):
    name = "v2_hybrid"
    flags = Flags(hybrid=True)
