"""Claim splitting and grounding (B3).

A draft is split into sentences; sentences that assert experience, results or facts about
the freelancer are claims. Each claim is checked against the evidence the writer saw:

* the cross-encoder scores (claim, evidence) pairs; the best pair is the claim's support;
* every number and every named tool in the claim must appear in that evidence, so
  "cut costs 45%" is unsupported when the evidence says 35%;
* supported:        score >= supported_at and all specifics found
* partly_supported: score >= partly_at, or some specifics found
* unsupported:      otherwise

Unsupported claims are removed before the Critic sees the draft (deterministic, so the
removal can be audited); partly supported claims are kept and flagged to the Critic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.handoffs import Claim, ClaimSupport, Evidence

SUPPORTED_AT = 0.55
PARTLY_AT = 0.25

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_NUM = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|k\b|x\b)?")
_CLAIM_CUES = re.compile(
    r"\b(I|I've|I have|I'm|my|we|our)\b.*\b(built|build|delivered|developed|created|designed|"
    r"led|shipped|cut|reduced|raised|increased|improved|saved|migrated|deployed|trained|"
    r"fine-tuned|automated|worked|experience|years|helped|launched|implemented|wrote|ran|"
    r"analy[sz]ed|reached|achieved|managed|handled|fixed|solved)\b",
    re.I,
)
_TOOL = re.compile(r"\b([A-Z][a-zA-Z0-9+#]*(?:\.[a-z]+)?|[a-z]+\.js|dbt|scikit-learn)\b")
_STOP_TOOLS = {"I", "I've", "I'm", "My", "We", "Our", "The", "This", "That", "In", "For",
               "Last", "Your", "You", "Happy", "Hello", "Hi", "Dear", "Best", "Thanks",
               "Regards", "It", "A", "An", "On", "With", "And", "Looking", "If", "When"}


@dataclass
class Verification:
    claims: list[Claim]
    cleaned_text: str
    removed: list[str]

    @property
    def unsupported_rate(self) -> float:
        n = len(self.claims)
        return sum(c.support == ClaimSupport.unsupported for c in self.claims) / n if n else 0.0


def split_sentences(text: str) -> list[tuple[int, str]]:
    out = []
    for p_idx, para in enumerate(p for p in text.split("\n\n") if p.strip()):
        for s in _SENT.split(para.strip()):
            if s.strip():
                out.append((p_idx, s.strip()))
    return out


def is_claim(sentence: str) -> bool:
    if sentence.endswith("?"):
        return False
    return bool(_CLAIM_CUES.search(sentence)) or bool(_NUM.search(sentence) and "I" in sentence)


def _specifics(sentence: str) -> tuple[set[str], set[str]]:
    nums = {n.strip().replace(",", "") for n in _NUM.findall(sentence) if n.strip()}
    tools = {t for t in _TOOL.findall(sentence) if t not in _STOP_TOOLS and len(t) > 1}
    return nums, tools


def _found(spec: set[str], text: str) -> float:
    if not spec:
        return 1.0
    low = text.lower().replace(",", "")
    return sum(s.lower().rstrip("%kx ").strip() in low for s in spec) / len(spec)


def _scores(pairs: list[tuple[str, str]]) -> list[float]:
    if not pairs:
        return []
    try:
        import numpy as np

        from agent.config import get_config
        from rag.index.store import _cross_encoder

        ce = _cross_encoder(get_config().models.reranker.model)
        logits = ce.predict(pairs, batch_size=16, show_progress_bar=False)
        return (1 / (1 + np.exp(-np.asarray(logits, dtype=float)))).tolist()
    except Exception:  # model unavailable: lexical fallback keeps verification running
        from rag.index.store import tokenize

        out = []
        for claim, ev in pairs:
            c, e = set(tokenize(claim)), set(tokenize(ev))
            out.append(len(c & e) / max(1, len(c)))
        return out


def check_claims(text: str, evidence: list[Evidence]) -> list[Claim]:
    sents = [(p, s) for p, s in split_sentences(text) if is_claim(s)]
    if not sents:
        return []
    ev_texts = [f"{e.text} Skills: {', '.join(e.skills)}" for e in evidence]
    claims: list[Claim] = []
    for p_idx, s in sents:
        if not evidence:
            claims.append(Claim(text=s[:600], support=ClaimSupport.unsupported,
                                paragraph_index=p_idx))
            continue
        scores = _scores([(s, t) for t in ev_texts])
        order = sorted(range(len(evidence)), key=lambda i: -scores[i])
        best = order[0]
        top_text = " ".join(ev_texts[i] for i in order[:3])
        nums, tools = _specifics(s)
        num_ok, tool_ok = _found(nums, top_text), _found(tools, top_text)
        spec_ok = min(num_ok, tool_ok)
        if scores[best] >= SUPPORTED_AT and spec_ok == 1.0:
            support = ClaimSupport.supported
        elif num_ok < 1.0 and nums:
            # a number that is not in the evidence is a fabricated result
            support = ClaimSupport.unsupported
        elif scores[best] >= PARTLY_AT or spec_ok >= 0.5:
            support = ClaimSupport.partly_supported
        else:
            support = ClaimSupport.unsupported
        ids = [evidence[i].id for i in order[:3] if scores[i] >= PARTLY_AT] or [evidence[best].id]
        claims.append(Claim(text=s[:600], evidence_ids=ids[:10], support=support,
                            paragraph_index=p_idx))
    return claims


def verify_claims(text: str, evidence: list[Evidence]) -> Verification:
    """Check every claim and remove unsupported ones from the text."""
    claims = check_claims(text, evidence)
    bad = {c.text for c in claims if c.support == ClaimSupport.unsupported}
    paras = []
    for para in (p for p in text.split("\n\n") if p.strip()):
        kept = [s for s in _SENT.split(para.strip()) if s.strip() and s.strip()[:600] not in bad]
        if kept:
            paras.append(" ".join(kept))
    return Verification(claims=claims, cleaned_text="\n\n".join(paras), removed=sorted(bad))
