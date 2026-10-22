import json
import tempfile
import unittest
from pathlib import Path

from app.knowledge import KnowledgeBase
from app.nlp import TfidfRetriever, normalize, tokenize
from app.privacy import AuditLog, pseudonymize, redact
from app.referral import ReferralDirectory


class NlpTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  I DON’T   feel  Well "), "i don't feel well")
        self.assertEqual(tokenize("Café, now!"), ["cafe", "now"])

    def test_retriever_ranks_relevant_doc_first(self):
        r = TfidfRetriever({"a": ["malaria mosquito net"], "b": ["breastfeeding baby milk"]})
        self.assertEqual(r.query("mosquito")[0].doc_id, "a")

    def test_retriever_requires_documents(self):
        with self.assertRaises(ValueError):
            TfidfRetriever({})


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase()

    def test_answers_common_questions(self):
        cases = {
            "what should i eat when pregnant": "nutrition",
            "how many antenatal visits": "anc_visits",
            "how long should i breastfeed": "breastfeeding",
            "mosquito net": "malaria",
        }
        for q, expected in cases.items():
            with self.subTest(q=q):
                self.assertEqual(self.kb.ask(q).id, expected)

    def test_tolerates_spelling_variation(self):
        self.assertEqual(self.kb.ask("wht food is gud for pregnant woman").id, "nutrition")

    def test_out_of_scope_returns_none(self):
        self.assertIsNone(self.kb.ask("what is the capital of france"))

    def test_every_entry_has_source(self):
        for e in self.kb.entries.values():
            self.assertTrue(e["source"], e["id"])


class PrivacyTests(unittest.TestCase):
    def test_pseudonymize_is_stable_and_keyed(self):
        a = pseudonymize("+2348012345678", "secret-1")
        self.assertEqual(a, pseudonymize("+2348012345678", "secret-1"))
        self.assertNotEqual(a, pseudonymize("+2348012345678", "secret-2"))
        self.assertNotIn("8012345678", a)
        with self.assertRaises(ValueError):
            pseudonymize("x", "")

    def test_redact(self):
        out = redact("call +234 801 234 5678 or mail a.b@example.com")
        self.assertNotIn("5678", out)
        self.assertNotIn("example.com", out)

    def test_audit_log_refuses_free_text_fields(self):
        with tempfile.TemporaryDirectory() as d:
            log = AuditLog(Path(d) / "audit.jsonl")
            with self.assertRaises(ValueError):
                log.record(event="screen", message="I am bleeding")
            log.record(event="screen", user="abc", level="emergency", signs=["vaginal_bleeding"])
            line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
            self.assertEqual(line["level"], "emergency")
            self.assertNotIn("message", line)


class ReferralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ReferralDirectory()

    def test_resolve_state(self):
        self.assertEqual(self.r.resolve_state("Abuja"), "FCT")
        self.assertEqual(self.r.resolve_state("I am in lagos"), "Lagos")
        self.assertIsNone(self.r.resolve_state("Atlantis"))

    def test_emergency_referral_only_24h_higher_level(self):
        for f in self.r.find("Lagos", "emergency"):
            self.assertEqual(f["hours"], "24h")
            self.assertIn(f["level"], ("tertiary", "secondary"))

    def test_routine_prefers_primary(self):
        self.assertEqual(self.r.find("Lagos", "routine")[0]["level"], "primary")


if __name__ == "__main__":
    unittest.main()
