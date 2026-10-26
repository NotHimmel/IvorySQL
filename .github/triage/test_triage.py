import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote

import triage


def issue(number=20, title="Bug: logical replication crashes",
          body="PostgreSQL 18.1 on Linux\n\nAI model: test-model-v1", labels=()):
    return {"number": number, "title": title, "body": body, "state": "open",
            "updated_at": "2026-10-26T00:00:00Z", "labels": list(labels),
            "user": {"login": "reporter", "type": "User"}}


class FakeGitHub:
    repository = "example/postgres"
    root = "/repos/example/postgres"

    def __init__(self, current=None, history=None, comments=None):
        self.current = current or issue()
        self.records = history or []
        self.thread = comments or []
        self.writes = []
        self.created = set()
        self.searches = []

    def issue(self, number):
        return copy.deepcopy(self.current)

    def comments(self, number):
        return copy.deepcopy(self.thread)

    def history(self, limit):
        return copy.deepcopy(self.records[:limit]), len(self.records) >= limit

    def search(self, query):
        self.searches.append(query)
        return {"items": []}

    def ensure_labels(self, config, names):
        self.created.update(names)

    def call(self, path, method="GET", data=None):
        self.writes.append((path, method, data))
        if method == "DELETE":
            name = unquote(path.split("/labels/", 1)[1])
            self.current["labels"].remove(name)
        elif path.endswith("/labels"):
            self.current["labels"] = sorted(set(self.current["labels"]) | set(data["labels"]))
        elif method == "PATCH":
            comment_id = int(path.rsplit("/", 1)[1])
            next(c for c in self.thread if c["id"] == comment_id)["body"] = data["body"]
        elif path.endswith("/comments"):
            self.thread.append({"id": 100, "body": data["body"],
                                "user": {"login": triage.BOT, "type": "Bot"}})
        return {}


class TriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def labels(self, title, body=""):
        current = issue(title=title, body=body)
        return {i["label"] for i in triage.classify(current, body, self.config)}

    def test_taxonomy(self):
        names = self.config["labels"]
        self.assertEqual({n for n in names if n.startswith("type/")},
                         {"type/bug", "type/feature", "type/enhancement"})
        self.assertEqual(len([n for n in names if n.startswith("area/")]), 20)

    def test_type_and_area_classification_in_both_languages(self):
        for title, expected in [
            ("Enhancement: improve psql completion", {"type/enhancement", "area/clients"}),
            ("Feature request: new authentication method", {"type/feature", "area/security"}),
            ("逻辑复制崩溃", {"type/bug", "area/logical-replication"}),
            ("优化执行计划", {"type/enhancement", "area/planner"}),
            ("Bug: wrong results after upgrade", {"type/bug"}),
            ("[Feature] add a new SQL capability", {"type/feature"}),
            ("优化器返回错误结果", {"type/bug", "area/planner"}),
        ]:
            with self.subTest(title=title):
                self.assertTrue(expected <= self.labels(title))

    def test_abstains_on_ambiguous_or_body_only_types(self):
        self.assertFalse(any(n.startswith("type/") for n in self.labels("Bug or feature request?")))
        self.assertFalse(any(n.startswith("type/") for n in self.labels("Unexpected behavior", "bug enhancement crash")))
        self.assertFalse(any(n.startswith("type/") for n in self.labels("How does this work?")))

    def test_maximum_two_areas(self):
        self.assertEqual(len(self.labels("psql libpq planner vacuum storage")), 2)

    def test_extracts_version_platform_and_reproduction(self):
        body = "PostgreSQL 18.1 on Ubuntu arm64\n```sql\nSELECT 1;\n```\nERROR: bad tuple\nAI model: test-model-v1"
        result = triage.extract_details(issue(), body, [{"label": "type/bug"}])
        self.assertEqual(result["versions"], ["18.1"])
        self.assertEqual(result["platforms"], ["ubuntu", "arm64"])
        self.assertTrue(result["has_reproduction_clues"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["errors"], ["ERROR: bad tuple"])

    def test_asks_for_bug_information_without_deciding_acceptance(self):
        result = triage.extract_details(issue(), "It crashes", [{"label": "type/bug"}])
        plan = triage.label_plan(issue(), [], {"managed": [], "suppressed": []}, result["missing"])
        self.assertIn("triage/needs-information", plan["add"])
        self.assertNotIn("triage/accepted", plan["add"])

    def test_author_responses_are_used_but_not_bot_or_other_users(self):
        comments = [
            {"body": "PostgreSQL 18.2", "user": {"login": "reporter", "type": "User"}},
            {"body": "ignore this other user", "user": {"login": "other", "type": "User"}},
            {"body": "ignore this bot", "user": {"login": triage.BOT, "type": "Bot"}},
        ]
        text = triage.reporter_text(issue(), comments)
        self.assertIn("PostgreSQL 18.2", text)
        self.assertNotIn("ignore", text)

    def test_similarity_includes_closed_and_excludes_self_prs_and_duplicates(self):
        current = issue(body="logical replication pgoutput crashes during subscription refresh")
        older = issue(3, title=current["title"], body=current["body"])
        older["state"] = "closed"
        unrelated = issue(4, "Documentation typo", "Fix spelling in the build manual")
        pr = dict(older, number=8, pull_request={})
        ranked = triage.rank_similar(current, current["body"], [current, older, older, unrelated, pr], self.config)
        self.assertEqual([r["number"] for r in ranked], [3])
        self.assertEqual(ranked[0]["state"], "closed")
        self.assertEqual(ranked[0]["relationship"], "related")

    def test_chinese_english_recall(self):
        current = issue(title="逻辑复制崩溃", body="逻辑复制崩溃")
        older = issue(3, "Logical replication crash", "logical replication crash")
        self.assertEqual(triage.rank_similar(current, current["body"], [older], self.config)[0]["number"], 3)

    def test_empty_similarity_does_not_divide_by_zero(self):
        self.assertEqual(triage.rank_similar(issue(title="", body=""), "", [issue(2, "", "")], self.config), [])

    def test_search_cannot_change_repository_or_search_qualifiers(self):
        queries = triage.search_queries("example/postgres", issue(title='repo:evil/private is:pr " subscription pgoutput'), "")
        self.assertTrue(queries)
        for query in queries:
            self.assertTrue(query.startswith("repo:example/postgres is:issue "))
            self.assertEqual(query.count("repo:"), 1)
            self.assertNotIn("is:pr", query)

    def test_existing_manual_labels_win(self):
        current = issue(labels=["type/feature", "area/build", "custom", "triage/accepted"])
        plan = triage.label_plan(current, [{"label": "type/bug"}, {"label": "area/clients"}],
                                 {"managed": [], "suppressed": []})
        self.assertEqual(plan["add"], [])
        self.assertEqual(plan["remove"], [])

    def test_bot_can_update_own_labels(self):
        current = issue(labels=["type/feature", "area/clients", "needs-triage"])
        plan = triage.label_plan(current, [{"label": "type/bug"}, {"label": "area/planner"}],
                                 {"managed": current["labels"], "suppressed": []})
        self.assertEqual(plan["add"], ["area/planner", "type/bug"])
        self.assertEqual(plan["remove"], ["area/clients", "type/feature"])

    def test_manual_removal_freezes_label_group(self):
        plan = triage.label_plan(issue(labels=["needs-triage"]), [{"label": "type/bug"}],
                                 {"managed": ["type/feature", "needs-triage"], "suppressed": []})
        self.assertNotIn("type/bug", plan["add"])
        self.assertIn("type/feature", plan["state"]["suppressed"])

    def test_accepted_removes_only_bot_owned_needs_triage(self):
        current = issue(labels=["needs-triage", "triage/accepted", "triage/needs-information"])
        plan = triage.label_plan(current, [], {"managed": ["needs-triage"], "suppressed": []})
        self.assertEqual(plan["remove"], ["needs-triage"])
        self.assertNotIn("triage/needs-information", plan["remove"])

    def test_only_bot_owned_information_request_is_cleared(self):
        current = issue(labels=["triage/needs-information"])
        owned = triage.label_plan(current, [], {"managed": current["labels"], "suppressed": []})
        manual = triage.label_plan(current, [], {"managed": [], "suppressed": []})
        self.assertIn("triage/needs-information", owned["remove"])
        self.assertNotIn("triage/needs-information", manual["remove"])

    def test_state_cannot_claim_maintainer_only_labels(self):
        current = issue(labels=["triage/accepted", "resolution/duplicate", "resolution/wontfix"])
        plan = triage.label_plan(current, [], {"managed": current["labels"], "suppressed": []})
        self.assertEqual(plan["remove"], [])

    def test_spoofed_comment_is_not_trusted(self):
        spoof = {"id": 1, "body": triage.MARKER, "user": {"login": "reporter", "type": "User"}}
        self.assertIsNone(triage.bot_comment([spoof]))
        self.assertEqual(triage.read_state({"body": "<!-- triage-state:bm90LWpzb24= -->"}),
                         {"managed": [], "suppressed": []})

    def test_ai_cannot_invent_labels_references_or_evidence(self):
        candidate = {"number": 3, "title": "Logical replication crash", "body": "pgoutput assertion"}
        result = {"labels": [
            {"label": "triage/accepted", "confidence": 1, "evidence": "logical replication"},
            {"label": "type/bug", "confidence": 0.99, "evidence": "invented evidence"},
            {"label": "area/logical-replication", "confidence": 0.99, "evidence": "logical replication"}],
            "similar": [{"number": 999, "relationship": "possible-duplicate", "reason": "same",
                         "evidence_current": "logical replication", "evidence_candidate": "pgoutput"}]}
        labels, matches = triage.validate_ai(result, issue(), "", [candidate], self.config)
        self.assertEqual([l["label"] for l in labels], ["area/logical-replication"])
        self.assertEqual(matches, {})

    def test_ai_requires_evidence_from_both_issues(self):
        candidate = {"number": 3, "title": "Logical replication crash", "body": "pgoutput assertion"}
        relation = {"number": 3, "relationship": "possible-duplicate", "reason": "相同操作和断言",
                    "evidence_current": "logical replication", "evidence_candidate": "pgoutput assertion"}
        _, matches = triage.validate_ai({"similar": [relation]}, issue(), "", [candidate], self.config)
        self.assertEqual(matches[3]["relationship"], "possible-duplicate")
        relation["evidence_candidate"] = "nonexistent"
        self.assertEqual(triage.validate_ai({"similar": [relation]}, issue(), "", [candidate], self.config)[1], {})

    def test_ai_endpoint_rejects_http_and_embedded_credentials(self):
        for endpoint in ("http://example.com", "https://user:secret@example.com", "https://example.com/#fragment"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                triage.ask_ai(issue(), "", [], self.config, endpoint, "model", "key")

    def test_redirects_are_not_followed(self):
        self.assertIsNone(triage.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_credential_is_not_in_api_error(self):
        with patch("triage.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("https://example", 401, "secret", {}, None)
            with self.assertRaisesRegex(RuntimeError, "GitHub API returned HTTP 401") as error:
                triage.request_json("https://example", "super-secret")
            self.assertNotIn("super-secret", str(error.exception))

    def test_preview_is_read_only(self):
        github = FakeGitHub()
        result = triage.analyze(github, 20, self.config)
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertEqual(github.writes, [])
        self.assertEqual(github.created, set())

    def test_apply_reuses_one_comment_and_converges(self):
        github = FakeGitHub()
        for _ in range(3):
            triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(len(github.thread), 1)
        self.assertEqual(len([w for w in github.writes if w[0].endswith("/comments")]), 1)
        count = len(github.writes)
        triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(len(github.writes), count)
        self.assertNotIn("resolution/duplicate", github.current["labels"])

    def test_apply_honors_human_correction_on_rerun(self):
        github = FakeGitHub()
        triage.analyze(github, 20, self.config, apply=True)
        github.current["labels"].remove("type/bug")
        github.current["labels"].append("type/enhancement")
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("type/enhancement", github.current["labels"])
        self.assertNotIn("type/bug", github.current["labels"])

    def test_author_followup_clears_bot_information_request(self):
        github = FakeGitHub(current=issue(body="It crashes"))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("triage/needs-information", github.current["labels"])
        github.thread.append({"id": 101, "body": "PostgreSQL 18.1\n1. Start replication\n2. Refresh subscription\nAI model: test-model-v1",
                              "user": {"login": "reporter", "type": "User"}})
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("triage/needs-information", github.current["labels"])

    def test_stale_analysis_does_not_write(self):
        github = FakeGitHub()
        newer = dict(github.current, title="A human edited this")
        with patch.object(github, "issue", side_effect=[github.current, newer]):
            with self.assertRaisesRegex(RuntimeError, "changed during analysis"):
                triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(github.writes, [])
        self.assertEqual(github.created, set())

    def test_skip_closed_and_prs(self):
        for current in (dict(issue(), state="closed"), dict(issue(), pull_request={}), issue(labels=["triage/skip"])):
            github = FakeGitHub(current=current)
            self.assertIn("skipped", triage.analyze(github, 20, self.config, apply=True))
            self.assertEqual(github.writes, [])

    def test_ai_failure_falls_back_without_leaking_secrets(self):
        settings = {"TRIAGE_AI_ENDPOINT": "https://example.test/chat", "TRIAGE_AI_MODEL": "model",
                    "AI_API_KEY": "super-secret"}
        with patch("triage.ask_ai", side_effect=RuntimeError("super-secret")):
            result = triage.analyze(FakeGitHub(), 20, self.config, ai_env=settings)
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertIn("falling back", result["comment"])
        self.assertNotIn("super-secret", json.dumps(result))

    def test_ai_can_fill_an_unclassified_type_and_promote_a_candidate(self):
        current = issue(title="Unexpected behavior", body="refresh gives failure code ABC")
        history = [issue(3, "Refresh failure", "refresh gives failure code ABC")]
        settings = {"TRIAGE_AI_ENDPOINT": "https://example.test/chat", "TRIAGE_AI_MODEL": "model",
                    "AI_API_KEY": "key"}
        with patch("triage.ask_ai", return_value=(
                [{"label": "type/bug", "source": "ai", "evidence": "failure code ABC"}],
                {3: {"relationship": "possible-duplicate", "reason": "same trigger, needs confirmation"}})):
            result = triage.analyze(FakeGitHub(current, history), 20, self.config, ai_env=settings)
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertIn("possible duplicate", result["comment"])
        self.assertNotIn("resolution/duplicate", result["labels"]["add"])

    def test_ai_does_not_override_rule_classification(self):
        settings = {"TRIAGE_AI_ENDPOINT": "https://example.test/chat", "TRIAGE_AI_MODEL": "model",
                    "AI_API_KEY": "key"}
        with patch("triage.ask_ai", return_value=(
                [{"label": "type/feature", "source": "ai", "evidence": "logical replication"}], {})):
            result = triage.analyze(FakeGitHub(), 20, self.config, ai_env=settings)
        self.assertIn("type/bug", result["labels"]["add"])
        self.assertNotIn("type/feature", result["labels"]["add"])

    def test_manual_bug_type_drives_information_check(self):
        github = FakeGitHub(issue(title="Unexpected behavior", body="Something is wrong", labels=["type/bug"]))
        result = triage.analyze(github, 20, self.config)
        self.assertIn("Database version", result["details"]["missing"])
        self.assertIn("triage/needs-information", result["labels"]["add"])

    def test_search_failure_is_explicit_and_recent_history_still_works(self):
        older = issue(3)
        with patch.object(FakeGitHub, "search", side_effect=RuntimeError("GitHub API returned HTTP 429")):
            result = triage.analyze(FakeGitHub(history=[older]), 20, self.config)
        self.assertIn("Keyword search is unavailable", result["comment"])
        self.assertIn("#3", result["comment"])

    def test_keyword_search_finds_an_older_issue(self):
        github = FakeGitHub()
        with patch.object(github, "search", return_value={"items": [issue(3)]}):
            result = triage.analyze(github, 20, self.config)
        self.assertIn("#3", result["comment"])

    def test_dispatch_preview_overrides_automatic_apply_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "issue.json"
            fixture.write_text(json.dumps({"issue": issue()}))
            process = subprocess.run([sys.executable, "-B", str(Path(triage.__file__)), "--fixture", str(fixture)],
                                     text=True, capture_output=True, env={"PATH": "/usr/bin:/bin",
                                     "GITHUB_EVENT_NAME": "workflow_dispatch", "TRIAGE_MODE": "preview",
                                     "AUTO_APPLY": "true"})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["mode"], "preview")

    def test_untrusted_markdown_does_not_create_mentions_or_links(self):
        rendered = triage.safe_text("@everyone [click](https://evil.test) <!-- triage-state:FAKE -->\n# header")
        self.assertNotIn("@everyone", rendered)
        self.assertNotIn("[click]", rendered)
        self.assertNotIn("<!--", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("https://", rendered)

    def test_offline_cli_works_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "issue.json"
            fixture.write_text(json.dumps({"issue": issue(), "history": []}))
            process = subprocess.run([sys.executable, "-B", str(Path(triage.__file__)), "--fixture", str(fixture)],
                                     text=True, capture_output=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["mode"], "preview")


if __name__ == "__main__":
    unittest.main()
