"""Trained NLP triage classifier (safety net behind the rules engine).

A multinomial Naive Bayes model over word unigrams and bigrams, with negation
marking ("no bleeding" -> "NOT_bleeding"). Pure Python, so it trains in seconds
and runs on a small server with no GPU.

Role in the system
------------------
The transparent rules engine (``screening.py``) makes the decision. The model
is a *second opinion* that can only **escalate**: if the rules find nothing but
the model is confident the message describes a warning sign, the user is told
to get checked the same day. The model can never downgrade a rules result.

Training data is synthetic (generated from the clinically reviewed danger-sign
list plus hand-written examples, see ``train_classifier.py``). It must be
retrained on de-identified, consented, clinician-labelled messages before any
claim about real-world performance.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from .nlp import normalize

_TOKEN_RE = re.compile(r"[a-z0-9']+|[.,;:!?]")
_NEGATORS = frozenset("no not never without dont don't didnt didn't doesnt doesn't isnt isn't havent haven't nor".split())
_BREAKS = frozenset(". , ; : ! ? but and however although".split())


def featurize(text: str) -> list[str]:
    """Word unigrams + bigrams with negation scope marking."""
    words, negate = [], False
    for tok in _TOKEN_RE.findall(normalize(text)):
        if tok in _BREAKS:
            negate = False
            continue
        if tok in _NEGATORS:
            negate = True
            words.append(tok)
            continue
        words.append(("NOT_" + tok) if negate else tok)
    feats = list(words)
    feats += [f"{a}__{b}" for a, b in zip(words, words[1:])]
    return feats


class NaiveBayesClassifier:
    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.classes: list[str] = []
        self.log_prior: dict[str, float] = {}
        self.log_lik: dict[str, dict[str, float]] = {}
        self.log_unseen: dict[str, float] = {}
        self.meta: dict = {}

    # ------------------------------------------------------------------ training
    def fit(self, texts: Sequence[str], labels: Sequence[str]) -> "NaiveBayesClassifier":
        if len(texts) != len(labels) or not texts:
            raise ValueError("texts and labels must be non-empty and the same length")
        counts: dict[str, Counter] = defaultdict(Counter)
        n_per_class = Counter(labels)
        vocab: set[str] = set()
        for t, y in zip(texts, labels):
            f = featurize(t)
            counts[y].update(f)
            vocab.update(f)
        self.classes = sorted(n_per_class)
        n = len(labels)
        v = len(vocab)
        self.log_prior = {c: math.log(n_per_class[c] / n) for c in self.classes}
        self.log_lik, self.log_unseen = {}, {}
        for c in self.classes:
            total = sum(counts[c].values()) + self.alpha * v
            self.log_lik[c] = {w: math.log((k + self.alpha) / total) for w, k in counts[c].items()}
            self.log_unseen[c] = math.log(self.alpha / total)
        self._vocab = vocab
        return self

    # ------------------------------------------------------------------ inference
    def predict_proba(self, text: str) -> dict[str, float]:
        feats = [f for f in featurize(text) if f in self._vocab]
        if not feats:
            return {c: math.exp(self.log_prior[c]) for c in self.classes}
        scores = {
            c: self.log_prior[c] + sum(self.log_lik[c].get(f, self.log_unseen[c]) for f in feats)
            for c in self.classes
        }
        m = max(scores.values())
        exp = {c: math.exp(s - m) for c, s in scores.items()}
        z = sum(exp.values())
        return {c: round(e / z, 4) for c, e in exp.items()}

    def predict(self, text: str) -> str:
        p = self.predict_proba(text)
        return max(p, key=p.get)

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return {
            "type": "multinomial_naive_bayes",
            "alpha": self.alpha,
            "classes": self.classes,
            "log_prior": self.log_prior,
            "log_lik": self.log_lik,
            "log_unseen": self.log_unseen,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NaiveBayesClassifier":
        m = cls(alpha=d["alpha"])
        m.classes, m.log_prior, m.log_lik, m.log_unseen = d["classes"], d["log_prior"], d["log_lik"], d["log_unseen"]
        m.meta = d.get("meta", {})
        m._vocab = set().union(*(set(v) for v in m.log_lik.values()))
        return m

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "NaiveBayesClassifier":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def cross_validate(texts: Sequence[str], labels: Sequence[str], k: int = 5, seed: int = 7) -> dict:
    """Stratified-ish k-fold accuracy and per-class recall."""
    import random

    idx = list(range(len(texts)))
    random.Random(seed).shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    correct, total = 0, 0
    per_class = defaultdict(lambda: [0, 0])
    for i in range(k):
        test = set(folds[i])
        tr = [j for j in idx if j not in test]
        m = NaiveBayesClassifier().fit([texts[j] for j in tr], [labels[j] for j in tr])
        for j in folds[i]:
            pred = m.predict(texts[j])
            ok = pred == labels[j]
            correct += ok
            total += 1
            per_class[labels[j]][0] += ok
            per_class[labels[j]][1] += 1
    return {
        "folds": k,
        "accuracy": round(correct / total, 4),
        "recall": {c: round(a / b, 4) for c, (a, b) in sorted(per_class.items())},
        "n": total,
    }


def iter_lines(items: Iterable[str]) -> list[str]:
    return [i for i in items if i and i.strip()]
