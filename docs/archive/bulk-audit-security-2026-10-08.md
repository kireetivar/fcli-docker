# Historical bulk-audit security review, 2026-10-08

This report describes the earlier UBI-based PoC. It does not describe the current Amazon Linux image or its current vulnerability status.

The audit covered the POC branch changes, deployment templates, credential handling, CI, and the built Linux audit image.
The reviewed branch started at commit `20f5b2d`.
Gitleaks 8.30.1 found no secrets in the 19 POC commits reviewed before these fixes.
Trivy 0.75.0 found no secrets in the tracked source snapshot or the audit image.
Secret scans do not prove that every possible credential format is absent.

| Change | Reason |
| --- | --- |
| Replace the UBI 9.7 standard runtime with pinned UBI 9.8 minimal | Remove unused packages and apply available base-image fixes. |
| Remove privileged executable permissions | The audit process does not need tools that change user or group identity. |
| Pass the tenant as `--tenant=value` | Prevent fcli from treating tenant values as argument files or command options. |
| Disable process core dumps | Crash dumps can contain credentials from process memory. |
| Include the log directory suffix in `run_id` | Containers can start during the same second with the same process identifier. |
| Disable stored CI checkout credentials | The build and tests do not need repository credentials after checkout. |
| Pin the test dependency and scanner images | Dependency updates require a reviewed version change. |

An offline test confirmed that fcli 3.28.0 expands a separate tenant argument starting with `@`.
The updated runner passes that value literally, and a regression test checks the argument form.

Trivy reported these installed-package findings:

| Severity | Previous audit image | Updated audit image |
| --- | --- | --- |
| Critical | 0 | 0 |
| High | 72 | 13 |
| Medium | 353 | 116 |
| Low | 297 | 75 |

The 13 remaining high findings cover seven distinct CVEs across OpenSSL, PCRE2, and util-linux packages.
The scan lists no fixed package versions for those findings.

| Package family | Open CVEs |
| --- | --- |
| util-linux | `CVE-2026-53613` |
| OpenSSL | `CVE-2026-54876`, `CVE-2026-75804`, `CVE-2026-84782` |
| PCRE2 | `CVE-2026-103111`, `CVE-2026-86145`, `CVE-2026-89161` |

The scanner marks `CVE-2026-86145` as `will_not_fix`.
These findings remain open; container restrictions do not prove that the affected code is unreachable.
The generic `fcli-ubi9` image still uses its original base and needs separate remediation.

CI scans source files for secrets and known dependency vulnerabilities.
CI reports all high and critical audit-image findings.
CI fails on critical findings and high findings with available fixes.
A passing CI result does not close unfixed findings or approve production use.
For a local scan with Trivy installed, run:

```powershell
trivy image --scanners vuln,secret --severity HIGH,CRITICAL <historical-image-reference>
```

Review each scan against the exact image digest and current vulnerability database.
The image scan does not establish full dependency coverage inside the native fcli executable.
Obtain an fcli software bill of materials (SBOM), which lists build dependencies, for that review.

The configuration scan also reported default namespace, health-check, archive-copy, and Windows path warnings.
Use the dedicated namespace from section 4.
The audit container finishes each run, so a service health check does not apply.
The existing Dockerfiles use `ADD` to extract local archives; Windows targets use the absolute path `C:/data`.
The Windows runtime remains outside this Linux POC audit.
