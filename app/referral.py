"""Referral routing: map a screening result to suitable health facilities."""
from __future__ import annotations

import json
from pathlib import Path

from .nlp import normalize

DATA_DIR = Path(__file__).parent / "data"

# Which facility levels can handle each referral level, in order of preference.
LEVELS_FOR_REFERRAL = {
    "emergency": ["tertiary", "secondary"],          # 24h emergency obstetric / newborn care
    "same_day": ["secondary", "tertiary", "primary"],
    "routine": ["primary", "secondary", "tertiary"],
}


class ReferralDirectory:
    def __init__(self, path: Path | None = None):
        path = path or DATA_DIR / "facilities.sample.json"
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        self.note = cfg.get("note", "")
        self.emergency_number = cfg.get("emergency_number", "112")
        self.facilities = cfg["facilities"]
        self._aliases = {normalize(k): v for k, v in cfg.get("state_aliases", {}).items()}
        self.states = sorted({f["state"] for f in self.facilities})
        self._states_norm = {normalize(s): s for s in self.states}

    def resolve_state(self, text: str) -> str | None:
        t = normalize(text).replace(" state", "").strip(" .!")
        names = {**self._states_norm, **self._aliases}  # normalized name -> canonical state
        if t in names:
            return names[t]
        for norm, state in names.items():  # e.g. "i am in lagos"
            if f" {norm} " in f" {t} ":
                return state
        return None

    def find(self, state: str | None, referral_level: str = "routine", limit: int = 3) -> list[dict]:
        order = LEVELS_FOR_REFERRAL.get(referral_level, LEVELS_FOR_REFERRAL["routine"])
        pool = [f for f in self.facilities if state is None or f["state"] == state]
        if referral_level == "emergency":
            pool = [f for f in pool if f.get("hours") == "24h"]
        pool = [f for f in pool if f["level"] in order]
        pool.sort(key=lambda f: order.index(f["level"]))
        return pool[:limit]

    @staticmethod
    def format_facility(f: dict) -> str:
        return f"- {f['name']}, {f['area']} ({f['hours']}). Tel: {f['phone']}"
