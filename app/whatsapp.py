"""WhatsApp Business Cloud API integration (Meta).

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
* GET  webhook - subscription verification (hub.challenge)
* POST webhook - incoming messages, signed with X-Hub-Signature-256
* send_text   - reply through the Graph API
If no access token is configured the client runs in dry-run mode and only
logs that a message *would* have been sent (no content is logged).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import requests

log = logging.getLogger("zuritrustai.whatsapp")


@dataclass(frozen=True)
class IncomingMessage:
    sender: str
    text: str
    message_id: str


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret:
        return True  # signature checking disabled (development only)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_incoming(payload: dict) -> list[IncomingMessage]:
    """Extract text messages from a webhook payload. Non-text messages get a placeholder."""
    out: list[IncomingMessage] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                sender, mid = msg.get("from"), msg.get("id", "")
                if not sender:
                    continue
                mtype = msg.get("type")
                if mtype == "text":
                    text = (msg.get("text") or {}).get("body", "")
                elif mtype == "interactive":
                    inter = msg.get("interactive") or {}
                    text = ((inter.get("button_reply") or inter.get("list_reply") or {}).get("id", ""))
                else:
                    text = ""  # voice notes / images are not processed in v0.1
                out.append(IncomingMessage(sender, text[:1000], mid))
    return out


class WhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str, api_version: str = "v21.0", timeout: float = 10.0):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.timeout = timeout

    @property
    def dry_run(self) -> bool:
        return not (self.access_token and self.phone_number_id)

    def send_text(self, to: str, text: str) -> bool:
        if self.dry_run:
            log.info("WhatsApp dry-run: reply of %d chars not sent (no credentials)", len(text))
            return False
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text[:4096]},
        }
        try:
            r = requests.post(
                self.url,
                json=payload,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.error("WhatsApp send failed: %s", type(exc).__name__)
            return False
        if r.status_code >= 400:
            log.error("WhatsApp API error %s", r.status_code)
            return False
        return True
