import unittest
from unittest.mock import patch

import triage
from test_triage import FakeGitHub, issue


class FailingGitHub(FakeGitHub):
    """Simulate request failure before or after the server commits a mutation."""

    fail_when = None
    fail_after = False

    def call(self, path, method="GET", data=None):
        if self.fail_when and self.fail_when(path, method, data):
            self.fail_when = None
            if self.fail_after:
                super().call(path, method, data)
            raise triage.APIError(503)
        return super().call(path, method, data)


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def run_triage(self, github, apply=True):
        return triage.analyze(github, 20, self.config, apply=apply)

    def assert_recovered(self, github):
        self.run_triage(github)
        self.assertEqual(len(github.thread), 1)
        saved = triage.read_state(triage.bot_comment(github.thread))
        self.assertNotIn("pending", saved)
        self.assertNotIn("Writeback pending", github.thread[0]["body"])
        self.assertIn("type/bug", saved["managed"])
        self.assertIn("ai-model/test-model-v1", saved["managed"])
        self.assertEqual(saved["suppressed"], [])
        return saved

    def test_journal_failure_prevents_issue_label_mutation(self):
        github = FailingGitHub()
        github.fail_when = lambda path, method, data: path.endswith("/comments")
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertEqual(github.current["labels"], [])
        self.assertEqual(github.writes, [])
        self.assert_recovered(github)

    def test_lost_journal_create_response_reuses_the_existing_comment(self):
        github = FailingGitHub()
        github.fail_when = lambda path, method, data: path.endswith("/comments")
        github.fail_after = True
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertEqual(github.current["labels"], [])
        self.assertIn("pending", triage.read_state(github.thread[0]))
        self.assert_recovered(github)

    def test_add_label_failure_recovers_before_and_after_server_commit(self):
        for after in (False, True):
            with self.subTest(after=after):
                github = FailingGitHub()
                github.fail_when = lambda path, method, data: path.endswith("/labels") and method == "POST"
                github.fail_after = after
                with self.assertRaises(triage.APIError):
                    self.run_triage(github)
                self.assertIn("pending", triage.read_state(github.thread[0]))
                self.assert_recovered(github)
                github.current["title"] = "Enhancement: improve psql completion"
                self.run_triage(github)
                self.assertNotIn("type/bug", github.current["labels"])
                self.assertIn("type/enhancement", github.current["labels"])

    def test_partial_label_addition_does_not_suppress_unfinished_additions(self):
        github = FailingGitHub()
        github.fail_when = lambda path, method, data: path.endswith("/labels") and method == "POST"
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        github.current["labels"] = ["type/bug"]
        self.assert_recovered(github)

    def test_label_creation_failure_leaves_a_recoverable_journal(self):
        github = FailingGitHub()
        with patch.object(github, "ensure_labels", side_effect=triage.APIError(503)), self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertIn("pending", triage.read_state(github.thread[0]))
        self.assertEqual(github.current["labels"], [])
        self.assert_recovered(github)

    def test_final_comment_failure_preserves_label_ownership(self):
        for after in (False, True):
            with self.subTest(after=after):
                github = FailingGitHub()
                github.fail_when = lambda path, method, data: method == "PATCH" and "Writeback pending" not in data["body"]
                github.fail_after = after
                with self.assertRaises(triage.APIError):
                    self.run_triage(github)
                self.assertIn("type/bug", github.current["labels"])
                self.assert_recovered(github)

    def test_partial_deletion_recovers_without_freezing_the_old_group(self):
        for after in (False, True):
            with self.subTest(after=after):
                github = FailingGitHub()
                self.run_triage(github)
                github.current["title"] = "Enhancement: improve psql completion"
                github.current["body"] = "IvorySQL master\nAI model: test-model-v1"
                github.fail_when = lambda path, method, data: method == "DELETE"
                github.fail_after = after
                with self.assertRaises(triage.APIError):
                    self.run_triage(github)
                self.run_triage(github)
                self.assertIn("type/enhancement", github.current["labels"])
                self.assertNotIn("type/bug", github.current["labels"])
                self.assertNotIn("area/logical-replication", github.current["labels"])
                self.assertEqual(triage.read_state(github.thread[0])["suppressed"], [])

    def test_source_changes_after_interruption_are_reanalyzed(self):
        github = FailingGitHub()
        self.run_triage(github)
        github.current["title"] = "Enhancement: improve psql completion"
        github.current["body"] = "IvorySQL master\nAI model: test-model-v1"
        github.fail_when = lambda path, method, data: method == "DELETE" and path.endswith("type%2Fbug")
        github.fail_after = True
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        github.current["title"] = "Bug: logical replication crashes"
        self.assert_recovered(github)
        self.assertNotIn("type/enhancement", github.current["labels"])

    def test_recovery_preserves_unrelated_human_labels_and_corrections(self):
        github = FailingGitHub()
        github.fail_when = lambda path, method, data: method == "PATCH" and "Writeback pending" not in data["body"]
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        github.current["labels"].remove("type/bug")
        github.current["labels"].extend(["type/feature", "custom"])
        self.run_triage(github)
        self.assertIn("type/feature", github.current["labels"])
        self.assertIn("custom", github.current["labels"])
        self.assertNotIn("type/bug", github.current["labels"])
        self.assertNotIn("type/feature", triage.read_state(github.thread[0])["managed"])

    def test_recovery_preview_does_not_finalize_or_change_labels(self):
        github = FailingGitHub()
        github.fail_when = lambda path, method, data: path.endswith("/labels") and method == "POST"
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        before = list(github.writes)
        self.run_triage(github, apply=False)
        self.assertEqual(github.writes, before)
        self.assertIn("pending", triage.read_state(github.thread[0]))

    def test_existing_comment_journal_update_failure_prevents_label_mutation(self):
        github = FailingGitHub()
        self.run_triage(github)
        labels = list(github.current["labels"])
        github.current["title"] = "Enhancement: improve psql completion"
        github.fail_when = lambda path, method, data: method == "PATCH" and "Writeback pending" in data["body"]
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertEqual(github.current["labels"], labels)
        self.run_triage(github)
        self.assertIn("type/enhancement", github.current["labels"])
        self.assertNotIn("type/bug", github.current["labels"])

    def test_malformed_or_spoofed_pending_records_do_not_claim_ownership(self):
        invalid = {"managed": ["type/bug"], "suppressed": [], "pending": {"add": "type/bug", "remove": []}}
        self.assertEqual(triage.read_state({"body": triage.state_marker(invalid)}),
                         {"managed": [], "suppressed": []})
        spoofed = {"id": 99, "user": {"login": "reporter", "type": "User"},
                   "body": triage.MARKER + "\n" + triage.state_marker({
                       "managed": [], "suppressed": [], "pending": {"add": ["type/feature"], "remove": []}})}
        github = FakeGitHub(issue(labels=["type/feature"]), comments=[spoofed])
        self.run_triage(github)
        self.assertIn("type/feature", github.current["labels"])
        self.assertNotIn("type/feature", triage.read_state(triage.bot_comment(github.thread))["managed"])


if __name__ == "__main__":
    unittest.main()
