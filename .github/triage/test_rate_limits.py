"""Exercise rejected requests without sleeping or contacting either API."""

from contextlib import ExitStack
from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import triage
from test_triage import FakeGitHub


class Clock:
    def __init__(self):
        self.now = 1800000000.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    def __init__(self, data=None, headers=None):
        super().__init__(json.dumps(data or {"ok": True}).encode())
        self.headers = headers or {}


def error(status=429, headers=None, message="API rate limit exceeded"):
    return HTTPError("https://api.github.com/example", status, "private-response", headers or {},
                     io.BytesIO(json.dumps({"message": message}).encode()))


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.gate = triage.GitHubRateGate()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("triage.time.time", self.clock.time))
        self.stack.enter_context(patch("triage.time.monotonic", self.clock.time))
        self.stack.enter_context(patch("triage.time.sleep", self.clock.sleep))
        self.opener = self.stack.enter_context(patch("triage.build_opener")).return_value

    def request(self, path="/repos/example/postgres/issues", method="GET"):
        return triage.request_json("https://api.github.com" + path, "must-stay-secret", method,
                                  gate=self.gate)

    def test_retry_after_is_respected_before_a_safe_rejected_write_retry(self):
        self.opener.open.side_effect = [error(headers={"retry-after": "11"}), Response()]
        self.assertEqual(self.request(method="POST"), {"ok": True})
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertGreaterEqual(sum(self.clock.sleeps), 11)

    def test_primary_reset_and_retry_after_both_apply(self):
        self.opener.open.side_effect = [error(403, {"Retry-After": "2", "X-RateLimit-Remaining": "0",
                                                "X-RateLimit-Reset": str(self.clock.now + 9)}), Response()]
        self.request()
        self.assertGreaterEqual(sum(self.clock.sleeps), 10)
        self.assertLess(sum(self.clock.sleeps), 60)

    def test_http_date_retry_after(self):
        retry = format_datetime(datetime.fromtimestamp(self.clock.now + 20, timezone.utc), usegmt=True)
        self.opener.open.side_effect = [error(headers={"Retry-After": retry}), Response()]
        self.request()
        self.assertGreaterEqual(sum(self.clock.sleeps), 20)

    def test_secondary_limit_without_headers_waits_at_least_one_minute(self):
        self.opener.open.side_effect = [error(403, message="You have exceeded a secondary rate limit"), Response()]
        self.request()
        self.assertEqual(sum(self.clock.sleeps), 60)

    def test_permission_denial_does_not_retry(self):
        self.opener.open.side_effect = error(403, message="Resource not accessible by integration")
        with self.assertRaises(triage.APIError) as caught:
            self.request()
        self.assertNotIsInstance(caught.exception, triage.RateLimitError)
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_long_reset_defers_without_sleeping_or_more_requests(self):
        self.opener.open.side_effect = error(403, {"X-RateLimit-Remaining": "0",
                                                 "X-RateLimit-Reset": str(self.clock.now + 3600)})
        with self.assertRaises(triage.RateLimitError) as caught:
            self.request()
        with self.assertRaises(triage.RateLimitError):
            self.request()
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])
        self.assertNotIn("must-stay-secret", str(caught.exception))
        self.assertNotIn("private-response", str(caught.exception))

    def test_repeated_rejections_have_a_bounded_attempt_count(self):
        self.opener.open.side_effect = [error(headers={"Retry-After": "1"}) for _ in range(4)]
        with self.assertRaises(triage.RateLimitError):
            self.request()
        self.assertEqual(self.opener.open.call_count, 3)

    def test_secondary_exponential_backoff_stops_at_the_wait_budget(self):
        self.opener.open.side_effect = [error(), error(), Response()]
        with self.assertRaises(triage.RateLimitError):
            self.request()
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertEqual(sum(self.clock.sleeps), 60)

    def test_network_failure_does_not_retry_an_unknown_write_outcome(self):
        self.opener.open.side_effect = URLError("private-response")
        with self.assertRaisesRegex(RuntimeError, "GitHub API request failed"):
            self.request(method="POST")
        self.assertEqual(self.opener.open.call_count, 1)

    def test_successful_headers_pace_future_requests(self):
        self.opener.open.side_effect = [Response(headers={"X-RateLimit-Remaining": "950",
               "X-RateLimit-Reset": str(self.clock.now + 3600), "X-RateLimit-Resource": "core"}), Response()]
        self.request()
        self.request()
        self.assertGreaterEqual(sum(self.clock.sleeps), 4)

    def test_success_exhausting_a_bucket_stops_before_the_next_request(self):
        self.opener.open.side_effect = [Response(headers={"X-RateLimit-Remaining": "0",
                  "X-RateLimit-Reset": str(self.clock.now + 3600)}), Response()]
        self.request()
        with self.assertRaises(triage.RateLimitError):
            self.request()
        self.assertEqual(self.opener.open.call_count, 1)

    def test_search_and_content_writes_have_independent_minimum_intervals(self):
        self.opener.open.side_effect = [Response() for _ in range(4)]
        self.request("/search/issues?q=test")
        self.request("/search/issues?q=other")
        self.assertAlmostEqual(sum(self.clock.sleeps), 2.2, places=5)
        before = self.clock.now
        self.request(method="POST")
        self.request(method="PATCH")
        self.assertGreaterEqual(self.clock.now - before, 8)

    def test_rate_limit_stops_the_rest_of_a_batch_without_more_api_calls(self):
        targets = [{"number": number, "kind": "issue"} for number in (1, 2, 3)]
        with patch("triage.analyze", side_effect=triage.RateLimitError(self.clock.now + 3600)) as analyze:
            report = triage.run_targets(FakeGitHub(), targets, triage.load_config())
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(report["counts"], {"processed": 0, "skipped": 0, "failed": 3})

    def test_graphql_rate_limit_is_not_hidden_as_an_edit_timestamp_failure(self):
        github = triage.GitHub("example/postgres", "token")
        from test_triage import issue
        with patch.object(github, "call", return_value=issue()), patch("triage.request_json", side_effect=triage.RateLimitError(self.clock.now + 3600)):
            with self.assertRaises(triage.RateLimitError):
                github.issue(20)

class PersistedRateLimitTests(unittest.TestCase):
    def test_next_worker_honors_the_previous_workers_cooldown_without_an_http_call(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rate-limit.json"
            first = triage.GitHubRateGate(path, "example/postgres")
            first.defer(triage.time.time() + 3600)
            second = triage.GitHubRateGate(path, "example/postgres")
            with patch("triage.build_opener") as opener:
                with self.assertRaises(triage.RateLimitError):
                    triage.request_json("https://api.github.com/repos/example/postgres/issues", "key", gate=second)
            opener.assert_not_called()
            self.assertNotIn("key", path.read_text())

    def test_rate_state_is_repository_scoped_and_malformed_state_is_ignored(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rate-limit.json"
            first = triage.GitHubRateGate(path, "example/postgres")
            first.defer(triage.time.time() + 3600)
            self.assertEqual(triage.GitHubRateGate(path, "other/repository").blocked_until, 0)
            path.write_text('{"next_request": []}')
            self.assertEqual(triage.GitHubRateGate(path, "example/postgres").blocked_until, 0)
