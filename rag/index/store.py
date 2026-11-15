"""Portfolio index: dense vectors, BM25 and an optional cross-encoder, per persona.

Why one object: every retrieval variant composes the same three primitives, so variants
differ only in how they call them, and an ablation flips one flag at a time.
Embeddings are cached on disk under data/processed keyed by a corpus fingerprint, so
adding a case study re-embeds only once.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from agent.config import get_config
from rag.ingest.loaders import Chunk, corpus_fingerprint, load_corpus

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "processed"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


def tokenize(text: str) -> list[str]:
    """Keeps library names like next.js, c++, scikit-learn intact for exact matching."""
    return [t.strip(".-") for t in _TOKEN.findall(text.lower()) if t.strip(".-")]


@lru_cache(maxsize=2)
def _embedder(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device="cpu",
                               trust_remote_code=model_name.startswith("nomic-ai/"))


@lru_cache(maxsize=2)
def _cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, device="cpu", max_length=512)


class PortfolioIndex:
    def __init__(self, persona: str, chunks: list[Chunk] | None = None,
                 embed_model: str | None = None) -> None:
        cfg = get_config().models
        self.persona = persona
        self.chunks = chunks if chunks is not None else load_corpus(persona)
        self.by_id = {c.id: c for c in self.chunks}
        self.embed_model = embed_model or os.environ.get("EMBED_MODEL") or cfg.embeddings.model
        self.query_prefix = cfg.embeddings.query_prefix if embed_model is None else ""
        self.doc_prefix = cfg.embeddings.document_prefix if embed_model is None else ""
        self.rerank_model = cfg.reranker.model
        self.rerank_top_n = cfg.reranker.top_n
        self.bm25 = BM25Okapi([tokenize(self._doc_text(c)) for c in self.chunks])
        self.vectors = self._load_or_embed()

    @staticmethod
    def _doc_text(c: Chunk) -> str:
        skills = f" Skills: {', '.join(c.skills)}." if c.skills else ""
        return f"{c.text}{skills}"

    def _load_or_embed(self) -> np.ndarray:
        CACHE.mkdir(parents=True, exist_ok=True)
        tag = re.sub(r"[^a-zA-Z0-9]+", "_", self.embed_model)
        path = CACHE / f"emb_{self.persona}_{tag}_{corpus_fingerprint(self.chunks)}.npy"
        if path.exists():
            return np.load(path)
        model = _embedder(self.embed_model)
        vecs = model.encode([self.doc_prefix + self._doc_text(c) for c in self.chunks],
                            batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        vecs = np.asarray(vecs, dtype=np.float32)
        np.save(path, vecs)
        return vecs

    # ------------------------------------------------------------ primitives
    def dense(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        q = _embedder(self.embed_model).encode([self.query_prefix + query],
                                               normalize_embeddings=True,
                                               show_progress_bar=False)[0]
        scores = self.vectors @ q
        top = np.argsort(-scores)[:k]
        return [(self.chunks[i].id, float(scores[i])) for i in top]

    def sparse(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        top = np.argsort(-scores)[:k]
        return [(self.chunks[i].id, float(scores[i])) for i in top if scores[i] > 0]

    def rerank(self, query: str, ids: list[str]) -> list[tuple[str, float]]:
        ids = ids[: self.rerank_top_n]
        if not ids:
            return []
        ce = _cross_encoder(self.rerank_model)
        scores = ce.predict([(query[:2000], self._doc_text(self.by_id[i])[:2000]) for i in ids],
                            batch_size=16, show_progress_bar=False)
        # squash logits to 0..1 so thresholds in config stay meaningful
        probs = 1 / (1 + np.exp(-np.asarray(scores, dtype=np.float64)))
        return sorted(zip(ids, probs.tolist(), strict=True), key=lambda x: -x[1])


_INDEXES: dict[tuple[str, str], PortfolioIndex] = {}


def get_index(persona: str, embed_model: str | None = None) -> PortfolioIndex:
    key = (persona, embed_model or "")
    if key not in _INDEXES:
        _INDEXES[key] = PortfolioIndex(persona, embed_model=embed_model)
    return _INDEXES[key]


def reset_index(persona: str | None = None) -> None:
    """Drop cached indexes, e.g. after the user uploads new work (incremental re-index)."""
    for key in list(_INDEXES):
        if persona is None or key[0] == persona:
            del _INDEXES[key]


def warm(personas: list[str] | None = None) -> None:
    """Build indexes and load models up front (API startup, eval runners), so the first
    tool call does not pay model loading inside its timeout."""
    from agent.config import get_config

    for p in personas or ["ai_ml", "fullstack", "data_analyst"]:
        get_index(p)
    _cross_encoder(get_config().models.reranker.model)
