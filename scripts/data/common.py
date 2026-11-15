"""Shared helpers for the data pipeline: PII masking, parsing, classification.

Why a module: the build scripts and the unit tests must use exactly the same rules.
"""

from __future__ import annotations

import hashlib
import html
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
REAL = ROOT / "data" / "real"
TAXONOMY_PATH = REAL / "taxonomy.yaml"

# ------------------------------------------------------------------ PII masking

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|net|org|io|co|me|ly)/\S*")
# Candidate phone: optional +, digits with spaces, dots, dashes or brackets. Kept only if it
# has 9 to 15 digits, so budgets ("$2,500"), years and ranges ("10-25") are untouched.
PHONE_CANDIDATE_RE = re.compile(r"(?<![\w$])\+?\(?\d[\d\s().-]{7,}\d(?![\w%])")
HANDLE_RE = re.compile(r"(?i)\b(?:whatsapp|telegram|skype|wechat)\s*[:@]?\s*@?[\w.+-]{3,}")


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[PHONE]" if 9 <= len(digits) <= 15 else match.group(0)


def mask_pii(text: str) -> str:
    """Replace emails, URLs, phone numbers and messenger handles with placeholders."""
    if not text:
        return text
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = URL_RE.sub("[URL]", text)
    text = HANDLE_RE.sub(lambda m: m.group(0).split()[0].rstrip(":@") + " [HANDLE]", text)
    return PHONE_CANDIDATE_RE.sub(_mask_phone, text)


def has_pii(text: str) -> bool:
    if EMAIL_RE.search(text) or URL_RE.search(text):
        return True
    return any(_mask_phone(m) == "[PHONE]" for m in PHONE_CANDIDATE_RE.finditer(text))


# ------------------------------------------------------------------ parsing

MONEY_RE = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)")


def parse_money(value: Any) -> float | None:
    """'$2,500 ' -> 2500.0, '0' -> None (the 60k set uses 0 for missing)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, int | float):
        return float(value) if value > 0 else None
    m = MONEY_RE.search(str(value))
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    return amount if amount > 0 else None


def parse_rate_range(value: Any) -> tuple[float | None, float | None]:
    """'$10.00-$35.00' -> (10.0, 35.0); '$40.00' -> (40.0, 40.0)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, None
    parts = [m for p in str(value).split("-") if (m := parse_money(p)) is not None]
    if not parts:
        return None, None
    return min(parts), max(parts)


def clean_text(text: str) -> str:
    """Decode HTML entities (&amp; -> &) and collapse runs of spaces, keeping newlines."""
    text = html.unescape(html.unescape(text or ""))
    return re.sub(r"[ 	 ]+", " ", text).strip()


def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def near_dup_key(title: str, description: str, prefix_chars: int) -> str:
    return hashlib.sha1(
        (normalise_text(title) + "|" + normalise_text(description)[:prefix_chars]).encode()
    ).hexdigest()


# ------------------------------------------------------------------ taxonomy


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.#+-]*")


def tokenize(text: str) -> list[str]:
    """Lower case word tokens. Keeps '.', '#', '+', '-' inside tokens (node.js, c#, c++,
    front-end); '/' splits (ui/ux -> ui ux). Trailing punctuation is stripped."""
    return [t.rstrip(".-") for t in TOKEN_RE.findall(text.lower()) if t.rstrip(".-")]


class PhraseIndex:
    """Linear time phrase lookup over word n-grams.

    Why: a regex alternation of 1,500 skills is tested at every character and is far too
    slow on 100k descriptions; a dict lookup per n-gram is O(tokens x max phrase length).
    """

    def __init__(self, phrases: dict[str, str]) -> None:
        # phrases: raw phrase -> label. Keys are normalised with the same tokenizer as text.
        self.index: dict[tuple[str, ...], str] = {}
        for raw, label in phrases.items():
            key = tuple(tokenize(raw))
            if key:
                self.index.setdefault(key, label)
        self.max_n = max((len(k) for k in self.index), default=1)

    def matches(self, text: str) -> list[str]:
        """Labels of non overlapping matches, longest phrase first at each position."""
        toks = tokenize(text)
        out: list[str] = []
        i = 0
        while i < len(toks):
            for n in range(min(self.max_n, len(toks) - i), 0, -1):
                label = self.index.get(tuple(toks[i : i + n]))
                if label is not None:
                    out.append(label)
                    i += n
                    break
            else:
                i += 1
        return out


@dataclass
class Classifier:
    """Weighted keyword classifier over title, skills and description."""

    taxonomy: dict[str, Any]

    @cached_property
    def index(self) -> PhraseIndex:
        return PhraseIndex(
            {kw: name for name, c in self.taxonomy["categories"].items() for kw in c["keywords"]}
        )

    def scores(self, title: str, description: str, skills: Iterable[str]) -> dict[str, int]:
        w = self.taxonomy["weights"]
        scores = dict.fromkeys(self.taxonomy["categories"], 0)
        for field, text in (("title", title), ("skill", " | ".join(skills)), ("description", description)):
            for label in self.index.matches(text or ""):
                scores[label] += w[field]
        return scores

    def classify(self, title: str, description: str = "", skills: Iterable[str] = ()) -> str:
        scores = self.scores(title, description, skills)
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "other"


@dataclass
class SkillMatcher:
    """Finds vocabulary skills in free text (word boundaries, ambiguity rules from taxonomy)."""

    vocab: list[str]
    short_whitelist: list[str]

    @cached_property
    def index(self) -> PhraseIndex:
        short = set(self.short_whitelist)
        return PhraseIndex({s: s for s in self.vocab if s not in short})

    @cached_property
    def _short(self) -> re.Pattern[str] | None:
        short = [s for s in self.short_whitelist if s in self.vocab]
        if not short:
            return None
        return re.compile(
            r"(?<![A-Za-z0-9])(" + "|".join(re.escape(s) for s in short) + r")(?![A-Za-z0-9+#])"
        )

    def find(self, text: str, limit: int = 15) -> list[str]:
        found = dict.fromkeys(self.index.matches(text))
        if self._short is not None:
            for m in self._short.finditer(text):
                found.setdefault(m.group(1), None)
        return list(found)[:limit]
