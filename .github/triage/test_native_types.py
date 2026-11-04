"""Native types preserve human choices and survive interrupted migrations."""

import contextlib
import copy
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

import triage
from test_triage import FakeGitHub, issue
from test_submissions import COMPLETE_BUG


CATALOG = {name.casefold(): {"id": index, "name": name}
           for index, name in enumerate(("Bug", "Feature", "Enhancement", "Task"), 101)}
FEATURE = 'Description: Add a new psql summary command.\nAI usage: Not used'


class NativeGitHub(FakeGitHub):
    def __init__(self, current=None, catalog=None):
        super().__init__(current)
        self.catalog = copy.deepcopy(CATALOG if catalog is None else catalog)
        self.fail_when = None
        self.fail_after = False
        self.ignore_type = False

    def issue_types(self):
        return self.catalog

    def call(self, path, method="GET", data=None):
        failing = self.fail_when and self.fail_when(path, method, data)
        if failing:
            self.fail_when = None
            if not self.fail_after:
                raise triage.APIError(503)
        if method == 'PATCH' and path == self.root + '/issues/' + str(self.current['number']):
            self.writes.append((path, method, data))
            if not self.ignore_type:
                self.current['type'] = copy.deepcopy(self.catalog[data['type'].casefold()])
            result = copy.deepcopy(self.current)
        else:
            result = super().call(path, method, data)
        if failing:
            raise triage.APIError(503)
        return result


class NativeTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = triage.load_config()
        cls.ai = {'TRIAGE_AI_ENDPOINT': 'https://example.com/v1', 'TRIAGE_AI_MODEL': 'model', 'AI_API_KEY': 'key'}

    def run_triage(self, github, apply=True, **kwargs):
        return triage.analyze(github, 20, self.config, apply=apply, **kwargs)

    def state(self, github):
        return triage.read_state(triage.bot_comment(github.thread))

    def assert_no_type_labels(self, github):
        self.assertFalse(any(name.startswith('type/') or name in triage.LEGACY_TYPE_LABELS for name in github.current['labels']))

    def type_writes(self, github):
        return [data for path, method, data in github.writes if method == 'PATCH' and path.endswith('/issues/20')]

    def test_native_bug_is_written_without_a_redundant_type_label(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        result = self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Bug')
        self.assertEqual(result['issue_type']['backend'], 'native')
        self.assertTrue(self.state(github)['issue_type']['managed'])
        self.assert_no_type_labels(github)
        self.assertEqual(result['details']['missing'], [])

    def test_preview_plans_native_type_and_cleanup_without_writes(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG, labels=['type/bug']))
        result = self.run_triage(github, apply=False)
        self.assertEqual(result['issue_type']['after']['name'], 'Bug')
        self.assertIn('type/bug', result['labels']['remove'])
        self.assertEqual(github.writes, [])
        self.assertNotIn('type', github.current)

    def test_missing_capability_falls_back_to_labels(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG), catalog={})
        result = self.run_triage(github)
        self.assertEqual(result['issue_type']['backend'], 'labels')
        self.assertIn('type/bug', github.current['labels'])
        self.assertEqual(self.type_writes(github), [])

    def test_unconfigured_enhancement_falls_back_then_migrates_when_enabled(self):
        github = NativeGitHub(issue(title='Enhancement: improve psql completion', body=FEATURE),
                              catalog={key: value for key, value in CATALOG.items() if key != 'enhancement'})
        self.run_triage(github, automatic=True)
        self.assertIn('type/enhancement', github.current['labels'])
        github.catalog['enhancement'] = copy.deepcopy(CATALOG['enhancement'])
        self.run_triage(github, automatic=True)
        self.assertEqual(github.current['type']['name'], 'Enhancement')
        self.assertTrue(self.state(github)['issue_type']['managed'])
        self.assert_no_type_labels(github)

    def test_manual_native_bug_drives_information_checks_despite_feature_title(self):
        current = dict(issue(title='Feature request: new psql command', body=FEATURE), type=copy.deepcopy(CATALOG['bug']))
        github = NativeGitHub(current)
        result = self.run_triage(github)
        self.assertIn('Database version', result['details']['missing'])
        self.assertEqual(github.current['type']['name'], 'Bug')
        self.assertFalse(self.state(github)['issue_type']['managed'])
        self.assertEqual(self.type_writes(github), [])

    def test_manual_native_feature_overrides_old_bug_labels_and_bug_title(self):
        current = dict(issue(title='Bug: psql crashes', body=FEATURE, labels=['bug', 'type/bug']), type=copy.deepcopy(CATALOG['feature']))
        github = NativeGitHub(current)
        result = self.run_triage(github)
        self.assertEqual(result['details']['missing'], [])
        self.assertEqual(github.current['type']['name'], 'Feature')
        self.assert_no_type_labels(github)

    def test_manual_native_type_is_not_overridden_by_ai(self):
        current = dict(issue(body=FEATURE), type=copy.deepcopy(CATALOG['feature']))
        github = NativeGitHub(current)
        with patch('triage.ask_ai', return_value=([{'label': 'type/bug', 'source': 'ai', 'evidence': 'psql'}], {})):
            self.run_triage(github, ai_env=self.ai)
        self.assertEqual(github.current['type']['name'], 'Feature')
        self.assertEqual(self.type_writes(github), [])

    def test_unknown_manual_native_type_is_preserved_and_routes_to_maintainers(self):
        current = dict(issue(body=FEATURE), type=copy.deepcopy(CATALOG['task']))
        github = NativeGitHub(current)
        result = self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Task')
        self.assertEqual(result['details']['review_status'], 'needs-reproduce')
        self.assertTrue(result['details']['classification_pending'])
        self.assertEqual(self.type_writes(github), [])

    def test_manual_type_label_migration_retains_manual_priority(self):
        for label in ('type/bug', 'bug'):
            with self.subTest(label=label):
                github = NativeGitHub(issue(body=COMPLETE_BUG, labels=[label]))
                self.run_triage(github)
                self.assertFalse(self.state(github)['issue_type']['managed'])
                github.current['title'] = 'Enhancement: improve psql completion'
                self.run_triage(github)
                self.assertEqual(github.current['type']['name'], 'Bug')
                self.assert_no_type_labels(github)

    def test_owned_native_type_can_follow_a_changed_report(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        github.current['title'] = 'Enhancement: improve psql completion'
        github.current['body'] = FEATURE
        result = self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Enhancement')
        self.assertTrue(self.state(github)['issue_type']['managed'])
        self.assertEqual(result['details']['missing'], [])
        self.assert_no_type_labels(github)

    def test_a_human_type_change_transfers_ownership_to_the_human(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        github.current['type'] = copy.deepcopy(CATALOG['feature'])
        self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Feature')
        self.assertFalse(self.state(github)['issue_type']['managed'])

    def test_a_human_clear_does_not_get_undone_or_replaced_with_a_type_label(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        github.current['type'] = None
        result = self.run_triage(github)
        self.assertIsNone(github.current['type'])
        self.assertTrue(self.state(github)['type_suppressed'])
        self.assertEqual(result['details']['review_status'], 'needs-reproduce')
        self.assert_no_type_labels(github)
        self.run_triage(github)
        self.assertIsNone(github.current['type'])

    def test_an_untyped_event_before_first_triage_respects_the_human_clear(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        github.type_event = {'number': 20, 'action': 'untyped', 'type': None}
        self.run_triage(github, automatic=True)
        self.assertIsNone(github.current.get('type'))
        self.assertTrue(self.state(github)['type_suppressed'])
        self.assert_no_type_labels(github)

    def test_a_human_typed_event_can_confirm_an_already_owned_value(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github, automatic=True)
        github.type_event = {'number': 20, 'action': 'typed', 'type': copy.deepcopy(CATALOG['bug'])}
        result = self.run_triage(github, automatic=True)
        self.assertNotIn('skipped', result)
        self.assertFalse(self.state(github)['issue_type']['managed'])

    def test_a_manual_type_is_not_replaced_by_a_recreated_catalog_entry_with_the_same_name(self):
        current = dict(issue(body=COMPLETE_BUG), type=copy.deepcopy(CATALOG['bug']))
        github = NativeGitHub(current)
        github.catalog['bug']['id'] = 999
        self.run_triage(github)
        self.assertEqual(github.current['type']['id'], CATALOG['bug']['id'])
        self.assertEqual(self.type_writes(github), [])

    def test_main_routes_a_human_untyped_event_into_type_suppression(self):
        from pathlib import Path
        import tempfile
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / 'event.json'
            event.write_text(json.dumps({'action': 'untyped', 'sender': {'type': 'User'},
                                         'issue': {'number': 20, 'type': None}}))
            env = {'GH_TOKEN': 'key', 'GITHUB_EVENT_NAME': 'issues', 'GITHUB_EVENT_PATH': str(event), 'AUTO_APPLY': 'true'}
            with patch.dict(os.environ, env, clear=True), patch.object(sys, 'argv', ['triage', '--repository', 'example/postgres']), \
                    patch('triage.GitHub', return_value=github), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(triage.main(), 0)
        self.assertIsNone(github.current.get('type'))
        self.assertTrue(self.state(github)['type_suppressed'])

    def test_failed_native_write_keeps_existing_labels_and_pending_intent(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG, labels=['type/bug']))
        github.fail_when = lambda path, method, data: method == 'PATCH' and path.endswith('/issues/20')
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertIn('type/bug', github.current['labels'])
        self.assertIn('issue_type', self.state(github)['pending'])
        self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Bug')
        self.assertFalse(self.state(github)['issue_type']['managed'])
        self.assert_no_type_labels(github)

    def test_silently_ignored_write_is_detected_before_label_cleanup(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG, labels=['type/bug']))
        github.ignore_type = True
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            self.run_triage(github)
        self.assertIn('type/bug', github.current['labels'])
        self.assertIn('pending', self.state(github))

    def test_lost_native_write_response_recovers_ownership(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        github.fail_when = lambda path, method, data: method == 'PATCH' and path.endswith('/issues/20')
        github.fail_after = True
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Bug')
        self.run_triage(github)
        self.assertTrue(self.state(github)['issue_type']['managed'])
        self.assertEqual(len(self.type_writes(github)), 1)
        self.assertNotIn('pending', self.state(github))

    def test_partial_migration_cleanup_failure_preserves_manual_priority(self):
        for after in (False, True):
            with self.subTest(after=after):
                github = NativeGitHub(issue(body=COMPLETE_BUG, labels=['type/bug']))
                github.fail_when = lambda path, method, data: method == 'DELETE' and path.endswith('/labels/type%2Fbug')
                github.fail_after = after
                with self.assertRaises(triage.APIError):
                    self.run_triage(github)
                self.run_triage(github)
                self.assertFalse(self.state(github)['issue_type']['managed'])
                self.assert_no_type_labels(github)
                self.assertNotIn('pending', self.state(github))

    def test_a_human_type_change_during_recovery_is_preserved(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG, labels=['type/bug']))
        github.fail_when = lambda path, method, data: method == 'DELETE'
        with self.assertRaises(triage.APIError):
            self.run_triage(github)
        github.current['type'] = copy.deepcopy(CATALOG['feature'])
        self.run_triage(github)
        self.assertEqual(github.current['type']['name'], 'Feature')
        self.assertFalse(self.state(github)['issue_type']['managed'])

    def test_type_changes_during_analysis_reject_a_stale_write(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        def change(*args):
            github.current['type'] = copy.deepcopy(CATALOG['feature'])
            return [], {}
        with patch('triage.ask_ai', side_effect=change), self.assertRaisesRegex(RuntimeError, 'Issue changed'):
            self.run_triage(github, ai_env=self.ai)
        self.assertEqual(github.writes, [])

    def test_unavailable_target_does_not_contradict_an_existing_native_type(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG))
        self.run_triage(github)
        del github.catalog['enhancement']
        github.current['title'] = 'Enhancement: improve psql completion'
        with patch('triage.ask_ai', return_value=([{'label': 'type/enhancement', 'source': 'ai', 'evidence': 'psql'}], {})):
            result = self.run_triage(github, ai_env=self.ai)
        self.assertEqual(github.current['type']['name'], 'Bug')
        self.assertNotIn('type/enhancement', github.current['labels'])
        self.assertEqual(result['details']['review_status'], 'needs-reproduce')

    def test_manual_removal_of_an_old_bot_type_label_is_not_bypassed_by_native_types(self):
        github = NativeGitHub(issue(body=COMPLETE_BUG), catalog={})
        self.run_triage(github)
        github.current['labels'].remove('type/bug')
        github.catalog = copy.deepcopy(CATALOG)
        self.run_triage(github)
        self.assertIsNone(github.current.get('type'))
        self.assert_no_type_labels(github)

    def test_sync_labels_only_creates_fallback_types_missing_from_the_catalog(self):
        github = NativeGitHub(catalog={key: value for key, value in CATALOG.items() if key != 'enhancement'})
        with patch.dict(os.environ, {'GH_TOKEN': 'key'}, clear=True), patch.object(sys, 'argv',
                ['triage', '--repository', 'example/postgres', '--sync-labels', '--apply']), \
                patch('triage.GitHub', return_value=github), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(triage.main(), 0)
        self.assertIn('type/enhancement', github.created)
        self.assertNotIn('type/bug', github.created)
        self.assertNotIn('type/feature', github.created)


class TypeDiscoveryAndValidationTests(unittest.TestCase):
    def test_repository_catalog_is_cached_and_disabled_types_are_excluded(self):
        github = triage.GitHub('example/postgres', 'key')
        with patch.object(github, 'call', return_value=[CATALOG['bug'], dict(CATALOG['feature'], is_enabled=False)]) as call:
            self.assertEqual(github.issue_types(), {'bug': CATALOG['bug']})
            self.assertEqual(github.issue_types(), {'bug': CATALOG['bug']})
        call.assert_called_once_with('/repos/example/postgres/issue-types')

    def test_unavailable_catalog_falls_back_but_rate_limits_propagate(self):
        for status in (403, 404, 503):
            github = triage.GitHub('example/postgres', 'key')
            with patch.object(github, 'call', side_effect=triage.APIError(status)):
                self.assertEqual(github.issue_types(), {})
                self.assertTrue(github.type_notes)
        github = triage.GitHub('example/postgres', 'key')
        with patch.object(github, 'call', side_effect=triage.RateLimitError(1800000000)):
            with self.assertRaises(triage.RateLimitError):
                github.issue_types()

    def test_ai_type_field_is_validated_by_name_score_and_original_evidence(self):
        config = triage.load_config()
        for name, confidence, evidence, expected in [('bug', .99, 'logical replication', True),
                ('bug', .5, 'logical replication', False), ('question', 1, 'logical replication', False),
                ('bug', .99, 'fabricated evidence', False)]:
            with self.subTest(name=name, confidence=confidence, evidence=evidence):
                labels, _ = triage.validate_ai({'type': {'name': name, 'confidence': confidence, 'evidence': evidence}},
                                              issue(), '', [], config)
                self.assertEqual(bool(labels), expected)

    def test_ai_type_validation_uses_the_native_mapping_independently_of_fallback_labels(self):
        config = copy.deepcopy(triage.load_config())
        config['labels'] = {key: value for key, value in config['labels'].items() if not key.startswith('type/')}
        labels, _ = triage.validate_ai({'type': {'name': 'bug', 'confidence': .99, 'evidence': 'logical replication'}},
                                      issue(), '', [], config)
        self.assertEqual(labels[0]['label'], 'type/bug')

    def test_ai_payload_separates_the_type_field_from_area_labels(self):
        config = triage.load_config()
        with patch('triage.request_json', return_value={'choices': [{'message': {'content': '{"type": null, "labels": [], "similar": []}'}}]}) as request:
            triage.ask_ai(issue(), '', [], config, 'https://example.com/v1', 'model', 'key')
        prompt = request.call_args.args[3]['messages'][0]['content']
        self.assertIn('"type":', prompt)
        self.assertIn('"labels":', prompt)
        self.assertNotIn('type/bug', prompt)

    def test_malformed_type_ownership_cannot_claim_a_manual_type(self):
        for record in ({'value': {'id': True, 'name': 'Bug'}, 'managed': True},
                       {'value': CATALOG['bug'], 'managed': 'true'}):
            state = {'managed': [], 'suppressed': [], 'issue_type': record}
            self.assertEqual(triage.read_state({'body': triage.state_marker(state)}), {'managed': [], 'suppressed': []})
