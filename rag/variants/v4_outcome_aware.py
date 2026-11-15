"""V4: boost evidence from projects and proposals that won or got replies.

Weight is retrieval.outcome_boost_weight in config.
"""

from rag.variants.base import Flags, Pipeline


class V4OutcomeAware(Pipeline):
    name = "v4_outcome_aware"
    flags = Flags(outcome=True)
