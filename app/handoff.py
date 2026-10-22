"""Hand-off to Zuri Circle's licensed health professionals (telehealth).

When a user asks to talk to a person, a hand-off *ticket* is sent to a staff
webhook (e.g. the clinicians' case-management tool or a secure team channel).
The ticket contains a pseudonymous id, triage level and matched sign ids. The
user's phone number is included **only** after the user explicitly consents.
Message text is never sent.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import requests

log = logging.getLogger("zuritrustai.handoff")


class HandoffService:
    def __init__(self, webhook_url: str = "", telehealth_contact: str = "", timeout: float = 8.0):
        self.webhook_url = webhook_url
        self.telehealth_contact = telehealth_contact
        self.timeout = timeout
        self.sent: list[dict] = []  # last tickets, kept in memory for tests/dry-run

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def request(self, user: str, channel: str, level: str = "routine", signs: list[str] | None = None,
                contact: str | None = None) -> str | None:
        ticket = {
            "ticket": "ZT-" + secrets.token_hex(4).upper(),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user": user,
            "channel": channel,
            "level": level,
            "signs": signs or [],
            "contact": contact,  # only set after explicit consent
        }
        self.sent = (self.sent + [ticket])[-50:]
        if not self.enabled:
            log.info("Hand-off dry-run: ticket %s not sent (no webhook configured)", ticket["ticket"])
            return ticket["ticket"]
        try:
            r = requests.post(self.webhook_url, json=ticket, timeout=self.timeout)
            if r.status_code >= 400:
                log.error("Hand-off webhook error %s", r.status_code)
                return None
        except requests.RequestException as exc:
            log.error("Hand-off webhook failed: %s", type(exc).__name__)
            return None
        return ticket["ticket"]
