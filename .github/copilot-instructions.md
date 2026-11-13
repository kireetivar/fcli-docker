# fcli-docker — Copilot Instructions

Docker image definitions for fcli. General images include `fcli-scratch`, `fcli-ubi9`, and ScanCentral variants. The separate `fcli-bulk-audit` target runs the three supported SSC/Aviator actions on Amazon Linux 2023 Minimal.

## Structure

- `linux/` — Linux Dockerfiles and build scripts
- `windows/` — Windows Dockerfiles and build scripts
- `.github/workflows/` — CI/CD for building and publishing images to Docker Hub (`fortifydocker/fcli`)

## Key Rules

- Images must stay minimal; do not add unnecessary packages
- The scratch image has no shell — only direct fcli entrypoint
- Test both variants when changing shared build logic

## Release and audit contracts

- `bulk-audit-release.json` owns audit-runner release defaults. Run `python scripts/sync-bulk-release.py` after updating it.
- `linux/bulk-audit.sh` owns the three action definitions and their fcli options.
- `scripts/release.py` validates general-image release inputs and selects archive digests.
- Release tests and scans use a derived Docker archive. Publication copies the original attested OCI archive after all required checks pass.
- Use `docs/bulk-audit-guide.md`, `docs/bulk-audit-runbook.md`, and `docs/bulk-audit-release.md` for current instructions. Dated scan reports are historical evidence.
