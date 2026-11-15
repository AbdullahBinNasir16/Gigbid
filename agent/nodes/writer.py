"""Proposal Writer: cover letter and screening answers with evidence citations.

The model sees numbered evidence [E1..En] and must tag every experience sentence. Tags are
mapped back to evidence ids (so the UI can show evidence on hover) and stripped from the
text. If the model is unavailable, or generation.writer_mode=template, a deterministic
writer composes the letter only from evidence sentences, so the graph never stalls.
"""

from __future__ import annotations

import re

from agent.config import get_config
from agent.handoffs import Claim, Evidence, ProposalDraft
from agent.nodes._common import call_llm, event, timed, untrusted, word_count
from agent.prompts import load_prompt, prompt_version
from agent.state import step

_TAG = re.compile(r"\s*\[E(\d+)\]")
_SENT = re.compile(r"(?<=[.!?])\s+")


def evidence_block(evidence: list[Evidence]) -> str:
    lines = []
    for i, e in enumerate(evidence, 1):
        meta = f"{e.type.value}, project {e.project or '-'}"
        if e.type.value == "proposal":
            meta = (f"PAST PROPOSAL, outcome {e.outcome.value if e.outcome else '?'}: phrasing "
                    "reference only, NOT proof of experience, never cite it")
        lines.append(f"[E{i}] ({meta}) {e.text[:700]}")
    return "\n".join(lines) or "(no evidence found)"


def parse_tagged(text: str, evidence: list[Evidence]) -> tuple[list[str], list[str], list[Claim]]:
    body, _, screening = text.partition("SCREENING:")
    paragraphs, claims = [], []
    for p_idx, para in enumerate(p.strip() for p in body.strip().split("\n\n") if p.strip()):
        clean_sents = []
        for s in _SENT.split(para):
            ids = [evidence[int(n) - 1].id for n in _TAG.findall(s) if 0 < int(n) <= len(evidence)]
            clean = _TAG.sub("", s).strip()
            if not clean:
                continue
            clean_sents.append(clean)
            if ids:
                claims.append(Claim(text=clean[:600], evidence_ids=ids[:10],
                                    paragraph_index=p_idx))
        if clean_sents:
            paragraphs.append(" ".join(clean_sents)[:2000])
    answers = [_TAG.sub("", a).strip()[:1000] for a in screening.strip().splitlines() if a.strip()]
    return paragraphs[:12], answers[:10], claims[:40]


def _first_sentence(text: str) -> str:
    body = re.sub(r"^#+.*$", "", text, flags=re.MULTILINE).strip()
    body = re.sub(r"^.*?\.\s", "", body, count=1) if body.count(".") > 1 else body
    return _SENT.split(body)[0].strip()


def template_letter(job: dict, evidence: list[Evidence], spec_reqs: list[str],
                    matched: list[str] | None = None) -> str:
    """Deterministic fallback: restate the job in its own title words, name the listed skills
    the portfolio evidences, and quote real built/result sentences verbatim."""
    title = (job.get("title") or (spec_reqs[0] if spec_reqs else "your project")).rstrip(".")
    paras = [f"You are looking for help with {title[:160]}."]
    if matched:
        paras[0] += f" Your post asks for {', '.join(matched[:4])}."
    cited: list[str] = []
    used_projects: list[str | None] = []
    for i, e in enumerate(evidence, 1):
        if e.type.value not in ("case_study", "review", "cv"):
            continue
        for pat in (r"\bI built [^.]*\.", r"\bThe work [^.]*\.", r"\b(?:cut|raised|reached|"
                    r"lowered|saved|rose|fell)[^.]*\d[^.]*\."):
            m = re.search(pat, e.text)
            if m and (e.project not in used_projects or pat != r"\bI built [^.]*\."):
                sent = m.group(0).replace("The work", "That work", 1)
                if sent[0].islower():
                    sent = "That work " + sent
                if f"{sent} [E{i}]" not in cited:
                    cited.append(f"{sent} [E{i}]")
                    used_projects.append(e.project)
        if len(set(used_projects)) >= 2 or len(cited) >= 3:
            break
    if cited:
        paras.append(" ".join(cited[:3]))
    paras.append("I would start by confirming the scope and success criteria with you, then "
                 "share a short plan with milestones. Which part matters most to you first?")
    return "\n\n".join(paras)


def writer(state: dict) -> dict:
    cfg = get_config().generation
    k = int(cfg.get("evidence_k", 6))
    pool = state.get("evidence", [])
    proof = [e for e in pool if e.type.value != "proposal"]
    phrasing = [e for e in pool if e.type.value == "proposal"][:2]
    job, evidence = state["job"], (proof[: k - len(phrasing[:2])] + phrasing)[:k]
    spec = state.get("analyses", {}).get("job_spec")
    price = state.get("price")
    critiques = state.get("critiques", [])
    drafts = state.get("drafts", [])
    revision = len(drafts)
    from agent.memory.store import style_rules_text

    style = style_rules_text(state.get("user_id", "default"))
    fit = state.get("analyses", {}).get("fit")
    matched = list(fit.matched_skills) if fit else []
    tokens, mode = 0, cfg.get("writer_mode", "llm")
    with timed() as t:
        text = ""
        if mode == "llm":
            system = load_prompt("writer").replace("{style_rules}", style)
            user = (f"JOB POST:\n{untrusted('job', job.get('title', '') + chr(10) + job.get('description', ''))}\n\n"
                    f"CLIENT'S LISTED SKILLS: {', '.join(job.get('skills') or []) or 'none'}\n"
                    f"LISTED SKILLS YOU HAVE EVIDENCE FOR: {', '.join(matched) or 'none'}\n"
                    f"SCREENING QUESTIONS: {spec.screening_questions if spec else []}\n"
                    f"PRICE: {price.amount if price else '?'} {price.budget_type if price else ''}\n\n"
                    f"EVIDENCE:\n{evidence_block(evidence)}")
            if critiques and drafts:
                issues = "\n".join(f"- {i.kind}: {i.detail}" for i in critiques[-1].issues)
                user += "\n\n" + load_prompt("writer_revision").format(
                    issues=issues, draft=drafts[-1].cover_letter)
            try:
                text, tokens = call_llm("writer", system, user)
            except Exception:  # noqa: BLE001 - template writer is the fallback
                text, mode = "", "template"
        if not text.strip():
            mode = "template"
            text = template_letter(job, evidence, [r.text for r in spec.requirements] if spec else [], matched)
        paragraphs, answers, claims = parse_tagged(text, evidence)
        if not paragraphs:
            paragraphs, answers, claims = parse_tagged(
                template_letter(job, evidence, [], matched), evidence)
    draft = ProposalDraft(job_id=job["job_id"], paragraphs=paragraphs, screening_answers=answers,
                          evidence_ids=[e.id for e in evidence], claims=claims,
                          revision=min(revision, 10),
                          strategy=f"{mode}:{prompt_version('writer')}")
    return {"drafts": [draft], "counters": step(tokens, writer_call=True),
            "trace": [event(state, "writer", tokens=tokens, duration_ms=t["ms"],
                            result_summary=f"rev {revision}, {word_count(draft.cover_letter)} "
                                           f"words, {len(claims)} tagged claims, mode {mode}")]}
