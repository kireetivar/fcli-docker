# This Dockerfile defines the following targets for building fcli Docker images:
# - fcli-alpine
# - fcli-ubi9
# - fcli-scratch
# You can select between these variants by passing the --target option to the 'docker build'
# command, for example 'docker build . --target fcli-alpine'. If no target is specified, all
# targets may be built but the final image will correspond to the fcli-scratch target.
#
# In general, the fcli-scratch image is preferred to avoid having to deal with any CVEs reported
# on the base images, and potentially having to provide refreshed images for older fcli versions
# to fix such CVEs.
#
# We publish the following Linux images:
# - fcli-scratch: minimal scratch-based image (preferred for minimal attack surface)
# - fcli-ubi9: UBI9-based image providing a shell environment for running multiple fcli commands
# - fcli-ubi9-sc<version>: UBI9-based image with ScanCentral Client pre-installed (embedded JRE)
#
# The scratch image has minimal attack surface, while the UBI9 image provides a shell-based
# environment for running multiple fcli commands in sequence. The fcli-ubi9-sc variants extend
# fcli-ubi9 with a pre-installed ScanCentral Client (including an embedded JRE), so users can
# run 'scancentral' commands directly inside the container without any additional setup.
#
# Note: if there's demand, we can also publish alpine and/or other (like busybox) images that
# include a shell. Primary advantage is that this would allow for running a sequence of fcli
# commands in a single container invocation. Primary disadvantage is that users might expect
# to be able to run something like the following:
#   fcli tool sc-client install
#   scancentral package ...
#   submit scan request, ...
# However, the plain shell images don't include Java (required to run ScanCentral Client) nor
# any other build tools. Use the fcli-ubi9-sc variants for pre-installed ScanCentral Client,
# or mount a host directory and install via fcli from one of the other image variants.
# 
# Build Arguments:
# - FCLI_VERSION:       fcli version to download (required, e.g., "v3.14.0")
# - ALPINE_BASE:        Alpine base image (default: alpine:3.23.4, digest-pinned)
# - UBI_BASE:           Red Hat UBI base image (default: redhat/ubi9:9.8, digest-pinned)
# - AMAZON_LINUX_BASE:  Amazon Linux 2023 minimal base for the bulk-audit target (digest-pinned)
# - SC_CLIENT_VERSION:  ScanCentral Client version to install (required for fcli-ubi9-sc target)
# - ALLOW_STALE_TOOL_DEFINITIONS: set to "true" to fall back to the fcli bundled tool
#                       definitions when 'fcli tool definitions update' fails (default: false)
#
# All of the targets defined below have more or less the same structure:
# - Add fcli user to /etc/passwd
# - Add fcli executable to the image
# - Add /data (and /tmp for fcli-scratch) directories with 777 permissions to the image
# - Set WORKDIR to /data
# - Set FCLI_USER_HOME to /data
# - Set container user to fcli user
# - Define an appropriate entrypoint (fcli for fcli-scratch, shell for others)
#
# Regarding FCLI_USER_HOME, fcli uses user.home by default, but if the Docker container is being
# run as a different user through 'docker run -u <UID>:<GID>', user.home returns a directory 
# containing a '?' to represent unknown user name for the given UID, which causes issues. Fcli
# versions 2.5.4 and up allow for overriding user.home through FCLI_USER_HOME.

# ============================================================================
# Global build arguments (must be before any FROM to use in FROM statements)
# ============================================================================
ARG ALPINE_BASE=alpine:3.23.4@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11
ARG UBI_BASE=redhat/ubi9:9.8@sha256:1963e00991088221a3405be7eb315a3dbc0be0f1f7440f0bd537d481cf33c83e
ARG AMAZON_LINUX_BASE=public.ecr.aws/amazonlinux/amazonlinux:2023-minimal@sha256:158a9044f9dc0777f098b76c8b54346f6ed4560b9a6a416dec7a5ba3bc483af4

# ============================================================================
# Stage: fcli-downloader
# Downloads fcli binary and verifies signature
# ============================================================================
FROM ${ALPINE_BASE} AS fcli-downloader

# Install dependencies for download and signature verification
RUN apk add --no-cache curl openssl ca-certificates

# Build arguments
ARG FCLI_VERSION
ARG TARGETPLATFORM
ARG CACHE_BUST
# Optional archive pin, particularly useful for rolling development releases.
ARG FCLI_SHA256

# Validate FCLI_VERSION is provided
RUN test -n "$FCLI_VERSION" || (echo "ERROR: FCLI_VERSION build argument is required" && exit 1)

# Fortify public key for signature verification
RUN mkdir -p /tmp/keys && \
    echo "-----BEGIN PUBLIC KEY-----" > /tmp/keys/fortify.pub && \
    echo "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArij9U9yJVNc53oEMFWYp" >> /tmp/keys/fortify.pub && \
    echo "NrXUG1UoRZseDh/p34q1uywD70RGKKWZvXIcUAZZwbZtCu4i0UzsrKRJeUwqanbc" >> /tmp/keys/fortify.pub && \
    echo "woJvYanp6lc3DccXUN1w1Y0WOHOaBxiiK3B1TtEIH1cK/X+ZzazPG5nX7TSGh8Tp" >> /tmp/keys/fortify.pub && \
    echo "/uxQzUFli2mDVLqaP62/fB9uJ2joX9Gtw8sZfuPGNMRoc8IdhjagbFkhFT7WCZnk" >> /tmp/keys/fortify.pub && \
    echo "FH/4Co007lmXLAe12lQQqR/pOTeHJv1sfda1xaHtj4/Tcrq04Kx0ZmGAd5D9lA92" >> /tmp/keys/fortify.pub && \
    echo "8pdBbzoe/mI5/Sk+nIY3AHkLXB9YAaKJf//Wb1yiP1/hchtVkfXyIaGM+cVyn7AN" >> /tmp/keys/fortify.pub && \
    echo "VQIDAQAB" >> /tmp/keys/fortify.pub && \
    echo "-----END PUBLIC KEY-----" >> /tmp/keys/fortify.pub

# Determine platform-specific archive name.
# The fcli release publishes a single linux/amd64 archive, so fail fast on anything else
# instead of packaging a binary that cannot run on the target platform. BuildKit sets
# TARGETPLATFORM; otherwise fall back to the host architecture and refuse non-amd64 hosts.
RUN target="${TARGETPLATFORM:-}" && \
    if [ -z "$target" ]; then \
      case "$(uname -m)" in \
        x86_64|amd64) target=linux/amd64 ;; \
        *) echo "Cannot build on this host ($(uname -m)): the fcli Linux release only publishes an amd64 archive; pass --platform linux/amd64." && exit 1 ;; \
      esac; \
    fi && \
    case "$target" in \
      "linux/amd64") ARCHIVE="fcli-linux.tgz" ;; \
      *) echo "Unsupported platform: ${target}. The fcli Linux release only publishes an amd64 archive; refusing to build a mismatched image (use --platform linux/amd64)." && exit 1 ;; \
    esac && \
    echo "$ARCHIVE" > /tmp/archive_name

# Download fcli and signature
RUN echo "Archive SHA-256: ${FCLI_SHA256}; cache bust: ${CACHE_BUST}" && \
    ARCHIVE=$(cat /tmp/archive_name) && \
    DOWNLOAD_URL="https://github.com/fortify/fcli/releases/download/${FCLI_VERSION}/${ARCHIVE}" && \
    SIGNATURE_URL="${DOWNLOAD_URL}.rsa_sha256" && \
    echo "Downloading fcli from: $DOWNLOAD_URL" && \
    curl -fsSL --retry 3 --retry-all-errors --max-time 600 "$DOWNLOAD_URL" -o "/tmp/${ARCHIVE}" && \
    if [ -n "$FCLI_SHA256" ]; then echo "$FCLI_SHA256  /tmp/$ARCHIVE" | sha256sum -c -; fi && \
    echo "Downloading signature from: $SIGNATURE_URL" && \
    curl -fsSL --retry 3 --retry-all-errors --max-time 600 "$SIGNATURE_URL" -o "/tmp/${ARCHIVE}.rsa_sha256"

# Verify signature
RUN ARCHIVE=$(cat /tmp/archive_name) && \
    echo "Verifying signature..." && \
    openssl dgst -sha256 -verify /tmp/keys/fortify.pub \
      -signature "/tmp/${ARCHIVE}.rsa_sha256" "/tmp/${ARCHIVE}" && \
    echo "✓ Signature verification successful"

# Extract fcli binary
RUN ARCHIVE=$(cat /tmp/archive_name) && \
    mkdir -p /tmp/fcli-bin && \
    tar -xzf "/tmp/${ARCHIVE}" -C /tmp/fcli-bin && \
    chmod +x /tmp/fcli-bin/fcli && \
    /tmp/fcli-bin/fcli --version

# ============================================================================
# Stage: fcli-alpine
# Alpine-based image with shell access
# ============================================================================
FROM ${ALPINE_BASE} AS fcli-alpine

# Bring build args into this stage
ARG FCLI_VERSION
ARG ALPINE_BASE
LABEL org.opencontainers.image.source="https://github.com/fortify/fcli-docker" \
      org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.documentation="https://github.com/fortify/fcli#readme" \
      org.opencontainers.image.title="Fortify CLI (Alpine)" \
      org.opencontainers.image.description="Fortify CLI on Alpine Linux base image" \
      org.opencontainers.image.version="${FCLI_VERSION}" \
      com.fortify.fcli.version="${FCLI_VERSION}" \
      com.fortify.base.image="${ALPINE_BASE}"

RUN echo "fcli:x:10001:10001:fcli:/data:/sbin/nologin" >> /etc/passwd
COPY --from=fcli-downloader /tmp/fcli-bin/fcli /usr/bin/fcli
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY welcome*.txt /usr/share/fcli/
# Windows checkouts may retain CRLF despite .gitattributes. Normalize before exec.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod 0755 /usr/local/bin/docker-entrypoint.sh
ADD data.tgz /
WORKDIR /data
ENV FCLI_USER_HOME=/data
USER fcli
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/bin/sh"]

# ============================================================================
# Stage: fcli-ubi9
# Red Hat UBI9 standard image with bash and package manager
# Uses standard ubi9 (not minimal) to allow sub-images to install packages
# ============================================================================
FROM ${UBI_BASE} AS fcli-ubi9

# Bring build args into this stage
ARG FCLI_VERSION
ARG UBI_BASE
LABEL org.opencontainers.image.source="https://github.com/fortify/fcli-docker" \
      org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.documentation="https://github.com/fortify/fcli#readme" \
      org.opencontainers.image.title="Fortify CLI (UBI9)" \
      org.opencontainers.image.description="Fortify CLI on Red Hat Universal Base Image 9" \
      org.opencontainers.image.version="${FCLI_VERSION}" \
      com.fortify.fcli.version="${FCLI_VERSION}" \
      com.fortify.base.image="${UBI_BASE}"

RUN echo "fcli:x:10001:10001:fcli:/data:/sbin/nologin" >> /etc/passwd
COPY --from=fcli-downloader /tmp/fcli-bin/fcli /usr/bin/fcli
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY welcome*.txt /usr/share/fcli/
# Windows checkouts may retain CRLF despite .gitattributes. Normalize before exec.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod 0755 /usr/local/bin/docker-entrypoint.sh
ADD data.tgz /
WORKDIR /data
ENV FCLI_USER_HOME=/data
USER fcli
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/bin/bash"]

# ============================================================================
# Stage: fcli-ubi9-sc
# UBI9 image with fcli and ScanCentral Client (with embedded JRE) pre-installed.
# Extends fcli-ubi9; installs sc-client into /opt/fortify/sc-client and writes
# the fcli install descriptor into fcli state dir.
# Requires SC_CLIENT_VERSION build argument.
# ============================================================================
FROM fcli-ubi9 AS fcli-ubi9-sc

ARG SC_CLIENT_VERSION
ARG ALLOW_STALE_TOOL_DEFINITIONS=false
LABEL org.opencontainers.image.title="Fortify CLI (UBI9 + ScanCentral Client)" \
      org.opencontainers.image.description="Fortify CLI on Red Hat Universal Base Image 9, with ScanCentral Client pre-installed" \
      com.fortify.sc_client.version="${SC_CLIENT_VERSION}"

USER root
RUN test -n "$SC_CLIENT_VERSION" || \
      (echo "ERROR: SC_CLIENT_VERSION build argument is required for this target" && exit 1) && \
    # A stale tool definition could select an unverified sc-client patch release,
    # so fail instead of silently falling back to the bundled definitions.
    # Allow an explicit opt-out for offline or restricted build environments.
    if ! fcli tool definitions update; then \
      echo "ERROR: Could not update fcli tool definitions." >&2; \
      echo "A stale definition could select an unverified ScanCentral Client patch release." >&2; \
      if [ "${ALLOW_STALE_TOOL_DEFINITIONS}" != "true" ]; then \
        echo "Re-run with --build-arg ALLOW_STALE_TOOL_DEFINITIONS=true to fall back to the definitions bundled with fcli." >&2; \
        exit 1; \
      fi; \
      echo "WARNING: ALLOW_STALE_TOOL_DEFINITIONS=true; using the tool definitions bundled with fcli." >&2; \
    fi && \
    fcli tool sc-client install \
      --version "$SC_CLIENT_VERSION" \
      --install-dir /opt/fortify/sc-client \
      --with-jre && \
    chown -R 10001:10001 /opt/fortify/sc-client "${FCLI_USER_HOME}/.fortify"
ENV SC_CLIENT_HOME=/opt/fortify/sc-client
ENV SC_CLIENT_CMD=/opt/fortify/sc-client/bin/scancentral
ENV PATH="/opt/fortify/sc-client/bin:${PATH}"
USER fcli

# Normalize the runner in the build stage; the minimal runtime needs no sed.
FROM fcli-downloader AS bulk-audit-script
COPY bulk-audit.sh /tmp/bulk-audit.sh
RUN sed -i 's/\r$//' /tmp/bulk-audit.sh

# ============================================================================
# Stage: fcli-bulk-audit
# One-shot runner for SSC/Aviator bulk audits. No credentials in the image.
# ============================================================================
FROM ${AMAZON_LINUX_BASE} AS fcli-bulk-audit
ARG FCLI_VERSION
ARG FCLI_SHA256
ARG RUNNER_VERSION=development
LABEL org.opencontainers.image.title="Fortify CLI Bulk Audit" \
      org.opencontainers.image.description="One-shot SSC and Aviator bulk-audit runner" \
      org.opencontainers.image.source="https://github.com/fortify/fcli-docker" \
      org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${RUNNER_VERSION}" \
      com.fortify.fcli.version="${FCLI_VERSION}" \
      com.fortify.fcli.archive.sha256="${FCLI_SHA256}"
USER 0:0
SHELL ["/bin/bash", "-c"]
COPY --from=fcli-downloader /tmp/fcli-bin/fcli /usr/bin/fcli
COPY --from=bulk-audit-script /tmp/bulk-audit.sh /usr/local/bin/fcli-bulk-audit
RUN test -n "$FCLI_SHA256" || { echo "ERROR: FCLI_SHA256 is required for the bulk-audit image." >&2; exit 1; } && \
    chmod 0755 /usr/local/bin/fcli-bulk-audit && \
    echo "fcli:x:10001:10001:fcli:/work:/sbin/nologin" >> /etc/passwd && \
    echo "fcli:x:10001:" >> /etc/group && \
    for file in /usr/bin/* /usr/sbin/*; do if [[ -f $file && ( -u $file || -g $file ) ]]; then chmod a-s "$file"; fi; done && \
    mkdir -p /work /logs && chown 10001:10001 /work /logs && chmod 0700 /logs
USER 10001:10001
# Verify packaged action interfaces without authenticating or contacting SSC.
RUN /usr/local/bin/fcli-bulk-audit --check-image
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/fcli-bulk-audit"]
CMD []

# ============================================================================
# Stage: fcli-scratch
# Minimal scratch-based image (default/preferred)
# ============================================================================
FROM scratch AS fcli-scratch

# OCI labels - common across all images
ARG FCLI_VERSION
LABEL org.opencontainers.image.source="https://github.com/fortify/fcli-docker" \
      org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.documentation="https://github.com/fortify/fcli#readme" \
      org.opencontainers.image.title="Fortify CLI (Scratch)" \
      org.opencontainers.image.description="Fortify CLI on minimal scratch image" \
      org.opencontainers.image.version="${FCLI_VERSION}" \
      com.fortify.fcli.version="${FCLI_VERSION}" \
      com.fortify.base.image="scratch"

ADD minimal-passwd /etc/passwd
COPY --from=fcli-downloader /tmp/fcli-bin/fcli /usr/bin/fcli
ADD tmp.tgz /
ADD data.tgz /
WORKDIR /data
ENV FCLI_USER_HOME=/data
USER fcli
ENTRYPOINT ["/usr/bin/fcli"]
CMD ["-h"]
