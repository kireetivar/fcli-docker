# Required Changes for fortify/fcli Repository

This file records the original move out of the fcli repository. It is not the current install or security guide.
Use [the install guide](docs/bulk-audit-guide.md) and [release maintenance](docs/bulk-audit-release.md).
The sample image tags and workflow inputs below are not current.

This document describes the changes needed in the main `fortify/fcli` repository to integrate with the new standalone `fortify/fcli-docker` repository.

## Summary

The Docker image build process has been moved to a separate repository (`fortify/fcli-docker`) to allow independent testing and publishing of Docker images. The fcli repository needs to be updated to:

1. Remove the moved Docker-related files and directories
2. Update the CI workflow to trigger Docker builds in the new repository

## Files and Directories to Remove

The following files/directories should be **deleted** from the `fortify/fcli` repository:

```
fcli-other/fcli-docker/
├── README.md
├── linux/
│   ├── .gitignore
│   ├── Dockerfile
│   ├── data.tgz
│   ├── minimal-passwd
│   └── tmp.tgz
└── windows/
    ├── .gitignore
    ├── Dockerfile
    └── data.tgz
```

**Commands to remove:**
```bash
cd /path/to/fcli
git rm -r fcli-other/fcli-docker/
git commit -m "Move Docker configuration to fortify/fcli-docker repository"
```

## Workflow File to Remove or Archive

The following workflow should be **removed** or **renamed** to archive it:

```
.github/workflows/docker.yml
```

**Option 1: Remove (Recommended)**
```bash
git rm .github/workflows/docker.yml
git commit -m "Remove docker.yml workflow (moved to fcli-docker repo)"
```

**Option 2: Archive for reference**
```bash
git mv .github/workflows/docker.yml .github/workflows/docker.yml.archived
git commit -m "Archive docker.yml workflow (moved to fcli-docker repo)"
```

## Update CI Workflow

The main CI workflow (`.github/workflows/ci.yml`) should be updated to trigger Docker builds in the new `fortify/fcli-docker` repository when releases are published.

### Changes to `.github/workflows/ci.yml`

Add a new job at the end of the workflow to trigger the Docker build:

```yaml
  # Trigger Docker image builds in the fcli-docker repository
  trigger-docker-build:
    name: Trigger Docker Build
    needs: [release]
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/')
    steps:
      - name: Extract release tag
        id: extract_tag
        run: |
          TAG=${GITHUB_REF#refs/tags/}
          echo "tag=${TAG}" >> $GITHUB_OUTPUT
          echo "Release tag: ${TAG}"
      
      - name: Trigger docker.yml workflow in fcli-docker repo
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.FCLI_DOCKER_TRIGGER_TOKEN }}
          script: |
            const tag = '${{ steps.extract_tag.outputs.tag }}';
            console.log(`Triggering Docker build for fcli ${tag}`);
            
            await github.rest.actions.createWorkflowDispatch({
              owner: 'fortify',
              repo: 'fcli-docker',
              workflow_id: 'docker.yml',
              ref: 'main',
              inputs: {
                releaseTag: tag,
                doPublish: 'true',
                alpineBase: 'alpine:3.23.0',
                ubiBase: 'redhat/ubi9:9.7',
                servercoreBase: 'mcr.microsoft.com/windows/servercore:ltsc2022',
                updateBaseImages: 'false'
              }
            });
            
            console.log('✓ Docker build triggered successfully');
```

### Required Secret

A new repository secret needs to be created in the `fortify/fcli` repository:

- **Secret Name:** `FCLI_DOCKER_TRIGGER_TOKEN`
- **Secret Value:** A GitHub Personal Access Token (PAT) with `workflow` scope
- **Purpose:** Allows the fcli repository to trigger workflows in the fcli-docker repository

**To create the PAT (Fine-grained token recommended):**
1. Go to GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Create new token with:
   - Token name: `fcli-docker-trigger`
   - Expiration: Choose appropriate expiration (e.g., 1 year, then rotate)
   - Repository access: **Only select repositories** → `fortify/fcli-docker`
   - Repository permissions:
     - Actions: **Read and write** (required to trigger workflows)
     - Metadata: **Read** (automatically included)
3. Generate token and copy it immediately
4. Add it as a secret in the `fortify/fcli` repository settings:
   - Go to fortify/fcli repository → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `FCLI_DOCKER_TRIGGER_TOKEN`
   - Value: Paste the token
   - Click "Add secret"

**Note:** Use fine-grained tokens instead of classic PATs for better security and minimal permissions.

### Alternative: Manual Trigger

If automatic triggering is not desired initially, the Docker builds can be triggered manually:

1. After releasing a new fcli version, go to: https://github.com/fortify/fcli-docker/actions/workflows/docker.yml
2. Click "Run workflow"
3. Enter the release tag (e.g., `v3.14.0`)
4. Set `doPublish` to `true`
5. Click "Run workflow"

## Testing the Integration

After making these changes:

1. **Test removal:**
   ```bash
   # Verify files are removed
   ls fcli-other/fcli-docker/  # Should not exist
   ls .github/workflows/docker.yml  # Should not exist
   ```

2. **Test CI workflow:**
   - Create a test tag in the fcli repository
   - Verify that the fcli-docker workflow is triggered automatically
   - Check the Actions tab in fcli-docker repository for the build

3. **Test manual trigger:**
   - Go to fcli-docker Actions tab
   - Manually trigger docker.yml workflow
   - Verify builds complete successfully

## Documentation Updates

Update the following documentation in the `fortify/fcli` repository:

### README.md or CONTRIBUTING.md

Add a note about Docker image builds:

```markdown
## Docker Images

Docker images for fcli are built and published separately in the [fortify/fcli-docker](https://github.com/fortify/fcli-docker) repository.

To trigger Docker image builds for a new release:
1. Docker builds are automatically triggered when a new release tag is pushed
2. Alternatively, manually trigger the workflow at: https://github.com/fortify/fcli-docker/actions/workflows/docker.yml

For more information about Docker images, see the [fcli-docker repository](https://github.com/fortify/fcli-docker).
```

## Migration Checklist

- [ ] Remove `fcli-other/fcli-docker/` directory
- [ ] Remove or archive `.github/workflows/docker.yml`
- [ ] Update `.github/workflows/ci.yml` to trigger fcli-docker builds
- [ ] Create `FCLI_DOCKER_TRIGGER_TOKEN` secret (if using automatic triggering)
- [ ] Update documentation (README.md, CONTRIBUTING.md)
- [ ] Test with a development/test release
- [ ] Verify Docker images are published correctly

## Rollback Plan

If issues arise, the changes can be rolled back:

1. Revert the commits that removed the Docker files
2. Re-enable the old docker.yml workflow
3. Continue using the old approach until issues are resolved

The fcli-docker repository will remain available and can be used for testing without affecting the main fcli builds.

## Benefits of This Approach

1. **Independent Testing:** Docker images can be built and tested without waiting for fcli releases
2. **Faster Iteration:** Changes to Dockerfiles or base images can be tested independently
3. **Cleaner Separation:** Docker-specific CI/CD logic is separate from main fcli builds
4. **Easier Maintenance:** Docker image updates don't require changes to the main fcli repository
5. **Better Organization:** Each repository has a single, focused responsibility

## Contact

For questions or issues with the migration, please:
- Open an issue in the [fcli-docker repository](https://github.com/fortify/fcli-docker/issues)
- Contact the fcli maintainers
