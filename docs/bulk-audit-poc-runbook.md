# Bulk Audit POC: Temporary Runbook

Use Docker Compose for one computer. Use Helm for a Kubernetes cluster.
Choose one method for the live test to avoid auditing the same application twice.
These commands use PowerShell. Start from the repository root.

You need access to SSC and Aviator, three credential files, and a small test application.
You do not need fcli installed on the computer.
A dry run previews work without performing an audit.

## Docker Compose

1. Start Docker with Linux containers. Prepare local settings if these files do not already exist:

   ```powershell
   cd deploy/compose
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   New-Item -ItemType Directory -Force secrets, logs
   ```

2. Edit `.env`. Set `SSC_URL`, `AVIATOR_URL`, `AVIATOR_TENANT`, and `BULK_AUDIT_FILTER` for the test application.
   Keep these settings:

   ```dotenv
   BULK_AUDIT_ACTION=bulkaudit-sast
   BULK_AUDIT_DRY_RUN=true
   BULK_AUDIT_MAX_AUDITS=1
   SSC_INSECURE=false
   ```

3. Save credentials in these files. Keep credentials out of `.env` and Git.

   | File | Content |
   | --- | --- |
   | `secrets/ssc-token` | SSC token |
   | `secrets/aviator-token` | Aviator user token |
   | `secrets/aviator-private-key` | Complete Aviator admin PEM private key |

   Use UTF-8 without a byte-order mark. Preserve the private key's line breaks.
   Restrict file access. The container user `10001` must have read access.

4. Build the image and check compatibility. Stop if a command fails.

   ```powershell
   docker compose config --quiet
   docker compose build --pull bulk-audit
   docker compose run --rm bulk-audit --check-image
   ```

   The last command must report `image_compatible`.

5. Start the dry run and save the output:

   ```powershell
   docker compose up --abort-on-container-exit --exit-code-from bulk-audit --force-recreate bulk-audit
   $auditExitCode = $LASTEXITCODE
   Write-Output "Container exit code: $auditExitCode"
   docker compose logs --no-color bulk-audit | Out-File -Encoding utf8 logs/dry-run.log
   ```

6. Confirm successful logins, `dry_run=true`, and the intended application version. Stop if the output reports failures.
7. For one live audit, set `BULK_AUDIT_DRY_RUN=false`. Keep the filter and `BULK_AUDIT_MAX_AUDITS=1`.
8. Repeat step 5. Change the output filename to `logs/live-sast.log` before saving the live output.
9. Check the audit results in SSC. Restore `BULK_AUDIT_DRY_RUN=true`.

## Helm

Helm installs a Kubernetes Job, which runs once and stops.
You need Helm, `kubectl`, and a test cluster with access to SSC and Aviator.

1. Make the audit image available to the cluster.
   Use the Compose build above, or an image supplied by your team.
   For a remote cluster, push the image to your registry and use that image address below.
   A Docker image on your computer is not automatically available to every cluster.

2. From the repository root, check the cluster and prepare local values:

   ```powershell
   kubectl config current-context
   kubectl create namespace fcli-audit
   if (!(Test-Path charts/fcli-bulk-audit/values.local.yaml)) { Copy-Item charts/fcli-bulk-audit/values.yaml charts/fcli-bulk-audit/values.local.yaml }
   ```

   Skip namespace creation if `fcli-audit` already exists.

3. Create the credential Secret from the three files described above:

   ```powershell
   kubectl -n fcli-audit create secret generic fcli-bulk-audit-credentials --from-file=ssc-token=deploy/compose/secrets/ssc-token --from-file=aviator-token=deploy/compose/secrets/aviator-token --from-file=aviator-private-key=deploy/compose/secrets/aviator-private-key
   ```

   Skip this command if your platform already supplies this Secret.

4. Edit `charts/fcli-bulk-audit/values.local.yaml`:

   - Set `image.repository` and `image.tag` to the available image.
   - Set `imagePullSecrets` if your registry requires authentication.
   - Set `audit.sscUrl`, `audit.aviatorUrl`, `audit.aviatorTenant`, and `audit.filter`.
   - Keep `audit.action: bulkaudit-sast`, `audit.dryRun: true`, and `audit.maxAudits: 1`.
   - Keep `schedule.enabled: false` and `audit.sscInsecure: false`.
   - Use `image.pullPolicy: Never` only when every eligible cluster node already has the image.

5. Install the dry-run Job. Use an unused Helm release name; these commands use `poc`.

   ```powershell
   helm lint charts/fcli-bulk-audit -f charts/fcli-bulk-audit/values.local.yaml
   helm install poc charts/fcli-bulk-audit -n fcli-audit -f charts/fcli-bulk-audit/values.local.yaml
   kubectl -n fcli-audit get jobs,pods
   kubectl -n fcli-audit logs -f job/poc-bulk-audit
   ```

   If the Pod is still starting, repeat the logs command after the Pod starts.

6. Confirm successful logins, `dry_run=true`, and the intended application version. Wait for the Job to finish.
   Save the output before removing the Job:

   ```powershell
   New-Item -ItemType Directory -Force deploy/compose/logs
   kubectl -n fcli-audit logs job/poc-bulk-audit | Out-File -Encoding utf8 deploy/compose/logs/helm-dry-run.log
   ```

7. For one live audit, remove the completed dry-run release:

   ```powershell
   helm uninstall poc -n fcli-audit
   ```

8. Set `audit.dryRun: false` in the local values. Keep the filter and `audit.maxAudits: 1`.
9. Repeat steps 5 and 6. Save the output as `helm-live-sast.log`.
10. Check the audit results in SSC. Restore `audit.dryRun: true` in the local values.

## Check the result

- A successful dry run must select the intended test application version.
- A live audit must show the expected result in SSC.
- Exit code `0` or a completed Job does not prove every audit succeeded. Check the action output for failures.
- The limit allows one application-version audit, which can contain many issues.
- Review SSC before repeating a failed or interrupted live audit.
- Save logs before replacing containers or deleting Jobs.

Use the [POC guide](bulk-audit-poc-guide.md) for private certificates, AWS secrets, CloudWatch, scheduling, and troubleshooting.
