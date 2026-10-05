#!/usr/bin/env bash
# Run from any directory on a host with a running Linux Docker engine.
set -Eeuo pipefail
# Prevent Git Bash from rewriting Linux container mount paths on Windows.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
version=${FCLI_VERSION:-dev_feat.v3.x.aviator.26.4}
sha=${FCLI_SHA256:-46ff9d7f939d4ca39b114be85c4a82d9df2d54bc088c289271134f4a27a13bc0}
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
