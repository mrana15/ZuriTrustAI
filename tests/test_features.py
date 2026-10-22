"""Tests for the trained classifier, 90-day tracks, clinician hand-off and community indicators."""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.classifier import NaiveBayesClassifier, featurize
from app.insights import compute_indicators
from app.main import create_app
from app.screening import DangerSignScreener
from app.tracks import COMPLETION_MIN_CHECKINS, TrackStore
from tests.test_api_and_dialogue import make_config, wa_payload


class ClassifierTests(unittest.TestCase):
    def test_negation_marking(self):
        f = featurize("no bleeding but fever")
        self.assertIn("NOT_bleeding", f)
        self.assertIn("fever", f)  # scope ends at "but"

    def test_fit_predict_and_roundtrip(self):
        m = NaiveBayesClassifier().fit(
            ["heavy bleeding", "blood everywhere", "I feel fine", "all good today", "mild fever", "hot body"],
            ["emergency", "emergency", "routine", "routine", "urgent", "urgent"],
        )
        self.assertEqual(m.predict("bleeding a lot"), "emergency")
        m2 = NaiveBayesClassifier.from_dict(json.loads(json.dumps(m.to_dict())))
        self.assertEqual(m2.predict_proba("bleeding"), m.predict_proba("bleeding"))

    def test_shipped_model_is_loaded(self):
        s = DangerSignScreener()
        self.assertIsNotNone(s.model)
        self.assertGreater(s.model.meta["n_examples"], 500)

    def test_model_never_changes_rules_decision(self):
        with_model, without = DangerSignScreener(), DangerSignScreener(model_path=False)
        for text in ["I am bleeding", "my feet are swollen", "I feel fine", "I am losing water slowly",
                     "no bleeding", "my gums bleed"]:
            with self.subTest(text=text):
                self.assertEqual(with_model.screen_text(text).level, without.screen_text(text).level)

    def test_model_adds_caution_when_rules_miss(self):
        r = DangerSignScreener().screen_text("I am losing water slowly")
        self.assertEqual(r.level, "routine")
        self.assertTrue(r.model["flag"])
        self.assertIn("AI model", r.advice)


class TrackTests(unittest.TestCase):
    def setUp(self):
        self.t = TrackStore(":memory:")

    def test_enroll_checkin_once_per_week(self):
        start = date(2026, 1, 1)
        st, new = self.t.enroll("u1", today=start)
        self.assertTrue(new)
        self.assertFalse(self.t.enroll("u1", today=start)[1])
        self.t.checkin("u1", today=start)
        st = self.t.checkin("u1", today=start + timedelta(days=2))  # same week
        self.assertEqual(st.checkins, [1])
        st = self.t.checkin("u1", today=start + timedelta(days=8))
        self.assertEqual((st.week, st.checkins), (2, [1, 2]))

    def test_completion_and_stats(self):
        start = date(2026, 1, 1)
        self.t.enroll("done", today=start)
        self.t.enroll("partial", today=start)
        for w in range(COMPLETION_MIN_CHECKINS):
            self.t.checkin("done", today=start + timedelta(days=7 * w))
        self.t.checkin("partial", today=start)
        stats = self.t.stats(today=start + timedelta(days=95))
        self.assertEqual((stats["finished"], stats["completed"], stats["completion_rate"]), (2, 1, 0.5))

    def test_delete(self):
        self.t.enroll("u2")
        self.assertTrue(self.t.delete("u2"))
        self.assertIsNone(self.t.status("u2"))


class AppFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self.tmp.name, telehealth_contact="+234-000-HEALTH", admin_token="x" * 40)
        self.app = create_app(self.cfg)
        self.c = self.app.test_client()
        self.handoff = self.app.extensions["zuri"]["handoff"]

    def tearDown(self):
        self.tmp.cleanup()

    def chat(self, msg, sid="f1"):
        return self.c.post("/api/chat", json={"session_id": sid, "message": msg}).get_json()["reply"]

    def test_track_flow_and_delete(self):
        self.assertIn("Welcome to your 90-day", self.chat("join"))
        self.assertIn("Check-in saved", self.chat("checkin"))
        self.assertIn("Week 1 of 13", self.chat("progress"))
        self.chat("delete")
        self.assertIn("not joined", self.chat("progress"))

    def test_web_handoff_gives_direct_contact(self):
        self.assertIn("+234-000-HEALTH", self.chat("talk", sid="f2"))
        self.assertEqual(self.handoff.sent, [])  # no ticket without a contact to call back

    def test_whatsapp_handoff_requires_consent_and_sends_no_text(self):
        import hashlib, hmac
        def post(text, mid):
            body = json.dumps(wa_payload("2348011111111", text, mid)).encode()
            sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
            self.c.post("/webhook/whatsapp", data=body, content_type="application/json",
                        headers={"X-Hub-Signature-256": sig})
        post("I am bleeding heavily", "m1")
        post("5", "m2")
        self.assertEqual(self.handoff.sent, [])          # nothing sent before consent
        post("yes", "m3")
        t = self.handoff.sent[-1]
        self.assertEqual((t["level"], t["contact"]), ("emergency", "2348011111111"))
        self.assertIn("vaginal_bleeding", t["signs"])
        self.assertNotIn("heavily", json.dumps(t))       # message text never shared

    def test_handoff_decline_on_whatsapp(self):
        engine = self.app.extensions["zuri"]["engine"]
        self.assertIn("Reply YES", engine.handle("w1", "talk", channel="whatsapp", contact="2348000000001").text)
        self.assertIn("no request was sent", engine.handle("w1", "no", channel="whatsapp", contact="2348000000001").text)
        self.assertEqual(self.handoff.sent, [])

    def test_insights_auth_and_suppression(self):
        for i in range(6):
            self.chat("I am bleeding", sid=f"u{i}")
        self.chat("my feet are swollen", sid="v1")
        self.assertEqual(self.c.get("/api/insights").status_code, 401)
        d = self.c.get("/api/insights", headers={"Authorization": "Bearer " + "x" * 40}).get_json()
        self.assertEqual(d["screens_by_level"]["emergency"], 6)
        self.assertEqual(d["screens_by_level"]["urgent"], "<5")
        self.assertIn("execution_tracks", d)

    def test_insights_disabled_without_token(self):
        c = create_app(make_config(self.tmp.name)).test_client()
        self.assertEqual(c.get("/api/insights").status_code, 404)

    def test_compute_indicators_ignores_bad_lines(self):
        p = Path(self.tmp.name) / "a.jsonl"
        p.write_text('not json\n{"ts":"2026-01-05T10:00:00+00:00","event":"screen","level":"routine","user":"a"}\n')
        self.assertEqual(compute_indicators(p)["screens_by_level"], {"routine": "<5"})


if __name__ == "__main__":
    unittest.main()
