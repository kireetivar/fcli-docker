# This Dockerfile allows for building a Windows-based fcli image. Although functional, for now 
# this is considered just a prototype and not automatically published; we can fine-tune and 
# publish if there's any demand for a Windows-based image.
#
# Uses Windows Server Core (not Nano Server) for the final image to:
# - Provide full PowerShell access for users
# - Allow installation of additional build tools/packages
# - Simplify Dockerfile (no need to manually copy DLLs)
# - Mirror the UBI9 philosophy (standard image, not minimal)
#
# Build Arguments:
# - FCLI_VERSION: fcli version to download (required, e.g., "v3.14.0")
# - SERVERCORE_BASE: Windows Server Core base image (default: mcr.microsoft.com/windows/servercore:ltsc2025)
# 
# The Dockerfile uses a two-stage build:
# 1. Download stage: Downloads fcli, verifies signature, and downloads VC++ redistributables
# 2. Final stage: Installs VC++ redistributables and fcli on Server Core

# ============================================================================
# Global build arguments (must be before any FROM to use in FROM statements)
# ============================================================================
ARG SERVERCORE_BASE=mcr.microsoft.com/windows/servercore:ltsc2022

# ============================================================================
# Stage: fcli-downloader
# Downloads fcli, signature file, and VC++ redistributables
# Uses .NET SDK image which has modern .NET 8+ with full crypto API support
# Note: Uses Nano Server variant for faster builds (smaller image download)
# ============================================================================
FROM mcr.microsoft.com/dotnet/sdk:8.0-nanoserver-ltsc2022 AS fcli-downloader

# Nano Server has PowerShell Core (pwsh) not Windows PowerShell (powershell)
SHELL ["pwsh", "-Command"]

# Build arguments
ARG FCLI_VERSION
ARG CACHE_BUST
ARG FCLI_SHA256

# Validate FCLI_VERSION is provided
RUN $ErrorActionPreference = 'Stop'; \
    if (-not $env:FCLI_VERSION) { throw 'ERROR: FCLI_VERSION build argument is required' }

# Create temp directory and download fcli with signature
# Note: CACHE_BUST arg forces re-download for rolling tags when release is updated
RUN $ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; \
    Write-Host \"Cache bust: $env:CACHE_BUST\"; \
    Write-Host "Archive SHA-256: $env:FCLI_SHA256"; \
    New-Item -ItemType Directory -Path C:\temp -Force | Out-Null; \
    Write-Host \"Downloading fcli $env:FCLI_VERSION...\"; \
    $url = \"https://github.com/fortify/fcli/releases/download/$env:FCLI_VERSION/fcli-windows.zip\"; \
    $sigUrl = \"$url.rsa_sha256\"; \
    Write-Host \"Download URL: $url\"; \
    Invoke-WebRequest -Uri $url -OutFile C:\temp\fcli-windows.zip; \
    if ($env:FCLI_SHA256 -and (Get-FileHash C:\temp\fcli-windows.zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $env:FCLI_SHA256) { throw 'Archive SHA-256 mismatch' }; \
    Write-Host \"Downloading signature...\"; \
    Invoke-WebRequest -Uri $sigUrl -OutFile C:\temp\fcli-windows.zip.rsa_sha256

# Verify signature using .NET 8+ crypto APIs
RUN $ErrorActionPreference = 'Stop'; \
    Write-Host 'Verifying signature...'; \
    $publicKeyBase64 = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArij9U9yJVNc53oEMFWYpNrXUG1UoRZseDh/p34q1uywD70RGKKWZvXIcUAZZwbZtCu4i0UzsrKRJeUwqanbcwoJvYanp6lc3DccXUN1w1Y0WOHOaBxiiK3B1TtEIH1cK/X+ZzazPG5nX7TSGh8Tp/uxQzUFli2mDVLqaP62/fB9uJ2joX9Gtw8sZfuPGNMRoc8IdhjagbFkhFT7WCZnkFH/4Co007lmXLAe12lQQqR/pOTeHJv1sfda1xaHtj4/Tcrq04Kx0ZmGAd5D9lA928pdBbzoe/mI5/Sk+nIY3AHkLXB9YAaKJf//Wb1yiP1/hchtVkfXyIaGM+cVyn7ANVQIDAQAB'; \
    $publicKeyBytes = [Convert]::FromBase64String($publicKeyBase64); \
    $rsa = [System.Security.Cryptography.RSA]::Create(); \
    $rsa.ImportSubjectPublicKeyInfo($publicKeyBytes, [ref]$null); \
    $signature = [System.IO.File]::ReadAllBytes('C:\temp\fcli-windows.zip.rsa_sha256'); \
    $fileBytes = [System.IO.File]::ReadAllBytes('C:\temp\fcli-windows.zip'); \
    $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($fileBytes); \
    $verified = $rsa.VerifyHash($hash, $signature, [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1); \
    if (-not $verified) { throw 'Signature verification failed' }; \
    Write-Host '✓ Signature verification successful'

# Extract fcli to temp directory
RUN $ErrorActionPreference = 'Stop'; \
    Write-Host 'Extracting fcli...'; \
    Expand-Archive -Path C:\temp\fcli-windows.zip -DestinationPath C:\temp; \
    if (-not (Test-Path C:\temp\fcli.exe)) { throw 'fcli.exe not found after extraction' };

# Download VC++ redistributable
RUN $ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; \
    Write-Host 'Downloading Visual C++ Redistributable...'; \
    Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile C:\temp\vc_redist.x64.exe

# ============================================================================
# Stage: fcli-ltsc2022
# Final Server Core image with fcli and VC++ redistributables
# Uses Server Core (not Nano) to provide full PowerShell and tool installation capability
# ============================================================================
FROM ${SERVERCORE_BASE} AS fcli-ltsc2022

# Bring build args into this stage
ARG FCLI_VERSION
ARG SERVERCORE_BASE

# Use PowerShell for RUN commands in this stage too
SHELL ["powershell", "-Command"]

# Create fcli directory first
RUN $ErrorActionPreference = 'Stop'; \
    New-Item -ItemType Directory -Path 'C:\Program Files\fcli' -Force | Out-Null

# Copy fcli, entrypoint, welcome, and VC++ redistributable from download stage
COPY --from=fcli-downloader ["C:/temp/fcli.exe", "C:/Program Files/fcli/fcli.exe"]
COPY --from=fcli-downloader ["C:/temp/vc_redist.x64.exe", "C:/vc_redist.x64.exe"]
COPY ["docker-entrypoint.cmd", "C:/Program Files/fcli/docker-entrypoint.cmd"]
COPY ["welcome.txt", "C:/Program Files/fcli/welcome.txt"]

# Install VC++ redistributables and clean up
RUN $ErrorActionPreference = 'Stop'; \
    Write-Host 'Installing Visual C++ Redistributable...'; \
    Start-Process -FilePath C:\vc_redist.x64.exe -ArgumentList '/install', '/quiet', '/norestart' -Wait; \
    Remove-Item C:\vc_redist.x64.exe -Force

# Create data directory and non-admin user for security (matching Linux approach)
RUN $ErrorActionPreference = 'Stop'; \
    New-Item -ItemType Directory -Path C:\data -Force | Out-Null; \
    net user fcli /add; \
    icacls 'C:\Program Files\fcli' /grant 'fcli:(RX)'; \
    icacls C:\data /grant 'fcli:(F)'

# Configure environment and PATH
WORKDIR C:/data
ENV FCLI_USER_HOME=C:/data
ENV PATH="C:\Program Files\fcli;${PATH}"

# OCI standard labels (multi-line for optimization)
LABEL org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.title="fcli Windows (ltsc2022)" \
      org.opencontainers.image.description="Fortify CLI on Windows Server Core ltsc2022" \
      org.opencontainers.image.version="${FCLI_VERSION}" \
      org.opencontainers.image.url="https://github.com/fortify/fcli" \
      org.opencontainers.image.source="https://github.com/fortify/fcli" \
      org.opencontainers.image.documentation="https://fortify.github.io/fcli/" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="${SERVERCORE_BASE}"

# Switch to non-admin user
USER fcli

# Set entrypoint and default to PowerShell for full scripting capability
ENTRYPOINT ["C:\\Program Files\\fcli\\docker-entrypoint.cmd"]
CMD ["powershell.exe"]

# ============================================================================
# Stage: fcli-ltsc2025
# Final Server Core image with fcli and VC++ redistributables (ltsc2025)
# Uses Server Core (not Nano) to provide full PowerShell and tool installation capability
# ============================================================================
FROM mcr.microsoft.com/windows/servercore:ltsc2025 AS fcli-ltsc2025

# Bring build args into this stage
ARG FCLI_VERSION

# Use PowerShell for RUN commands in this stage too
SHELL ["powershell", "-Command"]

# Create fcli directory first
RUN $ErrorActionPreference = 'Stop'; \
    New-Item -ItemType Directory -Path 'C:\Program Files\fcli' -Force | Out-Null

# Copy fcli, entrypoint, welcome, and VC++ redistributable from download stage
COPY --from=fcli-downloader ["C:/temp/fcli.exe", "C:/Program Files/fcli/fcli.exe"]
COPY --from=fcli-downloader ["C:/temp/vc_redist.x64.exe", "C:/vc_redist.x64.exe"]
COPY ["docker-entrypoint.cmd", "C:/Program Files/fcli/docker-entrypoint.cmd"]
COPY ["welcome.txt", "C:/Program Files/fcli/welcome.txt"]

# Install VC++ redistributables and clean up
RUN $ErrorActionPreference = 'Stop'; \
    Write-Host 'Installing Visual C++ Redistributable...'; \
    Start-Process -FilePath C:\vc_redist.x64.exe -ArgumentList '/install', '/quiet', '/norestart' -Wait; \
    Remove-Item C:\vc_redist.x64.exe -Force

# Create data directory and non-admin user for security (matching Linux approach)
RUN $ErrorActionPreference = 'Stop'; \
    New-Item -ItemType Directory -Path C:\data -Force | Out-Null; \
    net user fcli /add; \
    icacls 'C:\Program Files\fcli' /grant 'fcli:(RX)'; \
    icacls C:\data /grant 'fcli:(F)'

# Configure environment and PATH
WORKDIR C:/data
ENV FCLI_USER_HOME=C:/data
ENV PATH="C:\Program Files\fcli;${PATH}"

# OCI standard labels (multi-line for optimization)
LABEL org.opencontainers.image.vendor="Fortify" \
      org.opencontainers.image.title="fcli Windows (ltsc2025)" \
      org.opencontainers.image.description="Fortify CLI on Windows Server Core ltsc2025" \
      org.opencontainers.image.version="${FCLI_VERSION}" \
      org.opencontainers.image.url="https://github.com/fortify/fcli" \
      org.opencontainers.image.source="https://github.com/fortify/fcli" \
      org.opencontainers.image.documentation="https://fortify.github.io/fcli/" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="mcr.microsoft.com/windows/servercore:ltsc2025"

# Switch to non-admin user
USER fcli

# Set entrypoint and default to PowerShell for full scripting capability
ENTRYPOINT ["C:\\Program Files\\fcli\\docker-entrypoint.cmd"]
CMD ["powershell.exe"]
