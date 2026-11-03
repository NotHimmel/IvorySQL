"""Share bounded history snapshots without caching authoritative issue reads."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import triage
from test_triage import issue


class HistoryCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "history.json"
        self.now = time.time()

    def client(self, repository="example/postgres"):
        return triage.GitHub(repository, "must-not-be-cached", self.path)

    def seed(self, records=None, age=0, full_age=None, limit=1000):
        cache = {"version": 1, "repository": "example/postgres", "limit": limit,
                 "synced_at": self.now - age, "full_synced_at": self.now - (full_age or age),
                 "capped": False, "items": records if records is not None else [issue(1)]}
        # Saved snapshots contain only ranking inputs.
        for record in cache["items"]:
            for key in list(record):
                if key not in {"number", "title", "body", "state", "created_at", "updated_at", "pull_request"}:
                    del record[key]
        self.path.write_text(json.dumps(cache))
        return cache

    def test_initial_refresh_is_saved_and_the_next_process_reuses_it(self):
        client = self.client()
        record = issue(1)
        record.update(user={"login": "reporter"}, private_metadata="not-for-cache")
        with patch.object(client, "pages", return_value=[record]) as pages:
            client.history(1000)
            client.history(1000)
        self.assertEqual(pages.call_count, 1)
        self.assertTrue(client.cache_updated)
        self.assertNotIn("must-not-be-cached", self.path.read_text())
        self.assertNotIn("private_metadata", self.path.read_text())
        other = self.client()
        with patch.object(other, "pages") as pages:
            records, capped = other.history(1000)
        pages.assert_not_called()
        self.assertEqual([item["number"] for item in records], [1])
        self.assertFalse(capped)
        self.assertFalse(other.cache_updated)

    def test_expired_snapshot_merges_incremental_edits_new_issues_and_closures(self):
        self.seed([issue(1), issue(2)], age=1000)
        updated = dict(issue(1), title="Corrected title", state="closed")
        newest = dict(issue(3), created_at="2026-10-30T00:00:00Z")
        client = self.client()
        with patch.object(client, "pages", return_value=[updated, newest]) as pages:
            records, _ = client.history(1000)
        self.assertEqual(pages.call_count, 1)
        path, cap = pages.call_args.args
        query = parse_qs(urlsplit(path).query)
        self.assertEqual(query["sort"], ["updated"])
        self.assertIn("since", query)
        self.assertEqual(cap, 1001)
        by_number = {record["number"]: record for record in records}
        self.assertEqual(by_number[1]["state"], "closed")
        self.assertEqual(by_number[1]["title"], "Corrected title")
        self.assertEqual(set(by_number), {1, 2, 3})
        saved = json.loads(self.path.read_text())
        self.assertLess(saved["full_synced_at"], saved["synced_at"])

    def test_full_refresh_periodically_removes_deleted_historical_records(self):
        self.seed(age=10, full_age=90000)
        client = self.client()
        with patch.object(client, "pages", return_value=[issue(2)]) as pages:
            records, _ = client.history(1000)
        self.assertIn("sort=created", pages.call_args.args[0])
        self.assertEqual([item["number"] for item in records], [2])

    def test_overflowing_delta_falls_back_to_a_bounded_full_refresh(self):
        self.seed(age=1000, limit=2)
        client = self.client()
        with patch.object(client, "pages", side_effect=[[issue(2), issue(3), issue(4)], [issue(4), issue(3)]]) as pages:
            records, capped = client.history(2)
        self.assertEqual(pages.call_count, 2)
        self.assertEqual(pages.call_args.args[1], 2)
        self.assertEqual([record["number"] for record in records], [4, 3])
        self.assertTrue(capped)

    def test_wrong_repository_future_timestamps_and_malformed_snapshots_are_ignored(self):
        for change in ({"repository": "other/private"}, {"synced_at": self.now + 1000},
                       {"items": [{"number": 1}]}, {"version": 99}, {"items": "invalid"}):
            with self.subTest(change=change):
                cache = self.seed()
                cache.update(change)
                self.path.write_text(json.dumps(cache))
                client = self.client()
                with patch.object(client, "pages", return_value=[issue(3)]) as pages:
                    records, _ = client.history(1000)
                pages.assert_called_once()
                self.assertEqual(records[0]["number"], 3)
                self.assertTrue(client.history_notes)

    def test_invalid_json_does_not_prevent_a_fresh_history_scan(self):
        self.path.write_text("not-json")
        client = self.client()
        with patch.object(client, "pages", return_value=[]) as pages:
            self.assertEqual(client.history(1000), ([], False))
        pages.assert_called_once()

    def test_failed_refresh_keeps_the_previous_cache_and_watermark(self):
        self.seed(age=1000)
        previous = self.path.read_bytes()
        client = self.client()
        with patch.object(client, "pages", side_effect=triage.RateLimitError(self.now + 3600)):
            with self.assertRaises(triage.RateLimitError):
                client.history(1000)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertFalse(client.cache_updated)

    def test_empty_delta_advances_the_watermark_without_losing_history(self):
        self.seed(age=1000)
        client = self.client()
        with patch.object(client, "pages", return_value=[]) as pages:
            records, _ = client.history(1000)
        self.assertEqual([record["number"] for record in records], [1])
        self.assertGreater(json.loads(self.path.read_text())["synced_at"], self.now - 1000)

    def test_cache_write_failure_does_not_discard_successful_retrieval(self):
        client = self.client()
        with patch.object(client, "pages", return_value=[issue(1)]), patch.object(Path, "write_text", side_effect=OSError("unwritable")):
            records, _ = client.history(1000)
        self.assertEqual(records[0]["number"], 1)
        self.assertFalse(client.cache_updated)
        self.assertTrue(client.history_notes)

    def test_history_never_substitutes_for_an_authoritative_issue_read(self):
        self.seed()
        client = self.client()
        current = issue(1, body="Current body, not a cached report")
        response = {"data": {"repository": {"issue": {"body": current["body"], "createdAt": current["created_at"], "lastEditedAt": None}}}}
        with patch.object(client, "pages") as pages, patch.object(client, "call", return_value=current) as get, patch("triage.request_json", return_value=response):
            client.history(1000)
            self.assertEqual(client.issue(1)["body"], current["body"])
        pages.assert_not_called()
        get.assert_called_once()

    def test_a_real_preview_batch_shares_one_history_fetch(self):
        from test_triage import FakeGitHub
        history_client = self.client()
        class Batch(FakeGitHub):
            def issue(self, number):
                return issue(number)
            def history(self, limit):
                return history_client.history(limit)
        targets = [{"number": number, "kind": "issue"} for number in (1, 2, 3)]
        with patch.object(history_client, "pages", return_value=[issue(10)]) as pages:
            report = triage.run_targets(Batch(), targets, triage.load_config())
        self.assertEqual(report["counts"], {"processed": 3, "skipped": 0, "failed": 0})
        pages.assert_called_once()
