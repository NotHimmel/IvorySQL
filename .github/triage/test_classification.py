import unittest
from unittest.mock import patch

import triage
from test_submissions import COMPLETE_BUG
from test_triage import FakeGitHub, issue


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()
        cls.ai_env = {"TRIAGE_AI_MODEL": "test-model", "AI_API_KEY": "never-log-this"}

    def test_ai_assigns_the_type_when_no_type_label_exists(self):
        current = issue(title="Version constructor rejects full psql output", body=COMPLETE_BUG)
        with patch("triage.ask_ai", return_value=([{"label": "type/bug", "source": "ai", "evidence": "crashes"}], {})) as ai:
            result = triage.analyze(FakeGitHub(current), 20, self.config, ai_env=self.ai_env)
        ai.assert_called_once()
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertNotIn("Issue type", result["details"]["missing"])

    def test_existing_canonical_type_wins_over_ai(self):
        current = issue(body=COMPLETE_BUG, labels=["type/enhancement"])
        with patch("triage.ask_ai", return_value=([{"label": "type/bug", "source": "ai", "evidence": "crashes"}], {})):
            result = triage.analyze(FakeGitHub(current), 20, self.config, ai_env=self.ai_env)
        self.assertNotIn("type/bug", result["labels"]["add"])
        self.assertNotIn("type/enhancement", result["labels"]["remove"])

    def test_legacy_bug_label_is_recognized_even_when_ai_fails(self):
        current = issue(title="Version constructor rejects full psql output", body=COMPLETE_BUG, labels=["bug"])
        with patch("triage.ask_ai", side_effect=triage.APIError(429)):
            result = triage.analyze(FakeGitHub(current), 20, self.config, ai_env=self.ai_env)
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(result["analysis"]["error"], {"kind": "APIError", "http_status": 429})
        self.assertNotIn("never-log-this", str(result))

    def test_other_legacy_type_labels_are_normalized(self):
        for label, expected in (("enhancement", "type/enhancement"), ("feature", "type/feature"), ("feature-request", "type/feature")):
            with self.subTest(label=label):
                current = issue(title="Please investigate", body="Description: Improve an existing workflow.\nAI model: not used", labels=[label])
                result = triage.analyze(FakeGitHub(current), 20, self.config)
                self.assertIn(expected, result["labels"]["add"])

    def test_explicit_form_type_wins_over_ai(self):
        current = issue(title="Unexpected behavior", body="Issue type: enhancement\nDescription: Improve an existing workflow.\nAI model: not used")
        with patch("triage.ask_ai", return_value=([{"label": "type/bug", "source": "ai", "evidence": "workflow"}], {})):
            result = triage.analyze(FakeGitHub(current), 20, self.config, ai_env=self.ai_env)
        self.assertIn("type/enhancement", result["labels"]["add"])
        self.assertNotIn("type/bug", result["labels"]["add"])

    def test_failed_ai_without_rule_evidence_requests_maintainer_classification(self):
        current = issue(title="Please investigate", body="Description: Something is unexpected.\nAI model: not used")
        with patch("triage.ask_ai", side_effect=triage.APIError(503)):
            result = triage.analyze(FakeGitHub(current), 20, self.config, ai_env=self.ai_env)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("triage/needs-review", result["labels"]["add"])
        self.assertNotIn("Issue type:", result["comment"])

    def test_unknown_type_does_not_hide_other_clear_missing_fields(self):
        result = triage.analyze(FakeGitHub(issue(title="Please investigate", body="Something is unexpected.")), 20, self.config)
        self.assertTrue(any(name.startswith("AI model") for name in result["details"]["missing"]))
        self.assertNotIn("Issue type", result["details"]["missing"])
        self.assertIn("Yes. Please provide:", result["comment"])

    def test_rule_type_is_kept_if_ai_abstains(self):
        with patch("triage.ask_ai", return_value=([], {})):
            result = triage.analyze(FakeGitHub(issue(body=COMPLETE_BUG)), 20, self.config, ai_env=self.ai_env)
        self.assertIn("type/bug", result["labels"]["add"])


if __name__ == "__main__":
    unittest.main()
