"""Render real Helm templates and validate deployment security/configuration."""
from pathlib import Path
import shutil
import subprocess
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
        self.assertNotIn("SSC_TOKEN", env)
        self.assertEqual("Memory", pod["volumes"][0]["emptyDir"]["medium"])
        self.assertEqual(0o440, pod["volumes"][2]["secret"]["defaultMode"])

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
        self.assertEqual("company-ca", pod["volumes"][-1]["secret"]["secretName"])
        self.assertTrue(pod["containers"][0]["image"].endswith("@" + digest))

    def test_invalid_values_rejected(self):
        for setting in ("audit.action=arbitrary", "audit.maxAudits=0", "audit.sscUrl=http://insecure",
                        "job.activeDeadlineSeconds=100", "image.digest=bad", "unknown=value"):
            with self.subTest(setting=setting):
                self.render("--set", setting, success=False)


class ComposeTests(unittest.TestCase):
    def test_no_inline_secrets_and_bounded_storage(self):
        doc = yaml.safe_load((ROOT / "deploy/compose/compose.yaml").read_text())
        service = doc["services"]["bulk-audit"]
        self.assertTrue(service["read_only"])
        self.assertEqual("no", service["restart"])
        self.assertEqual("10001:10001", service["user"])
        self.assertEqual(3, len(service["secrets"]))
        self.assertNotIn("SSC_TOKEN", service["environment"])
        self.assertTrue(all("size=" in mount for mount in service["tmpfs"]))
        self.assertEqual("local", service["logging"]["driver"])


if __name__ == "__main__":
    unittest.main()
