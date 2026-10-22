import unittest

from app.screening import DangerSignScreener


class ScreeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = DangerSignScreener(emergency_number="112")

    def level(self, text):
        return self.s.screen_text(text).level

    def ids(self, text):
        return [m.id for m in self.s.screen_text(text).signs]

    def test_emergency_signs(self):
        for text in [
            "I am bleeding",
            "she is having fits",
            "bad headache and blurred vision",
            "fever and too weak to get out of bed",
            "severe pain in my belly",
            "I cannot breathe",
            "my baby is not moving",
            "baby is not feeding",
        ]:
            with self.subTest(text=text):
                self.assertEqual(self.level(text), "emergency")

    def test_urgent_signs(self):
        for text in ["I have a fever", "my feet are swollen", "my water broke", "baby moving less"]:
            with self.subTest(text=text):
                self.assertEqual(self.level(text), "urgent")

    def test_routine(self):
        self.assertEqual(self.level("I feel fine today"), "routine")

    def test_negation(self):
        self.assertEqual(self.level("no bleeding"), "routine")
        self.assertEqual(self.level("I don't have fever"), "routine")
        self.assertEqual(self.level("without any swelling"), "routine")

    def test_negation_stops_at_clause_boundary(self):
        self.assertEqual(self.level("no fever but I am bleeding"), "emergency")
        self.assertEqual(self.level("no pain, there is bleeding"), "emergency")

    def test_context_exclusion(self):
        self.assertEqual(self.level("my gums are bleeding"), "routine")
        self.assertEqual(self.level("I need a blood test"), "routine")

    def test_severe_abdominal_pain_needs_same_clause(self):
        self.assertEqual(self.level("severe headache and my stomach is upset"), "urgent")
        self.assertIn("severe_abdominal_pain", self.ids("my stomach pain is very bad"))

    def test_supersedes_removes_weaker_duplicate(self):
        ids = self.ids("I have fever and I am too weak to stand")
        self.assertIn("fever_too_weak", ids)
        self.assertNotIn("fever", ids)

    def test_highest_level_wins(self):
        r = self.s.screen_text("my feet are swollen and I am bleeding")
        self.assertEqual(r.level, "emergency")
        self.assertEqual(r.signs[0].level, "emergency")
        self.assertEqual(len(r.signs), 2)

    def test_advice_contains_emergency_number(self):
        self.assertIn("112", self.s.screen_text("I am bleeding").advice)

    def test_self_harm_uses_supportive_advice(self):
        r = self.s.screen_text("I want to end my life")
        self.assertEqual(r.level, "emergency")
        self.assertIn("support", r.advice)

    def test_screen_ids(self):
        r = self.s.screen_ids(["swelling", "convulsions"])
        self.assertEqual(r.level, "emergency")
        with self.assertRaises(KeyError):
            self.s.screen_ids(["not_a_sign"])

    def test_result_always_has_disclaimer(self):
        d = self.s.screen_text("hello").to_dict()
        self.assertIn("does not diagnose", d["disclaimer"])
        self.assertFalse(d["is_danger"])

    def test_signs_have_valid_levels_and_labels(self):
        for s in self.s.list_signs():
            self.assertIn(s["level"], ("emergency", "urgent", "routine"))
            self.assertTrue(s["label"])


if __name__ == "__main__":
    unittest.main()
