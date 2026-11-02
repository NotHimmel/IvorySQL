import copy
import unittest
from unittest.mock import patch

import triage
from test_submissions import COMPLETE_BUG, comment
from test_triage import FakeGitHub, issue


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def run_triage(self, github, apply=True, automatic=False, config=None):
        return triage.analyze(github, 20, config or self.config, apply=apply, automatic=automatic)

    def state(self, github):
        return triage.read_state(triage.bot_comment(github.thread))

    def test_plain_author_response_routes_to_review_without_claiming_completion(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("The crash only occurs after restarting the replica."))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "needs-review")
        self.assertTrue(result["details"]["missing"])
        self.assertIn("triage/needs-review", github.current["labels"])
        self.assertNotIn("triage/needs-information", github.current["labels"])
        self.assertNotIn("Yes. Please provide:", result["comment"])
        self.assertNotIn("No missing required information detected.", result["comment"])
        self.assertNotIn("triage/accepted", github.current["labels"])
        for _ in range(2):
            self.run_triage(github)
        self.assertEqual(self.state(github)["review_status"], "needs-review")

    def test_structured_partial_response_keeps_only_remaining_information_requests(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("Database version: master\nAI model: not used"))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "needs-information")
        self.assertNotIn("Database version", result["details"]["missing"])
        self.assertIn("Expected behavior", result["details"]["missing"])
        self.assertIn("triage/needs-information", github.current["labels"])

    def test_reviewer_confirmation_clears_bot_review_label(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("The failure occurs only during recovery."))
        self.run_triage(github)
        github.current["labels"].append("triage/accepted")
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "maintainer-reviewed")
        self.assertNotIn("triage/needs-review", github.current["labels"])
        self.assertNotIn("triage/needs-information", github.current["labels"])

    def test_complete_supplement_clears_a_previous_review_request(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("I have more observations."))
        self.run_triage(github)
        github.thread.append(comment(COMPLETE_BUG, number=102, updated_at="2026-10-30T12:00:00Z"))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "complete")
        self.assertNotIn("triage/needs-review", github.current["labels"])

    def test_other_user_response_does_not_end_waiting_for_the_author(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("I see this too.", login="other"))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "needs-information")

    def test_automatic_plain_response_defers_expensive_analysis_and_preserves_classification(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        original = {n for n in github.current["labels"] if n.startswith(("type/", "area/"))}
        github.thread.append(comment("I am still investigating the reproduction conditions."))
        with patch.object(github, "history") as history, patch.object(github, "search") as search, patch("triage.ask_ai") as ai:
            result = self.run_triage(github, automatic=True)
        history.assert_not_called()
        search.assert_not_called()
        ai.assert_not_called()
        self.assertEqual({n for n in github.current["labels"] if n.startswith(("type/", "area/"))}, original)
        self.assertEqual(result["details"]["review_status"], "needs-review")
        self.assertIn("Not refreshed; awaiting maintainer review.", result["comment"])

    def test_manual_review_label_is_authoritative(self):
        github = FakeGitHub(issue(body="The server crashes.", labels=["triage/needs-review"]))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["review_status"], "needs-review")
        self.assertNotIn("triage/needs-information", github.current["labels"])

    def test_manual_information_request_is_retained_after_a_plain_response(self):
        github = FakeGitHub(issue(body="The server crashes.", labels=["triage/needs-information"]))
        self.run_triage(github)
        github.thread.append(comment("I can reproduce it on a second machine."))
        self.run_triage(github)
        self.assertIn("triage/needs-information", github.current["labels"])

    def test_new_placeholder_version_does_not_reuse_the_old_valid_version(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=[comment("Database version: TODO")])
        result = self.run_triage(github)
        self.assertEqual(result["details"]["versions"], [])
        self.assertIn("Database version", result["details"]["missing"])

    def test_conflicting_model_answers_do_not_relabel_the_report(self):
        current = issue(body=COMPLETE_BUG)
        current["body_updated_at"] = None
        github = FakeGitHub(current, comments=[comment("AI model: different-model")])
        result = self.run_triage(github)
        self.assertIn("AI model", result["details"]["conflicts"])
        self.assertIn("triage/needs-review", github.current["labels"])
        self.assertFalse(any(label.startswith("ai-model/") for label in github.current["labels"]))

    def test_new_body_answer_overrides_an_older_comment(self):
        current = issue(body=COMPLETE_BUG)
        current["body_updated_at"] = "2026-11-02T12:00:00Z"
        github = FakeGitHub(current, comments=[comment("Compatible mode: unknown")])
        result = self.run_triage(github)
        self.assertEqual(result["details"]["compatible_mode"], "pg")
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(result["details"]["field_sources"]["Compatible mode"]["source"], "body")

    def test_new_comment_can_correct_a_body_answer(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=[comment("Compatible mode: oracle")])
        result = self.run_triage(github)
        self.assertEqual(result["details"]["compatible_mode"], "oracle")
        self.assertEqual(result["details"]["field_sources"]["Compatible mode"]["source"], "comment:101")

    def test_unrelated_body_edit_does_not_reassert_unchanged_old_fields(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=[comment("Compatible mode: oracle")])
        self.run_triage(github)
        github.current["body"] = COMPLETE_BUG.replace("crashes the server", "crashes the replica")
        github.current["body_updated_at"] = "2026-11-02T12:00:00Z"
        result = self.run_triage(github)
        self.assertEqual(result["details"]["compatible_mode"], "oracle")
        self.assertEqual(result["details"]["field_sources"]["Compatible mode"]["source"], "comment:101")

    def test_an_actual_body_field_change_overrides_the_previous_comment(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=[comment("Compatible mode: oracle")])
        self.run_triage(github)
        github.current["body"] = COMPLETE_BUG.replace("Compatible mode: pg", "Compatible mode: both")
        github.current["body_updated_at"] = "2026-11-02T12:00:00Z"
        result = self.run_triage(github)
        self.assertEqual(result["details"]["compatible_mode"], "both")

    def test_unrelated_comment_edit_does_not_reassert_old_model_answer(self):
        first = comment("AI model: model-old\nExpected behavior: It should work.")
        second = comment("AI model: model-current", number=102, updated_at="2026-10-30T12:00:00Z")
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=[first, second])
        self.run_triage(github)
        first["body"] = "AI model: model-old\nExpected behavior: The subscription should refresh."
        first["updated_at"] = "2026-11-02T12:00:00Z"
        result = self.run_triage(github)
        self.assertEqual(result["details"]["reported_models"][0]["name"], "model-current")

    def test_edited_untracked_old_comment_does_not_gain_authority_on_a_rerun(self):
        old = comment("Compatible mode: pg\nDescription: The subscription fails.", updated_at="2026-10-27T12:00:00Z")
        comments = [old, comment("Compatible mode: oracle", number=102, updated_at="2026-10-28T12:00:00Z"),
                    comment("Compatible mode: both", number=103, updated_at="2026-10-29T12:00:00Z")]
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=comments)
        self.run_triage(github)
        old["body"] = "Compatible mode: pg\nDescription: The subscription fails only during recovery."
        old["updated_at"] = "2026-11-02T12:00:00Z"
        for _ in range(2):
            result = self.run_triage(github)
            self.assertIn("Compatible mode", result["details"]["conflicts"])
            self.assertEqual(result["details"]["review_status"], "needs-review")

    def test_missing_or_tied_edit_times_route_conflicting_answers_to_review(self):
        for edited_at in (None, "2026-10-29T12:00:00Z"):
            with self.subTest(edited_at=edited_at):
                current = issue(body=COMPLETE_BUG)
                current["body_updated_at"] = edited_at
                github = FakeGitHub(current, comments=[comment("Compatible mode: oracle")])
                result = self.run_triage(github)
                self.assertIn("Compatible mode", result["details"]["conflicts"])
                self.assertEqual(result["details"]["review_status"], "needs-review")
                self.assertNotIn("No missing required information detected.", result["comment"])

    def test_filled_field_only_code_block_is_accepted_as_an_author_reply(self):
        github = FakeGitHub(issue(body="The server crashes."))
        self.run_triage(github)
        github.thread.append(comment("```text\n" + COMPLETE_BUG + "```"))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(result["details"]["review_status"], "complete")

    def test_single_requested_field_is_accepted_inside_a_text_code_block(self):
        github = FakeGitHub(issue(title="Enhancement: improve psql completion", body="Description: Improve completion for existing commands."))
        self.run_triage(github)
        github.thread.append(comment("```text\nAI model: not used\n```"))
        result = self.run_triage(github)
        self.assertEqual(result["details"]["missing"], [])

    def test_arbitrary_logs_do_not_become_field_replies(self):
        text = "```text\nERROR: bad tuple\nAI model: model-a\nExpected behavior: success\n```"
        self.assertEqual(triage.unwrap_field_reply(text), text)

    def test_version_with_sentence_punctuation_is_recognized(self):
        for text, expected in (("PostgreSQL 18.1.", "18.1"), ("IvorySQL 5.0.", "5.0")):
            with self.subTest(text=text):
                self.assertEqual(triage.database_versions(text), [expected])

    def test_natural_prose_can_supply_expected_behavior_and_runtime_settings(self):
        text = ("The subscription refresh crashes. PostgreSQL 18.1.\n1. Refresh a subscription.\n"
                "I expected the refresh to finish without crashing.\n"
                "The server runs in pg compatibility mode with UTF8 encoding.\nAI model: not used\nReproduced in a real environment: Yes")
        result = self.run_triage(FakeGitHub(issue(body=text)))
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(self.run_triage(FakeGitHub(issue(body=text.replace("I expected", "I expect"))))["details"]["missing"], [])

    def test_other_encoding_can_be_supplied_in_the_template_additional_section(self):
        body = COMPLETE_BUG.replace("Server encoding: UTF8", "### Server encoding\n\nOther\n\n### Anything else we need to know?\n\nThe server uses LATIN1.")
        result = self.run_triage(FakeGitHub(issue(body=body)))
        self.assertEqual(result["details"]["missing"], [])
        self.assertEqual(result["details"]["server_encoding"], "LATIN1")

    def test_automatic_duplicate_event_skips_history_search_ai_and_writes(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        before = len(github.writes)
        with patch.object(github, "history") as history, patch.object(github, "search") as search, patch("triage.ask_ai") as ai:
            result = self.run_triage(github, automatic=True)
        self.assertIn("unchanged", result["skipped"])
        history.assert_not_called()
        search.assert_not_called()
        ai.assert_not_called()
        self.assertEqual(len(github.writes), before)

    def test_manual_run_always_reanalyzes_even_when_inputs_match(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        with patch.object(github, "history", wraps=github.history) as history:
            result = self.run_triage(github)
        self.assertIn("details", result)
        history.assert_called_once()

    def test_policy_change_invalidates_the_saved_fingerprint(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        config = copy.deepcopy(self.config)
        config["similarity_threshold"] = 0.3
        with patch.object(github, "history", wraps=github.history) as history:
            result = self.run_triage(github, automatic=True, config=config)
        self.assertIn("details", result)
        history.assert_called_once()

    def test_cache_does_not_reveal_the_api_key_and_model_changes_invalidate_it(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        settings = {"TRIAGE_AI_MODEL": "model-a", "AI_API_KEY": "must-not-be-stored"}
        with patch("triage.ask_ai", return_value=([], {})):
            triage.analyze(github, 20, self.config, apply=True, ai_env=settings)
            settings["TRIAGE_AI_MODEL"] = "model-b"
            with patch.object(github, "history", wraps=github.history) as history:
                result = triage.analyze(github, 20, self.config, apply=True, ai_env=settings, automatic=True)
        self.assertIn("details", result)
        history.assert_called_once()
        self.assertNotIn("must-not-be-stored", str(self.state(github)))

    def test_label_and_author_content_changes_invalidate_the_saved_fingerprint(self):
        for change in ("label", "author"):
            with self.subTest(change=change):
                github = FakeGitHub(issue(body=COMPLETE_BUG))
                self.run_triage(github)
                if change == "label":
                    github.current["labels"].append("custom")
                else:
                    github.thread.append(comment("More observations."))
                self.assertIn("details", self.run_triage(github, automatic=True))

    def test_preview_does_not_save_a_fingerprint_or_change_labels(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github, apply=False, automatic=True)
        self.assertEqual(github.thread, [])
        self.assertEqual(github.writes, [])
        self.assertEqual(github.current["labels"], [])

    def test_pending_journal_disables_duplicate_skipping(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        state = self.state(github)
        state["pending"] = {"add": [], "remove": []}
        github.thread[0]["body"] = triage.MARKER + "\n" + triage.state_marker(state)
        result = self.run_triage(github, automatic=True)
        self.assertIn("details", result)
        self.assertNotIn("pending", self.state(github))

    def test_author_edit_during_journal_publication_prevents_label_writes(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        real_call = github.call

        def changed_after_journal(path, method="GET", data=None):
            result = real_call(path, method, data)
            if path.endswith("/comments"):
                github.current["body"] += "\nNew evidence changes the report."
            return result

        with patch.object(github, "call", side_effect=changed_after_journal), self.assertRaisesRegex(RuntimeError, "before label writes"):
            self.run_triage(github)
        self.assertEqual(github.current["labels"], [])
        self.assertIn("pending", self.state(github))

    def test_human_label_change_before_finalization_keeps_the_journal_for_recovery(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG))
        real_call = github.call

        def changed_after_labels(path, method="GET", data=None):
            result = real_call(path, method, data)
            if path.endswith("/labels"):
                github.current["labels"].append("human-label")
            return result

        with patch.object(github, "call", side_effect=changed_after_labels), self.assertRaisesRegex(RuntimeError, "before comment finalization"):
            self.run_triage(github)
        self.assertIn("pending", self.state(github))
        self.run_triage(github)
        self.assertNotIn("pending", self.state(github))
        self.assertIn("human-label", github.current["labels"])

    def test_body_edit_time_is_fetched_separately_from_rest_activity_time(self):
        github = triage.GitHub("example/postgres", "token")
        current = issue(body=COMPLETE_BUG)
        response = {"data": {"repository": {"issue": {"body": COMPLETE_BUG, "createdAt": current["created_at"],
                    "lastEditedAt": "2026-11-02T12:00:00Z"}}}}
        with patch.object(github, "call", return_value=current), patch("triage.request_json", return_value=response) as graphql:
            fetched = github.issue(20)
        self.assertEqual(fetched["body_updated_at"], "2026-11-02T12:00:00Z")
        self.assertEqual(graphql.call_args.args[0], "https://api.github.com/graphql")

    def test_failed_graphql_lookup_does_not_use_rest_updated_at_as_a_body_edit(self):
        github = triage.GitHub("example/postgres", "token")
        current = issue(body=COMPLETE_BUG)
        current["updated_at"] = "2026-11-02T12:00:00Z"
        with patch.object(github, "call", return_value=current), patch("triage.request_json", side_effect=triage.APIError(403)):
            fetched = github.issue(20)
        self.assertIsNone(fetched["body_updated_at"])

    def test_inconsistent_graphql_body_does_not_supply_a_misleading_edit_time(self):
        github = triage.GitHub("example/postgres", "token")
        response = {"data": {"repository": {"issue": {"body": "A different revision", "createdAt": "2026-10-26T00:00:00Z",
                    "lastEditedAt": "2026-11-02T12:00:00Z"}}}}
        with patch.object(github, "call", return_value=issue(body=COMPLETE_BUG)), patch("triage.request_json", return_value=response):
            fetched = github.issue(20)
        self.assertIsNone(fetched["body_updated_at"])

    def test_graphql_creation_time_is_used_for_an_unedited_body(self):
        github = triage.GitHub("example/postgres", "token")
        response = {"data": {"repository": {"issue": {"body": COMPLETE_BUG, "createdAt": "2026-10-26T00:00:00Z",
                    "lastEditedAt": None}}}}
        with patch.object(github, "call", return_value=issue(body=COMPLETE_BUG)), patch("triage.request_json", return_value=response):
            fetched = github.issue(20)
        self.assertEqual(fetched["body_updated_at"], "2026-10-26T00:00:00Z")

    def test_pull_request_does_not_trigger_a_body_revision_lookup(self):
        github = triage.GitHub("example/postgres", "token")
        with patch.object(github, "call", return_value=dict(issue(), pull_request={})), patch("triage.request_json") as graphql:
            github.issue(20)
        graphql.assert_not_called()

    def test_state_metadata_remains_bounded_on_a_long_author_discussion(self):
        comments = [comment("More investigation.", number=n) for n in range(101, 601)]
        github = FakeGitHub(issue(body="The server crashes."), comments=comments)
        self.run_triage(github)
        state = self.state(github)
        self.assertIn("request", state)
        self.assertLess(len(triage.state_marker(state)), 15000)

    def test_field_history_retains_at_most_two_comment_declarations_per_field(self):
        comments = [comment("AI model: model-" + str(n), number=n, updated_at=f"2026-10-30T12:00:{n - 100:02}Z")
                    for n in range(101, 131)]
        github = FakeGitHub(issue(body=COMPLETE_BUG), comments=comments)
        self.run_triage(github)
        history = self.state(github)["field_history"]
        self.assertLessEqual(len(history), 3)
        self.assertIn("body", history)

    def test_old_comments_without_new_metadata_remain_compatible(self):
        state = {"managed": ["type/bug"], "suppressed": []}
        self.assertEqual(triage.read_state({"body": triage.state_marker(state)}), state)
        invalid = dict(state, request={"fields": ["AI model"], "sources": {}})
        self.assertEqual(triage.read_state({"body": triage.state_marker(invalid)}), {"managed": [], "suppressed": []})


if __name__ == "__main__":
    unittest.main()
