"""Explicit promotion rules: the only path from observations into long-term memory.

Style memory: an edit pattern (cut the first sentence, never use a word, keep it shorter)
is promoted only after it appears in memory.style.min_edits_to_promote DISTINCT proposals.

Outcome memory: a lesson per job category ("specific openings get more replies") is
promoted only with memory.outcome.min_samples_to_promote outcomes and a reply-rate gap of
at least memory.outcome.min_reply_rate_delta.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from agent.config import get_config
from agent.memory.store import get_store

WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
_SENT = re.compile(r"(?<=[.!?])\s+")


def edit_patterns(original: str, edited: str) -> list[tuple[str, str]]:
    """(key, rule) patterns found in one user edit."""
    out: list[tuple[str, str]] = []
    o_sents, e_sents = _SENT.split(original.strip()), _SENT.split(edited.strip())
    if o_sents and e_sents and o_sents[0].strip() != e_sents[0].strip() \
            and o_sents[0].strip() not in edited:
        out.append(("cut_first_sentence", ("Cut the generic first sentence; start with the "
                                          "client's problem.")))
    removed = {w.lower() for w in WORD.findall(original)} - {w.lower() for w in
                                                            WORD.findall(edited)}
    for w in sorted(removed):
        if len(w) >= 6 or w in {"passionate", "expert", "guru", "ninja", "rockstar"}:
            out.append((f"avoid_word:{w}", f"Never use the word \"{w}\"."))
    if len(edited) < 0.8 * len(original):
        out.append(("shorter", "Keep proposals shorter; the freelancer trims long drafts."))
    sm = difflib.SequenceMatcher(None, original, edited)
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        added = edited[j1:j2].strip()
        if tag in ("insert", "replace") and re.match(r"^(Best|Thanks|Cheers|Regards)", added):
            out.append((f"signoff:{added.split()[0].lower()}", f"Sign off with \"{added[:40]}\"."))
    return out[:15]


def record_edit(user: str, proposal_id: str, original: str, edited: str) -> list[str]:
    """Store edit patterns as candidates, then promote the ones that pass the rule."""
    store = get_store()
    ns_c, ns_m = ("candidates", user, "style"), ("memory", user, "style")
    need = get_config().memory.style.min_edits_to_promote
    promoted = []
    for key, rule in edit_patterns(original, edited):
        item = store.get(ns_c, key)
        seen = set(item.value["proposals"]) if item else set()
        seen.add(proposal_id)
        store.put(ns_c, key, {"rule": rule, "proposals": sorted(seen)})
        if len(seen) >= need and store.get(ns_m, key) is None:
            store.put(ns_m, key, {"rule": rule, "promoted_by": f"seen in {len(seen)} distinct "
                                  f"proposals (rule: >= {need})", "evidence": sorted(seen)[:10]})
            promoted.append(rule)
    _cap(ns_m, get_config().memory.style.max_items)
    return promoted


def record_outcome(user: str, category: str, feature: str, replied: bool) -> list[str]:
    """Tally an outcome by (category, feature) and promote a lesson when the rule allows.

    feature examples: "specific_opening" vs "generic_opening", "cites_evidence".
    """
    cfg = get_config().memory.outcome
    store = get_store()
    ns_c, ns_m = ("candidates", user, "outcome"), ("memory", user, "outcome")
    key = f"{category}"
    item = store.get(ns_c, key)
    tally: dict[str, Any] = item.value if item else {"features": {}}
    f = tally["features"].setdefault(feature, {"n": 0, "replied": 0})
    f["n"] += 1
    f["replied"] += int(replied)
    store.put(ns_c, key, tally)
    promoted = []
    feats = tally["features"]
    for a, b in (("specific_opening", "generic_opening"), ("cites_evidence", "no_evidence")):
        if a in feats and b in feats and feats[a]["n"] + feats[b]["n"] >= cfg.min_samples_to_promote:
            ra, rb = feats[a]["replied"] / feats[a]["n"], feats[b]["replied"] / feats[b]["n"]
            if abs(ra - rb) >= cfg.min_reply_rate_delta:
                better = a if ra > rb else b
                lesson = (f"In {category}, proposals with {better.replace('_', ' ')} got "
                          f"{max(ra, rb):.0%} replies vs {min(ra, rb):.0%}.")
                store.put(ns_m, f"{category}:{a}", {"rule": lesson, "promoted_by":
                          f"n={feats[a]['n'] + feats[b]['n']} >= {cfg.min_samples_to_promote}, "
                          f"delta {abs(ra - rb):.2f} >= {cfg.min_reply_rate_delta}"})
                promoted.append(lesson)
    return promoted


def _cap(ns: tuple[str, ...], max_items: int) -> None:
    items = get_store().search(ns, limit=1000)
    for it in sorted(items, key=lambda i: i.updated_at)[:-max_items or None][:max(0, len(items) - max_items)]:
        get_store().delete(ns, it.key)
