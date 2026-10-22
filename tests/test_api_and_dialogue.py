import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from app.config import Config
from app.main import create_app


def make_config(tmp: str, **overrides) -> Config:
    cfg = Config(
        hmac_secret="test-secret",
        audit_log_path=str(Path(tmp) / "audit.jsonl"),
        tracks_db=str(Path(tmp) / "tracks.sqlite3"),
        env="development",
        wa_verify_token="verify-me",
        wa_app_secret="app-secret",
        wa_access_token="",
        wa_phone_number_id="",
        rate_limit_per_minute=1000,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def wa_payload(sender: str, text: str, mid: str) -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": sender, "id": mid, "type": "text", "text": {"body": text}}
    ]}}]}]}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self.tmp.name)
        self.app = create_app(self.cfg)
        self.c = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def chat(self, msg, sid="s1"):
        return self.c.post("/api/chat", json={"session_id": sid, "message": msg}).get_json()

    # ---- basic endpoints
    def test_health_and_index(self):
        self.assertEqual(self.c.get("/health").get_json()["status"], "ok")
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ZuriTrustAI", r.get_data(as_text=True))
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_screen_text_and_ids(self):
        r = self.c.post("/api/screen", json={"text": "I am bleeding"}).get_json()
        self.assertEqual(r["level"], "emergency")
        r = self.c.post("/api/screen", json={"sign_ids": ["swelling"]}).get_json()
        self.assertEqual(r["level"], "urgent")

    def test_screen_validation(self):
        self.assertEqual(self.c.post("/api/screen", json={}).status_code, 400)
        self.assertEqual(self.c.post("/api/screen", json={"sign_ids": ["nope"]}).status_code, 400)
        self.assertEqual(self.c.post("/api/screen", data="x", content_type="text/plain").status_code, 400)

    def test_facilities(self):
        d = self.c.get("/api/facilities?state=abuja&level=emergency").get_json()
        self.assertEqual(d["state"], "FCT")
        self.assertTrue(all(f["hours"] == "24h" for f in d["facilities"]))
        self.assertIn("SAMPLE", d["note"])

    # ---- dialogue
    def test_menu(self):
        self.assertIn("Reply with a number", self.chat("hi")["reply"])

    def test_danger_is_detected_before_answering_questions(self):
        r = self.chat("what should I eat? also I am bleeding")
        self.assertEqual(r["triage"]["level"], "emergency")
        self.assertIn("Which state", r["reply"])
        r2 = self.chat("Lagos")
        self.assertIn("Go now", r2["reply"])
        self.assertTrue(r2["facilities"])

    def test_symptom_check_flow_routine(self):
        self.chat("2", sid="s2")
        r = self.chat("I feel okay, just tired", sid="s2")
        self.assertEqual(r["triage"]["level"], "routine")

    def test_knowledge_answer_and_fallback(self):
        r = self.chat("how long should I breastfeed", sid="s3")
        self.assertEqual(r["kb_id"], "breastfeeding")
        self.assertIn("Source:", r["reply"])
        r = self.chat("who won the football match", sid="s3")
        self.assertIn("do not have a verified answer", r["reply"])

    def test_resources_and_delete(self):
        self.assertIn("90-day", self.chat("4", sid="s4")["reply"])
        self.assertIn("deleted", self.chat("DELETE", sid="s4")["reply"])

    def test_audit_log_never_contains_message_text(self):
        self.chat("I am bleeding heavily", sid="s5")
        log = (Path(self.tmp.name) / "audit.jsonl").read_text()
        self.assertNotIn("heavily", log)
        self.assertNotIn("s5", log)  # session id is pseudonymized

    # ---- WhatsApp webhook
    def test_whatsapp_verification(self):
        ok = self.c.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=42")
        self.assertEqual((ok.status_code, ok.get_data(as_text=True)), (200, "42"))
        bad = self.c.get("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42")
        self.assertEqual(bad.status_code, 403)

    def _post_signed(self, payload, secret="app-secret"):
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.c.post("/webhook/whatsapp", data=body, content_type="application/json",
                           headers={"X-Hub-Signature-256": sig})

    def test_whatsapp_signed_message_is_processed_once(self):
        p = wa_payload("2348000000000", "I have fits", "wamid.1")
        self.assertEqual(self._post_signed(p).get_json()["processed"], 1)
        self.assertEqual(self._post_signed(p).get_json()["processed"], 0)  # retry is de-duplicated

    def test_whatsapp_rejects_bad_signature(self):
        r = self._post_signed(wa_payload("2348000000000", "hi", "wamid.2"), secret="wrong")
        self.assertEqual(r.status_code, 403)

    def test_rate_limit(self):
        app = create_app(make_config(self.tmp.name, rate_limit_per_minute=2))
        c = app.test_client()
        codes = [c.get("/api/danger-signs").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


if __name__ == "__main__":
    unittest.main()


class ProductionConfigTests(unittest.TestCase):
    STRONG = "a" * 8 + "9f3c2b7d4e1a6c8b0d5f2e7a9c3b1d4e6f8a0c2"

    def test_production_rejects_missing_or_placeholder_secret(self):
        from app.config import ConfigError
        for secret in ["", "REPLACE_WITH_RANDOM_64_HEX_CHARACTER_SECRET", "change-me-to-a-long-random-string", "short"]:
            with self.subTest(secret=secret), self.assertRaises(ConfigError):
                Config(env="production", hmac_secret=secret, wa_access_token="", wa_phone_number_id="")

    def test_production_requires_webhook_secret_when_whatsapp_enabled(self):
        from app.config import ConfigError
        with self.assertRaises(ConfigError):
            Config(env="production", hmac_secret=self.STRONG, wa_access_token="tok",
                   wa_phone_number_id="123", wa_app_secret="", wa_verify_token="verify-token-123456")
        ok = Config(env="production", hmac_secret=self.STRONG, wa_access_token="tok", wa_phone_number_id="123",
                    wa_app_secret=self.STRONG, wa_verify_token="verify-token-123456")
        self.assertTrue(ok.is_production)

    def test_development_replaces_placeholder_with_random_secret(self):
        import warnings
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            cfg = Config(env="development", hmac_secret="REPLACE_WITH_RANDOM_64_HEX_CHARACTER_SECRET")
        self.assertNotIn("REPLACE", cfg.hmac_secret)

    def test_spoofed_forwarded_for_does_not_bypass_rate_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = create_app(make_config(tmp, rate_limit_per_minute=2, trusted_proxies=0)).test_client()
            codes = [c.get("/api/danger-signs", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(3)]
            self.assertEqual(codes, [200, 200, 429])

    def test_trusted_proxy_uses_forwarded_client_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = create_app(make_config(tmp, rate_limit_per_minute=1, trusted_proxies=1)).test_client()
            a = c.get("/api/danger-signs", headers={"X-Forwarded-For": "10.0.0.1"}).status_code
            b = c.get("/api/danger-signs", headers={"X-Forwarded-For": "10.0.0.2"}).status_code
            self.assertEqual((a, b), (200, 200))
