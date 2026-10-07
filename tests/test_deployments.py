"""Render real Helm templates and validate deployment security/configuration."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/fcli-bulk-audit"


@unittest.skipUnless(shutil.which("helm"), "Helm is required for template checks")
class HelmTests(unittest.TestCase):
    def render(self, *options, success=True):
        result = subprocess.run(["helm", "template", "poc", str(CHART), *options], capture_output=True, text=True)
        if not success:
            self.assertNotEqual(0, result.returncode, result.stdout)
            return result
        self.assertEqual(0, result.returncode, result.stderr)
        return list(yaml.safe_load_all(result.stdout))[0]

    def test_job_security_and_safe_defaults(self):
        doc = self.render()
        self.assertEqual("Job", doc["kind"])
        self.assertEqual(0, doc["spec"]["backoffLimit"])
        pod = doc["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual("Never", pod["restartPolicy"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        container = pod["containers"][0]
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        env = {item["name"]: item["value"] for item in container["env"]}
        self.assertEqual("true", env["BULK_AUDIT_DRY_RUN"])
        self.assertEqual("1", env["BULK_AUDIT_MAX_AUDITS"])
        self.assertEqual("", env["BULK_AUDIT_FILTER"])
        self.assertEqual("false", env["SSC_INSECURE"])
        self.assertNotIn("SSC_TOKEN", env)
        volumes = {item['name']: item for item in pod['volumes']}
        self.assertEqual("Memory", volumes['sessions']["emptyDir"]["medium"])
        self.assertEqual(0o440, volumes['credentials']["secret"]["defaultMode"])
        self.assertEqual('128Mi', volumes['audit-logs']['emptyDir']['sizeLimit'])
        self.assertIn({'name': 'audit-logs', 'mountPath': '/logs'}, container['volumeMounts'])

    def test_persistent_diagnostic_logs(self):
        doc = self.render('--set', 'storage.existingLogClaim=audit-history')
        volumes = {item['name']: item for item in doc['spec']['template']['spec']['volumes']}
        volume = volumes['audit-logs']
        self.assertEqual({'claimName': 'audit-history'}, volume['persistentVolumeClaim'])
        self.assertNotIn('emptyDir', volume)

    def test_cronjob_is_suspended_and_forbids_overlap(self):
        doc = self.render("--set", "schedule.enabled=true")
        self.assertEqual("CronJob", doc["kind"])
        self.assertTrue(doc["spec"]["suspend"])
        self.assertEqual("Forbid", doc["spec"]["concurrencyPolicy"])
        self.assertEqual(0, doc["spec"]["jobTemplate"]["spec"]["backoffLimit"])

    def test_truststore_and_digest(self):
        digest = "sha256:" + "a" * 64
        doc = self.render("--set", "truststore.existingSecret=company-ca", "--set", "image.digest=" + digest)
        pod = doc["spec"]["template"]["spec"]
        volumes = {item['name']: item for item in pod['volumes']}
        self.assertEqual("company-ca", volumes['truststore']["secret"]["secretName"])
        self.assertTrue(pod["containers"][0]["image"].endswith("@" + digest))

    def test_deadline_follows_timeout_for_jobs_and_schedules(self):
        for scheduled in ('false', 'true'):
            with self.subTest(scheduled=scheduled):
                doc = self.render('--set', 'schedule.enabled=' + scheduled,
                                  '--set', 'audit.timeoutSeconds=7200',
                                  '--set', 'job.terminationGracePeriodSeconds=90')
                job = doc['spec']['jobTemplate']['spec'] if scheduled == 'true' else doc['spec']
                self.assertEqual(7305, job['activeDeadlineSeconds'])
                self.assertEqual(90, job['template']['spec']['terminationGracePeriodSeconds'])

    def test_external_provider_matches_the_mounted_secret_contract(self):
        example = ROOT / 'deploy/kubernetes/external-secrets-aws.yaml'
        store, external = list(yaml.safe_load_all(example.read_text()))
        secret_name = external['spec']['target']['name']
        doc = self.render('--set', 'existingSecret=' + secret_name)
        pod = doc['spec']['template']['spec']
        volumes = {item['name']: item for item in pod['volumes']}
        secret = volumes['credentials']['secret']
        self.assertEqual(secret_name, secret['secretName'])
        self.assertEqual({item['key'] for item in secret['items']},
                         {item['secretKey'] for item in external['spec']['data']})
        self.assertEqual(store['metadata']['name'], external['spec']['secretStoreRef']['name'])
        self.assertEqual('SecretsManager', store['spec']['provider']['aws']['service'])
        self.assertNotIn('auth', store['spec']['provider']['aws'])
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertTrue(all('remoteRef' in item for item in external['spec']['data']))

    def test_invalid_values_rejected(self):
        for setting in ("audit.action=arbitrary", "audit.maxAudits=0", "audit.sscUrl=http://insecure",
                        "audit.sscInsecure=yes", "job.activeDeadlineSeconds=100", "image.digest=bad", "unknown=value"):
            with self.subTest(setting=setting):
                self.render("--set", setting, success=False)

    def test_optional_filter(self):
        for setting, expected in (("audit.filter=", ""), ("audit.filter=null", ""),
                                  ("audit.filter=Languages:java", "Languages:java")):
            with self.subTest(setting=setting):
                doc = self.render("--set", setting)
                container = doc["spec"]["template"]["spec"]["containers"][0]
                env = {item["name"]: item["value"] for item in container["env"]}
                self.assertEqual(expected, env["BULK_AUDIT_FILTER"])

    def test_ssc_insecure_opt_in(self):
        doc = self.render("--set", "audit.sscInsecure=true")
        container = doc["spec"]["template"]["spec"]["containers"][0]
        env = {item["name"]: item["value"] for item in container["env"]}
        self.assertEqual("true", env["SSC_INSECURE"])
        self.assertNotIn("AVIATOR_INSECURE", env)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for configuration checks")
class ComposeTests(unittest.TestCase):
    def render(self, *overrides, **settings):
        compose = ROOT / 'deploy/compose'
        prefixes = ('BULK_AUDIT_', 'FCLI_', 'SSC_', 'AVIATOR_', 'AWS_', 'CLOUDWATCH_', 'COMPOSE_')
        env = {key: value for key, value in os.environ.items() if not key.startswith(prefixes)}
        env.update(settings)
        command = ['docker', 'compose', '--env-file', str(compose / '.env.example'),
                   '-f', str(compose / 'compose.yaml')]
        for override in overrides:
            command.extend(['-f', str(compose / override)])
        result = subprocess.run(command + ['config', '--format', 'json'],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_runtime_defaults_and_secret_files(self):
        doc = self.render()
        service = doc['services']['bulk-audit']
        self.assertTrue(service['read_only'])
        self.assertEqual('no', service['restart'])
        self.assertEqual('10001:10001', service['user'])
        self.assertEqual(['ALL'], service['cap_drop'])
        self.assertEqual('true', service['environment']['BULK_AUDIT_DRY_RUN'])
        self.assertEqual('1', service['environment']['BULK_AUDIT_MAX_AUDITS'])
        self.assertEqual('false', service['environment']['SSC_INSECURE'])
        self.assertEqual('', service['environment']['BULK_AUDIT_FILTER'])
        self.assertNotIn('SSC_TOKEN', service['environment'])
        self.assertEqual({'ssc-token', 'aviator-token', 'aviator-private-key'}, set(doc['secrets']))
        self.assertTrue(all('size=' in mount for mount in service['tmpfs']))
        self.assertEqual('local', service['logging']['driver'])
        self.assertTrue(any(mount['target'] == '/logs' for mount in service['volumes']))
        defaults = dict(line.split('=', 1) for line in (ROOT / 'deploy/compose/.env.example').read_text().splitlines()
                        if line and not line.startswith('#'))
        self.assertEqual(defaults['FCLI_VERSION'], service['build']['args']['FCLI_VERSION'])
        self.assertEqual(defaults['FCLI_SHA256'], service['build']['args']['FCLI_SHA256'])
        chart = yaml.safe_load((CHART / 'values.yaml').read_text())
        self.assertEqual(service['image'], chart['image']['repository'] + ':' + chart['image']['tag'])

    def test_customer_settings_and_external_file_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'provider-token'
            token.write_text('TEST_ONLY_TOKEN')
            doc = self.render(SSC_TOKEN_SOURCE=str(token), SSC_INSECURE='true',
                              BULK_AUDIT_FILTER='Languages:java')
            self.assertEqual(token.resolve(), Path(doc['secrets']['ssc-token']['file']).resolve())
            env = doc['services']['bulk-audit']['environment']
            self.assertEqual('true', env['SSC_INSECURE'])
            self.assertEqual('Languages:java', env['BULK_AUDIT_FILTER'])
            self.assertNotIn('TEST_ONLY_TOKEN', json.dumps(doc))
            self.assertFalse(any(key.startswith('AWS_') for key in env))

    def test_cloudwatch_replaces_local_options_and_preserves_truststore(self):
        doc = self.render('compose.truststore.yaml', 'compose.cloudwatch.yaml',
                          AWS_REGION='us-east-1', CLOUDWATCH_LOG_GROUP='/test/bulk-audit')
        service = doc['services']['bulk-audit']
        self.assertEqual({'driver': 'awslogs', 'options': {
            'awslogs-region': 'us-east-1', 'awslogs-group': '/test/bulk-audit',
            'awslogs-create-group': 'false', 'awslogs-create-stream': 'true'}}, service['logging'])
        self.assertEqual('/run/truststore/store', service['environment']['FCLI_TRUSTSTORE'])
        self.assertEqual('/run/secrets/truststore-password', service['environment']['FCLI_TRUSTSTORE_PWD_FILE'])
        self.assertFalse(any(key.startswith('AWS_') for key in service['environment']))


if __name__ == '__main__':
    unittest.main()
