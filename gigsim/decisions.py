"""How a simulated client reacts to a proposal.

Rule mode (tests, CI, default): the client's reply probability is a base rate from
competition (applicants per job, from real data) times exp(sum of weighted features).
The features reward what a real client values and what the brief says to reward:
naming the client's hidden must-have skills, citing concrete past work, a non generic
opening that mirrors the problem, a price under the hidden ceiling. Very long letters
are penalised so the simulator cannot be gamed by length.

LLM mode: an open model reads the letter and the hidden preferences and returns a
JSON decision; the rule result is the fallback if the call fails.

Every random draw uses an RNG seeded from (global seed, user, job, client), so the
same proposal always gets the same outcome no matter when or in which order it is sent.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from gigsim.settings import load_templates

WORD_RE = re.compile(r"[a-z0-9][a-z0-9.+#-]*")
STOP = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "need", "needed",
        "looking", "expert", "developer", "project", "job", "help", "want", "required", "urgent"}


@dataclass(frozen=True)
class HiddenPrefs:
    must_have_skills: tuple[str, ...]
    budget_ceiling: float | None
    dislikes_generic: bool
    is_scam: bool = False


@dataclass
class Features:
    skill_coverage: float
    evidence: float
    generic_opening: float
    mirrors_problem: float
    over_budget: float
    too_long: float
    too_short: float
    words: int

    def as_dict(self) -> dict[str, float]:
        return {k: round(float(v), 4) for k, v in self.__dict__.items()}


@dataclass
class Decision:
    viewed: bool
    replied: bool
    interview: bool
    hired: bool
    p_reply: float
    features: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    mode: str = "rule"


def seeded_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def _first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return " ".join(parts[:n]).lower()


def extract_features(
    letter: str, amount: float, job: dict[str, Any], prefs: HiddenPrefs, cfg: dict[str, Any]
) -> Features:
    d = cfg["decision"]
    low = letter.lower()
    words = _words(letter)

    if prefs.must_have_skills:
        hits = sum(1 for s in prefs.must_have_skills if re.search(
            r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", low))
        coverage = hits / len(prefs.must_have_skills)
    else:
        coverage = 0.0

    has_verb = any(re.search(rf"\b{v}\b", low) for v in d["evidence_verbs"])
    has_number = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|x|k|ms|users|clients|hours|days|weeks|months|years)?\b", low))
    evidence = 1.0 if (has_verb and has_number) else 0.5 if has_verb else 0.0

    opening = _first_sentences(letter, 1)
    generic = 1.0 if any(g in opening for g in d["generic_openings"]) else 0.0

    title_words = {w for w in _words(job.get("title", "")) if w not in STOP and len(w) > 2}
    open_words = set(_words(_first_sentences(letter, 2)))
    mirrors = min(1.0, len(title_words & open_words) / 2) if title_words else 0.0

    over = 0.0
    if prefs.budget_ceiling and amount > prefs.budget_ceiling:
        over = min(2.0, (amount - prefs.budget_ceiling) / prefs.budget_ceiling)

    n = len(words)
    # Grows with the extra length (1.0 at the limit, 2.0 at double), so padding never pays.
    long_limit = d["long_letter_words"]
    too_long = 1.0 + min(1.0, (n - long_limit) / long_limit) if n > long_limit else 0.0
    too_short = 1.0 if n < d["short_letter_words"] else 0.0
    return Features(coverage, evidence, generic, mirrors, over, too_long, too_short, n)


def base_reply_rate(job: dict[str, Any], priors: dict[str, Any], cfg: dict[str, Any]) -> float:
    d = cfg["decision"]
    mids = priors.get("applicant_midpoints", {})
    mid = mids.get(job.get("applicants") or "", None)
    if mid is None:
        comp = priors.get("competition_by_category", {}).get(job.get("category") or "", {})
        mid = comp.get("applicants_mid_mean", d["default_applicants_mid"])
    return min(d["max_reply_probability"], d["reply_scale"] / max(1.0, float(mid)))


def rule_decide(
    *, letter: str, amount: float, job: dict[str, Any], prefs: HiddenPrefs,
    priors: dict[str, Any], cfg: dict[str, Any], rng: random.Random,
) -> Decision:
    d = cfg["decision"]
    w = d["weights"]
    f = extract_features(letter, amount, job, prefs, cfg)
    logit = (
        w["skill_coverage"] * f.skill_coverage
        + w["evidence"] * f.evidence
        + (w["generic_opening"] * f.generic_opening if prefs.dislikes_generic else 0.0)
        + w["mirrors_problem"] * f.mirrors_problem
        + w["over_budget"] * f.over_budget
        + w["too_long"] * f.too_long
        + w["too_short"] * f.too_short
    )
    p_reply = min(d["max_reply_probability"], base_reply_rate(job, priors, cfg) * math.exp(logit))
    if prefs.is_scam:
        p_reply = max(p_reply, 0.6)  # scam clients reply eagerly, then ask to go off platform
    p_view = min(1.0, 0.35 + 2.5 * p_reply)
    ib, ibonus = d["interview_given_reply"]
    viewed = rng.random() < p_view
    replied = viewed and rng.random() < p_reply / max(p_view, 1e-9)
    interview = replied and not prefs.is_scam and rng.random() < ib + ibonus * f.skill_coverage
    hired = interview and f.over_budget == 0 and rng.random() < d["hire_given_interview"]
    return Decision(viewed, replied, interview, hired, round(p_reply, 4), f.as_dict(),
                    reason=f"logit={logit:.2f}")


def llm_decide(
    *, letter: str, amount: float, job: dict[str, Any], prefs: HiddenPrefs,
    priors: dict[str, Any], cfg: dict[str, Any], rng: random.Random, seed: int,
) -> Decision:
    """Ask an open model to play the client. Falls back to rule mode on any failure."""
    rule = rule_decide(letter=letter, amount=amount, job=job, prefs=prefs, priors=priors,
                       cfg=cfg, rng=random.Random(rng.random()))
    llm = cfg["decision"]["llm"]
    base_url = os.environ.get(llm["base_url_env"])
    model = os.environ.get(llm["model_env"])
    if not base_url or not model:
        rule.reason += " (llm not configured, rule fallback)"
        return rule
    instructions = load_templates()["llm_client_instructions"]
    payload = {
        "job_title": job.get("title"), "job_budget": [job.get("budget_min"), job.get("budget_max")],
        "private_preferences": {
            "must_have_skills": list(prefs.must_have_skills),
            "budget_ceiling": prefs.budget_ceiling, "dislikes_generic_openings": prefs.dislikes_generic,
        },
        "base_reply_rate": base_reply_rate(job, priors, cfg),
        "proposal_amount": amount,
        "proposal": f"<<<PROPOSAL\n{letter}\nPROPOSAL>>>",
    }
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get(llm['api_key_env'], 'none')}"},
            json={
                "model": model, "temperature": 0, "seed": seed,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": instructions},
                             {"role": "user", "content": json.dumps(payload)}],
            },
            timeout=llm["timeout_seconds"],
        )
        resp.raise_for_status()
        out = json.loads(resp.json()["choices"][0]["message"]["content"])
        viewed = bool(out.get("viewed"))
        replied = viewed and bool(out.get("replied"))
        interview = replied and bool(out.get("interview")) and not prefs.is_scam
        hired = interview and bool(out.get("hired"))
        return Decision(viewed, replied, interview, hired, rule.p_reply, rule.features,
                        reason=str(out.get("reason", ""))[:300], mode="llm")
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        rule.reason += f" (llm failed: {type(exc).__name__}, rule fallback)"
        return rule


def decide(**kwargs: Any) -> Decision:
    cfg = kwargs["cfg"]
    if cfg["decision"]["mode"] == "llm":
        return llm_decide(**kwargs)
    kwargs.pop("seed", None)
    return rule_decide(**kwargs)
