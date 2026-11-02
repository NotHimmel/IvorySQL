"""AI usage choices and legacy declarations share one source history."""

import unittest

import triage
from test_submissions import comment
from test_triage import FakeGitHub, issue


class AIUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def github(self, disclosure):
        return FakeGitHub(issue(title="Enhancement: improve logging", body=(
            "### Description\n\nShow the compatibility mode in the prompt.\n\n" + disclosure)))

    def run_triage(self, github, apply=False):
        return triage.analyze(github, 20, self.config, apply=apply)

    def test_not_used_allows_an_empty_optional_model(self):
        for model in ("", "_No response_", "not used"):
            with self.subTest(model=model):
                result = self.run_triage(self.github("### AI usage\n\nNot used\n\n### AI model\n\n" + model))
                self.assertEqual(result["details"]["missing"], [])
                self.assertIn("ai-model/not-used", result["labels"]["add"])
                self.assertEqual(result["details"]["review_status"], "complete")

    def test_not_used_does_not_require_a_model_heading(self):
        result = self.run_triage(self.github("AI usage: Not used"))
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("ai-model/not-used", result["labels"]["add"])

    def test_used_requires_a_concrete_model(self):
        for model in ("", "_No response_", "Cursor", "not used"):
            with self.subTest(model=model):
                result = self.run_triage(self.github("### AI usage\n\nUsed\n\n### AI model\n\n" + model))
                self.assertEqual(result["details"]["reported_models"], [])
                self.assertIn("triage/needs-information", result["labels"]["add"])
                self.assertIn("AI model name/version", result["comment"])

    def test_used_with_multiple_models(self):
        result = self.run_triage(self.github("### AI usage\n\nUsed\n\n### AI model\n\nmodel-a-v2, model-b-v1"))
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual([m["label"] for m in result["details"]["reported_models"]],
                         ["ai-model/model-a-v2", "ai-model/model-b-v1"])

    def test_contradictory_default_and_model_require_clarification(self):
        result = self.run_triage(self.github("AI usage: Not used\nAI model: model-a-v2"))
        self.assertEqual(result["details"]["reported_models"], [])
        self.assertIn("triage/needs-information", result["labels"]["add"])

    def test_missing_invalid_or_quoted_choice_does_not_default_to_not_used(self):
        for disclosure in ("", "AI usage: _No response_", "AI usage: perhaps",
                           "> AI usage: Not used", "```\nAI usage: Not used\n```",
                           "<!-- AI usage: Not used -->"):
            with self.subTest(disclosure=disclosure):
                result = self.run_triage(self.github(disclosure))
                self.assertEqual(result["details"]["reported_models"], [])
                self.assertIn("triage/needs-information", result["labels"]["add"])

    def test_later_model_comment_corrects_not_used_choice(self):
        github = self.github("AI usage: Not used\nAI model: _No response_")
        self.run_triage(github, apply=True)
        github.thread.append(comment("AI model: model-a-v2"))
        result = self.run_triage(github, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("ai-model/model-a-v2", github.current["labels"])
        self.assertNotIn("ai-model/not-used", github.current["labels"])
        # Editing an unrelated paragraph must not revive the older default.
        github.current["body"] += "\n\nAdditional context."
        github.current["body_updated_at"] = "2026-10-31T12:00:00Z"
        result = self.run_triage(github, apply=True)
        self.assertIn("ai-model/model-a-v2", github.current["labels"])
        self.assertEqual(result["details"]["field_sources"]["AI model"]["source"], "comment:101")

    def test_later_not_used_choice_clears_an_older_model(self):
        github = self.github("AI usage: Used\nAI model: model-a-v2")
        self.run_triage(github, apply=True)
        github.thread.append(comment("AI usage: Not used"))
        result = self.run_triage(github, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("ai-model/not-used", github.current["labels"])
        self.assertNotIn("ai-model/model-a-v2", github.current["labels"])

    def test_switching_to_used_requires_a_model_then_recovers(self):
        github = self.github("AI usage: Not used")
        self.run_triage(github, apply=True)
        github.current["body"] = github.current["body"].replace("Not used", "Used")
        github.current["body_updated_at"] = "2026-10-28T12:00:00Z"
        result = self.run_triage(github, apply=True)
        self.assertEqual(result["details"]["reported_models"], [])
        self.assertIn("triage/needs-information", github.current["labels"])
        self.assertNotIn("ai-model/not-used", github.current["labels"])
        github.thread.append(comment("AI model: model-a-v2"))
        result = self.run_triage(github, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertNotIn("triage/needs-information", github.current["labels"])
        self.assertIn("ai-model/model-a-v2", github.current["labels"])

    def test_unknown_order_freezes_the_model_labels_for_review(self):
        github = self.github("AI usage: Not used")
        self.run_triage(github, apply=True)
        github.thread.append(comment("AI model: model-a-v2", updated_at="unknown"))
        result = self.run_triage(github, apply=True)
        self.assertIn("AI model", result["details"]["conflicts"])
        self.assertIn("triage/needs-review", github.current["labels"])
        self.assertIn("ai-model/not-used", github.current["labels"])
        self.assertNotIn("ai-model/model-a-v2", github.current["labels"])

    def test_empty_description_cannot_be_filled_by_the_usage_field(self):
        result = self.run_triage(FakeGitHub(issue(title="Enhancement: improve logging", body=(
            "### Description\n\nAI usage: Not used\nAI model: _No response_"))))
        self.assertIn("Issue description", result["details"]["missing"])
        self.assertIn("ai-model/not-used", result["labels"]["add"])

    def test_usage_metadata_is_excluded_from_classification_and_similarity(self):
        text = "### AI usage\n\nUsed\n\n### AI model\n\nmodel-a-v2\n\n### Description\n\nImprove logging."
        self.assertEqual(triage.without_model_metadata(text), "### Description\n\nImprove logging.")
        self.assertEqual(triage.without_model_metadata("AI usage: Not used\nImprove logging.").strip(),
                         "Improve logging.")
