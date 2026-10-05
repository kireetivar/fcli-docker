# fcli Docker Images

This directory contains Dockerfiles and build configurations for creating fcli Docker images.

## Bulk-audit POC

The [bulk-audit runbook](docs/bulk-audit-poc.md) covers the dedicated runner image,
Docker Compose, and the Helm Job/CronJob chart. Start with a SAST dry run, then
review the selection before performing at most one live audit. Credentials are
mounted as files; host fcli sessions are not required. The POC uses a pinned Aviator
development build because the latest stable release checked does not contain the
split SAST/DAST actions. See the runbook for validation status and limitations.

For the purpose of Compose versus Helm and secret-management options, see the
[deployment design](docs/bulk-audit-deployment.md).

## Available Images

### Published Images (Docker Hub: `fortifydocker/fcli`)

#### 1. **fcli-scratch** (Primary/Recommended)
- **Base:** `scratch` (minimal, no OS layer)
- **Size:** ~15-20 MB
- **Use case:** Single command execution, CI/CD pipelines
- **Security:** Minimal attack surface, no CVEs from base OS
- **Shell:** None (direct fcli entrypoint)

```bash
# Run single command
docker run --rm fortifydocker/fcli:latest --version

# With volume mount for data persistence
docker run --rm -v $(pwd)/data:/data fortifydocker/fcli:latest tool sc-client install
```

#### 2. **fcli-ubi9** (Shell-based)
- **Base:** Red Hat Universal Base Image 9 (standard, not minimal)
- **Size:** ~200-250 MB
- **Use case:** Interactive usage, shell scripts, base for custom images requiring additional packages
- **Security:** Red Hat maintained base, regular security updates
- **Package Manager:** yum/dnf available for installing additional tools
- **Shell:** `/bin/bash`

```bash
# Interactive shell
docker run -it --rm fortifydocker/fcli:latest-ubi9 /bin/bash

# Run multiple commands
docker run --rm fortifydocker/fcli:latest-ubi9 bash -c "fcli --version && fcli tool list"
```

#### 3. **fcli-ubi9-sc\<version\>** (UBI9 + ScanCentral Client)
- **Base:** `fcli-ubi9` (inherits all UBI9 image features)
- **Size:** ~500-600 MB (includes embedded JRE and ScanCentral Client)
- **Use case:** Running ScanCentral Client commands directly inside the container without any additional setup
- **Security:** Same as UBI9 image; sc-client and embedded JRE are pre-installed at a fixed path
- **Shell:** `/bin/bash`
- **Pre-installed tools:** ScanCentral Client at `/opt/fortify/sc-client` with embedded JRE
- **Environment variables set** (matching `fcli tool sc-client env` output):
  - `SC_CLIENT_HOME=/opt/fortify/sc-client`
  - `SC_CLIENT_CMD=/opt/fortify/sc-client/bin/scancentral`
  - `PATH` is prepended with `/opt/fortify/sc-client/bin`

```bash
# Run scancentral directly (no installation needed)
docker run --rm fortifydocker/fcli:latest-ubi9-sc25.4 scancentral --version

# Use fcli tool env to source environment (already set, but useful for scripts)
docker run --rm fortifydocker/fcli:latest-ubi9-sc25.4 bash -c "\
  fcli tool sc-client env shell && scancentral package ..."
```

> **Note:** The sc-client install descriptor is stored in the image at
> `/data/.fortify/tool-data/sc-client/`, so `fcli tool sc-client env` and related
> fcli commands can locate the pre-installed sc-client automatically.

### Test-Only Images (Not Published)

#### 3. **fcli-alpine**
- Built and tested in CI/CD but not published
- **Base:** Alpine Linux
- **Shell:** `/bin/sh`
- Can be built locally if needed

#### 4. **fcli-windows**
- Built and tested on Windows runners
- **Base:** Windows Server Core ltsc2022
- **Shell:** PowerShell
- Not published; prototype only
- Provides full PowerShell and package management capability

## Image Tags

All tag patterns apply to both scratch and ubi9 images. UBI9 tags carry a `-ubi9` suffix;
UBI9+ScanCentral Client tags carry a `-ubi9-sc{scVersion}` suffix.

| Tag pattern | Description | Example |
|---|---|---|
| `latest` | Latest stable release (scratch) | `fortifydocker/fcli:latest` |
| `latest-ubi9` | Latest stable release (UBI9) | `fortifydocker/fcli:latest-ubi9` |
| `{version}` | Specific fcli version (scratch) | `fortifydocker/fcli:3.15.0` |
| `{version}-ubi9` | Specific fcli version (UBI9) | `fortifydocker/fcli:3.15.0-ubi9` |
| `{version}-ubi9-sc{scVersion}` | UBI9 with ScanCentral Client pre-installed | `fortifydocker/fcli:3.15.0-ubi9-sc25.4` |
| `{major}.{minor}` | Latest patch for minor version (scratch) | `fortifydocker/fcli:3.15` |
| `{major}.{minor}-ubi9` | Latest patch for minor version (UBI9) | `fortifydocker/fcli:3.15-ubi9` |
| `{major}.{minor}-ubi9-sc{scVersion}` | Latest patch for minor version (UBI9+sc-client) | `fortifydocker/fcli:3.15-ubi9-sc25.4` |
| `{major}` | Latest release for major version (scratch) | `fortifydocker/fcli:3` |
| `{major}-ubi9` | Latest release for major version (UBI9) | `fortifydocker/fcli:3-ubi9` |
| `{major}-ubi9-sc{scVersion}` | Latest release for major version (UBI9+sc-client) | `fortifydocker/fcli:3-ubi9-sc25.4` |
| `{version}-{timestamp}` | Immutable timestamped tag (scratch) | `fortifydocker/fcli:3.15.0-20260319120000` |
| `{version}-ubi9-{timestamp}` | Immutable timestamped tag (UBI9) | `fortifydocker/fcli:3.15.0-ubi9-20260319120000` |
| `{version}-ubi9-sc{scVersion}-{timestamp}` | Immutable timestamped tag (UBI9+sc-client) | `fortifydocker/fcli:3.15.0-ubi9-sc25.4-20260319120000` |

> **Note on ScanCentral Client versions:** `{scVersion}` is in `YY.Q` form (e.g., `25.4`).
> The image contains the latest available patch release within that quarter at the time it was
> built. Timestamped tags are immutable; the floating `{version}` and `{major}.{minor}` tags
> are updated when images are refreshed (e.g., for base-image CVE fixes).

## Building Locally

### Prerequisites
- Docker 20.10+ or Docker Desktop
- Docker Buildx (for multi-platform builds)

### Linux Images

```bash
cd linux

# Build scratch image (default)
docker build . \
  --build-arg FCLI_VERSION=v3.15.0 \
  --target fcli-scratch \
  -t fcli:scratch

# Build UBI9 image
docker build . \
  --build-arg FCLI_VERSION=v3.15.0 \
  --target fcli-ubi9 \
  -t fcli:ubi9

# Build UBI9 image with ScanCentral Client 25.4 pre-installed
docker build . \
  --build-arg FCLI_VERSION=v3.15.0 \
  --build-arg SC_CLIENT_VERSION=25.4 \
  --target fcli-ubi9-sc \
  -t fcli:ubi9-sc25.4

# Build Alpine image
docker build . \
  --build-arg FCLI_VERSION=v3.15.0 \
  --target fcli-alpine \
  -t fcli:alpine

# Build with custom base images
docker build . \
  --build-arg FCLI_VERSION=v3.15.0 \
  --build-arg ALPINE_BASE=alpine:3.23.0 \
  --build-arg UBI_BASE=redhat/ubi9:9.7 \
  --target fcli-scratch \
  -t fcli:scratch
```

### Windows Images

```powershell
cd windows

docker build . `
  --build-arg FCLI_VERSION=v3.15.0 `
  --target fcli-ltsc2022 `
  -t fcli:windows
```

## Usage Examples

### Basic Command Execution

```bash
# Check version
docker run --rm fortifydocker/fcli:latest --version

# List available tools
docker run --rm fortifydocker/fcli:latest tool list

# Get help
docker run --rm fortifydocker/fcli:latest --help
```

### Data Persistence

```bash
# Create data directory
mkdir -p ./fcli-data

# Install tools with persistent storage
docker run --rm \
  -v $(pwd)/fcli-data:/data \
  fortifydocker/fcli:latest \
  tool sc-client install

# Tools are now available in ./fcli-data/fortify/tools/
ls -la ./fcli-data/fortify/tools/
```

### CI/CD Integration

#### GitHub Actions

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    container:
      image: fortifydocker/fcli:latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Run fcli commands
        run: |
          fcli --version
          fcli tool sc-client install
```

Or use the UBI9+ScanCentral Client image to skip the install step:

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    container:
      image: fortifydocker/fcli:latest-ubi9-sc25.4
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Run scancentral
        run: |
          scancentral --version
          scancentral package -bt mvn -o package.zip
```

#### GitLab CI

```yaml
# Plain UBI9 — install sc-client at runtime
scan:
  image: fortifydocker/fcli:latest-ubi9
  script:
    - fcli --version
    - fcli tool sc-client install

# Or use the pre-installed sc-client variant
scan-with-sc:
  image: fortifydocker/fcli:latest-ubi9-sc25.4
  script:
    - scancentral --version
    - scancentral package -bt mvn -o package.zip
```

#### Jenkins Pipeline

```groovy
pipeline {
    agent {
        docker {
            image 'fortifydocker/fcli:latest'
            args '-v $HOME/.fortify:/data'
        }
    }
    stages {
        stage('Setup') {
            steps {
                sh 'fcli --version'
                sh 'fcli tool sc-client install'
            }
        }
    }
}
```

### Running as Different User

```bash
# Run as specific UID/GID
docker run --rm \
  -u $(id -u):$(id -g) \
  -v $(pwd)/data:/data \
  fortifydocker/fcli:latest \
  tool list

# The FCLI_USER_HOME environment variable handles user home directory resolution
```

### Interactive Shell and ScanCentral Client (UBI9 variants)

```bash
# Start interactive bash session (plain UBI9)
docker run -it --rm \
  -v $(pwd)/data:/data \
  fortifydocker/fcli:latest-ubi9 \
  /bin/bash

# Inside container:
fcli --version
fcli tool sc-client install
fcli tool list

# UBI9 has package manager — install additional tools if needed
yum install -y jq
exit

# Use the UBI9+sc-client image to run scancentral without any installation
docker run --rm \
  -v $(pwd)/data:/data \
  fortifydocker/fcli:latest-ubi9-sc25.4 \
  scancentral package -bt mvn -o package.zip
```

## Architecture & Security

### Signature Verification

All Docker builds (Linux and Windows):
1. Download fcli binary from GitHub releases
2. Download corresponding `.rsa_sha256` signature file
3. Verify signature using Fortify's public RSA key
4. Build fails if signature verification fails

**Implementation details:**
- **Linux**: Uses OpenSSL in Alpine-based downloader stage
- **Windows**: Uses .NET 8 SDK image for downloader stage (has modern crypto APIs), then copies verified fcli to Server Core final image

Public key is embedded in Dockerfiles and matches the key used by `fortify-setup-js`.

### Multi-Stage Build Process

```
┌─────────────────────────┐
│  fcli-downloader        │  Alpine-based stage
│  - Downloads fcli       │  - Installs curl, openssl
│  - Verifies signature   │  - Validates signature
│  - Extracts binary      │  - Outputs /tmp/fcli-bin/fcli
└─────────┬───────────────┘
          │
          ├──────────────────────────────────────────────┐
          │                                              │
┌─────────▼─────────┐   ┌──────────────▼────────────┐   │
│  fcli-scratch     │   │  fcli-ubi9                │   │
│  Copies from      │   │  Standard UBI9 (not       │   │
│  downloader       │   │  minimal) for package     │   │
└───────────────────┘   │  installation support     │   │
                        └──────────────┬────────────┘   │
                                       │                │
                        ┌──────────────▼────────────┐   │
                        │  fcli-ubi9-sc             │   │
                        │  Extends fcli-ubi9;       │   │
                        │  installs ScanCentral     │   │
                        │  Client + embedded JRE    │◄──┘
                        └───────────────────────────┘
```

### Security Features

- ✅ **Non-root user:** All images run as UID 10001 (user `fcli`)
- ✅ **Signature verification:** RSA SHA256 verification before build
- ✅ **Minimal attack surface:** Scratch image has no OS layer
- ✅ **Pinned base images:** Default base images are pinned to specific versions
- ✅ **SBOM & Provenance:** GitHub Actions build includes SBOM and attestation
- ✅ **No secrets:** No credentials or tokens embedded in images

### OCI Labels

All images include standard OCI labels:
- `org.opencontainers.image.source`
- `org.opencontainers.image.version`
- `org.opencontainers.image.vendor`
- `org.opencontainers.image.licenses`
- `org.opencontainers.image.documentation`
- `com.fortify.fcli.version` - fcli version included
- `com.fortify.base.image` - Base image used for build

```bash
# Inspect labels
docker inspect fortifydocker/fcli:latest | jq '.[0].Config.Labels'
```

## Build Arguments

### Linux Dockerfile

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `FCLI_VERSION` | Yes | - | fcli release tag (e.g., `v3.15.0`) |
| `ALPINE_BASE` | No | `alpine:3.23.0` | Alpine base image for downloader and alpine target |
| `UBI_BASE` | No | `redhat/ubi9:9.7` | Red Hat UBI9 standard base image (not minimal) |
| `SC_CLIENT_VERSION` | Required for `fcli-ubi9-sc` target | - | ScanCentral Client version to pre-install (e.g., `25.4`); resolved to latest patch release at build time |

### Windows Dockerfile

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `FCLI_VERSION` | Yes | - | fcli release tag (e.g., `v3.14.0`) |
| `SERVERCORE_BASE` | No | `mcr.microsoft.com/windows/servercore:ltsc2022` | Windows Server Core for VC++ install |
| `NANOSERVER_BASE` | No | `mcr.microsoft.com/windows/nanoserver:ltsc2022` | Windows Nano Server for final image |

## CI/CD Workflow

The `.github/workflows/docker.yml` workflow provides:

- **Automated builds:** Triggered via workflow_dispatch
- **Multi-image support:** Builds scratch, UBI9, UBI9+ScanCentral Client (multiple sc-client versions), Alpine (test), and Windows (test)
- **Signature verification:** Built into Dockerfile
- **Automated testing:** Tests tool installation in each image; verifies pre-installed sc-client and env vars in ubi9-sc variants
- **SBOM generation:** Provenance and SBOM attestation
- **Base image updates:** Support for republishing with updated base images
- **Selective publishing:** Publishes scratch, UBI9 and UBI9+sc-client variants to Docker Hub
- **Automatic sc-client version detection:**
  - First publish: bootstraps by picking the two latest YY.Q release groups from the [tool definitions](https://github.com/fortify/tool-definitions)
  - Subsequent refreshes: detects already-published sc-client versions from existing Docker Hub tags and refreshes those
  - Additional sc-client versions can be specified explicitly via the `scClientVersions` input

### Triggering Builds

```bash
# Via GitHub CLI — initial publish or full refresh
gh workflow run docker.yml \
  -f releaseTag=v3.15.0 \
  -f doPublish=true \
  -f ubiBase=redhat/ubi9:9.7

# Refresh existing images only (sc-client versions auto-detected from published tags)
gh workflow run docker.yml \
  -f releaseTag=v3.15.0 \
  -f doPublish=true

# Add a new sc-client version to an existing release
gh workflow run docker.yml \
  -f releaseTag=v3.15.0 \
  -f doPublish=true \
  -f scClientVersions=26.2
```

## Maintenance

### Updating Base Images

Base images should be updated periodically for security patches:

1. **Check for updates:**
   - Alpine: https://hub.docker.com/_/alpine
   - Red Hat UBI9: https://catalog.redhat.com/software/containers/ubi9/ubi/615bcf606feffc5384e8452e

2. **Test locally:**
   ```bash
   docker build . \
     --build-arg FCLI_VERSION=v3.14.0 \
     --build-arg ALPINE_BASE=alpine:3.23.0 \
     --build-arg UBI_BASE=redhat/ubi9:9.7 \
     --target fcli-scratch
   ```

3. **Update defaults in Dockerfile** or **trigger workflow with custom bases**

4. **Republish existing fcli version** with updated base images:
   ```bash
   gh workflow run docker.yml \
     -f releaseTag=v3.15.0 \
     -f doPublish=true \
     -f ubiBase=redhat/ubi9:9.8
   ```
   This creates new immutable timestamped tags (e.g., `3.15.0-20260401120000`,
   `3.15.0-ubi9-20260401120000`, `3.15.0-ubi9-sc25.4-20260401120000`) while also
   updating the floating `3.15.0`, `3.15`, and `3` tags to the refreshed images.

### Testing Checklist

Before publishing:
- [ ] Build completes successfully
- [ ] Signature verification passes
- [ ] `fcli --version` works in container
- [ ] `fcli tool sc-client install` succeeds with volume mount
- [ ] Installed tools are accessible in mounted volume
- [ ] Container runs as non-root user
- [ ] Image size is reasonable

## Troubleshooting

### Signature Verification Fails

```
ERROR: Signature verification failed
```

**Cause:** Downloaded fcli binary doesn't match signature.

**Solution:**
- Verify `FCLI_VERSION` matches an existing GitHub release
- Check network connectivity
- Verify Fortify public key in Dockerfile is up-to-date

### Permission Denied on Volume Mount

```
ERROR: Permission denied writing to /data
```

**Cause:** Host directory permissions don't allow container user (UID 10001).

**Solution:**
```bash
# Run as your user
docker run --rm -u $(id -u):$(id -g) -v $(pwd)/data:/data fortifydocker/fcli:latest tool list

# Or fix host directory permissions
chmod 777 data
```

### Windows Image: Missing DLLs

```
ERROR: vcruntime140.dll not found
```

**Cause:** Required VC++ runtime DLLs not copied correctly.

**Solution:**
- Rebuild image (DLLs are copied from vcredist-installer stage)
- Add missing DLLs to COPY list in Dockerfile if fcli requires additional ones
- Check that VC++ redistributable installed successfully

### fcli Tool Installation Fails

```
ERROR: Cannot write to /data/fortify/tools
```

**Cause:** Volume mount permissions or path issues.

**Solution:**
```bash
# Ensure volume mount is correct
docker run --rm -v $(pwd)/data:/data fortifydocker/fcli:latest tool sc-client install

# Check that /data exists and is writable
docker run --rm -v $(pwd)/data:/data fortifydocker/fcli:latest-ubi9 ls -la /data
```

## Contributing

When modifying Dockerfiles:
1. Maintain security best practices (non-root user, signature verification)
2. Keep images minimal
3. Test all targets before committing
4. Update this README with any new features or changes
5. Pin base images to specific versions
6. Add appropriate OCI labels

## Resources

- [fcli Documentation](https://github.com/fortify/fcli#readme)
- [Docker Hub: fortifydocker/fcli](https://hub.docker.com/r/fortifydocker/fcli)
- [Alpine Docker Images](https://hub.docker.com/_/alpine)
- [Red Hat UBI Images](https://catalog.redhat.com/software/containers/search?q=ubi9)
- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [OCI Image Spec](https://github.com/opencontainers/image-spec/blob/main/annotations.md)
