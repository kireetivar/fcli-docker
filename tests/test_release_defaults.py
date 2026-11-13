"""Check the release identity consumed by Compose and Helm."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_release", ROOT / "scripts/sync-bulk-release.py")
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class ReleaseDefaultsTests(unittest.TestCase):
    def test_checked_in_defaults_match_release(self):
        for path, expected in SYNC.generated_files(ROOT):
            self.assertEqual(expected, path.read_text(),
                             f"Run python scripts/sync-bulk-release.py to update {path}")

    def test_new_runner_release_updates_all_deployment_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("bulk-audit-release.json", "deploy/compose/.env.example",
                         "charts/fcli-bulk-audit/Chart.yaml", "charts/fcli-bulk-audit/values.yaml"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            release = json.loads((root / "bulk-audit-release.json").read_text())
            release["runner_version"] = "0.4.0-rc.1"
            (root / "bulk-audit-release.json").write_text(json.dumps(release))
            outputs = {path.name: content for path, content in SYNC.generated_files(root)}
            self.assertIn("BULK_AUDIT_IMAGE=fcli-bulk-audit:0.4.0-rc.1", outputs[".env.example"])
            self.assertIn("RUNNER_VERSION=0.4.0-rc.1", outputs[".env.example"])
            self.assertIn("version: 0.4.0-rc.1", outputs["Chart.yaml"])
            self.assertIn('appVersion: "0.4.0-rc.1"', outputs["Chart.yaml"])
            self.assertIn("tag: 0.4.0-rc.1", outputs["values.yaml"])
