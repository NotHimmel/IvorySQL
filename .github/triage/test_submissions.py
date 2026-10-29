import unittest

import triage
from test_triage import FakeGitHub, issue


COMPLETE_BUG = """Description: Refreshing a subscription crashes the server.
Database version: master
Reproduction steps: Create a subscription and refresh it while decoding changes.
Expected behavior: The subscription refreshes without crashing.
Compatible mode: pg
Server encoding: UTF8
AI model: not used
"""


def comment(body, login="reporter", number=101, updated_at="2026-10-29T12:00:00Z"):
    return {"id": number, "body": body, "updated_at": updated_at,
            "user": {"login": login, "type": "User"}}


class SubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def analyze(self, current, comments=None, apply=False):
        return triage.analyze(FakeGitHub(current, comments=comments), 20, self.config, apply=apply)

    def test_free_form_incomplete_bug_gets_actionable_missing_fields_and_copyable_reply(self):
        result = self.analyze(issue(body="It crashes."))
        for field in ("Database version", "Reproduction steps or minimal SQL", "Expected behavior", "Compatible mode", "Server encoding"):
            self.assertIn(field, result["details"]["missing"])
        self.assertIn("triage/needs-information", result["labels"]["add"])
        body = result["comment"]
        self.assertIn("Action required from the issue author", body)
        self.assertIn("SELECT version()", body)
        self.assertIn("SHOW ivorysql.compatible_mode", body)
        self.assertIn("Database version: TODO", body)
        self.assertIn("AI model: TODO", body)
        self.assertIn("https://github.com/example/postgres/issues/new/choose", body)
        self.assertNotIn("Submission check passed", body)

    def test_complete_free_form_bug_does_not_require_exact_markdown_headings(self):
        result = self.analyze(issue(body=COMPLETE_BUG))
        self.assertEqual(result["details"]["missing"], [])
        self.assertNotIn("triage/needs-information", result["labels"]["add"])
        self.assertIn("Submission check passed", result["comment"])
        self.assertNotIn("Action required from the issue author", result["comment"])

    def test_bug_form_headings_accept_expected_output_in_code(self):
        body = """### What happened?

The query crashes.

### What did you expect to happen?

```text
one row
```

### How can we reproduce it (as minimally and precisely as possible)?

```sql
SELECT 1;
```

### IvorySQL version

master

### Compatible mode

oracle

### Server encoding

UTF8

### AI model

not used
"""
        self.assertEqual(self.analyze(issue(body=body))["details"]["missing"], [])

    def test_author_can_complete_a_report_in_one_comment_without_duplicate_bot_comments(self):
        github = FakeGitHub(issue(body="### Description\n\n_No response_\n\n### OS version\n\n_No response_"))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("triage/needs-information", github.current["labels"])
        github.thread.append(comment(COMPLETE_BUG))
        result = triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertNotIn("triage/needs-information", github.current["labels"])
        bots = [c for c in github.thread if c["user"]["login"] == triage.BOT]
        self.assertEqual(len(bots), 1)
        self.assertIn("Submission check passed", bots[0]["body"])
        self.assertNotIn("Action required from the issue author", bots[0]["body"])

    def test_partial_supplements_shrink_the_checklist_and_repeated_runs_do_not_spam(self):
        github = FakeGitHub(issue(body="The server crashes."))
        triage.analyze(github, 20, self.config, apply=True)
        github.thread.append(comment("Database version: master\nAI model: not used"))
        result = triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("Database version: TODO", result["comment"])
        self.assertNotIn("AI model: TODO", result["comment"])
        self.assertIn("Expected behavior: TODO", result["comment"])
        triage.analyze(github, 20, self.config, apply=True)
        before = len(github.writes)
        triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(len(github.writes), before)
        self.assertEqual(len([c for c in github.thread if c["user"]["login"] == triage.BOT]), 1)

    def test_other_users_and_bots_cannot_complete_the_report(self):
        for login, user_type in (("maintainer", "User"), (triage.BOT, "Bot")):
            with self.subTest(login=login):
                supplement = comment(COMPLETE_BUG, login=login)
                supplement["user"]["type"] = user_type
                result = self.analyze(issue(body="It crashes."), [supplement])
                self.assertIn("Database version", result["details"]["missing"])
                self.assertIn("Expected behavior", result["details"]["missing"])

    def test_supplements_survive_more_than_five_subsequent_comments(self):
        comments = [comment("Issue type: bug\n" + COMPLETE_BUG)]
        comments.extend(comment("More investigation.", number=n, updated_at="2026-10-29T13:00:00Z")
                        for n in range(102, 110))
        result = self.analyze(issue(title="Unexpected behavior", body="It fails."), comments)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("type/bug", result["labels"]["add"])

    def test_latest_explicit_correction_can_request_information_again(self):
        result = self.analyze(issue(body=COMPLETE_BUG), [comment("Expected behavior: TODO")])
        self.assertEqual(result["details"]["missing"], ["Expected behavior"])
        self.assertIn("triage/needs-information", result["labels"]["add"])

    def test_deleting_a_supplement_restores_the_information_request(self):
        github = FakeGitHub(issue(body="It crashes."), comments=[comment(COMPLETE_BUG)])
        triage.analyze(github, 20, self.config, apply=True)
        github.thread = [c for c in github.thread if c["user"]["login"] == triage.BOT]
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("triage/needs-information", github.current["labels"])

    def test_copying_unfilled_todo_reply_does_not_pass_validation(self):
        fields = [definition[0] + ": TODO" for definition in triage.SUBMISSION_FIELDS.values()]
        result = self.analyze(issue(body="The server crashes."), [comment("\n".join(fields))])
        self.assertIn("Database version", result["details"]["missing"])
        self.assertIn("Expected behavior", result["details"]["missing"])
        self.assertIn("Compatible mode", result["details"]["missing"])
        self.assertIn("Server encoding", result["details"]["missing"])
        self.assertTrue(any(name.startswith("AI model") for name in result["details"]["missing"]))

    def test_empty_feature_and_enhancement_templates_need_a_description(self):
        for heading, label in (("Feature Request", "type/feature"), ("Enhancement", "type/enhancement")):
            with self.subTest(heading=heading):
                body = f"## {heading}\n\n## AI model\n\n<!-- Fill in the model. -->"
                result = self.analyze(issue(title="Please investigate", body=body, labels=[label]))
                self.assertIn("Issue description", result["details"]["missing"])

    def test_filled_legacy_feature_template_keeps_text_after_the_prompt(self):
        body = "## Feature Request\n\n**Describe the feature you'd like to propose:**\n\nAdd a psql command to show the compatibility mode.\n\n## AI model\n\nnot used"
        result = self.analyze(issue(title="Please add this", body=body, labels=["type/feature"]))
        self.assertEqual(result["details"]["missing"], [])

    def test_empty_expected_heading_cannot_be_filled_by_later_inline_fields(self):
        body = COMPLETE_BUG.replace("Expected behavior: The subscription refreshes without crashing.", "### Expected behavior\n\nTODO\n")
        self.assertIn("Expected behavior", self.analyze(issue(body=body))["details"]["missing"])

    def test_quoted_and_hidden_field_names_do_not_satisfy_expected_behavior(self):
        body = COMPLETE_BUG.replace("Expected behavior: The subscription refreshes without crashing.", "")
        for supplement in ("> Expected behavior: It should succeed.", "<!-- Expected behavior: It should succeed. -->",
                           "```text\nExpected behavior: It should succeed.\n```"):
            with self.subTest(supplement=supplement):
                result = self.analyze(issue(body=body), [comment(supplement)])
                self.assertIn("Expected behavior", result["details"]["missing"])

    def test_complete_feature_and_enhancement_do_not_need_bug_fields(self):
        for title in ("Feature request: add a psql command", "Enhancement: improve psql completion"):
            with self.subTest(title=title):
                result = self.analyze(issue(title=title, body="Description: Show the current compatibility mode in the prompt.\nAI model: not used"))
                self.assertEqual(result["details"]["missing"], [])

    def test_unknown_type_prompts_for_the_issue_type(self):
        result = self.analyze(issue(title="Please investigate", body="Something is unexpected.\nAI model: not used"))
        self.assertIn("Issue type", result["details"]["missing"])
        self.assertIn("Issue type: TODO", result["comment"])

    def test_build_only_bug_does_not_require_running_server_settings(self):
        body = "Description: The linker fails.\nDatabase version: master\nReproduction steps: Run meson setup and compile.\nExpected behavior: The build succeeds.\nAI model: not used"
        result = self.analyze(issue(title="Bug: meson build fails", body=body))
        self.assertEqual(result["details"]["missing"], [])

    def test_explained_not_applicable_runtime_fields_are_accepted(self):
        body = COMPLETE_BUG.replace("Compatible mode: pg", "Compatible mode: not applicable: this is upstream PostgreSQL")
        body = body.replace("Server encoding: UTF8", "Server encoding: not applicable: the server fails before startup")
        self.assertEqual(self.analyze(issue(body=body))["details"]["missing"], [])

    def test_runtime_placeholders_and_bare_other_do_not_pass(self):
        for mode, encoding in (("_No response_", "Other"), ("n/a", "unknown"), ("TODO", "TODO")):
            with self.subTest(mode=mode, encoding=encoding):
                body = COMPLETE_BUG.replace("Compatible mode: pg", "Compatible mode: " + mode)
                body = body.replace("Server encoding: UTF8", "Server encoding: " + encoding)
                result = self.analyze(issue(body=body))
                self.assertIn("Compatible mode", result["details"]["missing"])
                self.assertIn("Server encoding", result["details"]["missing"])

    def test_template_guidance_does_not_accept_close_or_resolve_the_issue(self):
        github = FakeGitHub(issue(body="It crashes."))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(github.current["state"], "open")
        self.assertNotIn("triage/accepted", github.current["labels"])
        self.assertFalse(any(name.startswith("resolution/") for name in github.current["labels"]))


if __name__ == "__main__":
    unittest.main()
