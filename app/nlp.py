"""Lightweight natural-language processing for ZuriTrustAI.

Pure Python (no heavy ML dependencies) so it runs on low-cost servers:

* ``normalize`` / ``tokenize`` - text clean-up shared by every module.
* ``TfidfRetriever`` - TF-IDF over word unigrams plus character n-grams,
  ranked by cosine similarity. Character n-grams make matching robust to the
  spelling variation and typos common in SMS / WhatsApp messages.

The retriever only ever returns answers from the curated, clinically reviewed
knowledge base. It never generates free-form medical advice.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

_APOSTROPHES = {"’": "'", "‘": "'", "ʼ": "'", "`": "'"}
_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9']+")

STOPWORDS = frozenset(
    "a an the and or of to in on at for is are am be been i me my we you your it this that "
    "with do does did can could should would will what how when where why which who please "
    "about have has had so if as by from".split()
)


def normalize(text: str) -> str:
    """Lower-case, strip accents, unify apostrophes and collapse whitespace."""
    if not text:
        return ""
    for src, dst in _APOSTROPHES.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _SPACE_RE.sub(" ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize(text))


def _features(text: str, ngram_range: tuple[int, int] = (3, 5)) -> Counter:
    """Word unigrams (minus stopwords) + character n-grams inside word boundaries."""
    feats: Counter = Counter()
    for tok in tokenize(text):
        if tok not in STOPWORDS:
            feats["w:" + tok] += 1
        padded = f" {tok} "
        lo, hi = ngram_range
        for n in range(lo, hi + 1):
            for i in range(len(padded) - n + 1):
                feats["c:" + padded[i : i + n]] += 1
    return feats


@dataclass(frozen=True)
class Match:
    doc_id: str
    score: float


class TfidfRetriever:
    """Minimal TF-IDF + cosine-similarity retriever."""

    def __init__(self, documents: dict[str, Sequence[str]]):
        """``documents`` maps a document id to one or more example texts."""
        if not documents:
            raise ValueError("TfidfRetriever needs at least one document")
        raw = {doc_id: _features(" \n ".join(texts)) for doc_id, texts in documents.items()}
        n_docs = len(raw)
        df: Counter = Counter()
        for feats in raw.values():
            df.update(feats.keys())
        # Smoothed IDF (same form as scikit-learn's default).
        self._idf = {f: math.log((1 + n_docs) / (1 + c)) + 1.0 for f, c in df.items()}
        self._vectors = {doc_id: self._weight(feats) for doc_id, feats in raw.items()}

    def _weight(self, feats: Counter) -> dict[str, float]:
        vec = {f: (1 + math.log(tf)) * self._idf[f] for f, tf in feats.items() if f in self._idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {f: v / norm for f, v in vec.items()}

    def query(self, text: str, top_k: int = 3) -> list[Match]:
        q = self._weight(_features(text))
        if not q:
            return []
        scores = []
        for doc_id, vec in self._vectors.items():
            small, large = (q, vec) if len(q) < len(vec) else (vec, q)
            s = sum(w * large.get(f, 0.0) for f, w in small.items())
            scores.append(Match(doc_id, round(s, 4)))
        scores.sort(key=lambda m: m.score, reverse=True)
        return scores[:top_k]


def contains_any(text: str, phrases: Iterable[str]) -> bool:
    t = f" {normalize(text)} "
    return any(f" {normalize(p)} " in t for p in phrases)
