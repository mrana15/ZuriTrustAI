"""Preliminary maternal and newborn danger-sign screening.

Transparent, rules-based triage over a clinically reviewed danger-sign list
(``data/danger_signs.json``). Natural-language symptom descriptions are mapped
to danger signs with phrase matching that handles negation ("no bleeding") and
clause boundaries ("no fever but bleeding").

Design principles
-----------------
* Safety first: when in doubt, escalate. The highest matched level wins.
* Explainable: every result lists exactly which signs were matched.
* Not a diagnosis: the output is a referral level, never a medical decision.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .nlp import normalize

DATA_DIR = Path(__file__).parent / "data"

NEGATORS = frozenset(
    "no not never without denies deny dont don't didnt didn't doesnt doesn't isnt isn't "
    "havent haven't hasnt hasn't nor none neither free".split()
)
NEGATION_WINDOW = 4
CLAUSE_BREAK_RE = re.compile(r"[.,;:!?]|\bbut\b|\band\b|\bhowever\b|\balthough\b|\bthough\b|\bnow\b")

DISCLAIMER = (
    "ZuriTrustAI gives information and referral support only. "
    "It does not diagnose. Always follow the advice of a qualified health worker."
)


@dataclass
class MatchedSign:
    id: str
    label: str
    level: str


@dataclass
class ScreeningResult:
    level: str
    referral_level: str
    advice: str
    signs: list[MatchedSign] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    content_version: str = ""
    model: dict | None = None  # second opinion from the trained classifier, if loaded

    @property
    def is_danger(self) -> bool:
        return self.level in ("emergency", "urgent")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_danger"] = self.is_danger
        return d


def _phrase_regex(phrase: str) -> re.Pattern:
    words = [re.escape(w) for w in normalize(phrase).split()]
    return re.compile(r"(?<![a-z0-9'])" + r"\s+".join(words) + r"(?![a-z0-9'])")


class DangerSignScreener:
    MODEL_NOTE = (
        "Our AI model noticed words that are sometimes linked to warning signs. "
        "If you are unsure or it gets worse, please get checked by a health worker today."
    )

    def __init__(
        self,
        path: Path | None = None,
        emergency_number: str = "112",
        model_path: Path | None | bool = None,
        model_threshold: float = 0.85,
    ):
        path = path or DATA_DIR / "danger_signs.json"
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        self.version = cfg.get("version", "")
        self.review_status = cfg.get("review_status", "")
        self.levels = cfg["levels"]
        self.signs = {s["id"]: s for s in cfg["signs"]}
        self.emergency_number = emergency_number
        self._compiled: dict[str, re.Pattern] = {}
        self.model_threshold = model_threshold
        self.model = None
        if model_path is not False:
            from .classifier import NaiveBayesClassifier

            mp = Path(model_path) if model_path else DATA_DIR / "triage_model.json"
            if mp.exists():
                self.model = NaiveBayesClassifier.load(mp)
        for sign in cfg["signs"]:
            unknown = sign["level"] not in self.levels
            if unknown:
                raise ValueError(f"Unknown level {sign['level']!r} for sign {sign['id']}")

    # ------------------------------------------------------------------ matching
    def _rx(self, phrase: str) -> re.Pattern:
        if phrase not in self._compiled:
            self._compiled[phrase] = _phrase_regex(phrase)
        return self._compiled[phrase]

    @staticmethod
    def _is_negated(text: str, start: int) -> bool:
        clause = CLAUSE_BREAK_RE.split(text[:start])[-1]
        preceding = clause.split()[-NEGATION_WINDOW:]
        return any(tok in NEGATORS for tok in preceding)

    @staticmethod
    def _clause_id(text: str, pos: int) -> int:
        return len(CLAUSE_BREAK_RE.findall(text[:pos]))

    def _occurrences(self, text: str, phrases: Iterable[str], exclude_context: Iterable[str] = ()) -> list[tuple[int, int]]:
        """Return (start, end) spans of non-negated phrase occurrences.

        ``exclude_context`` words (e.g. "gums", "nose" for bleeding) cancel a match
        when they appear in the same clause, within 4 words before or 3 words after.
        """
        spans = []
        excl = {normalize(e) for e in exclude_context}
        for phrase in phrases:
            for m in self._rx(phrase).finditer(text):
                if self._is_negated(text, m.start()):
                    continue
                if excl:
                    before = CLAUSE_BREAK_RE.split(text[: m.start()])[-1].split()[-4:]
                    after = CLAUSE_BREAK_RE.split(text[m.end():])[0].split()[:3]
                    if excl & set(before + after):
                        continue
                spans.append((m.start(), m.end()))
        return spans

    def _matches(self, sign: dict, text: str) -> bool:
        if "phrases" in sign:
            return bool(self._occurrences(text, sign["phrases"], sign.get("exclude_context", ())))
        groups = [self._occurrences(text, g) for g in sign.get("all_of", [])]
        if not groups or not all(groups):
            return False
        if not sign.get("same_clause"):
            return True
        # every group must occur in the same clause (e.g. "severe ... belly pain")
        clause_sets = [{self._clause_id(text, s) for s, _ in g} for g in groups]
        return bool(set.intersection(*clause_sets))

    # ------------------------------------------------------------------ public API
    def screen_text(self, text: str) -> ScreeningResult:
        norm = normalize(text)
        matched = [s for s in self.signs.values() if self._matches(s, norm)]
        result = self._result(matched)
        if self.model is not None:
            # Second opinion: may add a caution note, never changes the rules decision.
            p = self.model.predict_proba(norm)
            p_danger = round(p.get("emergency", 0) + p.get("urgent", 0), 4)
            flag = result.level == "routine" and p_danger >= self.model_threshold
            result.model = {"p_danger": p_danger, "flag": flag}
            if flag:
                result.advice = f"{result.advice} {self.MODEL_NOTE}"
        return result

    def screen_ids(self, sign_ids: Iterable[str]) -> ScreeningResult:
        unknown = [i for i in sign_ids if i not in self.signs]
        if unknown:
            raise KeyError(f"Unknown danger sign id(s): {', '.join(unknown)}")
        return self._result([self.signs[i] for i in dict.fromkeys(sign_ids)])

    def list_signs(self) -> list[dict]:
        return [{"id": s["id"], "label": s["label"], "level": s["level"]} for s in self.signs.values()]

    def _result(self, matched: list[dict]) -> ScreeningResult:
        superseded = {sid for s in matched for sid in s.get("supersedes", [])}
        matched = [s for s in matched if s["id"] not in superseded]
        matched.sort(key=lambda s: -self.levels[s["level"]]["rank"])
        level = matched[0]["level"] if matched else "routine"
        lvl = self.levels[level]
        override = next((s["advice_override"] for s in matched if s.get("advice_override")), None)
        advice = (override or lvl["advice"]).format(emergency_number=self.emergency_number)
        return ScreeningResult(
            level=level,
            referral_level=lvl["referral_level"],
            advice=advice,
            signs=[MatchedSign(s["id"], s["label"], s["level"]) for s in matched],
            content_version=self.version,
        )
