import unittest

import triage
from test_triage import FakeGitHub, issue


class InformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()

    def details(self, body):
        return triage.extract_details(issue(title="Bug: build fails"), body,
                                      [{"label": "type/bug"}], self.config)

    def test_form_versions_accept_branches_releases_and_commit_ids(self):
        for heading, value, expected in [
            ("IvorySQL version", "master", "master"),
            ("Database version", "main", "main"),
            ("Database version", "abc1234", "abc1234"),
            ("Commit SHA", "c75bd4ac2e5f6eb5bc516ec891838d63d0d2142e", "c75bd4ac2e5f6eb5bc516ec891838d63d0d2142e"),
            ("IvorySQL version", "IvorySQL V5", "5"),
            ("PostgreSQL version", "18.1", "18.1"),
            ("Database version", "REL_18_STABLE", "REL_18_STABLE"),
            ("数据库版本", "master", "master"),
        ]:
            with self.subTest(heading=heading, value=value):
                body = f"### {heading}\n\n{value}\n\n### Reproduction steps\n\nRun meson setup and compile.\n\nAI model: not used"
                result = self.details(body)
                self.assertIn(expected, result["versions"])
                self.assertNotIn("Database version", result["missing"])

    def test_free_form_database_versions_still_work(self):
        for value, expected in [("IvorySQL master", "master"), ("PostgreSQL 18.1", "18.1"),
                                ("PostgreSQL 19beta1", "19beta1"), ("HPEDB v1.0.4", "1.0.4")]:
            with self.subTest(value=value):
                self.assertIn(expected, self.details(value)["versions"])

    def test_missing_version_placeholders_and_unrelated_versions_are_not_accepted(self):
        for value in ("_No response_", "unknown", "TODO", "", "<!-- master -->"):
            with self.subTest(value=value):
                result = self.details("### Database version\n\n" + value + "\n\n### Description\n\nBuild fails.")
                self.assertIn("Database version", result["missing"])
        self.assertEqual(self.details("OS version: 22.04\nAI model: model-version-2")["versions"], [])

    def test_shell_reproduction_is_accepted_with_master_version(self):
        body = """### AI model

not used

### What happened?

The build fails with an undefined reference.

### How can we reproduce it (as minimally and precisely as possible)?

```sh
meson setup build
meson compile -C build
```

### IvorySQL version

master

### What did you expect to happen?

The build should finish successfully.
"""
        current = issue(title="Bug: build fails", body=body, labels=["type/bug", "needs-triage"])
        result = triage.analyze(FakeGitHub(current), 20, self.config)
        self.assertEqual(result["details"]["missing"], [])
        self.assertNotIn("triage/needs-information", result["labels"]["add"])

    def test_reproduction_accepts_prose_shell_and_sql_without_numbering(self):
        examples = [
            "### Reproduction steps\n\nOpen two sessions, update the same row, then commit the first session.",
            "Steps to reproduce: Start a standby and restart the primary.",
            "### 复现步骤\n\n打开两个会话，同时更新同一行。",
            "```bash\n./configure --enable-debug\nmake -j2\n```",
            "```\n./configure --enable-debug\nmake -j2\n```",
            "~~~console\n$ meson setup build\n$ meson compile -C build\n~~~",
            "```sql\nSELECT 1;\n```",
            "1. Start a server.\n2. Restart it.",
        ]
        for reproduction in examples:
            with self.subTest(reproduction=reproduction):
                result = self.details("IvorySQL master\nAI model: not used\n\n" + reproduction)
                self.assertTrue(result["has_reproduction_clues"])
                self.assertEqual(result["missing"], [])

    def test_empty_reproduction_fields_and_comment_only_scripts_still_need_information(self):
        for reproduction in [
            "### Reproduction steps\n\n_No response_",
            "### Reproduction steps\n\nTODO",
            "### Reproduction steps\n\n<!-- add steps here -->",
            "```sh\n# paste commands here\n```",
        ]:
            with self.subTest(reproduction=reproduction):
                result = self.details("IvorySQL master\nAI model: not used\n\n" + reproduction)
                self.assertFalse(result["has_reproduction_clues"])
                self.assertIn("Reproduction steps or minimal SQL", result["missing"])

    def test_empty_description_field_is_not_hidden_by_other_metadata(self):
        result = self.details("### Description\n\n_No response_\n\n### Database version\n\nmaster\n\nAI model: not used")
        self.assertIn("Issue description", result["missing"])

    def test_environment_scaffolding_and_logs_do_not_supply_reproduction(self):
        for heading in ("OS version", "Logs"):
            with self.subTest(heading=heading):
                body = ("IvorySQL master\nAI model: not used\n\n### Reproduction steps\n\n_No response_\n\n"
                        f"### {heading}\n\n```console\n$ cat /etc/os-release\n# paste output here\n$ uname -a\n```\n")
                result = self.details(body)
                self.assertFalse(result["has_reproduction_clues"])
                self.assertIn("Reproduction steps or minimal SQL", result["missing"])

    def test_code_only_description_is_not_reported_as_empty(self):
        body = ("### What happened?\n\n```text\nERROR: undefined reference to symbol\n```\n\n"
                "### Database version\n\nmaster\n\nAI model: not used")
        self.assertNotIn("Issue description", self.details(body)["missing"])

    def test_comment_lines_in_fenced_scripts_are_not_form_headings(self):
        body = "IvorySQL master\nAI model: not used\n\n```bash\n# OS version\nmeson setup build\n```"
        self.assertTrue(self.details(body)["has_reproduction_clues"])


if __name__ == "__main__":
    unittest.main()
