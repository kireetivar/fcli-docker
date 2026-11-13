# Maintain and verify a bulk-audit release

The bulk-audit runner is a release candidate. Repository checks do not establish production approval or verify live SSC and Aviator behavior.
Use the [installation guide](bulk-audit-guide.md) for deployment configuration and the [runbook](bulk-audit-runbook.md) for execution.

## Update the release identity

[bulk-audit-release.json](../bulk-audit-release.json) owns the runner version, bundled fcli version, Linux archive checksum, and local image repository.
The runner version identifies wrapper behavior independently of the fcli version.
The Helm chart version and `appVersion` follow the runner version.

1. Update the release metadata. Assign a new runner version when releasing changed wrapper behavior.
2. Obtain the archive checksum from the selected upstream release. Keep Fortify signature verification enabled.
3. Regenerate the committed Compose and Helm defaults:

   ```bash
   python scripts/sync-bulk-release.py
   python scripts/sync-bulk-release.py --check
   ```

4. Review the generated diff. For an existing deployment, copy `RUNNER_VERSION`, `FCLI_VERSION`, `FCLI_SHA256`, and `BULK_AUDIT_IMAGE` into its settings.
5. Replace old `bulkaudit*` configuration values with the supported public action names. The current runner rejects those old names.

Use a registry digest in production deployment values after the image has been published to the approved registry.
Tags, including timestamped tags, are names that a registry can move. A tag alone does not guarantee immutable deployment bytes.
The default repository is a local build name. The project does not select a production registry for the bulk-audit image.

## Verify changes locally

Use Python 3.11 or later, Bash, Docker with Linux containers, and Helm.
Install the pinned Python test dependency from `tests/requirements.txt`.
Run the runner tests on Linux because GNU timeout and POSIX signal delivery are part of the runtime contract.
Git Bash on Windows can expire the short test deadline before the simulated audit child starts.

```bash
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
python scripts/sync-bulk-release.py --check
helm lint charts/fcli-bulk-audit
bash tests/smoke-images.sh
bash tests/smoke-images.sh --windows-checkout
```

The suite checks release inputs, artifact identities, action behavior, and rendered deployment configuration.
The image smoke test checks the packaged fcli interfaces, non-root execution, restricted-container compatibility, and retained logs.
These tests use no SSC or Aviator credentials.

## Understand the release workflow

[docker.yml](../.github/workflows/docker.yml) maintains the existing general fcli image variants.
Its publication control remains `doPublish`, which defaults to false.
It does not publish the bulk-audit image.

1. The release helper validates dispatch inputs before network requests or Docker commands.
2. It resolves SHA-256 values from the selected GitHub release assets. Missing digest metadata fails the release plan.
3. Each Linux variant builds once into an OCI archive with SBOM and provenance attestations.
4. Skopeo derives a Docker archive for testing. The verifier checks its configuration and filesystem layers against the OCI image.
5. Runtime tests and vulnerability checks run on that image.
6. A separate publication job waits for every Linux variant and each requested Windows test to pass.
7. The publication job verifies the downloaded artifact identity, then copies the original OCI archive with `--all --preserve-digests`.

The workflow does not rebuild between testing and publication.
Only the publication job receives Docker Hub publishing credentials.
Windows images remain test-only. Their build checks the archive checksum and Fortify signature before running fcli.
Windows container execution must be validated on the Windows CI runners; the local Linux verification does not cover it.

Build artifacts are retained for seven days. Vulnerability reports are retained for thirty days.
The published digest appears in the workflow summary.
Registry promotion can partially complete if a network or registry operation fails. Check published digests before retrying.

## Verify an OCI artifact

On a Linux host with Docker and Skopeo, use an attested OCI archive exported by the release workflow:

```bash
skopeo copy --override-os linux --override-arch amd64 \
  oci-archive:image.oci.tar docker-archive:test-image.tar:fcli-candidate:test
docker load --input test-image.tar
python scripts/oci-image.py image.oci.tar \
  --docker-archive test-image.tar --image fcli-candidate:test
bash scripts/scan-image.sh test-image.tar reports
```

The verifier rejects missing SBOM or provenance, attestations for another runtime image, changed configuration, and changed filesystem layers.
Docker can represent the imported image with a different manifest identifier. The verifier compares runtime configuration and uncompressed filesystem content instead of assuming Docker's image ID equals the OCI index digest.
The original OCI archive remains the release artifact.

The copy behavior follows the [Skopeo copy contract](https://github.com/containers/skopeo/blob/main/docs/skopeo-copy.1.md).
The build uses Docker's [OCI exporter](https://docs.docker.com/build/exporters/oci-docker/).

## Review vulnerability evidence

[bulk-audit.yml](../.github/workflows/bulk-audit.yml) runs on relevant changes, manual dispatch, and Mondays at 04:17 UTC.
GitHub schedules run from the default branch, so the schedule takes effect after this workflow reaches that branch.
The scheduled check rebuilds the candidate from the checked-in pins and scans it with an updated vulnerability database.
It does not update dependencies, approve exceptions, or publish an image.

Runner tests use Ubuntu 24.04 to match the GNU `timeout` behavior in Amazon Linux.
Ubuntu 26.04 uses [Rust coreutils by default](https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/).
Its `timeout` returned `124` for an external SIGTERM in a local reproduction, while GNU `timeout` returned `143`.
Recheck signal forwarding and deadline expiry before changing the validation host.

[scan-image.sh](../scripts/scan-image.sh) owns the shared image policy:

- Save the full package vulnerability report, including unfixed findings, and any detected secrets.
- Fail on any critical finding.
- Fail on high findings with available fixes.
- Fail on any detected secret.
- Leave other findings visible for review.

The bulk-audit workflow also scans tracked source content for secrets and dependency vulnerabilities.
Operating-system package scans do not establish complete dependency coverage inside the native fcli executable.
Use a current report for the exact release artifact. The dated [provider evaluation](base-image-provider-evaluation-2026-11-03.md), [November scan](bulk-audit-vulnerability-scan-2026-11-01.md), and [earlier UBI review](archive/bulk-audit-security-2026-10-08.md) are historical evidence.

## Complete production acceptance

The following work still requires the target environment or an operational decision:

- Establish reliable per-application outcomes and the policy for partial failures and empty selections. The current exit status remains the fcli process status.
- Validate all three actions against dedicated SSC and Aviator test data, including interruption and recovery.
- Select the bulk-audit registry and deploy the approved image digest.
- Establish one execution owner or coordination across manual runs and schedules. `Forbid` prevents overlap only within one CronJob.
- Verify credential rotation, certificate trust, network restrictions, resource limits, and durable log collection.
- Assign alert routing, log retention, vulnerability remediation, and exception ownership.
- Require the relevant CI checks in repository protection rules.

The [decision trail](production-readiness-decisions.tsv) records the implementation and local verification completed in this repository.
