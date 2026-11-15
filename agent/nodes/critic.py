"""Critic: grounding, personalisation and length. Sends the draft back at most
budgets.critic_max_loops times, with reasons.

Rules run first (cheap, deterministic); in rules+llm mode the critic model adds issues the
rules cannot see. A revise verdict always lists issues.
"""

from __future__ import annotations

import re

from agent.config import get_config
from agent.handoffs import Critique, CritiqueIssue
from agent.nodes._common import call_llm, event, parse_json, timed, untrusted, word_count
from agent.prompts import load_prompt
from agent.state import step
from rag.index.store import tokenize

GENERIC = re.compile(r"^(dear (sir|madam|hiring manager)|hello|hi there|hi,|greetings|i am a "
                     r"highly|i have read your|i am (very )?interested|i am passionate)", re.I)


def rule_issues(text: str, job: dict, verification: dict | None) -> list[CritiqueIssue]:
    g = get_config().generation
    issues = []
    first = text.strip().split("\n")[0]
    if GENERIC.search(first.strip()):
        issues.append(CritiqueIssue(kind="generic_opening", detail="Opening is generic; mirror "
                                    "the client's specific problem in the first sentence.",
                                    paragraph_index=0))
    words = word_count(text)
    if words > int(g.get("max_words", 250)):
        issues.append(CritiqueIssue(kind="too_long", detail=f"{words} words; cut to under "
                                    f"{g.get('max_words', 250)}."))
    job_terms = {t for t in tokenize(f"{job.get('title', '')} {' '.join(job.get('skills') or [])}")
                 if len(t) > 3}
    if job_terms and not (job_terms & set(tokenize(text))):
        issues.append(CritiqueIssue(kind="not_personalised", detail="Mentions nothing from the "
                                    "job title or skills; address what this client asked for."))
    if verification and verification.get("partly"):
        issues.append(CritiqueIssue(kind="unsupported_claim", detail=("Only partly supported: "
                                    + verification["partly"][0])[:500]))
    return issues


def critic(state: dict) -> dict:
    cfg, budgets = get_config().generation, get_config().budgets
    draft, job = state["drafts"][-1], state["job"]
    loops = state["counters"].critic_loops if state.get("counters") else 0
    tokens = 0
    with timed() as t:
        issues = rule_issues(draft.cover_letter, job, state.get("verification"))
        score = max(0.0, 9.0 - 2.0 * len(issues))
        if cfg.get("critic_mode") == "rules+llm" and not issues:
            try:
                text, tokens = call_llm("critic", load_prompt("critic"),
                                        f"JOB:\n{untrusted('job', job.get('title', '') + chr(10) + job.get('description', '')[:2500])}"
                                        f"\n\nPROPOSAL:\n{draft.cover_letter}")
                data = parse_json(text) or {}
                for i in data.get("issues", [])[:5]:
                    kind = i.get("kind") if i.get("kind") in CritiqueIssue.model_fields["kind"].annotation.__args__ else "other"  # type: ignore[union-attr]
                    if str(i.get("detail", "")).strip():
                        issues.append(CritiqueIssue(kind=kind, detail=str(i["detail"])[:500]))
                if isinstance(data.get("score"), int | float):
                    score = float(min(10, max(0, data["score"])))
            except Exception:  # noqa: BLE001 - rules verdict stands
                pass
    can_loop = loops < budgets.critic_max_loops
    verdict = "revise" if issues and can_loop else "accept"
    c = Critique(verdict=verdict, score=score, issues=issues if verdict == "revise" else issues,
                 instructions="; ".join(i.detail for i in issues)[:2000])
    return {"critiques": [c], "counters": step(tokens, critic_loop=verdict == "revise"),
            "trace": [event(state, "critic", tokens=tokens, duration_ms=t["ms"],
                            result_summary=f"{verdict} score {score:.1f}, {len(issues)} issues"
                                           + ("" if can_loop or not issues else " (loop limit)"))]}
