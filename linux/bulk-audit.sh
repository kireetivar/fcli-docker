#!/usr/bin/env bash
# All arguments are assembled as arrays. Never evaluate configuration as shell code.
set +x
set -Eeuo pipefail
umask 077

if [[ ${1:-} == --help ]]; then
    printf '%s\n' 'Configure this one-shot runner using BULK_AUDIT_*, SSC_URL, AVIATOR_URL and AVIATOR_TENANT.' \
        'See docs/bulk-audit-poc.md. --check-image checks CLI compatibility without credentials.'
    exit 0
fi
if (( $# > 1 )) || { (( $# == 1 )) && [[ $1 != --check-image ]]; }; then
    echo 'Unsupported runner argument; see --help.' >&2
    exit 64
fi

duration=${BULK_AUDIT_TIMEOUT_SECONDS:-3600}
if [[ ! $duration =~ ^[1-9][0-9]{0,5}$ ]]; then
    echo 'BULK_AUDIT_TIMEOUT_SECONDS must be a positive integer (at most six digits).' >&2
    exit 64
fi
# Bound login as well as audit time. GNU timeout returns 124 on deadline expiry.
if [[ ${BULK_AUDIT_UNDER_TIMEOUT:-} != 1 ]]; then
    export BULK_AUDIT_UNDER_TIMEOUT=1
    exec timeout --signal=TERM --kill-after=30s "$duration" bash "$0" "$@"
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
phase=validation
child_pid=
state_dir=
scratch_dir=
action=${BULK_AUDIT_ACTION:-bulkaudit-sast}
dry_run=${BULK_AUDIT_DRY_RUN:-true}
max_audits=${BULK_AUDIT_MAX_AUDITS:-1}
started=$SECONDS

# Values passed to event() are fixed messages or validated identifiers/numbers.
event() {
    printf '{"schema_version":1,"time":"%s","run_id":"%s","event":"%s","phase":"%s","detail":"%s","elapsed_seconds":%d,"exit_code":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$run_id" "$1" "$phase" "${2:-}" \
        "$((SECONDS-started))" "${3:-null}" >&2
}
fail() { event configuration_error "$1"; exit 64; }
finish() {
    local rc=$?
    trap - EXIT
    # Both directories are private mktemp allocations, never configuration paths.
    [[ -z $scratch_dir ]] || rm -rf -- "$scratch_dir" || true
    [[ -z $state_dir ]] || rm -rf -- "$state_dir" || true
    unset ssc_token
    event finished "" "$rc"
    exit "$rc"
}
stop() {
    local code=$1
    trap '' TERM INT
    if [[ -n $child_pid ]]; then
        kill -TERM "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    event interrupted
    exit "$code"
}
trap finish EXIT
trap 'stop 143' TERM
trap 'stop 130' INT

prepare_session() {
    local name work_root
    # Do not inherit a host's session selectors, credentials, or action defaults.
    for name in ${!FCLI_DEFAULT_@}; do unset "$name"; done
    export FCLI_DEFAULT_PROGRESS=simple
    export NO_COLOR=1

    work_root=${BULK_AUDIT_WORK_ROOT:-/work}
    [[ -d $work_root && -w $work_root ]] || fail work_directory_not_writable
    state_dir=$(mktemp -d "$work_root/session.XXXXXXXX")
    scratch_dir=$(mktemp -d "${TMPDIR:-/tmp}/bulkaudit.XXXXXXXX")
    export FCLI_USER_HOME="$state_dir/home"
    # Let fcli derive its directory layout from the private home. Independent
    # directory overrides can violate its home-path validation.
    unset FCLI_DATA_DIR FCLI_CONFIG_DIR FCLI_STATE_DIR FORTIFY_DATA_DIR FCLI_HOME
    export TMPDIR="$scratch_dir"
    mkdir -p "$FCLI_USER_HOME"
    cd "$scratch_dir"
}

check_image() {
    local candidate help_text required
    fcli --version
    for candidate in bulkaudit bulkaudit-sast bulkaudit-dast; do
        help_text=$(fcli ssc action help "$candidate" 2>&1) || {
            event incompatible_image "$candidate"; return 69;
        }
        for required in --dry-run --max-audits --filter; do
            [[ $help_text == *"$required"* ]] || { event incompatible_image "$candidate"; return 69; }
        done
        if [[ $candidate != bulkaudit-dast && $help_text != *--add-aviator-tags* ]]; then
            event incompatible_image "$candidate"; return 69
        fi
    done
    event image_compatible
}

validate_config() {
    local name value
    case "$action" in bulkaudit|bulkaudit-sast|bulkaudit-dast) ;; *) fail invalid_action ;; esac
    case "$dry_run" in true|false) ;; *) fail invalid_dry_run ;; esac
    ssc_insecure=${SSC_INSECURE:-false}
    case "$ssc_insecure" in true|false) ;; *) fail invalid_ssc_insecure ;; esac
    [[ $max_audits =~ ^[1-9][0-9]{0,5}$ ]] || fail invalid_max_audits
    for name in SSC_URL AVIATOR_URL AVIATOR_TENANT; do
        value=${!name:-}
        [[ -n ${value//[[:space:]]/} && $value != *CHANGE_ME* ]] || fail "missing_$name"
    done
    filter=${BULK_AUDIT_FILTER:-}
    [[ $filter != *CHANGE_ME* ]] || fail invalid_BULK_AUDIT_FILTER
    for name in SSC_URL AVIATOR_URL; do
        value=${!name}
        [[ $value == https://* && $value != *'@'* && $value != *'?'* && $value != *'#'* && $value != *[[:space:]]* ]] || fail "invalid_$name"
    done
}

# Tokens are scalar values. Preserve PEM files without any transformation.
read_token() {
    local token
    token=$(<"$1")
    while [[ $token == *$'\r' || $token == *$'\n' ]]; do token=${token%?}; done
    [[ -n $token && $token != *[[:space:]]* ]] || fail "invalid_${2}_file"
    printf '%s' "$token"
}

prepare_credentials() {
    local ssc_file aviator_file path
    ssc_file=${SSC_TOKEN_FILE:-/run/secrets/ssc-token}
    aviator_file=${AVIATOR_TOKEN_FILE:-/run/secrets/aviator-token}
    admin_file=${AVIATOR_PRIVATE_KEY_FILE:-/run/secrets/aviator-private-key}
    for path in "$ssc_file" "$aviator_file" "$admin_file"; do
        [[ $path == /* && -f $path && -r $path && -s $path ]] || fail unreadable_or_empty_secret_file
    done
    # fcli needs an Aviator token file without trailing line endings.
    ssc_token=$(read_token "$ssc_file" ssc_token)
    aviator_token_file=$scratch_dir/aviator-token
    read_token "$aviator_file" aviator_token > "$aviator_token_file"
    if [[ -n ${FCLI_TRUSTSTORE:-} ]]; then
        [[ -r $FCLI_TRUSTSTORE && -s $FCLI_TRUSTSTORE ]] || fail unreadable_truststore
    fi
    if [[ -n ${FCLI_TRUSTSTORE_PWD_FILE:-} ]]; then
        [[ -r $FCLI_TRUSTSTORE_PWD_FILE && -s $FCLI_TRUSTSTORE_PWD_FILE ]] || fail unreadable_truststore_password
        FCLI_TRUSTSTORE_PWD=$(<"$FCLI_TRUSTSTORE_PWD_FILE")
        export FCLI_TRUSTSTORE_PWD
    fi
}

run_cli() {
    phase=$1
    shift
    local rc=0
    # fcli truncates --log-file on each invocation. Keep one file per phase.
    export FCLI_DEFAULT_LOG_FILE="$log_dir/$phase.log"
    : > "$FCLI_DEFAULT_LOG_FILE" || { event log_file_failed; exit 74; }
    event phase_started
    if [[ $phase == ssc_login ]]; then
        # The secret is an environment value only in this child, never an argv value.
        (export FCLI_DEFAULT_SSC_SESSION_LOGIN_TOKEN="$ssc_token"; exec fcli "$@") &
    else
        fcli "$@" &
    fi
    child_pid=$!
    wait "$child_pid" || rc=$?
    child_pid=
    if (( rc != 0 )); then
        event command_failed "" "$rc"
        exit "$rc"
    fi
    event phase_completed
}

prepare_logs() {
    local log_root
    # Retain diagnostics outside the disposable credential/session directories.
    # A random suffix also prevents collisions between containers sharing a volume.
    log_root=${BULK_AUDIT_LOG_DIR:-/logs}
    [[ $log_root == /* && -d $log_root && -w $log_root ]] || fail log_directory_not_writable
    log_dir=$(mktemp -d "$log_root/$run_id.XXXXXXXX") || { event log_file_failed; exit 74; }
    printf 'fcli diagnostic logs: %s\n' "$log_dir" >&2
    # fcli's console appender shows WARN/ERROR, while INFO diagnostics stay in files.
    # Keep direct command output visible, including login failures and audit progress.
    export FCLI_DEFAULT_LOG_LEVEL=INFO
    export FCLI_DEFAULT_LOG_MASK=high
}

main() {
    local -a ssc_login_args args
    prepare_session
    if [[ ${1:-} == --check-image ]]; then
        phase=compatibility
        check_image
        exit 0
    fi
    validate_config
    prepare_credentials
    prepare_logs
    event started "action=$action dry_run=$dry_run max_audits=$max_audits ssc_insecure=$ssc_insecure"
    ssc_login_args=(ssc session login --url "$SSC_URL" --disable sc-sast,sc-dast)
    if [[ $ssc_insecure == true ]]; then ssc_login_args+=(-k); fi
    run_cli ssc_login "${ssc_login_args[@]}"
    unset ssc_token
    run_cli aviator_login aviator session login --url "$AVIATOR_URL" --token "file:$aviator_token_file"
    run_cli aviator_admin aviator admin-config create --url "$AVIATOR_URL" --tenant "$AVIATOR_TENANT" --private-key "file:$admin_file"
    args=(ssc action run "$action" "--dry-run=$dry_run" "--max-audits=$max_audits" --progress=simple)
    # Omit blank filters so fcli uses its default of no inclusion filtering.
    if [[ -n ${filter//[[:space:]]/} ]]; then args+=("--filter=$filter"); fi
    if [[ $action != bulkaudit-dast ]]; then args+=(--add-aviator-tags); fi
    if [[ -n ${BULK_AUDIT_EXCLUDE_FILTER:-} ]]; then args+=("--exclude-filter=$BULK_AUDIT_EXCLUDE_FILTER"); fi
    run_cli audit "${args[@]}"
    event result_notice process_exit_does_not_guarantee_all_audits_succeeded
}

main "$@"
