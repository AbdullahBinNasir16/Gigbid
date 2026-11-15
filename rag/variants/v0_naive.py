"""V0 baseline: dense top-k cosine on the whole job post. Everything else must beat it."""

from rag.variants.base import Flags, Pipeline


class V0Naive(Pipeline):
    name = "v0_naive"
    flags = Flags()
