"""V1: one retrieval per extracted requirement, merged with reciprocal rank fusion.

Targets jobs that ask for several different things; one whole-post query blurs them.
"""

from rag.variants.base import Flags, Pipeline


class V1Decomposition(Pipeline):
    name = "v1_decomposition"
    flags = Flags(decompose=True)
