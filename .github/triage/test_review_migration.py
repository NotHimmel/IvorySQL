"""A label rename must not turn bot labels into permanent manual labels."""

import copy
import unittest

import triage
from test_submissions import COMPLETE_BUG, comment
from test_triage import FakeGitHub, issue


class ReviewMigrationTests(unittest.TestCase):
    def test_old_review_state_and_owned_label_are_recognized_after_repository_rename(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG.replace('environment: Yes', 'environment: No')))
        triage.analyze(github, 20, triage.load_config(), apply=True)
        current = triage.read_state(github.thread[0])
        old = copy.deepcopy(current)
        old['review_status'] = 'needs-review'
        old['managed'] = ['triage/needs-review' if name == 'triage/needs-reproduce' else name for name in old['managed']]
        github.thread[0]['body'] = github.thread[0]['body'].replace(triage.state_marker(current), triage.state_marker(old))
        github.thread.append(comment('Reproduced in a real environment: Yes'))
        result = triage.analyze(github, 20, triage.load_config(), apply=True)
        self.assertEqual(result['details']['review_status'], 'complete')
        self.assertNotIn('triage/needs-reproduce', github.current['labels'])
        self.assertNotIn('triage/needs-review', github.current['labels'])

    def test_pending_old_label_intent_keeps_ownership_after_server_side_rename(self):
        saved = {'managed': [], 'suppressed': [], 'review_status': 'needs-reproduce',
                 'pending': {'add': ['triage/needs-review'], 'remove': []}}
        recovered = triage.recover_state(saved, {'triage/needs-reproduce'})
        self.assertIn('triage/needs-reproduce', recovered['managed'])
        self.assertNotIn('pending', recovered)

    def test_manually_owned_renamed_label_still_requires_a_maintainer(self):
        github = FakeGitHub(issue(body=COMPLETE_BUG, labels=['triage/needs-reproduce']))
        result = triage.analyze(github, 20, triage.load_config(), apply=True)
        self.assertEqual(result['details']['review_status'], 'needs-reproduce')
        self.assertIn('triage/needs-reproduce', github.current['labels'])
        self.assertNotIn('triage/needs-reproduce', triage.read_state(github.thread[0])['managed'])
