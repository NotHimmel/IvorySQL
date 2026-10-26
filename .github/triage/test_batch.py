import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import triage
from test_triage import FakeGitHub, issue


def pull(number=30, title="Fix logical replication crash", body="Fix pgoutput decoding.\nAI model: model-a-v2", **overrides):
    return dict(issue(number, title, body), pull_request={"url": "https://api.github.com/repos/example/postgres/pulls/30"}, **overrides)


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def test_ranges_mix_single_ids_and_deduplicate(self):
        self.assertEqual(triage.parse_number_ranges("12,20-23,22,#31", 50), [12, 20, 21, 22, 23, 31])
        self.assertEqual(triage.parse_number_ranges("#1 - #3，5\n7", 50), [1, 2, 3, 5, 7])
        self.assertEqual(triage.parse_number_ranges("", 50), [])

    def test_bad_ranges_are_rejected_without_echoing_input(self):
        for text in ("0", "-1", "3-1", "1,,2", "1-", "1.5", "all", "secret-token", "1; echo bad", "1 2"):
            with self.subTest(text=text), self.assertRaises(ValueError) as caught:
                triage.parse_number_ranges(text, 50)
            if text in ("secret-token", "1; echo bad"):
                self.assertNotIn(text, str(caught.exception))

    def test_huge_ranges_fail_before_expansion(self):
        with self.assertRaisesRegex(ValueError, "50-item"):
            triage.parse_number_ranges("1-9999999999", 50)

    def test_explicit_legacy_pr_ranges_are_rejected(self):
        event = {"inputs": {"issue_numbers": "1-3", "pr_numbers": "3-4"}}
        with self.assertRaisesRegex(ValueError, "PR triage is not supported"):
            triage.select_targets(self.config, {}, event, dispatch=True)

    def test_unified_ranges_are_issue_only(self):
        event = {"inputs": {"numbers": "12,20-23,22"}}
        self.assertEqual(triage.select_targets(self.config, {}, event, dispatch=True), [
            {"number": n, "kind": "issue"} for n in (12, 20, 21, 22, 23)])
        self.assertEqual(triage.select_targets(self.config, {}, {}, numbers="12-13"), [
            {"number": 12, "kind": "issue"}, {"number": 13, "kind": "issue"}])

    def test_combined_limit_applies_after_deduplication(self):
        event = {"inputs": {"numbers": "1-25,20-50"}}
        self.assertEqual(len(triage.select_targets(self.config, {}, event, dispatch=True)), 50)
        event["inputs"]["numbers"] = "1-51"
        with self.assertRaisesRegex(ValueError, "50-item"):
            triage.select_targets(self.config, {}, event, dispatch=True)

    def test_legacy_single_cli_and_dispatch_inputs_still_work(self):
        self.assertEqual(triage.select_targets(self.config, {}, {}, number=12), [{"number": 12, "kind": "issue"}])
        self.assertEqual(triage.select_targets(self.config, {}, {"inputs": {"issue_number": "12"}}, dispatch=True),
                         [{"number": 12, "kind": "issue"}])
        with self.assertRaises(ValueError):
            triage.select_targets(self.config, {}, {}, number=0, issues="12")

    def test_automatic_events_do_not_read_manual_ranges(self):
        event = {"issue": {"number": 12}, "inputs": {"numbers": "40-45"}}
        self.assertEqual(triage.select_targets(self.config, {}, event), [{"number": 12, "kind": "issue"}])

    def test_matrix_target_takes_precedence_over_batch_inputs(self):
        env = {"TRIAGE_TARGET_NUMBER": "30", "TRIAGE_TARGET_KIND": "issue"}
        event = {"inputs": {"numbers": "1-30"}}
        self.assertEqual(triage.select_targets(self.config, env, event, dispatch=True), [{"number": 30, "kind": "issue"}])
        env["TRIAGE_TARGET_KIND"] = "pr"
        with self.assertRaisesRegex(ValueError, "Invalid matrix target"):
            triage.select_targets(self.config, env, event, dispatch=True)

    def test_plan_only_needs_no_credentials_and_never_prints_temporary_token(self):
        with tempfile.TemporaryDirectory() as directory:
            event_file = Path(directory) / "event.json"
            output_file = Path(directory) / "output"
            event_file.write_text(json.dumps({"inputs": {"mode": "preview", "numbers": "1-3,3-4",
                                  "ai_token": "must-not-print-this"}}))
            process = subprocess.run([sys.executable, "-B", triage.__file__, "--plan-only"],
                                     text=True, capture_output=True, env={"PATH": "/usr/bin:/bin",
                                     "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_EVENT_PATH": str(event_file),
                                     "GITHUB_OUTPUT": str(output_file)})
            self.assertEqual(process.returncode, 0, process.stderr)
            targets = json.loads(process.stdout)
            self.assertEqual(targets, [{"number": n, "kind": "issue"} for n in range(1, 5)])
            self.assertNotIn("must-not-print-this", process.stdout + process.stderr + output_file.read_text())
            self.assertEqual(json.loads(output_file.read_text().split("=", 1)[1]), targets)

    def test_sync_labels_has_a_single_matrix_task(self):
        process = subprocess.run([sys.executable, "-B", triage.__file__, "--plan-only", "--sync-labels"],
                                 text=True, capture_output=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), [{"number": 0, "kind": "labels"}])

    def test_pr_closed_and_skip_labels_are_read_only(self):
        for current, kind in [(pull(), "issue"), (pull(state="closed"), "issue"),
                              (dict(issue(), state="closed"), "issue"),
                              (issue(labels=["triage/skip"]), "issue")]:
            github = FakeGitHub(current)
            self.assertIn("skipped", triage.analyze(github, current["number"], self.config, apply=True, target_kind=kind))
            self.assertEqual(github.writes, [])

    def test_nonexistent_number_is_skipped_but_permission_errors_fail(self):
        with patch.object(FakeGitHub, "issue", side_effect=triage.APIError(404)):
            result = triage.analyze(FakeGitHub(), 404, self.config, target_kind="any")
        self.assertIn("skipped", result)
        with patch.object(FakeGitHub, "issue", side_effect=triage.APIError(403)), self.assertRaises(triage.APIError):
            triage.analyze(FakeGitHub(), 403, self.config)

    def test_pr_is_skipped_before_comments_history_ai_or_writes(self):
        for apply in (False, True):
            for target_kind in ("issue", "any"):
                github = FakeGitHub(pull())
                with patch.object(github, "comments") as comments, patch.object(github, "history") as history, \
                        patch("triage.ask_ai") as ai:
                    result = triage.analyze(github, 30, self.config, apply=apply, target_kind=target_kind)
                self.assertIn("PR skipped", result["skipped"])
                comments.assert_not_called()
                history.assert_not_called()
                ai.assert_not_called()
                self.assertEqual(github.writes, [])
                self.assertEqual(github.created, set())

    def test_mixed_number_range_processes_issues_and_skips_prs(self):
        github = FakeGitHub()
        with patch.object(github, "issue", side_effect=[issue(1), pull(2)]):
            report = triage.run_targets(github, [{"number": n, "kind": "issue"} for n in (1, 2)], self.config)
        self.assertEqual(report["counts"], {"processed": 1, "skipped": 1, "failed": 0})
        self.assertEqual(report["results"][1]["kind"], "pr")

    def test_prs_are_excluded_from_similar_issue_results(self):
        current = issue()
        older_pr = pull(10, title=current["title"], body=current["body"])
        older_issue = issue(11, title=current["title"], body=current["body"])
        result = triage.analyze(FakeGitHub(current, [older_pr, older_issue]), current["number"], self.config)
        self.assertNotIn("#10", result["comment"])
        self.assertIn("/issues/11)", result["comment"])

    def test_failure_does_not_interrupt_remaining_batch_items(self):
        targets = [{"number": n, "kind": "issue"} for n in range(1, 5)]
        outcomes = [{"issue": 1, "kind": "issue", "comment": "first"}, RuntimeError("API temporarily unavailable"),
                    {"issue": 3, "kind": "issue", "skipped": "closed"}, {"issue": 4, "kind": "issue", "comment": "last"}]
        with patch("triage.analyze", side_effect=outcomes) as analyze:
            report = triage.run_targets(FakeGitHub(), targets, self.config)
        self.assertEqual(analyze.call_count, 4)
        self.assertEqual(report["counts"], {"processed": 2, "skipped": 1, "failed": 1})
        summary = triage.render_summary("example/postgres", report)
        self.assertIn("API temporarily unavailable", summary)
        self.assertIn("#4", summary)

    def test_main_returns_failure_after_writing_summary_for_partial_batch(self):
        outcomes = [{"issue": 1, "kind": "issue", "comment": "first"}, triage.APIError(403)]
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary"
            env = {"GH_TOKEN": "github-secret", "GITHUB_STEP_SUMMARY": str(summary)}
            output = io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["triage", "--repository", "example/postgres", "--numbers", "1-2"]), \
                    patch("triage.analyze", side_effect=outcomes), contextlib.redirect_stdout(output):
                status = triage.main()
            self.assertEqual(status, 1)
            self.assertIn("failed: 1", summary.read_text())
            self.assertNotIn("github-secret", output.getvalue() + summary.read_text())
            self.assertEqual(json.loads(output.getvalue())["counts"]["processed"], 1)

    def test_history_cache_does_not_accumulate_search_results(self):
        github = triage.GitHub("example/postgres", "token")
        with patch.object(github, "pages", return_value=[issue(1), pull(2)]) as pages:
            first, _ = github.history(1000)
            first.append(issue(3))
            second, _ = github.history(1000)
        self.assertEqual(pages.call_count, 1)
        self.assertEqual([item["number"] for item in second], [1, 2])

    def test_workflow_matrix_keeps_per_number_serialization_and_trusted_checkout(self):
        workflow = (Path(triage.__file__).parent.parent / "workflows" / "issue-triage.yml").read_text()
        self.assertIn("fail-fast: false", workflow)
        self.assertIn("matrix.target.number", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertEqual(workflow.count("ref: ${{ github.event.repository.default_branch }}"), 2)
        self.assertNotIn("github.event.pull_request.head", workflow)
        self.assertIn("\n      numbers:", workflow)
        for name in ("issue_number", "issue_numbers", "pr_numbers"):
            self.assertNotIn("\n      " + name + ":", workflow)


if __name__ == "__main__":
    unittest.main()
