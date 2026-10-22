"""Channel-independent conversation engine (used by WhatsApp and the web chat).

Every free-text message is screened for danger signs *first*. Information
answers are only given when no danger sign is detected, so a woman who writes
"what should I eat, I am also bleeding" is sent to care immediately.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from pathlib import Path

from .knowledge import KnowledgeBase
from .nlp import normalize
from .privacy import AuditLog
from .referral import ReferralDirectory
from .screening import DISCLAIMER, DangerSignScreener, ScreeningResult
from .sessions import SessionStore

if TYPE_CHECKING:  # avoid import cycles at runtime
    from .handoff import HandoffService
    from .tracks import TrackStore

DATA_DIR = Path(__file__).parent / "data"
MAX_REPLY_CHARS = 4000  # WhatsApp text limit is 4096

GREETINGS = {"hi", "hello", "hey", "start", "menu", "good morning", "good afternoon", "good evening", "0"}
DELETE_WORDS = {"stop", "delete", "delete my data", "forget me", "unsubscribe"}
TALK_WORDS = {"5", "five", "talk", "talk to someone", "doctor", "nurse", "human", "agent", "talk to a doctor", "talk to a nurse"}
YES_WORDS = {"yes", "y", "ok", "okay", "yes please"}
JOIN_WORDS = {"join", "join track", "start track"}
CHECKIN_WORDS = {"checkin", "check in", "check-in"}
PROGRESS_WORDS = {"progress", "my progress", "track"}

MENU = (
    "Welcome to ZuriTrustAI from Zuri Circle.\n"
    "Reply with a number:\n"
    "1 - Ask a question about pregnancy, birth or your newborn\n"
    "2 - Check how you are feeling (danger signs)\n"
    "3 - Find a health facility\n"
    "4 - Money and business support (90-day track)\n"
    "5 - Talk to a Zuri Circle health professional\n"
    "Reply DELETE at any time to clear your session.\n"
    "If you have bleeding, fits or difficult breathing, go to a hospital NOW."
)
SHORT_DISCLAIMER = "(Information only - not a diagnosis.)"
FALLBACK = (
    "Sorry, I do not have a verified answer for that yet. Please ask a health worker at your "
    "nearest clinic. Reply 2 to check for danger signs or MENU for options."
)


@dataclass
class Reply:
    text: str
    triage: dict | None = None
    kb_id: str | None = None
    facilities: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"reply": self.text, "triage": self.triage, "kb_id": self.kb_id, "facilities": self.facilities}


class DialogueEngine:
    def __init__(
        self,
        screener: DangerSignScreener,
        kb: KnowledgeBase,
        referrals: ReferralDirectory,
        sessions: SessionStore,
        audit: AuditLog,
        tracks: "TrackStore | None" = None,
        handoff: "HandoffService | None" = None,
    ):
        self.screener = screener
        self.kb = kb
        self.referrals = referrals
        self.sessions = sessions
        self.audit = audit
        self.tracks = tracks
        self.handoff = handoff
        self.resources = json.loads((DATA_DIR / "capability_resources.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    def handle(self, user_key: str, text: str, channel: str = "web", contact: str | None = None) -> Reply:
        """``contact`` (e.g. WhatsApp number) is only used for a hand-off the user consents to."""
        msg = normalize(text)
        if msg in DELETE_WORDS:
            self.sessions.delete(user_key)
            if self.tracks:
                self.tracks.delete(user_key)
            self.audit.record(event="session_deleted", user=user_key, channel=channel)
            return Reply("Your session and any 90-day track record have been deleted. Send HI to start again.")

        sess = self.sessions.get(user_key)
        if not msg or msg in GREETINGS:
            sess.state, sess.data = "idle", {}
            self.audit.record(event="menu", user=user_key, channel=channel)
            return Reply(MENU)

        # 1) Safety first: screen every message for danger signs.
        result = self.screener.screen_text(msg)
        if result.is_danger:
            return self._danger_reply(user_key, sess, result, channel)

        # 2) Hand-off to a health professional (any time, including right after a danger reply).
        if sess.state == "await_handoff_consent":
            return self._handoff_consent_reply(user_key, sess, msg, channel, contact)
        if msg in TALK_WORDS:
            return self._handoff_start(user_key, sess, channel)

        # 3) Conversation states.
        if sess.state == "await_location":
            return self._location_reply(user_key, sess, msg, channel)
        if sess.state == "await_symptoms":
            sess.state = "idle"
            self.audit.record(event="screen", user=user_key, channel=channel, level=result.level, signs=[])
            return Reply(f"{result.advice}\n\n{DISCLAIMER}", triage=result.to_dict())

        # 4) Menu choices and commands.
        if msg in {"1", "one"}:
            sess.state = "ask"
            return Reply("Please type your question about pregnancy, birth or caring for your newborn.")
        if msg in {"2", "two"}:
            sess.state = "await_symptoms"
            return Reply("Tell me how you are feeling in your own words. For example: 'I have a headache and my feet are swollen'.")
        if msg in {"3", "three"}:
            sess.state, sess.data = "await_location", {"referral_level": "routine"}
            return Reply(self._ask_state())
        if msg in {"4", "four"}:
            return self._resources_reply(user_key, channel)
        if msg in JOIN_WORDS | CHECKIN_WORDS | PROGRESS_WORDS:
            return self._track_reply(user_key, msg, channel)

        # 5) A state name on its own -> facility search.
        state = self.referrals.resolve_state(msg)
        if state and len(msg.split()) <= 4:
            sess.data = {"referral_level": "routine"}
            return self._location_reply(user_key, sess, msg, channel)

        # 6) Verified information from the knowledge base.
        caution = ""
        if result.model and result.model.get("flag"):
            caution = "\n\n" + self.screener.MODEL_NOTE + " Reply 5 to talk to a health professional."
            self.audit.record(event="model_caution", user=user_key, channel=channel, score=result.model["p_danger"])
        answer = self.kb.ask(msg)
        if answer:
            self.audit.record(event="kb_answer", user=user_key, channel=channel, kb_id=answer.id, score=answer.score)
            text = f"{answer.title}\n{answer.text}\nSource: {answer.source}\n{SHORT_DISCLAIMER}{caution}\nReply MENU for options."
            return Reply(text[:MAX_REPLY_CHARS], kb_id=answer.id, triage=result.to_dict() if caution else None)

        self.audit.record(event="kb_no_answer", user=user_key, channel=channel)
        return Reply(FALLBACK + caution, triage=result.to_dict() if caution else None)

    # ------------------------------------------------------------------ hand-off
    def _handoff_start(self, user_key: str, sess, channel: str) -> Reply:
        last = sess.data.get("last_triage", {"level": "routine", "signs": []})
        sess.state, sess.data = "await_handoff_consent", {"last_triage": last}
        if channel == "whatsapp":
            return Reply(
                "A Zuri Circle health professional can contact you. Reply YES to share your WhatsApp number "
                "with them for this request only, or NO to cancel.\n"
                f"If this is an emergency, do not wait: go to the nearest hospital or call {self.referrals.emergency_number}."
            )
        # Web chat has no phone number to call back: show the health team's contact directly.
        sess.state, sess.data = "idle", {"last_triage": last}
        direct = self.handoff.telehealth_contact if self.handoff else ""
        self.audit.record(event="handoff", user=user_key, channel=channel, level=last["level"])
        if direct:
            return Reply(
                f"You can reach a Zuri Circle health professional at {direct}.\n"
                f"In an emergency, go to the nearest hospital or call {self.referrals.emergency_number}."
            )
        return Reply(
            "Our health team is not available on this channel yet. Please visit your nearest clinic, or in an "
            f"emergency call {self.referrals.emergency_number}."
        )

    def _handoff_consent_reply(self, user_key: str, sess, msg: str, channel: str, contact: str | None) -> Reply:
        last = sess.data.get("last_triage", {"level": "routine", "signs": []})
        sess.state, sess.data = "idle", {}
        if msg not in YES_WORDS:
            return Reply("Okay, no request was sent. Reply MENU for options.")
        direct = self.handoff.telehealth_contact if self.handoff else ""
        ticket = None
        if self.handoff and contact:  # a call-back ticket is only useful with a consented contact
            ticket = self.handoff.request(user_key, channel, last["level"], last["signs"], contact=contact)
        self.audit.record(event="handoff", user=user_key, channel=channel, level=last["level"])
        lines = []
        if ticket and contact:
            lines.append(f"Your request {ticket} has been sent. A Zuri Circle health professional will contact you.")
        if direct:
            lines.append(f"You can {'also ' if ticket and contact else ''}reach our health team directly: {direct}.")
        if not lines:
            lines.append("Our health team is not available on this channel yet. Please visit your nearest clinic.")
        lines.append(f"In an emergency, go to the nearest hospital or call {self.referrals.emergency_number}.")
        return Reply("\n".join(lines))

    # ------------------------------------------------------------------ 90-day tracks
    def _track_reply(self, user_key: str, msg: str, channel: str) -> Reply:
        if not self.tracks:
            return Reply("The 90-day track is not available yet. Reply MENU for options.")
        if msg in JOIN_WORDS:
            st, new = self.tracks.enroll(user_key)
            self.audit.record(event="track_join" if new else "track_status", user=user_key, channel=channel, week=st.week)
            head = "Welcome to your 90-day execution track!" if new else "You are already on a 90-day track."
            return Reply(f"{head}\n{st.summary}\nReply CHECKIN once each week to log progress, PROGRESS to see it.")
        if msg in CHECKIN_WORDS:
            st = self.tracks.checkin(user_key)
            if st is None:
                return Reply("You have not joined a track yet. Reply JOIN to start your 90-day execution track.")
            self.audit.record(event="track_checkin", user=user_key, channel=channel, week=st.week)
            return Reply(f"Check-in saved. {st.summary}")
        st = self.tracks.status(user_key)
        if st is None:
            return Reply("You have not joined a track yet. Reply JOIN to start your 90-day execution track.")
        done = " Track completed - well done!" if st.completed else ""
        return Reply(st.summary + done)

    # ------------------------------------------------------------------
    def _danger_reply(self, user_key: str, sess, result: ScreeningResult, channel: str) -> Reply:
        sess.state = "await_location"
        sess.data = {
            "referral_level": result.referral_level,
            "last_triage": {"level": result.level, "signs": [x.id for x in result.signs]},
        }
        self.audit.record(
            event="screen", user=user_key, channel=channel, level=result.level,
            signs=[s.id for s in result.signs],
        )
        found = ", ".join(s.label.lower() for s in result.signs)
        text = (
            f"{result.advice}\n\nSigns noticed: {found}.\n\n"
            f"{self._ask_state()}\n"
            "Reply 5 to ask a Zuri Circle health professional to contact you.\n\n"
            f"{DISCLAIMER}"
        )
        return Reply(text[:MAX_REPLY_CHARS], triage=result.to_dict())

    def _ask_state(self) -> str:
        return "Which state are you in? (e.g. " + ", ".join(self.referrals.states[:4]) + ")"

    def _location_reply(self, user_key: str, sess, msg: str, channel: str) -> Reply:
        state = self.referrals.resolve_state(msg)
        level = sess.data.get("referral_level", "routine")
        if not state:
            return Reply(
                "Sorry, I could not find that state. " + self._ask_state()
                + f"\nIn an emergency call {self.referrals.emergency_number}."
            )
        facilities = self.referrals.find(state, level)
        sess.state, sess.data = "idle", {"last_triage": sess.data.get("last_triage", {"level": "routine", "signs": []})}
        self.audit.record(event="referral", user=user_key, channel=channel, level=level, state=state)
        if not facilities:
            return Reply(f"I do not have facility details for {state} yet. Please go to your nearest hospital or call {self.referrals.emergency_number}.")
        lines = "\n".join(self.referrals.format_facility(f) for f in facilities)
        head = "Go now to one of these facilities:" if level == "emergency" else "Health facilities near you:"
        return Reply(f"{head}\n{lines}\nEmergency: {self.referrals.emergency_number}", facilities=facilities)

    def _resources_reply(self, user_key: str, channel: str) -> Reply:
        self.audit.record(event="resources", user=user_key, channel=channel)
        items = "\n".join(f"- {r['title']}: {r['summary']}" for r in self.resources["resources"])
        return Reply(
            f"{self.resources['intro']}\n{items}\n"
            "Reply JOIN to start your 90-day execution track, CHECKIN each week, PROGRESS to see it.\n"
            "Reply MENU for options."
        )
