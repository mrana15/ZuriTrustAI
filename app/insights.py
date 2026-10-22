"""Anonymized community health indicators for programme planning.

Aggregates the de-identified audit log (no message text, no phone numbers)
into counts that help Zuri Circle and partners plan resources: how many
danger-sign screens by level and week, which states referrals come from,
which signs are most common, and which questions the knowledge base could not
answer (content gaps). Counts below ``MIN_CELL`` are suppressed ("<5") so
small groups cannot be singled out.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MIN_CELL = 5


def _suppress(n: int) -> int | str:
    return n if n >= MIN_CELL else f"<{MIN_CELL}"


def _suppress_counter(c: Counter) -> dict:
    return {k: _suppress(v) for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))}


def compute_indicators(audit_path: str | Path, track_stats: dict | None = None) -> dict:
    path = Path(audit_path)
    screens_by_level: Counter = Counter()
    screens_by_week: dict[str, Counter] = defaultdict(Counter)
    referrals_by_state: Counter = Counter()
    signs: Counter = Counter()
    events: Counter = Counter()
    users: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = e.get("event", "")
            events[ev] += 1
            if e.get("user"):
                users.add(e["user"])
            if ev in ("screen", "api_screen") and e.get("level"):
                screens_by_level[e["level"]] += 1
                try:
                    y, w, _ = datetime.fromisoformat(e["ts"]).isocalendar()
                    screens_by_week[f"{y}-W{w:02d}"][e["level"]] += 1
                except (KeyError, ValueError):
                    pass
                signs.update(e.get("signs") or [])
            elif ev == "referral" and e.get("state"):
                referrals_by_state[e["state"]] += 1
    return {
        "note": f"De-identified aggregate counts. Values below {MIN_CELL} are suppressed.",
        "unique_users": _suppress(len(users)),
        "events": _suppress_counter(events),
        "screens_by_level": _suppress_counter(screens_by_level),
        "screens_by_week": {wk: _suppress_counter(c) for wk, c in sorted(screens_by_week.items())},
        "referrals_by_state": _suppress_counter(referrals_by_state),
        "top_danger_signs": _suppress_counter(Counter(dict(signs.most_common(10)))),
        "knowledge_gaps": _suppress(events.get("kb_no_answer", 0)),
        "handoffs": _suppress(events.get("handoff", 0)),
        "execution_tracks": track_stats,
    }
