# Bulk-audit POC: run and test

This POC provides a one-shot container, Docker Compose configuration, and a Helm chart. It defaults to **SAST, dry-run, at most one application-version audit**, with Aviator tag preparation enabled for a live SAST run. It creates fresh sessions from mounted credentials; you do not need to install fcli or log in on the host.

For the architectural comparison and proposed future fcli changes, see [deployment design](bulk-audit-deployment.md).

## What is included

| Location | Purpose |
| --- | --- |
| `linux/bulk-audit.sh` | Validate configuration, authenticate, execute, stream logs, and clean up |
| `linux/Dockerfile`, target `fcli-bulk-audit` | Dedicated runner image using the existing verified downloader and UBI9 base |
| `deploy/compose/compose.yaml` | Manual Docker execution with secret files and bounded temporary storage |
| `deploy/compose/compose.truststore.yaml` | Optional private CA/truststore configuration |
| `charts/fcli-bulk-audit` | Kubernetes Job by default, or an explicitly enabled, initially suspended CronJob |
| `tests` | Offline runner tests, Helm rendering tests, and a Docker smoke-test script |

### fcli build selection

The POC pins the stable **v3.28.0** release. Its Linux archive SHA-256 is:

```text
f1c272513e24c204abd700037d373b831131520e805b2b8409025e619f8b04f6
```

The build verifies both this checksum and Fortify's RSA signature, then checks the packaged action interfaces without authenticating. The build targets `linux/amd64`; native ARM support is not established by this POC.

The runner creates a private `FCLI_USER_HOME` and clears inherited directory overrides so fcli can derive a consistent directory layout. This avoids startup failures caused by state paths outside fcli's home.

When changing releases, update the version and checksum together and rerun compatibility checks. Source: [fcli v3.28.0](https://github.com/fortify/fcli/releases/tag/v3.28.0).

If you already created `deploy/compose/.env`, pulling this branch does not update that ignored file. Set `FCLI_VERSION=v3.28.0` and `FCLI_SHA256=f1c272513e24c204abd700037d373b831131520e805b2b8409025e619f8b04f6` there, preserving your endpoints and other settings, before rebuilding with Compose.

## 1. Prepare the PC that can reach SSC and Aviator

Prerequisites:

- Docker Engine or Docker Desktop/Rancher Desktop configured for Linux containers, with Docker Compose v2 or later.
- A running Docker engine. `docker version` must show both Client and Server; `docker compose version` must succeed.
- Network access from the container to SSC and Aviator, including VPN/routing requirements.
- An SSC token, Aviator user token, Aviator admin private key, and the Aviator tenant identifier.
- A small SSC test application with eligible SAST results, and available Aviator entitlement/quota.
- Enough memory for the POC defaults: a 4 GiB container limit, including memory-backed temporary files. Increase this and temporary storage for larger FPRs after measuring usage.

Copy or clone this repository on that PC. Do not copy an existing host fcli session directory into the container.

From the repository root:

```powershell
cd deploy/compose
Copy-Item .env.example .env
New-Item -ItemType Directory -Force secrets, logs
```

For Bash, the equivalent setup is:

```bash
cd deploy/compose
cp .env.example .env
mkdir -p secrets logs
chmod 700 secrets logs
```

Edit `.env` with your SSC URL, Aviator URL, tenant, and an **SSC filter verified to select the test application**. Keep `BULK_AUDIT_DRY_RUN=true` and `BULK_AUDIT_MAX_AUDITS=1`. The runner rejects empty filters and `CHANGE_ME` placeholders. A count limit alone does not select a particular application.

Use a trusted editor or your secret-management tool to create these UTF-8 files **without a byte-order mark**:

```text
secrets/ssc-token             SSC token value only
secrets/aviator-token         Aviator user token value only
secrets/aviator-private-key   Complete PEM private key, preserving its line breaks
```

Do not add quotation marks around tokens. Never paste secret values into shell commands, `.env`, Helm values, or committed files. These local directories and `.env` are ignored by Git and excluded from the Docker build context.

Protect the directory with your Windows account's ACLs. On a conventional rootful Linux Docker host, one approach is a private parent directory and secret files readable by container group 10001:

```bash
sudo chgrp 10001 secrets/ssc-token secrets/aviator-token secrets/aviator-private-key
chmod 640 secrets/ssc-token secrets/aviator-token secrets/aviator-private-key
```

Compose's file-backed secrets do not remap file ownership. Rootless Docker and desktop file sharing may behave differently; check readability without printing contents before running. See [Docker's secrets reference](https://docs.docker.com/reference/compose-file/services/#secrets).

## 2. Build and perform offline checks

Still in `deploy/compose`:

```text
docker compose config --quiet
docker compose build --pull bulk-audit
docker compose run --rm bulk-audit --check-image
```

The image check needs no valid sessions. Compose still needs its referenced files to exist so it can mount them.

Check the secret mounts without displaying their contents:

```text
docker compose run --rm --entrypoint /bin/bash bulk-audit -c 'for f in /run/secrets/*; do test -r "$f" && test -s "$f" || exit 1; done'
```

A zero exit status means the files are readable and nonempty, not that the credentials are valid. The runner validates authentication during the actual run.

If a release checksum mismatch occurs, stop and inspect the official release metadata. In PowerShell:

```powershell
$release = Invoke-RestMethod 'https://api.github.com/repos/fortify/fcli/releases/tags/v3.28.0'
$release | Select-Object tag_name, published_at
$release.assets | Where-Object name -eq 'fcli-linux.tgz' | Select-Object name, digest
```

Review the new build before updating `FCLI_SHA256` in `.env` to the digest without its `sha256:` prefix. Keep checksum verification enabled. Use `docker compose build --pull bulk-audit` after selecting a verified release and rerun compatibility checks. Record the resulting image ID with `docker image inspect fcli-bulk-audit:poc-20261005 --format '{{.Id}}'` and use a new image tag for a new build.

## 3. Run the dry run

```text
docker compose up --abort-on-container-exit --exit-code-from bulk-audit --force-recreate bulk-audit
```

Inspect `$LASTEXITCODE` in PowerShell or `$?` in Bash immediately after the command. Keep the stopped container until you have reviewed and saved its logs:

```text
docker compose logs --no-color bulk-audit
docker compose logs --no-color bulk-audit > logs/dry-run.log
```

Confirm that:

1. SSC login, Aviator user login, and Aviator admin setup succeed.
2. The preview identifies the intended application/version.
3. At most one audit is selected, and the runner reports `dry_run=true`.
4. The output describes what would be prepared/created/audited without performing those audit mutations.

The dry run is not offline: it authenticates and queries the servers. Stop here if selection is wrong or a required session fails. No eligible application is a valid empty result; verify pending SAST issues, filters, and application metrics before expecting an audit.

## 4. Perform one live SAST audit

After reviewing the dry run, edit `.env` to set:

```dotenv
BULK_AUDIT_ACTION=bulkaudit-sast
BULK_AUDIT_DRY_RUN=false
BULK_AUDIT_MAX_AUDITS=1
```

Run the same `docker compose up` command. This live run may create an Aviator application, prepare Aviator tags in SSC, consume audit quota, and update SSC audit results. Changing back to an older image does not undo those remote changes.

Save logs to `logs/live-sast.log` before recreating the container. Verify the audit outcome in SSC and the action output, then set `BULK_AUDIT_DRY_RUN=true` again.

**Known limitation:** the current actions can return zero even when individual operations fail. A zero container exit code means the fcli process completed; it does not prove every audit succeeded. The runner preserves nonzero exit codes and never automatically retries a whole audit. Logs and SSC verification are part of POC acceptance.

For a DAST trial, change `BULK_AUDIT_ACTION=bulkaudit-dast`, keep dry-run enabled, and use an application with a processed WebInspect result eligible for auditing. Review the preview before a live run. DAST handles its own preparation. `BULK_AUDIT_ACTION=bulkaudit` exercises the deprecated SAST alias.

Run one instance at a time for the same scope. This manual Compose POC does not implement a cross-process or distributed lock.

## 5. Transfer an image instead of building on the test PC

On a machine where the image has been built:

```text
docker image save -o fcli-bulk-audit.image.tar fcli-bulk-audit:poc-20261005
```

Transfer the archive and repository files, but provision credentials separately on the test PC. There:

```text
docker image load -i fcli-bulk-audit.image.tar
```

Prepare `.env` and secret files as above, then use `docker compose up --no-build --abort-on-container-exit --exit-code-from bulk-audit --force-recreate bulk-audit`. No image was built on the development PC during initial validation because its Docker engine was not running.

## 6. Optional truststore and proxy configuration

For a private CA, provide `certs/truststore.jks` and `secrets/truststore-password`. Use a truststore containing the required trusted certificates, not a private identity key. Both files must be readable by container UID/GID 10001.

Run Compose with the optional override consistently for build, checks, and execution:

```text
docker compose -f compose.yaml -f compose.truststore.yaml up --abort-on-container-exit --exit-code-from bulk-audit --force-recreate bulk-audit
```

The truststore type defaults to JKS; set `FCLI_TRUSTSTORE_TYPE=PKCS12` in `.env` for a PKCS12 store. Do not disable TLS verification to work around a trust problem.

For a proxy, add a local Compose override supplying the fcli-supported non-secret proxy settings (`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`). Do not put proxy credentials into YAML or URLs. Authenticated proxy handling is outside this initial POC and needs a separate secret-file design. Confirm Aviator's gRPC connectivity as well as SSC HTTPS connectivity; HTTP proxy configuration alone does not establish that both work.

## 7. Helm chart

Helm is included now. Scheduling is optional; the chart creates a **one-shot Job by default**. Kubernetes 1.27+ is required for the CronJob timezone field. Use Helm 3 or 4.

Make the same image available to the cluster, either by loading it into a local cluster using that runtime's documented procedure or pushing it to your registry. A host's Docker image cache is not automatically the cluster's image cache. For a registry image, configure `image.repository`, `image.tag`, and any `imagePullSecrets`; prefer `image.digest` for a reproducible installation.

From the repository root, create a dedicated namespace and a Secret from files on your own PC:

```text
kubectl create namespace fcli-audit
kubectl -n fcli-audit create secret generic fcli-bulk-audit-credentials --from-file=ssc-token=deploy/compose/secrets/ssc-token --from-file=aviator-token=deploy/compose/secrets/aviator-token --from-file=aviator-private-key=deploy/compose/secrets/aviator-private-key
```

The chart references this Secret; it does not create a Secret containing credentials or require the audit Pod to read the Kubernetes API. Production clusters still need appropriate RBAC and encryption at rest.

Copy `charts/fcli-bulk-audit/values.yaml` to `charts/fcli-bulk-audit/values.local.yaml`. Replace the placeholders under `audit`, set the image reference, and leave `dryRun: true`, `maxAudits: 1`, and `schedule.enabled: false` initially. Then:

```text
helm lint charts/fcli-bulk-audit -f charts/fcli-bulk-audit/values.local.yaml
helm template poc charts/fcli-bulk-audit -f charts/fcli-bulk-audit/values.local.yaml
helm install poc charts/fcli-bulk-audit -n fcli-audit -f charts/fcli-bulk-audit/values.local.yaml
kubectl -n fcli-audit get jobs,pods
kubectl -n fcli-audit logs -f job/poc-bulk-audit
kubectl -n fcli-audit describe job poc-bulk-audit
```

Helm installation success only means the resource was submitted. Review Job status and logs for execution results. Save logs before uninstalling or before the configured TTL removes the completed Job.

A Job's Pod template is immutable. To repeat a one-shot test with changed configuration, first confirm the previous Job has finished, save its logs, and uninstall its Helm release; then install it again. Do not create parallel releases targeting the same application scope.

For an optional truststore, create another Secret with keys `truststore.jks` and `password`, then set `truststore.existingSecret` to its name.

### Scheduling after the POC

After successful manual testing, install the chart with `schedule.enabled: true`, configure the schedule/timezone, and leave `schedule.suspend: true` while reviewing the rendered configuration. Enable execution by setting `schedule.suspend: false` when ready. Change `audit.dryRun` only after reviewing the same application scope.

The CronJob uses `Forbid` and zero Job retries. This prevents normal overlap within that CronJob but does not provide exactly-once execution or coordinate other releases and manual jobs. See [Kubernetes CronJob semantics](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/).

## Logs, credentials, and shutdown behavior

- Runner lifecycle events are JSON on stderr; fcli console output and masked file diagnostics are also streamed. The combined stream is not exclusively JSON. Authentication command output is suppressed; a login failure reports its phase and exit code without echoing credentials or server error bodies.
- Docker keeps bounded local logs (three 10 MB files). Save relevant logs before recreating/removing containers. Kubernetes logs can be collected by an existing Fluent Bit or other platform collector. CloudWatch setup is not bundled in this POC.
- Diagnostic masking uses fcli's `high` setting and is best effort. Treat logs as sensitive application data and review before sharing them.
- Sessions and downloaded temporary data use private directories in bounded memory-backed volumes. They are cleaned up after ordinary completion or cancellation; ephemeral mounts also limit persistence when the process is killed abruptly. The original mounted credential files remain on the host or in Kubernetes Secrets until their owner rotates/removes them.
- SSC's token value is exposed only to its login child through a scoped environment variable. Aviator receives file paths. Privileged host/container administrators remain able to inspect runtime credentials; this is not a boundary against a compromised host.
- The runner removes local sessions rather than invoking token-revoking logout operations. It does not revoke customer-supplied tokens after every run. Rotate credentials outside the container; each new invocation loads current files.
- The default overall timeout is 3,600 seconds, followed by a 30-second forced-stop window. Docker allows 45 seconds for shutdown; the Helm Job deadline is 3,660 seconds. Increase deadlines and resources together for larger audits.

| Result | Meaning |
| --- | --- |
| `0` | fcli process completed; inspect individual audit results |
| `64` | Runner configuration or secret-file validation failed |
| `69` | Packaged fcli action interface is incompatible (`--check-image`) |
| `74` | File-log streaming failed after the command completed |
| `124` | Overall execution deadline expired |
| `130` / `143` | Interrupted/terminated where the runner handled the signal |
| `137` | Forced termination or OOM; inspect Docker/Kubernetes state |
| Other nonzero | Propagated fcli/process failure; inspect the reported phase |

Codes can overlap with upstream fcli codes; use the lifecycle phase/event to distinguish the source. A timeout/cancellation can leave completed or in-flight remote mutations. Verify SSC before rerunning.

## Validation and acceptance

Offline checks from the repository root:

```text
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
helm lint charts/fcli-bulk-audit
docker compose --env-file deploy/compose/.env.example -f deploy/compose/compose.yaml config --quiet
```

Runner tests need Bash and GNU coreutils; Windows tests use Git Bash. Linux additionally runs the explicit SIGTERM test. With a running Docker engine, use `bash tests/smoke-images.sh` to build and check the runner and both existing shared image variants without credentials.

Initial validation on this development PC verified the downloaded Windows binary's checksum/signature and action/authentication help, runner tests with a test double, and Helm/Compose rendering. **Docker image builds, Kubernetes execution, and live SSC/Aviator auditing remain to be tested on a suitable machine.** The CI workflow provides Linux and image checks but has not been executed as part of this local task.

POC acceptance on the connected PC requires an intended-application dry run, one successful live SAST audit confirmed in SSC, readable logs, no credential values in logs, correct nonzero behavior for invalid credentials, and a fresh session on a subsequent invocation. DAST and the alias should then be exercised separately. Do not call this production-ready until the upstream failure-status limitation and the operational checks in the deployment design have been resolved.
