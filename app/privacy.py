"""Privacy-by-design helpers.

* Phone numbers and session ids are pseudonymized with a keyed HMAC before
  they are used as keys or written anywhere.
* The audit log records *events* (what kind of interaction, which triage
  level) - never message text, names or phone numbers.
* ``redact`` strips phone numbers and e-mail addresses from any string that
  might end up in application logs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

ALLOWED_AUDIT_FIELDS = frozenset({"event", "user", "channel", "level", "signs", "kb_id", "state", "score", "week"})


def pseudonymize(identifier: str, secret: str) -> str:
    """Stable, non-reversible id for a phone number or session id."""
    if not secret:
        raise ValueError("A non-empty secret is required for pseudonymization")
    digest = hmac.new(secret.encode(), identifier.strip().encode(), hashlib.sha256).hexdigest()
    return digest[:20]


def redact(text: str) -> str:
    text = _EMAIL_RE.sub("[email]", text)
    return _PHONE_RE.sub("[phone]", text)


class AuditLog:
    """Append-only JSON-lines log of de-identified events."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, **fields) -> dict:
        bad = set(fields) - ALLOWED_AUDIT_FIELDS
        if bad:
            # Defensive: refuse to log anything that is not on the allow-list.
            raise ValueError(f"Field(s) not allowed in audit log: {sorted(bad)}")
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
        if self.path:
            with self._lock, self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry
