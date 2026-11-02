import unittest
from unittest.mock import patch

import triage
from test_submissions import COMPLETE_BUG
from test_triage import FakeGitHub, issue
from test_recovery import FailingGitHub


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

    def test_legacy_bug_is_replaced_and_its_manual_priority_is_preserved(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG, labels=["bug"]))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("type/bug", github.current["labels"])
        self.assertNotIn("bug", github.current["labels"])
        state = triage.read_state(triage.bot_comment(github.thread))
        self.assertNotIn("type/bug", state["managed"])
        add = next(index for index, (path, method, _) in enumerate(github.writes) if path.endswith("/labels") and method == "POST")
        remove = next(index for index, (path, method, _) in enumerate(github.writes) if path.endswith("/labels/bug") and method == "DELETE")
        self.assertLess(add, remove)
        with patch("triage.ask_ai", return_value=([{"label": "type/feature", "source": "ai", "evidence": "subscription"}], {})):
            triage.analyze(github, 20, self.config, apply=True, ai_env=self.ai_env)
        self.assertIn("type/bug", github.current["labels"])
        self.assertNotIn("type/feature", github.current["labels"])

    def test_existing_duplicate_legacy_label_is_removed_without_readding_the_type(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG, labels=["bug", "type/bug"]))
        result = triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("bug", result["labels"]["remove"])
        self.assertNotIn("type/bug", result["labels"]["add"])
        self.assertIn("type/bug", github.current["labels"])
        self.assertNotIn("bug", github.current["labels"])

    def test_old_feature_template_enhancement_label_is_redundant(self):
        github = FakeGitHub(issue(title="Please investigate", body="Description: Add a capability.\nAI model: not used",
                                  labels=["enhancement", "type/feature"]))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual({name for name in github.current["labels"] if name in {"enhancement", "type/feature", "type/enhancement"}},
                         {"type/feature"})

    def test_conflicting_legacy_label_is_left_for_maintainers(self):
        current = issue(labels=["bug", "type/feature"])
        plan = triage.label_plan(current, [], {"managed": [], "suppressed": []})
        self.assertNotIn("bug", plan["remove"])

    def test_failed_replacement_addition_keeps_the_legacy_label(self):
        github = FailingGitHub(issue(body=COMPLETE_BUG, labels=["bug"]))
        github.fail_when = lambda path, method, data: path.endswith("/labels") and method == "POST"
        with self.assertRaises(triage.APIError):
            triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("bug", github.current["labels"])
        self.assertNotIn("type/bug", github.current["labels"])
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("bug", github.current["labels"])
        self.assertNotIn("type/bug", triage.read_state(triage.bot_comment(github.thread))["managed"])

    def test_interrupted_legacy_removal_preserves_manual_priority_on_recovery(self):
        github = FailingGitHub(issue(body=COMPLETE_BUG, labels=["bug"]))
        github.fail_when = lambda path, method, data: method == "DELETE" and path.endswith("/labels/bug")
        github.fail_after = True
        with self.assertRaises(triage.APIError):
            triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("bug", github.current["labels"])
        self.assertEqual(triage.read_state(triage.bot_comment(github.thread))["pending"]["manual_types"], ["type/bug"])
        with patch("triage.ask_ai", return_value=([{"label": "type/feature", "source": "ai", "evidence": "subscription"}], {})):
            triage.analyze(github, 20, self.config, apply=True, ai_env=self.ai_env)
        self.assertIn("type/bug", github.current["labels"])
        self.assertNotIn("type/feature", github.current["labels"])
        self.assertNotIn("type/bug", triage.read_state(triage.bot_comment(github.thread))["managed"])


if __name__ == "__main__":
    unittest.main()
