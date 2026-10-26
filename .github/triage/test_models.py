import json
from pathlib import Path
import re
import tokenize
import unittest
from unittest.mock import patch

import triage
from test_triage import FakeGitHub, issue


class ModelDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def extract(self, text):
        return triage.extract_reported_models(text, self.config)

    def test_inline_heading_chinese_and_bold_declarations(self):
        for text in ("AI model: Org/Model-A v2", "### AI model\n\nOrg/Model-A v2\n\n### Description\nA bug",
                     "使用的 AI 模型：Org/Model-A v2", "**AI model:** Org/Model-A v2"):
            with self.subTest(text=text):
                models, missing = self.extract(text)
                self.assertEqual(missing, [])
                self.assertEqual(models[0]["name"], "Org/Model-A v2")
                self.assertEqual(models[0]["label"], "ai-model/org-model-a-v2")

    def test_multiple_models_normalize_and_deduplicate(self):
        models, missing = self.extract("### AI models\n\n- Model-A v2\n- MODEL-A v2\n- model-b-v1")
        self.assertEqual(missing, [])
        self.assertEqual([m["label"] for m in models], ["ai-model/model-a-v2", "ai-model/model-b-v1"])

    def test_explicit_no_ai_is_a_disclosure(self):
        for declaration in ("未使用 AI", "not used", "no ai"):
            models, missing = self.extract("AI model: " + declaration)
            self.assertEqual(missing, [])
            self.assertEqual(models[0]["label"], "ai-model/not-used")

    def test_missing_placeholder_and_tool_only_need_information(self):
        for text in ("", "AI model:", "### AI model\n\n### Description\nA bug",
                     "AI model: _No response_", "AI model: unknown", "AI model: Cursor",
                     "AI model: 默认", "AI model: ???", "AI model: 1234"):
            with self.subTest(text=text):
                models, missing = self.extract(text)
                self.assertEqual(models, [])
                self.assertTrue(missing)

    def test_mentions_code_quotes_and_hidden_text_are_not_disclosures(self):
        for text in ("I compared model-a and model-b", "```text\nAI model: model-a\n```",
                     "~~~\nAI model: model-a\n~~~", "> AI model: model-a",
                     "<!-- AI model: model-a -->", "```\nAI model: model-a"):
            with self.subTest(text=text):
                self.assertTrue(self.extract(text)[1])

    def test_conflicting_no_ai_and_model_names_need_review(self):
        models, missing = self.extract("AI model: 未使用 AI, model-a-v2")
        self.assertEqual(models, [])
        self.assertTrue(missing)

    def test_latest_declaration_wins_even_if_incomplete(self):
        models, missing = self.extract("AI model: model-a-v2\n\nAI model: model-b-v1")
        self.assertEqual(models[0]["label"], "ai-model/model-b-v1")
        self.assertEqual(missing, [])
        self.assertTrue(self.extract("AI model: model-a-v2\n\nAI model: unknown")[1])

    def test_bounds_and_long_names(self):
        self.assertTrue(self.extract("AI model: " + ",".join(f"model-{n}" for n in range(6)))[1])
        first = triage.model_label("model-" + "a" * 80 + "x")
        second = triage.model_label("model-" + "a" * 80 + "y")
        self.assertLessEqual(len(first), 50)
        self.assertNotEqual(first, second)
        self.assertEqual(triage.model_label("Ｍｏｄｅｌ－Ａ"), "ai-model/model-a")

    def test_dynamic_labels_have_only_the_model_namespace(self):
        models, missing = self.extract("AI model: resolution/duplicate")
        self.assertEqual(missing, [])
        self.assertEqual(models[0]["label"], "ai-model/resolution-duplicate")
        client = triage.GitHub("example/postgres", "token")
        with patch.object(client, "pages", return_value=[]), patch.object(client, "call", return_value={}) as call:
            client.ensure_labels(self.config, [models[0]["label"]])
        self.assertEqual(call.call_args.args[2]["name"], "ai-model/resolution-duplicate")
        with self.assertRaises(ValueError):
            triage.label_definition(self.config, "unconfigured/label")

    def test_all_issue_types_require_model_disclosure(self):
        for title in ("Bug: crashes", "Feature request: new syntax", "Enhancement: improve logging"):
            result = triage.analyze(FakeGitHub(issue(title=title, body="A report")), 20, self.config)
            self.assertIn("triage/needs-information", result["labels"]["add"])
            self.assertTrue(any("AI model" in m for m in result["details"]["missing"]))

    def test_adding_a_model_label_does_not_replace_written_disclosure(self):
        current = issue(title="Enhancement: improve logging", body="A report", labels=["ai-model/manual"])
        result = triage.analyze(FakeGitHub(current), 20, self.config)
        self.assertIn("triage/needs-information", result["labels"]["add"])
        self.assertEqual(result["details"]["reported_models"], [])

    def test_reporter_followup_clears_only_the_bot_information_request(self):
        github = FakeGitHub(issue(title="Enhancement: improve logging", body="A report"))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("triage/needs-information", github.current["labels"])
        github.thread.append({"id": 101, "body": "AI model: model-a-v2",
                              "user": {"login": "reporter", "type": "User"}})
        result = triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("ai-model/model-a-v2", github.current["labels"])
        self.assertNotIn("triage/needs-information", github.current["labels"])
        self.assertEqual(len([c for c in github.thread if c["user"]["login"] == triage.BOT]), 1)

    def test_model_disclosure_is_retained_beyond_the_latest_five_comments(self):
        comments = [{"id": 101, "body": "AI model: model-a-v2", "user": {"login": "reporter", "type": "User"}}]
        comments += [{"id": n, "body": "More investigation", "user": {"login": "reporter", "type": "User"}}
                     for n in range(102, 110)]
        current = issue(title="Enhancement: improve logging", body="A report")
        result = triage.analyze(FakeGitHub(current, comments=comments), 20, self.config)
        self.assertEqual(result["details"]["reported_models"][0]["label"], "ai-model/model-a-v2")

    def test_unrelated_user_or_bot_cannot_supply_reporter_model(self):
        comments = [{"id": 101, "body": "AI model: model-a-v2", "user": {"login": "other", "type": "User"}},
                    {"id": 102, "body": "AI model: bot-model", "user": {"login": triage.BOT, "type": "Bot"}}]
        result = triage.analyze(FakeGitHub(issue(body="A report"), comments=comments), 20, self.config)
        self.assertEqual(result["details"]["reported_models"], [])
        self.assertIn("triage/needs-information", result["labels"]["add"])

    def test_edited_earlier_declaration_uses_its_update_time(self):
        comments = [
            {"body": "AI model: corrected-model", "updated_at": "2026-10-26T10:00:00Z",
             "user": {"login": "reporter", "type": "User"}},
            {"body": "AI model: older-model", "updated_at": "2026-10-26T09:00:00Z",
             "user": {"login": "reporter", "type": "User"}},
        ]
        result = triage.analyze(FakeGitHub(comments=comments), 20, self.config)
        self.assertEqual(result["details"]["reported_models"][0]["label"], "ai-model/corrected-model")

    def test_author_can_correct_the_model_and_delete_the_disclosure(self):
        github = FakeGitHub(issue(title="Enhancement: improve logging", body="A report\nAI model: model-a"))
        triage.analyze(github, 20, self.config, apply=True)
        github.thread.append({"id": 101, "body": "AI model: model-b", "user": {"login": "reporter", "type": "User"}})
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("ai-model/model-b", github.current["labels"])
        self.assertNotIn("ai-model/model-a", github.current["labels"])
        github.thread = [c for c in github.thread if c["id"] != 101]
        github.current["body"] = "A report"
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("ai-model/model-b", github.current["labels"])
        self.assertIn("triage/needs-information", github.current["labels"])

    def test_human_model_correction_is_preserved(self):
        github = FakeGitHub()
        triage.analyze(github, 20, self.config, apply=True)
        github.current["labels"].remove("ai-model/test-model-v1")
        github.current["labels"].append("ai-model/manually-verified")
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("ai-model/manually-verified", github.current["labels"])
        self.assertNotIn("ai-model/test-model-v1", github.current["labels"])

    def test_robot_configuration_cannot_fill_reporter_model(self):
        settings = {"TRIAGE_AI_ENDPOINT": "https://example.test/chat", "TRIAGE_AI_MODEL": "robot-model",
                    "AI_API_KEY": "secret"}
        with patch("triage.ask_ai", return_value=([], {})):
            result = triage.analyze(FakeGitHub(issue(body="A report")), 20, self.config, ai_env=settings)
        self.assertEqual(result["details"]["reported_models"], [])
        self.assertIn("triage/needs-information", result["labels"]["add"])
        self.assertNotIn("ai-model/robot-model", result["labels"]["add"])
        self.assertIn("Configured triage model: robot-model", result["comment"])

    def test_model_cannot_fill_its_own_disclosure_via_ai_output(self):
        result = {"labels": [{"label": "ai-model/not-used", "confidence": 1, "evidence": "A report"}]}
        self.assertEqual(triage.validate_ai(result, issue(), "A report", [], self.config)[0], [])

    def test_model_metadata_does_not_become_database_version_or_subsystem(self):
        for text in ("AI model: vacuum-planner version 2", "### AI model: vacuum-planner version 2",
                     "### **AI model**\n\nvacuum-planner version 2", "### AI model: vacuum-planner version 2\n"):
            with self.subTest(text=text):
                details = triage.extract_details(issue(title="Bug"), text, [{"label": "type/bug"}], self.config)
                self.assertEqual(details["versions"], [])
                self.assertFalse(any(s["label"].startswith("area/") for s in triage.classify(issue(title="Bug"), text, self.config)))
                self.assertEqual(triage.tokens(text), [])

    def test_same_model_does_not_make_unrelated_reports_similar(self):
        current = issue(title="Vacuum freezing", body="relfrozenxid autovacuum freeze\n\n### AI model\n\nmodel-xyz-pro-v2")
        older = issue(3, title="Documentation spelling", body="spelling paragraph prose\n\n### AI model\n\nmodel-xyz-pro-v2")
        self.assertEqual(triage.rank_similar(current, current["body"], [older], self.config), [])

    def test_form_type_is_explicit_even_without_a_keyword_in_the_title(self):
        current = issue(title="Please make this clearer", body="### Issue type\n\nenhancement\n\n### AI model\n\n未使用 AI")
        result = triage.analyze(FakeGitHub(current), 20, self.config)
        self.assertIn("type/enhancement", result["labels"]["add"])
        self.assertIn("ai-model/not-used", result["labels"]["add"])

    def test_comment_keeps_sections_and_empty_fields(self):
        for current in (issue(), issue(title="Unexpected behavior", body="")):
            result = triage.analyze(FakeGitHub(current), 20, self.config)
            self.assertEqual(re.findall(r"^### .*$", result["comment"], re.M), [
                "### 1. Classification and labels", "### 2. Information completeness", "### 3. Similar issues", "### 4. Label changes", "### 5. Triage notes"])
            for field in ("Database version", "Platform", "Reporter's declared AI model", "Reproduction clues", "Key errors"):
                self.assertIn("| " + field + " |", result["comment"])
            self.assertEqual(result["comment"].count(triage.MARKER), 1)

    def test_comment_shows_manual_model_and_the_different_suggestion(self):
        result = triage.analyze(FakeGitHub(issue(labels=["ai-model/manually-verified"])), 20, self.config)
        self.assertIn("| Reported AI model | `ai-model/manually-verified` | `ai-model/test-model-v1` |", result["comment"])

    def test_model_label_underscores_display_literally(self):
        result = triage.analyze(FakeGitHub(issue(body="AI model: model_a_v2")), 20, self.config)
        self.assertIn("`ai-model/model_a_v2`", result["comment"])
        self.assertNotIn("`ai-model/model\\_a\\_v2`", result["comment"])

    def test_example_comment_matches_the_fixed_template(self):
        root = Path(triage.__file__).parent
        fixture = json.loads((root / "example.json").read_text())
        github = FakeGitHub(fixture["issue"], fixture["history"], fixture["comments"])
        github.repository = "fixture/repository"
        result = triage.analyze(github, fixture["issue"]["number"], self.config)
        self.assertEqual(result["comment"] + "\n", (root / "example-comment.md").read_text())

    def test_comments_and_generated_example_use_english(self):
        root = Path(triage.__file__).parent
        for path in root.glob("*.py"):
            with path.open("rb") as source:
                for token in tokenize.tokenize(source.readline):
                    if token.type == tokenize.COMMENT:
                        self.assertIsNone(re.search(r"[\u3400-\u9fff]", token.string), str(path))
        for relative in ("comment.md", "example-comment.md", "README.md"):
            self.assertIsNone(re.search(r"[\u3400-\u9fff]", (root / relative).read_text()), relative)


if __name__ == "__main__":
    unittest.main()
