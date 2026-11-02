# Base image provider evaluation: 2026-11-03

## Recommendation

Amazon Linux 2023 Minimal is the strongest tested alternative in this evaluation when the priorities are an established provider, compatibility with the existing runner, and a clean vulnerability scan. The final audit candidate has zero detected package vulnerabilities and secrets, passes all 20 offline runner tests, and passes the real fcli compatibility check with networking disabled and restricted container permissions.

This is an AWS-maintained minimal base, not a dedicated hardened-image product or a certification. Retain our non-root, read-only filesystem, capability, session-cleanup, and timeout controls. Confirm the organization's support requirements and perform a live SSC/Aviator test before adopting any candidate.

The selected Amazon Linux base is now configured as the audit image default. This evaluation did not publish images or execute live audits.

## Method and scope

- Platform: Linux/amd64; fcli 3.29.0 throughout.
- Candidate images reuse the fcli executable from the previously checksum- and signature-verified POC image.
- Runtime bases are pinned by immutable registry digest.
- Trivy 0.75.0 scanned exported final image archives with vulnerability and secret scanners enabled. The same database, updated `2026-11-02T13:15:56Z`, was used for every Trivy result below, including fresh UBI and Wolfi comparisons.
- Grype 0.121.1 scanned Red Hat's vendor SPDX SBOM for the exact core-runtime base. Its downloaded binary was checked against the official GitHub release asset checksum. This result covers the base, not the added fcli executable.
- Counts below are raw scanner matches. No VEX suppression was applied. They do not establish exploitability or a complete security ranking across distributions and scanners.
- Offline runner tests use a test-only Python runtime and `cmp` utility. Neither is added to the scanned production candidates. The runner's fcli calls are simulated in these tests; separate image checks exercise the real fcli executable without credentials.

## Measured results

| Candidate | Scan scope/tool | Critical | High | Medium | Low | Validation |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Existing UBI 9 Minimal | Final image / Trivy | 0 | 11 | 116 | 87 | Existing baseline |
| Chainguard Wolfi | Final image / Trivy | 0 | 0 | 0 | 0 | 20 runner tests passed in previous evaluation; refreshed scan here |
| Amazon Linux 2023 Minimal | Final image / Trivy | 0 | 0 | 0 | 0 | 20 runner tests and restricted real-image check passed |
| Docker Hardened Bash, Debian 13 | Final image / Trivy | 2 | 12 | 65 | 108 | 20 runner tests and restricted real-image check passed |
| Docker Hardened Bash, Alpine 3.24 | Final image / Trivy | 0 | 2 | 2 | 44 | Build and restricted real-image compatibility checks passed; full runner suite not run |
| Red Hat Hardened core-runtime | Vendor base SBOM / Grype | 0 | 13 | 28 | 2 | Derived runtime candidate passed 20 runner tests and restricted real-image check |

Every final image scanned by Trivy reported zero detected secrets. Red Hat's SBOM scan does not assess secrets.

### Docker results require VEX reconciliation

The Debian image's critical matches are `CVE-2026-40468` and `CVE-2026-40469`, both against gawk. The Alpine and Debian results above must be reconciled against Docker's signed VEX and patch metadata before calling these exploitable vulnerabilities or rejecting the provider.

Docker explicitly documents that scanners need its VEX statements to account for findings that do not apply. Docker Scout is not installed in this environment, and VEX reconciliation remains open. A direct native Trivy registry scan also encountered an authentication failure; scanning Docker-exported archives succeeded. These are tooling and assessment constraints, not proof that Docker's products are unsafe.

See [Docker's scanning instructions](https://docs.docker.com/dhi/how-to/scan/) and [scanner integrations](https://docs.docker.com/dhi/explore/scanner-integrations/).

### Red Hat requires an SBOM-aware scan

Trivy classified the core-runtime OS as `none` and did not provide a usable OS vulnerability assessment. Its empty result must not be described as zero vulnerabilities. Grype recognized the Hummingbird distribution and matched the vendor SBOM against its Hummingbird advisory namespace, producing the counts above.

The inspected core-runtime includes Bash, GNU timeout, date, mktemp, mkdir, rm, and env. It lacks sed and find, which our Dockerfile used at build time. The runtime candidate reuses the normalized runner from the verified POC image and removes privileged executable bits using Bash, avoiding additional runtime packages. A builder-based candidate was also built during exploration but is not the recommended Red Hat runtime candidate.

Red Hat's hardened-image lifecycle follows upstream projects rather than the RHEL lifecycle. Do not assume that UBI/RHEL support commitments automatically apply. See [Red Hat's container support policy](https://access.redhat.com/support/policy/container-support-policy) and [vendor SBOM audit guidance](https://docs.redhat.com/en/documentation/red_hat_hardened_images/1-latest/develop-sbom_and_compliance).

## Other established-provider options

| Provider | Assessment for this POC |
| --- | --- |
| AWS | The minimal base supplies the runner's runtime utilities. No packages were installed into the recommended AWS candidate. AL2023 has a published support lifecycle through June 30, 2029; confirm package-specific and commercial support terms. |
| Docker | Dedicated hardened images with SBOM, provenance, and VEX. The Bash variants preserve our runner design. Paid tiers offer additional remediation and compliance commitments. Resolve the raw scan matches using vendor evidence before deciding. |
| Red Hat | Dedicated hardened runtime available from the same provider as UBI, and the candidate works. SBOM-aware scanning and review of the reported matches are required. |
| Canonical | Chiseled Ubuntu offers a vendor-supported minimal approach. Standard chiseled runtimes omit shells and package managers; our Bash runner needs a custom assembly or orchestration changes. Documentation reviewed; no candidate built or scanned. |
| GoogleContainerTools | Distroless images are signed and maintained, but standard runtime images omit the shell required here. A custom assembly or runner redesign would be needed. Documentation reviewed; no candidate built or scanned. |

Sources: [AWS minimal image](https://docs.aws.amazon.com/linux/al2023/ug/minimal-container.html), [AWS lifecycle](https://docs.aws.amazon.com/linux/al2023/ug/release-cadence.html), [Docker offerings](https://docs.docker.com/dhi/), [Canonical Chiseled](https://ubuntu.com/containers/chiseled), [GoogleContainerTools distroless](https://github.com/GoogleContainerTools/distroless).

## Exact evaluated bases and local artifacts

| Candidate | Base reference |
| --- | --- |
| AWS | `public.ecr.aws/amazonlinux/amazonlinux:2023-minimal@sha256:d4495d25da60ef3f2d44bc7f6a2dd2ec1646c14414e0dfaaa44dc3ff653e1c2b` |
| Docker Debian | `dhi.io/bash:5-debian13@sha256:8d67f470328164445f78cc0979b4205e2f56c307d18928891b5796ec0c64905d` |
| Docker Alpine | `dhi.io/bash:5-alpine3.24@sha256:a707212b3cedeb3241971658dba3f152d2d1a1cda5f7c4cc6f9582973b27a414` |
| Red Hat | `registry.access.redhat.com/hi/core-runtime:latest@sha256:4163796d8b7f28021178093d31cb97c05336fd3f3a4d7006603a7fef29e997e7` |

Local images:

- `fcli-bulk-audit:3.29.0-aws-runtime-eval`
- `fcli-bulk-audit:3.29.0-redhat-runtime-eval`
- `fcli-bulk-audit:3.29.0-dhi-eval`
- `fcli-bulk-audit:3.29.0-dhi-alpine-eval`

The directory `.cache/provider-evaluation-2026-11-03/` contains candidate Dockerfiles, exported image archives, raw JSON reports, the Red Hat vendor SBOM, test logs, and `summary.json`. It is excluded from Git. The recommended AWS prototype is `Dockerfile.aws-runtime`; `Dockerfile.aws` was an exploratory version that installed unnecessary build utilities.

For example, reproduce the AWS candidate from the repository root while the verified original POC image is available locally:

```powershell
docker build --platform linux/amd64 -f .cache/provider-evaluation-2026-11-03/Dockerfile.aws-runtime -t fcli-bulk-audit:3.29.0-aws-runtime-eval linux
docker save fcli-bulk-audit:3.29.0-aws-runtime-eval -o .cache/provider-evaluation-2026-11-03/aws-audit.image.tar
trivy image --input .cache/provider-evaluation-2026-11-03/aws-audit.image.tar --scanners vuln,secret --format json --output .cache/provider-evaluation-2026-11-03/aws-audit-report.json
```

Future adoption should download and verify fcli through the normal Dockerfile downloader stage rather than depend on a locally built POC image. Digest pinning records content identity; publisher-signature verification and release provenance should be included in the final build workflow. Native fcli dependency coverage and live service validation remain outside this evaluation.
