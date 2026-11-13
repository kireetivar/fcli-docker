#!/usr/bin/env bash
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
image=${1:?Usage: test-release-image.sh IMAGE VARIANT}
variant=${2:?Specify an image variant}
case "$variant" in
    ubi9-sc*)
        docker run --rm --network none "$image" sh -c \
            'test -n "$SC_CLIENT_HOME" && test -x "$SC_CLIENT_HOME/bin/scancentral"'
        ;;
    scratch|ubi9|alpine)
        command=(fcli)
        [[ $variant != scratch ]] || command=()
        docker run --rm --network none "$image" "${command[@]}" --version
        mkdir -p .cache
        work=$(mktemp -d .cache/release-image.XXXXXXXX)
        work=$(cd "$work" && pwd -P)
        case "$work" in
            "$(pwd -P)/.cache/release-image."*) ;;
            *) echo 'Temporary directory is outside the workspace' >&2; exit 64 ;;
        esac
        trap 'rm -rf -- "$work"' EXIT
        bind_work=$work
        if [[ ${OSTYPE:-} == msys* ]]; then bind_work=$(cygpath -m "$work"); fi
        docker run --rm -u "$(id -u):$(id -g)" -v "$bind_work:/data" \
            "$image" "${command[@]}" tool sc-client install
        test -f "$work/fortify/tools/bin/scancentral"
        ;;
    *) echo 'Unsupported image variant' >&2; exit 64 ;;
esac
