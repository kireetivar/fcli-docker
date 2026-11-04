"""Update or check deployment defaults against bulk-audit-release.json."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def generated_files(root):
    release = json.loads((root / "bulk-audit-release.json").read_text())
    runner = release["runner_version"]
    fcli = release["fcli_version"]
    sha = release["fcli_sha256"]
    repository = release["image_repository"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", runner):
        raise ValueError("runner_version must be a semantic version")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", fcli):
        raise ValueError("fcli_version must be a stable release tag")
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError("fcli_sha256 must be a SHA-256 digest")
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*", repository):
        raise ValueError("image_repository must be an untagged repository name")
    updates = {
        "deploy/compose/.env.example": {
            "FCLI_VERSION": fcli, "FCLI_SHA256": sha,
            "BULK_AUDIT_IMAGE": f"{repository}:{runner}",
            "RUNNER_VERSION": runner,
        },
        "charts/fcli-bulk-audit/Chart.yaml": {
            "version": runner, "appVersion": f'"{runner}"',
        },
        "charts/fcli-bulk-audit/values.yaml": {
            "  repository": repository, "  tag": runner,
        },
    }
    for name, values in updates.items():
        path = root / name
        content = path.read_text()
        separator = "=" if name.endswith(".env.example") else ": "
        for key, value in values.items():
            pattern = rf"^{re.escape(key + separator)}.*$"
            content, count = re.subn(pattern, lambda _: key + separator + value,
                                     content, flags=re.MULTILINE)
            if count != 1:
                raise ValueError(f"Expected one {key} in {name}, found {count}")
        yield path, content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in generated_files(ROOT):
        if path.read_text() != content:
            stale.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(content, newline="\n")
    if args.check and stale:
        parser.exit(1, "Release defaults are stale: " + ", ".join(stale)
                    + ". Run python scripts/sync-bulk-release.py.\n")


if __name__ == "__main__":
    main()
