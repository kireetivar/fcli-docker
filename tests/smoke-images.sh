#!/usr/bin/env bash
# Run from any directory on a host with a running Linux Docker engine.
set -Eeuo pipefail
# Prevent Git Bash from rewriting Linux container mount paths on Windows.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
version=${FCLI_VERSION:-v3.28.0}
sha=${FCLI_SHA256:-f1c272513e24c204abd700037d373b831131520e805b2b8409025e619f8b04f6}
for target in fcli-scratch fcli-ubi9 fcli-bulk-audit; do
    docker build --platform linux/amd64 --target "$target" \
        --build-arg "FCLI_VERSION=$version" --build-arg "FCLI_SHA256=$sha" \
        -t "fcli-test:$target" linux
done
docker run --rm --network none fcli-test:fcli-scratch --version
docker run --rm --network none fcli-test:fcli-ubi9 fcli --version
flags=(--rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges
    --tmpfs /work:rw,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700
    --tmpfs /tmp:rw,nosuid,nodev,size=1g,uid=10001,gid=10001,mode=0700)
docker run "${flags[@]}" fcli-test:fcli-bulk-audit --check-image
code=0
docker run "${flags[@]}" fcli-test:fcli-bulk-audit || code=$?
[[ $code == 64 ]] || { echo "Expected missing-configuration exit 64, got $code" >&2; exit 1; }
