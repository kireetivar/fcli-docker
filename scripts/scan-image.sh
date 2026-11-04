#!/usr/bin/env bash
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
archive=$(realpath "${1:?Usage: scan-image.sh IMAGE_ARCHIVE REPORT_DIRECTORY}")
mkdir -p "${2:?Specify a report directory}" .cache/trivy
reports=$(realpath "$2")
cache=$(realpath .cache/trivy)
if [[ ${OSTYPE:-} == msys* ]]; then
    archive=$(cygpath -m "$archive")
    reports=$(cygpath -m "$reports")
    cache=$(cygpath -m "$cache")
fi
scanner=(docker run --rm
    --mount "type=bind,src=$archive,dst=/image.tar,readonly"
    --mount "type=bind,src=$reports,dst=/reports"
    --mount "type=bind,src=$cache,dst=/cache"
    aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
    --cache-dir /cache image --input /image.tar --scanners vuln)
"${scanner[@]}" --format json --output /reports/vulnerabilities.json
"${scanner[@]}" --skip-db-update --severity CRITICAL --exit-code 1
"${scanner[@]}" --skip-db-update --severity HIGH --ignore-unfixed --exit-code 1
