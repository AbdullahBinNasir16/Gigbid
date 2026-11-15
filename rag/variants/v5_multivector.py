"""V5: case study, README, code, CV line and review chunks indexed separately and
returned as one project (best chunk per project), so a repo whose README looks
irrelevant can still surface through its code chunk."""

from rag.variants.base import Flags, Pipeline


class V5MultiVector(Pipeline):
    name = "v5_multivector"
    flags = Flags(multivector=True)
