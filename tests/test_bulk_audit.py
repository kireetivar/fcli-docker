"""Offline runner contract tests. Python 3 + Bash/coreutils; no live credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("TEST_BASH") or ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))


def shell_path(path):
    value = Path(path).resolve().as_posix()
    if os.name == "nt":
        return "/" + value[0].lower() + value[2:]
    return value


STUB = r'''#!/usr/bin/env bash
set -eu
[[ $(ulimit -c) == 0 ]] || exit 98
printf '===CALL===\n' >> "$RECORDER"
printf '%s\n' "$@" >> "$RECORDER"
for name in FCLI_DATA_DIR FCLI_CONFIG_DIR FCLI_STATE_DIR FORTIFY_DATA_DIR FCLI_HOME; do
    [[ ! -v $name ]] || exit 93
done
[[ -d $FCLI_USER_HOME && $FCLI_USER_HOME == "$BULK_AUDIT_WORK_ROOT"/session.*/home ]] || exit 94
if [[ ${1:-} == --version ]]; then echo 'fcli test double'; exit 0; fi
if [[ "${1:-} ${2:-} ${3:-}" == 'ssc action help' ]]; then
    [[ ${MOCK_INCOMPATIBLE:-false} != true ]] || exit 2
    echo '--dry-run --max-audits --filter --add-aviator-tags'
    exit 0
fi
printf '10:11:38.600 [main] INFO FCLI -- mock %s diagnostic\n' "${1:-}" > "$FCLI_DEFAULT_LOG_FILE"
if [[ "${1:-} ${2:-} ${3:-}" == 'ssc session login' ]]; then
    [[ ${FCLI_DEFAULT_SSC_SESSION_LOGIN_TOKEN:-} == "${EXPECTED_SSC_TOKEN:-SSC_SENTINEL}" ]] || exit 91
    echo 'ssc session login output'
elif [[ -n ${FCLI_DEFAULT_SSC_SESSION_LOGIN_TOKEN:-} ]]; then
    exit 92
fi
if [[ "${1:-} ${2:-} ${3:-}" == "${MOCK_FAIL_COMMAND:-none}" ]]; then
    echo 'mock login failure detail' >&2
    exit 23
fi
if [[ "${1:-} ${2:-} ${3:-}" == 'aviator session login' ]]; then
    token_file=
    for arg in "$@"; do
        [[ $arg == file:* ]] && token_file=${arg#file:}
    done
    [[ -n $token_file && -f $token_file ]] || exit 97
    # Command substitution would hide trailing LF and miss the original bug.
    printf '%s' "${EXPECTED_AVIATOR_TOKEN:-AVIATOR_SENTINEL}" | cmp -s - "$token_file" || exit 96
    echo 'aviator session login output'
fi
if [[ "${1:-} ${2:-} ${3:-}" == 'ssc action run' ]]; then
    printf 'mock file diagnostic\n' >> "$FCLI_DEFAULT_LOG_FILE"
    printf '%s\n' "$FCLI_USER_HOME" > "$STATE_RECORD"
    if [[ ${MOCK_WAIT:-false} == true ]]; then
        trap 'echo terminated > "$TERMINATED"; exit 143' TERM INT
        touch "$READY"
        while true; do sleep 0.1; done
    fi
    echo '[INFO] mock audit output'
    exit "${MOCK_AUDIT_EXIT:-0}"
fi
echo 'aviator admin output'
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bulk-audit-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for folder in ("bin", "work", "tmp", "secrets", "logs"):
            (self.base / folder).mkdir()
        stub = self.base / "bin/fcli"
        stub.write_text(STUB, newline="\n")
        stub.chmod(0o755)
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith(("FCLI_", "BULK_AUDIT_", "SSC_", "AVIATOR_")):
                self.env.pop(key)
        self.env.update({
            "SSC_URL": "https://ssc.example.test/ssc", "AVIATOR_URL": "https://aviator.example.test",
            "AVIATOR_TENANT": "test", "BULK_AUDIT_FILTER": 'Application:"test app"',
            "BULK_AUDIT_WORK_ROOT": shell_path(self.base / "work"),
            "BULK_AUDIT_LOG_DIR": shell_path(self.base / "logs"),
            "TMPDIR": shell_path(self.base / "tmp"), "BULK_AUDIT_TIMEOUT_SECONDS": "20",
            "RECORDER": shell_path(self.base / "calls"), "STATE_RECORD": shell_path(self.base / "state"),
            "TERMINATED": shell_path(self.base / "terminated"), "READY": shell_path(self.base / "ready"),
            "FCLI_STATE_DIR": "/inherited", "FCLI_CONFIG_DIR": "/inherited",
            "FCLI_DATA_DIR": "/inherited", "FORTIFY_DATA_DIR": "/inherited", "FCLI_HOME": "/inherited",
            "FCLI_DEFAULT_SSC_SESSION_LOGIN_TOKEN": "inherited",
        })
        for name, filename, value in (
            ("SSC_TOKEN_FILE", "ssc", "SSC_SENTINEL\r\n"),
            ("AVIATOR_TOKEN_FILE", "aviator", "AVIATOR_SENTINEL\n"),
            ("AVIATOR_PRIVATE_KEY_FILE", "admin", "PRIVATE_KEY_SENTINEL\n"),
        ):
            path = self.base / "secrets" / filename
            path.write_bytes(value.encode())
            self.env[name] = shell_path(path)

    def command(self, *args):
        return [BASH, "-c", 'export PATH="$1:$PATH"; shift; exec bash "$@"', "test",
                shell_path(self.base / "bin"), shell_path(ROOT / "linux/bulk-audit.sh"), *args]

    def run_runner(self, *args, **updates):
        result = subprocess.run(self.command(*args), env={**self.env, **updates},
                                capture_output=True, text=True, timeout=35)
        diagnostics = ''.join(path.read_text() for path in (self.base / 'logs').glob('*/*.log'))
        for secret in ("SSC_SENTINEL", "AVIATOR_SENTINEL", "PRIVATE_KEY_SENTINEL",
                       "ROTATED_SSC_TOKEN", "ROTATED_AVIATOR_TOKEN"):
            self.assertNotIn(secret, result.stdout + result.stderr + diagnostics + self.calls())
        self.assertEqual([], list((self.base / "work").iterdir()), result.stderr)
        self.assertEqual([], list((self.base / "tmp").iterdir()), result.stderr)
        return result

    def calls(self):
        path = self.base / "calls"
        return path.read_text() if path.exists() else ""

    def test_default_sast_dry_run_and_secret_isolation(self):
        result = self.run_runner()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('--dry-run=true\n', self.calls())
        self.assertIn('--max-audits=1\n', self.calls())
        self.assertIn('--add-aviator-tags\n', self.calls())
        self.assertIn('ssc session login output', result.stdout)
        self.assertIn('aviator session login output', result.stdout)
        self.assertIn('aviator admin output', result.stdout)
        self.assertIn('mock audit output', result.stdout)
        self.assertNotIn('mock file diagnostic', result.stdout + result.stderr)
        self.assertNotIn('INFO FCLI', result.stdout + result.stderr)
        run_dirs = list((self.base / "logs").iterdir())
        self.assertEqual(1, len(run_dirs))
        self.assertEqual({'ssc_login.log', 'aviator_login.log', 'aviator_admin.log', 'audit.log'},
                         {path.name for path in run_dirs[0].iterdir()})
        self.assertIn('mock file diagnostic', (run_dirs[0] / 'audit.log').read_text())
        self.assertIn('mock ssc diagnostic', (run_dirs[0] / 'ssc_login.log').read_text())
        self.assertIn(shell_path(run_dirs[0]), result.stderr)
        self.assertIn('process_exit_does_not_guarantee_all_audits_succeeded', result.stderr)
        self.assertNotIn('\n-k\n', self.calls())

    def test_lifecycle_events_have_stable_fields_for_log_collectors(self):
        result = self.run_runner(MOCK_AUDIT_EXIT='17')
        events = [json.loads(line) for line in result.stderr.splitlines() if line.startswith('{')]
        self.assertTrue(events)
        run_dirs = {path.name for path in (self.base / 'logs').iterdir()}
        self.assertEqual(1, len(run_dirs))
        self.assertEqual(run_dirs, {event['run_id'] for event in events})
        for event in events:
            self.assertEqual(1, event['schema_version'])
            self.assertIsInstance(event['elapsed_seconds'], int)
            self.assertGreaterEqual(event['elapsed_seconds'], 0)
        phases = [event['phase'] for event in events if event['event'] == 'phase_started']
        self.assertEqual(['ssc_login', 'aviator_login', 'aviator_admin', 'audit'], phases)
        failure = next(event for event in events if event['event'] == 'command_failed')
        self.assertEqual(17, failure['exit_code'])
        self.assertEqual('finished', events[-1]['event'])
        self.assertEqual(17, events[-1]['exit_code'])

    def test_each_run_reads_current_provider_files(self):
        self.assertEqual(0, self.run_runner().returncode)
        (self.base / 'secrets/ssc').write_bytes(b'ROTATED_SSC_TOKEN\r\n')
        (self.base / 'secrets/aviator').write_bytes(b'ROTATED_AVIATOR_TOKEN\n')
        result = self.run_runner(EXPECTED_SSC_TOKEN='ROTATED_SSC_TOKEN',
                                 EXPECTED_AVIATOR_TOKEN='ROTATED_AVIATOR_TOKEN')
        self.assertEqual(0, result.returncode, result.stderr)

    def test_aviator_token_normalizes_lf_and_crlf_without_changing_sources(self):
        token = self.base / "secrets/aviator"
        admin = self.base / "secrets/admin"
        original_admin = admin.read_bytes()
        for contents in (b"AVIATOR_SENTINEL", b"AVIATOR_SENTINEL\n",
                         b"AVIATOR_SENTINEL\r\n", b"AVIATOR_SENTINEL\r\n\r\n"):
            with self.subTest(contents=contents):
                (self.base / "calls").write_text("")
                token.write_bytes(contents)
                result = self.run_runner()
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(contents, token.read_bytes())
                self.assertEqual(original_admin, admin.read_bytes())
                self.assertIn('file:' + shell_path(admin) + '\n', self.calls())

    def test_logs_are_retained_separately_across_runs(self):
        for _ in range(2):
            result = self.run_runner()
            self.assertEqual(0, result.returncode, result.stderr)
        run_dirs = list((self.base / "logs").iterdir())
        self.assertEqual(2, len(run_dirs))
        for directory in run_dirs:
            self.assertEqual(1, (directory / 'audit.log').read_text().count('mock file diagnostic'))

    def test_invalid_log_directory_does_not_authenticate(self):
        for directory in ('relative/path', shell_path(self.base / 'missing')):
            result = self.run_runner(BULK_AUDIT_LOG_DIR=directory)
            self.assertEqual(64, result.returncode, result.stderr)
            self.assertIn('log_directory_not_writable', result.stderr)
            self.assertEqual('', self.calls())

    def test_ssc_insecure_only_applies_to_ssc_login(self):
        for value in ("true", "false"):
            with self.subTest(ssc_insecure=value):
                (self.base / "calls").write_text("")
                result = self.run_runner(SSC_INSECURE=value)
                self.assertEqual(0, result.returncode, result.stderr)
                calls = self.calls().split('===CALL===\n')[1:]
                ssc_login = next(call for call in calls if call.startswith('ssc\nsession\nlogin\n'))
                self.assertEqual(value == "true", '\n-k\n' in ssc_login)
                for call in calls:
                    if call != ssc_login:
                        self.assertNotIn('\n-k\n', call)
                self.assertIn('ssc_insecure=' + value, result.stderr)

    def test_dast_and_alias(self):
        for action in ("bulkaudit-dast", "bulkaudit"):
            with self.subTest(action=action):
                (self.base / "calls").write_text("")
                result = self.run_runner(BULK_AUDIT_ACTION=action, BULK_AUDIT_DRY_RUN="false")
                self.assertEqual(0, result.returncode, result.stderr)
                calls = self.calls()
                self.assertIn('ssc\naction\nrun\n' + action + '\n', calls)
                self.assertIn('--dry-run=false\n', calls)
                self.assertEqual(action != "bulkaudit-dast", '--add-aviator-tags\n' in calls)

    def test_configuration_is_not_shell_code(self):
        value = 'Application:"a b"; $(touch SHOULD_NOT_EXIST) `echo injected`'
        result = self.run_runner(BULK_AUDIT_FILTER=value)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('--filter=' + value + '\n', self.calls())
        self.assertNotIn('injected\n', result.stdout)

    def test_tenant_cannot_expand_argument_files_or_options(self):
        for tenant in ('@' + self.env['SSC_TOKEN_FILE'], '--help', 'tenant with spaces'):
            with self.subTest(tenant=tenant):
                (self.base / 'calls').write_text('')
                result = self.run_runner(AVIATOR_TENANT=tenant)
                self.assertEqual(0, result.returncode, result.stderr)
                calls = self.calls()
                self.assertIn('--tenant=' + tenant + '\n', calls)
                self.assertNotIn('\n' + tenant + '\n', calls)
                self.assertEqual(1, calls.count('ssc\naction\nrun\n'))

    def test_missing_empty_and_whitespace_filters_are_optional(self):
        self.env.pop("BULK_AUDIT_FILTER")
        for value in (None, "", " \t\r\n"):
            with self.subTest(filter=value):
                (self.base / "calls").write_text("")
                settings = {} if value is None else {"BULK_AUDIT_FILTER": value}
                result = self.run_runner(BULK_AUDIT_EXCLUDE_FILTER="Languages:c#", **settings)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn('--filter=', self.calls())
                self.assertIn('--exclude-filter=Languages:c#\n', self.calls())

    def test_missing_and_empty_secrets_do_not_authenticate(self):
        for name in ('ssc', 'aviator', 'admin'):
            path = self.base / 'secrets' / name
            original = path.read_bytes()
            for contents in (None, b''):
                with self.subTest(secret=name, contents=contents):
                    if contents is None:
                        path.unlink()
                    else:
                        path.write_bytes(contents)
                    result = self.run_runner()
                    self.assertEqual(64, result.returncode, result.stderr)
                    self.assertEqual('', self.calls())
                    path.write_bytes(original)

    def test_scalar_tokens_reject_whitespace_and_embedded_line_breaks(self):
        for name in ('ssc', 'aviator'):
            path = self.base / 'secrets' / name
            original = path.read_bytes()
            for contents in (b'\r\n\r\n', b'  \t', b'part1\npart2', b'part1\rpart2'):
                with self.subTest(secret=name, contents=contents):
                    path.write_bytes(contents)
                    result = self.run_runner()
                    self.assertEqual(64, result.returncode, result.stderr)
                    self.assertEqual('', self.calls())
                    path.write_bytes(original)

    def test_invalid_configuration_does_not_authenticate(self):
        for settings in ({"BULK_AUDIT_ACTION": "arbitrary"}, {"BULK_AUDIT_MAX_AUDITS": "-1"},
                         {"BULK_AUDIT_DRY_RUN": "yes"}, {"BULK_AUDIT_FILTER": "CHANGE_ME"},
                         {"SSC_INSECURE": "yes"}, {"SSC_INSECURE": "true; echo injected"},
                         {"SSC_URL": "http://insecure"}, {"SSC_URL": "https://invalid host"},
                         {"AVIATOR_TENANT": "CHANGE_ME"}):
            with self.subTest(settings=settings):
                result = self.run_runner(**settings)
                self.assertEqual(64, result.returncode, result.stderr)
                self.assertEqual("", self.calls())

    def test_each_login_failure_stops_before_audit(self):
        for command in ("ssc session login", "aviator session login", "aviator admin-config create"):
            with self.subTest(command=command):
                (self.base / "calls").write_text("")
                result = self.run_runner(MOCK_FAIL_COMMAND=command)
                self.assertEqual(23, result.returncode, result.stderr)
                self.assertIn('mock login failure detail', result.stderr)
                self.assertNotIn('ssc\naction\nrun\n', self.calls())
                self.assertTrue(any((self.base / 'logs').glob('*/*.log')))

    def test_audit_exit_code_is_preserved_without_retry(self):
        result = self.run_runner(MOCK_AUDIT_EXIT="17")
        self.assertEqual(17, result.returncode, result.stderr)
        self.assertEqual(1, self.calls().count('ssc\naction\nrun\n'))

    def test_image_check_requires_no_credentials(self):
        result = self.run_runner('--check-image', SSC_TOKEN_FILE="/missing")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('image_compatible', result.stderr)
        self.assertNotIn('session\nlogin', self.calls())

    def test_incompatible_image_fails(self):
        result = self.run_runner('--check-image', MOCK_INCOMPATIBLE="true")
        self.assertEqual(69, result.returncode, result.stderr)

    def test_deadline_terminates_child_and_cleans_up(self):
        result = self.run_runner(MOCK_WAIT="true", BULK_AUDIT_TIMEOUT_SECONDS="2")
        self.assertEqual(124, result.returncode, result.stderr)
        self.assertTrue((self.base / "terminated").exists(), result.stderr)
        self.assertTrue(any((self.base / 'logs').glob('*/audit.log')))

    @unittest.skipIf(os.name == "nt", "POSIX signal delivery is verified on Linux CI")
    def test_sigterm_is_forwarded(self):
        proc = subprocess.Popen(self.command(), env={**self.env, "MOCK_WAIT": "true"},
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not (self.base / "ready").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.base / "ready").exists())
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=10)
            self.assertEqual(143, proc.returncode, stderr)
            self.assertTrue((self.base / "terminated").exists())
            self.assertEqual([], list((self.base / "work").iterdir()))
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()


if __name__ == "__main__":
    unittest.main()
