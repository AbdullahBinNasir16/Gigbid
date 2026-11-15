"""Load a persona corpus into chunks with metadata.

Why: every chunk carries persona, type, project, skills, date, client industry and, for
proposals, outcome, so variants can filter, group by project (multi-vector) and boost by
outcome. Loaders are per source type so a new upload re-indexes only what changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = ROOT / "data" / "personas"


@dataclass
class Chunk:
    id: str
    persona: str
    type: str  # cv | case_study | repo | code | review | proposal
    source: str
    text: str
    project: str | None = None
    skills: list[str] = field(default_factory=list)
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, text


def load_case_studies(persona: str, base: Path) -> list[Chunk]:
    out = []
    for path in sorted((base / "case_studies").glob("*.md")):
        meta, body = _front_matter(path.read_text(encoding="utf-8"))
        sections = [s.strip() for s in re.split(r"\n(?=## )", body) if s.strip()]
        title = sections[0].lstrip("# ").strip() if sections else meta.get("title", path.stem)
        for i, sec in enumerate(sections[1:] or sections):
            out.append(Chunk(
                id=f"{meta.get('id', path.stem)}#{i}", persona=persona, type="case_study",
                source=f"case_studies/{path.name}", text=f"{title}. {sec.lstrip('# ')}",
                project=meta.get("project"), skills=list(meta.get("skills", [])),
                date=str(meta.get("date")) if meta.get("date") else None,
                client_industry=meta.get("client_industry"),
            ))
    return out


def load_repos(persona: str, base: Path) -> list[Chunk]:
    out = []
    for rdir in sorted(p for p in (base / "repos").glob("*") if p.is_dir()):
        readme = rdir / "README.md"
        if readme.exists():
            out.append(Chunk(id=f"repo:{persona}:{rdir.name}", persona=persona, type="repo",
                             source=f"repos/{rdir.name}/README.md",
                             text=readme.read_text(encoding="utf-8"), project=rdir.name))
        for code in sorted(rdir.glob("*.py")):
            out.append(Chunk(id=f"code:{persona}:{rdir.name}:{code.stem}", persona=persona,
                             type="code", source=f"repos/{rdir.name}/{code.name}",
                             text=code.read_text(encoding="utf-8"), project=rdir.name))
    return out


def load_cv(persona: str, base: Path) -> list[Chunk]:
    path = base / "cv.md"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out, skills_block = [], []
    for i, line in enumerate(lines):
        if line.startswith("- "):
            out.append(Chunk(id=f"cv:{persona}:{i}", persona=persona, type="cv", source="cv.md",
                             text=line[2:]))
        elif line and not line.startswith("#"):
            skills_block.append(line)
    if skills_block:
        out.append(Chunk(id=f"cv:{persona}:summary", persona=persona, type="cv", source="cv.md",
                         text=" ".join(skills_block)))
    return out


def load_reviews(persona: str, base: Path) -> list[Chunk]:
    path = base / "reviews.json"
    if not path.exists():
        return []
    return [Chunk(id=r["id"], persona=persona, type="review", source="reviews.json",
                  text=r["text"], project=r.get("project"), date=r.get("date"),
                  client_industry=r.get("client_industry"))
            for r in json.loads(path.read_text(encoding="utf-8"))]


def load_proposals(persona: str, base: Path) -> list[Chunk]:
    path = base / "proposals.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        out.append(Chunk(id=r["id"], persona=persona, type="proposal", source="proposals.jsonl",
                         text=f"Proposal for '{r['job_title']}': {r['text']}",
                         project=r.get("project"), skills=r.get("skills", []), date=r.get("date"),
                         outcome=r.get("outcome")))
    return out


LOADERS = [load_cv, load_case_studies, load_repos, load_reviews, load_proposals]


def resolve_cv_lines(chunks: list[Chunk], persona: str, base: Path) -> None:
    """Attach a project to CV lines by title match, so the CV is a third view of a project."""
    titles = {}
    for path in (base / "case_studies").glob("*.md"):
        meta, _ = _front_matter(path.read_text(encoding="utf-8"))
        if meta.get("title"):
            titles[meta["title"].lower()] = meta.get("project")
    for c in chunks:
        if c.type == "cv" and c.project is None:
            for title, proj in titles.items():
                if title in c.text.lower():
                    c.project = proj


def load_corpus(persona: str, base: Path | None = None) -> list[Chunk]:
    base = base or PERSONA_DIR / persona
    chunks: list[Chunk] = []
    for loader in LOADERS:
        chunks.extend(loader(persona, base))
    resolve_cv_lines(chunks, persona, base)
    return chunks


def corpus_fingerprint(chunks: list[Chunk]) -> str:
    """Stable hash of chunk ids and text; the index rebuilds only when this changes."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(c.id.encode())
        h.update(c.text.encode())
    return h.hexdigest()[:16]
