"""ZuriTrustAI web service (Flask).

Run locally:   python -m app.main            (http://127.0.0.1:8000)
Production:    gunicorn -w 2 -b 0.0.0.0:8000 "app.main:create_app()"
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from . import __version__
from .config import Config
from .dialogue import DialogueEngine
from .handoff import HandoffService
from .insights import compute_indicators
from .knowledge import KnowledgeBase
from .privacy import AuditLog, pseudonymize
from .referral import ReferralDirectory
from .screening import DangerSignScreener
from .sessions import SessionStore
from .tracks import TrackStore
from .whatsapp import WhatsAppClient, parse_incoming, verify_signature

STATIC_DIR = Path(__file__).parent / "static"
MAX_MESSAGE_CHARS = 1000

log = logging.getLogger("zuritrustai")


class RateLimiter:
    """Simple in-memory sliding-window limiter (per pseudonymous client key)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


class SeenIds:
    """Bounded set of processed WhatsApp message ids (webhooks can be retried)."""

    def __init__(self, maxlen: int = 5000):
        self._d: OrderedDict[str, None] = OrderedDict()
        self.maxlen = maxlen
        self._lock = threading.Lock()

    def add(self, mid: str) -> bool:
        with self._lock:
            if mid in self._d:
                return False
            self._d[mid] = None
            if len(self._d) > self.maxlen:
                self._d.popitem(last=False)
            return True


def create_app(config: Config | None = None) -> Flask:
    cfg = config or Config()
    app = Flask(__name__, static_folder=None)
    if cfg.trusted_proxies > 0:
        # Only trust X-Forwarded-* headers added by our own reverse proxy (e.g. nginx).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=cfg.trusted_proxies, x_proto=cfg.trusted_proxies)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    referrals = ReferralDirectory()
    screener = DangerSignScreener(
        emergency_number=cfg.emergency_number or referrals.emergency_number,
        model_threshold=cfg.model_threshold,
    )
    kb = KnowledgeBase(min_score=cfg.kb_min_score)
    audit = AuditLog(cfg.audit_log_path)
    tracks = TrackStore(cfg.tracks_db)
    handoff = HandoffService(cfg.handoff_webhook, cfg.telehealth_contact)
    engine = DialogueEngine(
        screener, kb, referrals, SessionStore(cfg.session_ttl_seconds), audit, tracks=tracks, handoff=handoff
    )
    wa = WhatsAppClient(cfg.wa_access_token, cfg.wa_phone_number_id, cfg.wa_api_version)
    limiter = RateLimiter(cfg.rate_limit_per_minute)
    seen = SeenIds()

    app.extensions["zuri"] = {"engine": engine, "screener": screener, "kb": kb, "referrals": referrals, "whatsapp": wa, "config": cfg, "tracks": tracks, "handoff": handoff}

    def client_key() -> str:
        # remote_addr is the direct peer, or the client address resolved by ProxyFix when
        # ZURI_TRUSTED_PROXIES is set. Raw client-supplied X-Forwarded-For is never trusted.
        return pseudonymize(request.remote_addr or "unknown", cfg.hmac_secret)

    @app.before_request
    def _rate_limit():
        if request.path.startswith("/api/") and not limiter.allow(client_key()):
            return jsonify(error="Too many requests. Please wait a minute."), 429

    @app.after_request
    def _security_headers(resp):
        resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def _json_body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, description="Expected a JSON object")
        return data

    @app.errorhandler(401)
    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def _err(e):
        return jsonify(error=getattr(e, "description", "Error")), e.code

    # ---------------------------------------------------------------- web
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC_DIR, name, max_age=3600)

    @app.get("/health")
    def health():
        return jsonify(
            status="ok", version=__version__,
            danger_signs_version=screener.version, knowledge_base_version=kb.version,
            whatsapp="live" if cfg.whatsapp_enabled else "dry-run",
            triage_model=(screener.model.meta.get("trained") if screener.model else None),
            handoff="live" if handoff.enabled else "dry-run",
        )

    # ---------------------------------------------------------------- API
    @app.get("/api/danger-signs")
    def danger_signs():
        return jsonify(review_status=screener.review_status, version=screener.version, signs=screener.list_signs())

    @app.post("/api/screen")
    def screen():
        data = _json_body()
        if data.get("sign_ids"):
            ids = data["sign_ids"]
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                abort(400, description="sign_ids must be a list of strings")
            try:
                result = screener.screen_ids(ids)
            except KeyError as e:
                abort(400, description=str(e.args[0]))
        else:
            text = data.get("text", "")
            if not isinstance(text, str) or not text.strip():
                abort(400, description="Provide 'text' or 'sign_ids'")
            result = screener.screen_text(text[:MAX_MESSAGE_CHARS])
        audit.record(event="api_screen", user=client_key(), channel="api", level=result.level, signs=[s.id for s in result.signs])
        return jsonify(result.to_dict())

    @app.post("/api/chat")
    def chat():
        data = _json_body()
        message, session_id = data.get("message", ""), data.get("session_id", "")
        if not isinstance(message, str) or not isinstance(session_id, str) or not session_id:
            abort(400, description="Provide 'message' and 'session_id' strings")
        reply = engine.handle(pseudonymize(session_id, cfg.hmac_secret), message[:MAX_MESSAGE_CHARS], channel="web")
        return jsonify(reply.to_dict())

    @app.get("/api/facilities")
    def facilities():
        state_q = request.args.get("state", "")
        level = request.args.get("level", "routine")
        state = referrals.resolve_state(state_q) if state_q else None
        if state_q and not state:
            return jsonify(state=None, facilities=[], states=referrals.states, note=referrals.note)
        return jsonify(state=state, facilities=referrals.find(state, level, limit=10), states=referrals.states, note=referrals.note)

    @app.get("/api/insights")
    def insights():
        # Aggregated, de-identified indicators for programme staff only.
        if not cfg.admin_token:
            abort(404)
        import hmac as _hmac
        supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not _hmac.compare_digest(supplied.encode(), cfg.admin_token.encode()):
            return jsonify(error="Unauthorized"), 401
        return jsonify(compute_indicators(cfg.audit_log_path, tracks.stats()))

    @app.get("/api/resources")
    def resources():
        return jsonify(engine.resources)

    # ---------------------------------------------------------------- WhatsApp
    @app.get("/webhook/whatsapp")
    def wa_verify():
        if (
            request.args.get("hub.mode") == "subscribe"
            and cfg.wa_verify_token
            and request.args.get("hub.verify_token") == cfg.wa_verify_token
        ):
            return request.args.get("hub.challenge", ""), 200
        return "Forbidden", 403

    @app.post("/webhook/whatsapp")
    def wa_receive():
        body = request.get_data()
        if not verify_signature(cfg.wa_app_secret, body, request.headers.get("X-Hub-Signature-256")):
            return "Invalid signature", 403
        payload = request.get_json(silent=True) or {}
        processed = 0
        for msg in parse_incoming(payload):
            if msg.message_id and not seen.add(msg.message_id):
                continue
            user = pseudonymize(msg.sender, cfg.hmac_secret)
            text = msg.text or "menu"
            reply = engine.handle(user, text, channel="whatsapp", contact=msg.sender)
            wa.send_text(msg.sender, reply.text)
            processed += 1
        # Always 200 so Meta does not retry endlessly.
        return jsonify(processed=processed), 200

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=8000, debug=False)
