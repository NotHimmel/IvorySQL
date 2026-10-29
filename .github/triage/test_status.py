import unittest

import triage
from test_triage import FakeGitHub, issue


class StatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def test_acceptance_clears_waiting_stage_without_prior_bot_ownership(self):
        github = FakeGitHub(issue(labels=["type/bug", "needs-triage", "triage/accepted"]))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("needs-triage", github.current["labels"])
        self.assertIn("triage/accepted", github.current["labels"])
        self.assertIn("type/bug", github.current["labels"])

    def test_resolution_clears_waiting_stage_without_prior_bot_ownership(self):
        for resolution in ("resolution/duplicate", "resolution/invalid", "resolution/wontfix"):
            with self.subTest(resolution=resolution):
                github = FakeGitHub(issue(labels=["needs-triage", resolution]))
                triage.analyze(github, 20, self.config, apply=True)
                self.assertNotIn("needs-triage", github.current["labels"])
                self.assertIn(resolution, github.current["labels"])
                self.assertNotIn("triage/accepted", github.current["labels"])

    def test_template_waiting_stage_is_adopted_then_cleared_on_acceptance(self):
        github = FakeGitHub(issue(labels=["type/bug", "needs-triage"]))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("needs-triage", triage.read_state(github.thread[0])["managed"])
        github.current["labels"].append("triage/accepted")
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("needs-triage", github.current["labels"])

    def test_removing_acceptance_restores_waiting_stage_on_the_next_run(self):
        github = FakeGitHub(issue(labels=["needs-triage", "triage/accepted"]))
        triage.analyze(github, 20, self.config, apply=True)
        github.current["labels"].remove("triage/accepted")
        triage.analyze(github, 20, self.config, apply=True)
        self.assertIn("needs-triage", github.current["labels"])
        self.assertNotIn("triage/accepted", github.current["labels"])

    def test_waiting_stage_is_not_permanently_suppressed(self):
        current = issue(labels=[])
        previous = {"managed": ["needs-triage"], "suppressed": ["needs-triage"]}
        plan = triage.label_plan(current, [], previous)
        self.assertIn("needs-triage", plan["add"])
        self.assertNotIn("needs-triage", plan["state"]["suppressed"])

    def test_acceptance_keeps_bot_information_requests_until_fields_are_supplied(self):
        github = FakeGitHub(issue(body="The server crashes.", labels=["needs-triage", "triage/accepted"]))
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("needs-triage", github.current["labels"])
        self.assertIn("triage/needs-information", github.current["labels"])
        github.current["body"] = "IvorySQL master\n1. Start the server.\nAI model: not used"
        triage.analyze(github, 20, self.config, apply=True)
        self.assertNotIn("triage/needs-information", github.current["labels"])
        self.assertIn("triage/accepted", github.current["labels"])

    def test_manual_information_request_is_preserved_after_acceptance(self):
        github = FakeGitHub(issue(body="IvorySQL master\n1. Start the server.\nAI model: not used",
                                  labels=["needs-triage", "triage/accepted", "triage/needs-information"]))
        result = triage.analyze(github, 20, self.config, apply=True)
        self.assertEqual(result["details"]["missing"], [])
        self.assertIn("triage/needs-information", github.current["labels"])
        self.assertNotIn("needs-triage", github.current["labels"])


if __name__ == "__main__":
    unittest.main()
