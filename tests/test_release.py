"""Release inputs stay data, and image plans select explicit archive identities."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts/release.py")
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)

ENV = {
    "RELEASE_TAG": "v3.29.0", "BUILD_PRODUCTION": "true", "BUILD_TEST": "false",
    "DO_PUBLISH": "false", "IS_LATEST": "false", "UBI_BASE": "redhat/ubi9:9.8",
    "ALPINE_BASE": "alpine:3.23.4", "SC_CLIENT_VERSIONS": "26.2", "SERVERCORE_VERSIONS": "ltsc2022,ltsc2025",
}
METADATA = {"tag_name": "v3.29.0", "draft": False, "assets": [
    {"name": "fcli-linux.tgz", "digest": "sha256:" + "a" * 64},
    {"name": "fcli-windows.zip", "digest": "sha256:" + "b" * 64},
]}


class ReleaseTests(unittest.TestCase):
    def test_invalid_inputs_fail_before_network_or_command_execution(self):
        cases = [(key, '$(echo injected)') for key in ENV]
        cases += [("RELEASE_TAG", "v3.29.0\ninjected"), ("RELEASE_TAG", "../v3.29.0"),
                  ("SC_CLIENT_VERSIONS", "26.2;exit"), ("SERVERCORE_VERSIONS", "ltsc2019"),
                  ("UBI_BASE", "image --build-arg X=Y"), ("DO_PUBLISH", "yes")]
        for name, value in cases:
            with self.subTest(name=name, value=value), patch.dict('os.environ', {**ENV, name: value}, clear=True), \
                    patch.object(RELEASE.subprocess, 'check_output') as command:
                with self.assertRaises(ValueError):
                    RELEASE.main()
                command.assert_not_called()

    def test_stable_tags_keep_major_minor_and_optional_latest(self):
        self.assertEqual(['repo:3.29.0-ubi9-20261104000000', 'repo:3.29.0-ubi9',
                          'repo:3.29-ubi9', 'repo:3-ubi9', 'repo:latest-ubi9'],
                         RELEASE.image_tags('repo', '3.29.0', '-ubi9', '20261104000000', True))

    def test_development_and_prerelease_tags_do_not_update_stable_aliases(self):
        for tag in ('dev_v3', '3.29.0-rc.1'):
            self.assertEqual(['repo:' + tag], RELEASE.image_tags('repo', tag, '', 'timestamp', True))
        with self.assertRaises(ValueError):
            RELEASE.validate_inputs({**ENV, 'RELEASE_TAG': 'dev_v3', 'IS_LATEST': 'true'})

    def test_missing_duplicate_and_invalid_asset_digests_fail_closed(self):
        for digest in (None, '', 'sha256:bad', 'md5:' + 'a' * 32):
            metadata = copy.deepcopy(METADATA)
            metadata['assets'][0]['digest'] = digest
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                RELEASE.build_plan(RELEASE.validate_inputs(ENV), metadata)
        for assets in ([], [METADATA['assets'][0], METADATA['assets'][0]]):
            with self.assertRaises(ValueError):
                RELEASE.archive_digest({'assets': assets}, 'fcli-linux.tgz')

    def test_asset_replacement_changes_build_identity_without_release_date_change(self):
        inputs = RELEASE.validate_inputs(ENV)
        before = RELEASE.build_plan(inputs, METADATA)
        updated = copy.deepcopy(METADATA)
        updated['assets'][0]['digest'] = 'sha256:' + 'c' * 64
        after = RELEASE.build_plan(inputs, updated)
        self.assertNotEqual(before['linux_sha256'], after['linux_sha256'])

    def test_existing_sc_versions_are_merged_and_bootstrap_uses_latest_two(self):
        inputs = RELEASE.validate_inputs(ENV)
        self.assertEqual(['25.4', '26.2'], RELEASE.sc_versions(inputs, ['3.29.0-ubi9-sc25.4'], ''))
        inputs['sc_versions'] = []
        self.assertEqual(['26.1', '26.2'], RELEASE.sc_versions(inputs, [],
            '  - version: 25.4.1\n  - version: 26.1.0\n  - version: 26.2.3\n'))
        with self.assertRaises(ValueError):
            RELEASE.sc_versions(inputs, [], '')

    def test_windows_only_resolves_supported_hosted_runners_and_its_digest(self):
        inputs = RELEASE.validate_inputs({**ENV, 'BUILD_TEST': 'true', 'BUILD_PRODUCTION': 'false'})
        plan = RELEASE.build_plan(inputs, METADATA)
        self.assertEqual(['alpine'], [v['name'] for v in plan['linux_matrix']['include']])
        self.assertTrue(all(not v['publish'] for v in plan['linux_matrix']['include']))
        self.assertEqual('b' * 64, plan['windows_sha256'])
        self.assertEqual(['windows-2022', 'windows-2025'],
                         [v['runner'] for v in plan['windows_matrix']['include']])

    def test_refresh_existing_versions_does_not_depend_on_tool_definition_service(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict('os.environ', {**ENV, 'SC_CLIENT_VERSIONS': '',
                           'GITHUB_OUTPUT': str(Path(directory) / 'outputs')}, clear=True), \
                patch.object(RELEASE, 'fetch', return_value=json.dumps(METADATA)) as fetch, \
                patch.object(RELEASE.subprocess, 'check_output',
                             return_value=json.dumps({'Tags': ['3.29.0-ubi9-sc25.4']})), \
                patch('builtins.print'):
            RELEASE.main()
            fetch.assert_called_once_with('https://api.github.com/repos/fortify/fcli/releases/tags/v3.29.0')

    def test_workflow_never_interpolates_expressions_into_shell_code(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/docker.yml').read_text())
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                self.assertNotIn('${{', step.get('run', ''), step.get('name'))

    def test_only_promotion_job_can_publish_after_all_requested_checks(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/docker.yml').read_text())['jobs']
        publish = jobs['publish']
        self.assertEqual({'plan', 'docker-linux', 'docker-windows'}, set(publish['needs']))
        self.assertIn("needs.docker-linux.result == 'success'", publish['if'])
        self.assertIn("!inputs.buildTest || needs.docker-windows.result == 'success'", publish['if'])
        self.assertIn('inputs.doPublish', publish['if'])
        build = next(step for step in jobs['docker-linux']['steps'] if step.get('name') == 'Build image')
        self.assertIs(False, build['with']['push'])
        self.assertIn('type=oci', build['with']['outputs'])
        for name, job in jobs.items():
            if name != 'publish':
                self.assertNotIn('secrets.DOCKER_', json.dumps(job))
        self.assertNotIn('build-push-action', json.dumps(publish))
        promote = next(step['run'] for step in publish['steps'] if step.get('name') == 'Promote the original OCI artifact')
        self.assertIn('--all --preserve-digests', promote)
        self.assertIn('oci-archive:artifact/image.oci.tar', promote)

    def test_download_layer_consumes_digest_before_fetching_archive(self):
        linux = (ROOT / 'linux/Dockerfile').read_text()
        download = next(run for run in linux.split('\nRUN ') if 'curl -fsSL "$DOWNLOAD_URL"' in run)
        self.assertIn('${FCLI_SHA256}', download)
        self.assertIn('sha256sum -c -', download)
        windows = (ROOT / 'windows/Dockerfile').read_text()
        download = next(run for run in windows.split('\nRUN ') if 'Invoke-WebRequest -Uri $url' in run)
        self.assertIn('$env:FCLI_SHA256', download)
        self.assertIn('Get-FileHash', download)
