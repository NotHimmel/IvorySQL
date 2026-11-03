import re
import unittest
from unittest.mock import patch

import triage
from test_submissions import COMPLETE_BUG, comment
from test_triage import FakeGitHub, issue


BASE_REPORT = COMPLETE_BUG.replace("Reproduced in a real environment: Yes\n", "")


class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def run_triage(self, github, apply=False):
        return triage.analyze(github, 20, self.config, apply=apply)

    def test_every_comment_starts_with_the_exact_welcome_once(self):
        github = FakeGitHub(issue(body=BASE_REPORT))
        for _ in range(2):
            result = self.run_triage(github, apply=True)
            visible = re.sub(r"<!--.*?-->", "", result["comment"], flags=re.S).strip()
            self.assertTrue(visible.startswith("Thanks for contributing to IvorySQL!"))
            self.assertEqual(visible.count("Thanks for contributing to IvorySQL!"), 1)
        self.assertEqual(len(github.thread), 1)

    def test_prose_instructions_need_real_reproduction_confirmation(self):
        result = self.run_triage(FakeGitHub(issue(body=BASE_REPORT)))
        self.assertEqual(result["details"]["missing"], ["Real reproduction"])
        self.assertIn("Have you reproduced this in a real environment with the reported version?", result["comment"])
        self.assertNotIn("AI-generated", result["comment"])

    def test_unfenced_perl_example_is_not_mistaken_for_a_verified_run(self):
        body = BASE_REPORT.replace("Reproduction steps: Create a subscription and refresh it while decoding changes.",
            'Reproduction steps: Load the real module and call its APIs.\n\nuse PostgreSQL::Version;\n'
            'my $v = PostgreSQL::Version->new("psql (PostgreSQL) 18.3");\nprint $v->major, "\\n";')
        result = self.run_triage(FakeGitHub(issue(body=body)))
        self.assertTrue(result["details"]["has_reproduction_clues"])
        self.assertFalse(result["details"]["has_reproduction_code"])
        self.assertIn("Real reproduction", result["details"]["missing"])

    def test_fenced_code_is_a_clue_and_does_not_claim_verified_reproduction(self):
        body = BASE_REPORT.replace("Reproduction steps: Create a subscription and refresh it while decoding changes.",
                                   "### Reproduction steps\n\n```perl\nuse PostgreSQL::Version;\nprint 1;\n```\n")
        result = self.run_triage(FakeGitHub(issue(body=body)))
        self.assertTrue(result["details"]["has_reproduction_code"])
        self.assertEqual(result["details"]["reproduction_status"], "unknown")
        self.assertNotIn("Real reproduction", result["details"]["missing"])

    def test_explicit_author_confirmation_accepts_prose_instructions(self):
        result = self.run_triage(FakeGitHub(issue(body=COMPLETE_BUG)))
        self.assertEqual(result["details"]["reproduction_status"], "author-confirmed")
        self.assertEqual(result["details"]["missing"], [])

    def test_no_or_not_verified_routes_to_review_without_repeating_the_question(self):
        for answer in ("No", "Not verified yet"):
            with self.subTest(answer=answer):
                body = COMPLETE_BUG.replace("Reproduced in a real environment: Yes", "Reproduced in a real environment: " + answer)
                result = self.run_triage(FakeGitHub(issue(body=body)))
                self.assertEqual(result["details"]["missing"], [])
                self.assertEqual(result["details"]["review_status"], "needs-reproduce")
                self.assertIn("reproduction has not been verified", result["comment"])
                self.assertNotIn("Have you reproduced", result["comment"])

    def test_author_can_reply_yes_and_the_answer_remains_valid_on_later_runs(self):
        github = FakeGitHub(issue(body=BASE_REPORT))
        self.run_triage(github, apply=True)
        github.thread.append(comment("Yes"))
        for _ in range(2):
            result = self.run_triage(github, apply=True)
            self.assertEqual(result["details"]["reproduction_status"], "author-confirmed")
            self.assertNotIn("triage/needs-information", github.current["labels"])

    def test_author_can_reply_no_then_edit_the_answer_to_yes(self):
        github = FakeGitHub(issue(body=BASE_REPORT))
        self.run_triage(github, apply=True)
        answer = comment("No")
        github.thread.append(answer)
        self.assertEqual(self.run_triage(github, apply=True)["details"]["review_status"], "needs-reproduce")
        answer["body"] = "Yes"
        answer["updated_at"] = "2026-11-02T12:00:00Z"
        self.assertEqual(self.run_triage(github, apply=True)["details"]["review_status"], "complete")

    def test_unrelated_old_yes_and_other_users_do_not_confirm_reproduction(self):
        for login in ("reporter", "other"):
            with self.subTest(login=login):
                github = FakeGitHub(issue(body=BASE_REPORT), comments=[comment("Yes", login=login)])
                self.run_triage(github, apply=True)
                result = self.run_triage(github, apply=True)
                self.assertIn("Real reproduction", result["details"]["missing"])

    def test_a_different_users_reply_after_the_question_does_not_count(self):
        github = FakeGitHub(issue(body=BASE_REPORT))
        self.run_triage(github, apply=True)
        github.thread.append(comment("Yes", login="other"))
        result = self.run_triage(github, apply=True)
        self.assertIn("Real reproduction", result["details"]["missing"])

    def test_changed_reported_version_invalidates_the_old_confirmation(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github, apply=True)
        github.current["body"] = COMPLETE_BUG.replace("Database version: master", "Database version: IvorySQL 5.0")
        github.current["body_updated_at"] = "2026-11-02T12:00:00Z"
        result = self.run_triage(github, apply=True)
        self.assertEqual(result["details"]["reproduction_status"], "outdated")
        self.assertIn("Real reproduction", result["details"]["missing"])
        github.thread.append(comment("Yes", updated_at="2026-11-03T12:00:00Z"))
        self.assertEqual(self.run_triage(github, apply=True)["details"]["review_status"], "complete")

    def test_features_do_not_require_bug_reproduction_confirmation(self):
        body = "Description: Add a useful capability.\nAI model: not used\nReproduced in a real environment: No"
        result = self.run_triage(FakeGitHub(issue(title="Feature request: add a command", body=body)))
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(result["details"]["review_status"], "complete")

    def test_ai_classification_cannot_supply_author_confirmation(self):
        with patch("triage.ask_ai", return_value=([{"label": "type/bug", "source": "ai", "evidence": "crashes"}], {})):
            result = triage.analyze(FakeGitHub(issue(body=BASE_REPORT)), 20, self.config,
                                    ai_env={"TRIAGE_AI_MODEL": "model", "AI_API_KEY": "key"})
        self.assertIn("Real reproduction", result["details"]["missing"])


if __name__ == "__main__":
    unittest.main()
