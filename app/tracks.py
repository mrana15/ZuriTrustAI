"""90-day execution tracks: enrolment, weekly check-ins and completion.

Stores only a pseudonymous user id, the start date and the weeks in which the
user checked in (SQLite, standard library). No names, phone numbers or message
text. ``delete`` supports the user's right to erase their data.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

TRACK_WEEKS = 13            # 91 days
COMPLETION_MIN_CHECKINS = 10  # check-ins in at least 10 of 13 weeks counts as completed


@dataclass
class TrackStatus:
    started: date
    week: int            # current week number, 1..13 (capped)
    checkins: list[int]  # distinct weeks with a check-in
    finished: bool       # 91 days have passed
    completed: bool      # met the completion rule

    @property
    def summary(self) -> str:
        return (
            f"Week {self.week} of {TRACK_WEEKS}. Check-ins: {len(self.checkins)}/{TRACK_WEEKS}. "
            f"Goal: {COMPLETION_MIN_CHECKINS}+ weeks."
        )


class TrackStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tracks (user TEXT PRIMARY KEY, started TEXT NOT NULL, checkins TEXT NOT NULL)"
        )
        self._conn.commit()

    def _row(self, user: str):
        return self._conn.execute("SELECT started, checkins FROM tracks WHERE user = ?", (user,)).fetchone()

    @staticmethod
    def _status(started: date, checkins: list[int], today: date) -> TrackStatus:
        days = (today - started).days
        week = min(days // 7 + 1, TRACK_WEEKS)
        return TrackStatus(
            started=started,
            week=max(week, 1),
            checkins=sorted(checkins),
            finished=days >= TRACK_WEEKS * 7,
            completed=len(checkins) >= COMPLETION_MIN_CHECKINS,
        )

    def enroll(self, user: str, today: date | None = None) -> tuple[TrackStatus, bool]:
        """Returns (status, newly_enrolled)."""
        today = today or date.today()
        with self._lock:
            row = self._row(user)
            if row:
                return self._status(date.fromisoformat(row[0]), json.loads(row[1]), today), False
            self._conn.execute("INSERT INTO tracks VALUES (?, ?, ?)", (user, today.isoformat(), "[]"))
            self._conn.commit()
        return self._status(today, [], today), True

    def checkin(self, user: str, today: date | None = None) -> TrackStatus | None:
        today = today or date.today()
        with self._lock:
            row = self._row(user)
            if not row:
                return None
            started, checkins = date.fromisoformat(row[0]), json.loads(row[1])
            st = self._status(started, checkins, today)
            if not st.finished and st.week not in checkins:
                checkins.append(st.week)
                self._conn.execute("UPDATE tracks SET checkins = ? WHERE user = ?", (json.dumps(checkins), user))
                self._conn.commit()
            return self._status(started, checkins, today)

    def status(self, user: str, today: date | None = None) -> TrackStatus | None:
        row = self._row(user)
        if not row:
            return None
        return self._status(date.fromisoformat(row[0]), json.loads(row[1]), today or date.today())

    def delete(self, user: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tracks WHERE user = ?", (user,))
            self._conn.commit()
            return cur.rowcount > 0

    def stats(self, today: date | None = None) -> dict:
        """Aggregate programme metrics. Completion rate uses only tracks that have finished."""
        today = today or date.today()
        rows = self._conn.execute("SELECT started, checkins FROM tracks").fetchall()
        sts = [self._status(date.fromisoformat(s), json.loads(c), today) for s, c in rows]
        finished = [s for s in sts if s.finished]
        done = sum(s.completed for s in finished)
        return {
            "enrolled": len(sts),
            "active": sum(not s.finished for s in sts),
            "finished": len(finished),
            "completed": done,
            "completion_rate": round(done / len(finished), 3) if finished else None,
            "rule": f"check-ins in at least {COMPLETION_MIN_CHECKINS} of {TRACK_WEEKS} weeks",
        }


def days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)
