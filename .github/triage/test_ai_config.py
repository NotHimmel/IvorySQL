import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import triage
from test_triage import FakeGitHub


class AIConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()
        cls.base = "https://openrouter.ai/api/v1"
        cls.endpoint = cls.base + "/chat/completions"

    def test_configured_base_url_and_completion_path(self):
        self.assertEqual(self.config["ai_base_url"], self.endpoint)
        self.assertEqual(triage.chat_endpoint(self.base), self.base + "/chat/completions")
        self.assertEqual(triage.chat_endpoint(self.base + "/"), self.base + "/chat/completions")
        self.assertEqual(triage.chat_endpoint(self.base + "/chat/completions"), self.base + "/chat/completions")

    def test_default_model_is_openrouter_free(self):
        self.assertEqual(self.config["ai_model"], "openrouter/free")
        resolved = triage.resolve_ai_env(self.config, {"AI_API_KEY": "test-key"}, {})
        self.assertEqual(resolved["TRIAGE_AI_MODEL"], "openrouter/free")
        with patch("triage.ask_ai", return_value=([], {})) as ai:
            triage.analyze(FakeGitHub(), 20, self.config, ai_env=resolved)
        self.assertEqual(ai.call_args.args[-2], "openrouter/free")

    def test_default_model_uses_json_output_without_provider_specific_flags(self):
        with patch("triage.request_json", return_value={"choices": [{"message": {
                "content": '{"labels": [], "similar": []}'}}]}) as request:
            triage.ask_ai({"title": "Report"}, "", [], self.config, self.endpoint, "openrouter/free", "test-key")
        payload = request.call_args.args[3]
        self.assertEqual(request.call_args.args[:3], (self.endpoint, "test-key", "POST"))
        self.assertNotIn("enable_thinking", payload)
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("JSON", payload["messages"][0]["content"])

    def test_existing_custom_full_endpoint_is_preserved(self):
        self.assertEqual(triage.chat_endpoint("https://example.test/chat?api-version=2026"),
                         "https://example.test/chat?api-version=2026")

    def test_base_url_request_uses_bearer_key_and_expected_payload(self):
        with patch("triage.request_json", return_value={"choices": [{"message": {
                "content": '{"labels": [], "similar": []}'}}]}) as request:
            triage.ask_ai({"title": "Report"}, "", [], self.config, self.base, "chosen-model", "test-key")
        self.assertEqual(request.call_args.args[:3], (self.base + "/chat/completions", "test-key", "POST"))
        self.assertEqual(request.call_args.args[3]["model"], "chosen-model")
        self.assertNotIn("test-key", json.dumps(request.call_args.args[3]))
        self.assertNotIn("enable_thinking", request.call_args.args[3])
        self.assertNotIn("response_format", request.call_args.args[3])

    def test_secret_takes_precedence_over_manual_token(self):
        resolved = triage.resolve_ai_env(self.config, {"AI_API_KEY": "secret-key"},
                                        {"inputs": {"ai_token": "manual-key"}}, dispatch=True)
        self.assertEqual(resolved["AI_API_KEY"], "secret-key")

    def test_manual_token_and_model_work_without_secret(self):
        resolved = triage.resolve_ai_env(self.config, {}, {"inputs": {
            "ai_token": "temporary-key", "ai_model": "chosen-model"}}, dispatch=True)
        self.assertEqual(resolved, {"TRIAGE_AI_ENDPOINT": self.endpoint,
                                   "TRIAGE_AI_MODEL": "chosen-model", "AI_API_KEY": "temporary-key"})

    def test_automatic_events_ignore_manual_inputs(self):
        resolved = triage.resolve_ai_env(self.config, {}, {"inputs": {
            "ai_token": "ignored-key", "ai_model": "ignored-model"}}, dispatch=False)
        self.assertEqual(resolved["AI_API_KEY"], "")
        self.assertEqual(resolved["TRIAGE_AI_MODEL"], "openrouter/free")

    def test_manual_model_overrides_variable_without_changing_credentials(self):
        resolved = triage.resolve_ai_env(self.config, {
            "TRIAGE_AI_MODEL": "configured-model", "AI_API_KEY": "secret-key"},
            {"inputs": {"ai_model": "manual-model"}}, dispatch=True)
        self.assertEqual(resolved["TRIAGE_AI_MODEL"], "manual-model")
        self.assertEqual(resolved["AI_API_KEY"], "secret-key")
        fallback = triage.resolve_ai_env(self.config, {"TRIAGE_AI_MODEL": "configured-model"}, {}, dispatch=True)
        self.assertEqual(fallback["TRIAGE_AI_MODEL"], "configured-model")
        fallback = triage.resolve_ai_env(self.config, {"TRIAGE_AI_MODEL": " "},
                                         {"inputs": {"ai_model": " "}}, dispatch=True)
        self.assertEqual(fallback["TRIAGE_AI_MODEL"], "openrouter/free")

    def test_endpoint_variable_overrides_default(self):
        endpoint = "https://example.test/v1"
        resolved = triage.resolve_ai_env(self.config, {"TRIAGE_AI_ENDPOINT": endpoint}, {})
        self.assertEqual(resolved["TRIAGE_AI_ENDPOINT"], endpoint)

    def test_both_secret_and_unused_manual_token_are_masked_before_analysis(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            resolved = triage.resolve_ai_env(self.config, {
                "GITHUB_ACTIONS": "true", "AI_API_KEY": "secret-key"},
                {"inputs": {"ai_token": "temporary-key", "ai_model": "chosen-model"}}, dispatch=True)
        self.assertEqual(output.getvalue().splitlines(), [
            "::add-mask::secret-key", "::add-mask::temporary-key"])
        with patch("triage.ask_ai", return_value=([], {})) as ai:
            report = triage.analyze(FakeGitHub(), 20, self.config, ai_env=resolved)
        self.assertEqual(ai.call_args.args[-1], "secret-key")
        for value in ("secret-key", "temporary-key"):
            self.assertNotIn(value, json.dumps(report))

    def test_workflow_command_data_is_escaped(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaisesRegex(ValueError, "whitespace"):
            triage.resolve_ai_env(self.config, {"GITHUB_ACTIONS": "true"},
                                  {"inputs": {"ai_token": "part%value\n::error::injection"}}, dispatch=True)
        self.assertEqual(output.getvalue().splitlines(), [
            "::add-mask::part%25value%0A::error::injection"])

    def test_local_resolution_does_not_print_the_token(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            triage.resolve_ai_env(self.config, {}, {"inputs": {"ai_token": "temporary-key"}}, dispatch=True)
        self.assertEqual(output.getvalue(), "")

    def test_missing_token_or_model_falls_back_and_never_calls_ai(self):
        for env in ({}, {"TRIAGE_AI_MODEL": "chosen-model"}):
            with self.subTest(env=env), patch("triage.ask_ai") as ai:
                resolved = triage.resolve_ai_env(self.config, env, {})
                result = triage.analyze(FakeGitHub(), 20, self.config, ai_env=resolved)
                ai.assert_not_called()
                self.assertIn("type/bug", result["labels"]["add"])
        with patch("triage.ask_ai") as ai:
            config = dict(self.config, ai_model="")
            resolved = triage.resolve_ai_env(config, {"AI_API_KEY": "test-key"}, {})
            triage.analyze(FakeGitHub(), 20, config, ai_env=resolved)
            ai.assert_not_called()

    def test_workflow_never_interpolates_temporary_token(self):
        workflow = Path(triage.__file__).parent.parent / "workflows" / "issue-triage.yml"
        source = workflow.read_text()
        self.assertIn("ai_token:", source)
        self.assertNotIn("${{ inputs.ai_token", source)
        self.assertNotIn("${{ github.event.inputs.ai_token", source)


if __name__ == "__main__":
    unittest.main()
