"""Reject changed runtime bytes or missing attestations before release promotion."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('oci_image', ROOT / 'scripts/oci-image.py')
OCI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OCI)


class OCIImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.layer = b'filesystem layer'
        self.config = {'config': {'User': '10001:10001'}, 'rootfs': {
            'type': 'layers', 'diff_ids': [OCI.sha256(self.layer)]}}

    def archive(self, predicates=('https://spdx.dev/Document', 'https://slsa.dev/provenance/v1'),
                wrong_subject=False, corrupt_config=False):
        files = {}

        def blob(value):
            raw = json.dumps(value).encode()
            digest = OCI.sha256(raw)
            files['blobs/sha256/' + digest.split(':')[1]] = raw
            return {'digest': digest, 'size': len(raw)}

        config = blob(self.config)
        runtime = blob({'config': config, 'layers': []})
        runtime['platform'] = {'os': 'linux', 'architecture': 'amd64'}
        digest = 'sha256:' + '0' * 64 if wrong_subject else runtime['digest']
        attest = blob({'subject': {'digest': digest}, 'layers': [
            blob({'predicateType': p, 'subject': []}) for p in predicates]})
        root = blob({'manifests': [runtime, attest]})
        files['index.json'] = json.dumps({'manifests': [root]}).encode()
        if corrupt_config:
            files['blobs/sha256/' + config['digest'].split(':')[1]] = b'{}'
        target = self.path / 'image.oci.tar'
        self.write_tar(target, files)
        return target

    def write_tar(self, target, files):
        with tarfile.open(target, 'w') as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    def test_accepts_attested_image_and_identical_test_archive(self):
        image = OCI.inspect_archive(self.archive())
        self.assertEqual(self.config, image['config'])
        target = self.path / 'test.tar'
        self.write_tar(target, {
            'manifest.json': json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}]).encode(),
            'config.json': json.dumps(self.config).encode(), 'layer.tar': self.layer,
        })
        OCI.verify_docker_archive(target, image)
        loaded = {'Config': self.config['config'], 'RootFS': {'Layers': self.config['rootfs']['diff_ids']},
                  'Os': 'linux', 'Architecture': 'amd64'}
        with patch.object(OCI.subprocess, 'check_output', return_value=json.dumps([loaded])):
            OCI.verify_loaded_image('candidate', image)

    def test_rejects_missing_sbom_or_provenance(self):
        for predicates in ((), ('https://spdx.dev/Document',), ('https://slsa.dev/provenance/v1',)):
            with self.subTest(predicates=predicates), self.assertRaises(ValueError):
                OCI.inspect_archive(self.archive(predicates))

    def test_rejects_attestation_for_another_image(self):
        with self.assertRaisesRegex(ValueError, 'refer to the runtime'):
            OCI.inspect_archive(self.archive(wrong_subject=True))

    def test_rejects_corrupt_configuration_blob(self):
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            OCI.inspect_archive(self.archive(corrupt_config=True))

    def test_rejects_changed_runtime_bytes_in_test_archive(self):
        image = OCI.inspect_archive(self.archive())
        target = self.path / 'changed.tar'
        for config, layer in ((b'{}', self.layer), (json.dumps(self.config).encode(), b'changed layer')):
            self.write_tar(target, {
                'manifest.json': json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}]).encode(),
                'config.json': config, 'layer.tar': layer,
            })
            with self.assertRaises(ValueError):
                OCI.verify_docker_archive(target, image)

    def test_rejects_wrong_loaded_platform(self):
        image = OCI.inspect_archive(self.archive())
        loaded = {'Config': self.config['config'], 'RootFS': {'Layers': self.config['rootfs']['diff_ids']},
                  'Os': 'linux', 'Architecture': 'arm64'}
        with patch.object(OCI.subprocess, 'check_output', return_value=json.dumps([loaded])), \
                self.assertRaisesRegex(ValueError, 'platform'):
            OCI.verify_loaded_image('candidate', image)
