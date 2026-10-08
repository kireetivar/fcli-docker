#!/usr/bin/env bash
# Run from any directory on a host with a running Linux Docker engine.
set -Eeuo pipefail
# Prevent Git Bash from rewriting Linux container mount paths on Windows.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
context=linux
case "${1:-}" in
    '') (( $# == 0 )) || exit 64 ;;
    --windows-checkout)
        (( $# == 1 )) || exit 64
        # Keep the Docker context relative for Git Bash with path conversion off.
        mkdir -p .cache
        context=$(mktemp -d .cache/smoke-images.XXXXXXXX)
        context_path=$(cd "$context" && pwd -P)
        case "$context_path" in
            "$(pwd -P)/.cache/smoke-images."*) ;;
            *) echo 'Temporary context is outside the workspace' >&2; exit 64 ;;
        esac
        trap 'rm -rf -- "$context_path"' EXIT
        cp -R linux/. "$context/"
        # Reproduce existing Windows files and restrictive checkout permissions.
        for script in docker-entrypoint.sh bulk-audit.sh; do
            awk '{ sub(/\r$/, ""); printf "%s\r\n", $0 }' "linux/$script" > "$context/$script"
            chmod 0600 "$context/$script"
        done
        ;;
    *) echo 'Usage: bash tests/smoke-images.sh [--windows-checkout]' >&2; exit 64 ;;
esac
# Read release defaults as data. Do not execute a configuration file.
defaults=deploy/compose/.env.example
version=${FCLI_VERSION:-$(sed -n 's/^FCLI_VERSION=//p' "$defaults" | tr -d '\r')}
sha=${FCLI_SHA256:-$(sed -n 's/^FCLI_SHA256=//p' "$defaults" | tr -d '\r')}
[[ -n $version && $sha =~ ^[a-f0-9]{64}$ ]] || { echo 'Invalid release defaults' >&2; exit 64; }
for target in fcli-scratch fcli-ubi9 fcli-bulk-audit; do
    docker build --platform linux/amd64 --target "$target" \
        --build-arg "FCLI_VERSION=$version" --build-arg "FCLI_SHA256=$sha" \
        -t "fcli-test:$target" "$context"
done
docker run --rm --network none fcli-test:fcli-scratch --version
docker run --rm --network none fcli-test:fcli-ubi9 fcli --version
flags=(--rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges
    --tmpfs "/work:rw,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700"
    --tmpfs "/tmp:rw,nosuid,nodev,size=1g,uid=10001,gid=10001,mode=0700")
docker run "${flags[@]}" --entrypoint /bin/bash fcli-test:fcli-bulk-audit \
    -c 'test "$(id -u)" = 10001 && test -z "$(find /usr/bin /usr/sbin -xdev -type f -perm /6000 -print)"'
docker run "${flags[@]}" fcli-test:fcli-bulk-audit --check-image
code=0
docker run "${flags[@]}" fcli-test:fcli-bulk-audit || code=$?
[[ $code == 64 ]] || { echo "Expected missing-configuration exit 64, got $code" >&2; exit 1; }

# Docker must initialize log-volume ownership for the non-root, read-only image.
# A second container demonstrates retention across container recreation.
(
    log_volume=$(docker volume create)
    trap 'docker volume rm "$log_volume" >/dev/null' EXIT
    docker run "${flags[@]}" -v "$log_volume:/logs" --entrypoint /bin/bash fcli-test:fcli-bulk-audit \
        -c 'test -w /logs && umask 077 && printf "%s\n" retained-diagnostic > /logs/smoke.log'
    docker run "${flags[@]}" -v "$log_volume:/logs" --entrypoint /bin/bash fcli-test:fcli-bulk-audit \
        -c 'test "$(cat /logs/smoke.log)" = retained-diagnostic'
)
