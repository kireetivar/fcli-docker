# Bulk Audit POC: Security Summary

This summary covers the Linux bulk-audit POC. These controls do not establish production approval.

## Implemented

- **Separate credentials:** Compose and Kubernetes mount credential files. Credentials stay outside the image and tracked settings.
- **Restricted container:** The audit runs as user `10001`. Compose and Helm restrict permissions and make the root filesystem read-only.
- **Smaller image:** The audit image uses UBI Minimal with an exact base-image identifier. This removes unnecessary packages.
- **Verified fcli download:** The build checks the publisher signature. Compose also supplies the expected archive checksum.
- **Safer inputs:** The runner validates settings and passes arguments without evaluating shell code. Tenant values cannot load argument files.
- **Temporary sessions:** The runner creates private sessions and removes temporary data on normal exit or handled stop signals.
- **Protected output:** The runner requests fcli credential masking and disables process memory dumps. Logs still require access controls.
- **Execution limits:** Dry-run mode and one audit are defaults. Timeouts and resource limits bound execution.
- **Automated checks:** The workflow scans source files for secrets and vulnerabilities. Image checks reject critical findings and fixable high findings.
- **Build credentials:** Checkout does not retain Git credentials. The workflow uses a read-only repository token.

## Remaining work

- **Review vulnerabilities:** The 2026-10-08 scan reported zero critical findings and 13 high package findings across seven vulnerabilities.
  Rescan the release image. Resolve findings or record an approved risk decision.
- **Review fcli dependencies:** Obtain the upstream dependency list. Operating system scans do not cover every dependency inside fcli.
- **Protect credentials:** Configure Kubernetes storage encryption and access controls. Test credential replacement and expiry.
- **Restrict network access:** Allow required service connections and block unnecessary cloud metadata access. Protect host crash collectors.
- **Validate logging:** Test CloudWatch delivery, access controls, and retention. The Helm chart does not install a collector.
- **Verify results:** Run a live preview and one audit. Check SSC because fcli can return success after individual audit failures.
- **Require build checks:** Configure merge and release rules to require successful security checks.

See the [POC guide](bulk-audit-poc-guide.md) for implementation details and the recorded security audit.
