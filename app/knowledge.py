"""Curated maternal-health knowledge base with NLP retrieval."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .nlp import TfidfRetriever

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Answer:
    id: str
    title: str
    text: str
    source: str
    score: float


class KnowledgeBase:
    def __init__(self, path: Path | None = None, min_score: float = 0.25):
        path = path or DATA_DIR / "knowledge_base.json"
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        self.version = cfg.get("version", "")
        self.entries = {e["id"]: e for e in cfg["entries"]}
        self.min_score = min_score
        self._retriever = TfidfRetriever(
            {e["id"]: [e["title"], *e["questions"]] for e in cfg["entries"]}
        )

    def ask(self, question: str) -> Answer | None:
        """Best verified answer, or None if nothing is similar enough."""
        matches = self._retriever.query(question, top_k=1)
        if not matches or matches[0].score < self.min_score:
            return None
        e = self.entries[matches[0].doc_id]
        return Answer(e["id"], e["title"], e["answer"], e["source"], matches[0].score)

    def get(self, entry_id: str) -> dict | None:
        return self.entries.get(entry_id)
