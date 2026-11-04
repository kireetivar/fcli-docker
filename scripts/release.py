"""Validate release inputs and produce the image matrix consumed by CI."""
import json
import os
import re
import subprocess
from datetime import datetime, timezone


def require_match(name, value, pattern):
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {name}")
    return value


def boolean(env, name):
    value = env[name].lower()
    require_match(name, value, r"true|false")
    return value == "true"


def version_list(value, pattern, name):
    values = [item.strip() for item in value.split(",") if item.strip()]
    for item in values:
        require_match(name, item, pattern)
    return sorted(set(values))


def validate_inputs(env):
    tag = require_match("release tag", env["RELEASE_TAG"],
                        r"(?:v?\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?|dev_[A-Za-z0-9][A-Za-z0-9_.-]*)")
    if len(tag) > 80:
        raise ValueError("Release tag is too long")
    image_pattern = r"[a-z0-9][a-z0-9./:_-]*(?:@sha256:[a-f0-9]{64})?"
    inputs = {
        "tag": tag,
        "production": boolean(env, "BUILD_PRODUCTION"),
        "test": boolean(env, "BUILD_TEST"),
        "publish": boolean(env, "DO_PUBLISH"),
        "latest": boolean(env, "IS_LATEST"),
        "ubi": require_match("UBI image", env["UBI_BASE"], image_pattern),
        "alpine": require_match("Alpine image", env["ALPINE_BASE"], image_pattern),
        "sc_versions": version_list(env["SC_CLIENT_VERSIONS"], r"\d+\.\d+", "ScanCentral version"),
        "windows": version_list(env["SERVERCORE_VERSIONS"], r"ltsc2022|ltsc2025", "Windows version"),
    }
    if not inputs["production"] and not inputs["test"]:
        raise ValueError("Select at least one image family")
    if inputs["test"] and not inputs["windows"]:
        raise ValueError("Select at least one Windows version for test builds")
    if inputs["latest"] and not re.fullmatch(r"v?\d+\.\d+\.\d+", tag):
        raise ValueError("Only stable releases can update latest tags")
    return inputs


def archive_digest(release, name):
    assets = [asset for asset in release["assets"] if asset["name"] == name]
    if len(assets) != 1:
        raise ValueError(f"Expected one release asset named {name}")
    digest = assets[0].get("digest") or ""
    require_match(f"SHA-256 for {name}", digest, r"sha256:[a-f0-9]{64}")
    return digest.removeprefix("sha256:")


def image_tags(repository, version, suffix, timestamp, latest=False):
    tags = [f"{repository}:{version}{suffix}"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match:
        major, minor, _ = match.groups()
        tags = [tags[0] + "-" + timestamp, tags[0],
                f"{repository}:{major}.{minor}{suffix}", f"{repository}:{major}{suffix}"]
        if latest:
            tags.append(f"{repository}:latest{suffix}")
    return tags


def published_sc_versions(tag, published_tags):
    version = tag.removeprefix("v")
    pattern = re.compile(re.escape(version) + r"-ubi9-sc(\d+\.\d+)")
    return {match.group(1) for tag in published_tags if (match := pattern.fullmatch(tag))}


def sc_versions(inputs, published_tags, definitions):
    selected = published_sc_versions(inputs["tag"], published_tags) | set(inputs["sc_versions"])
    if not selected:
        versions = re.findall(r"^  - version: (\d+\.\d+)\.\d+\s*$", definitions, re.MULTILINE)
        selected = set(sorted(set(versions), key=lambda v: tuple(map(int, v.split('.'))))[-2:])
    if not selected:
        raise ValueError("Cannot resolve ScanCentral versions; provide SC_CLIENT_VERSIONS")
    return sorted(selected, key=lambda v: tuple(map(int, v.split('.'))))


def build_plan(inputs, release, published_tags=(), definitions="", timestamp=None):
    if release.get("tag_name") != inputs["tag"] or release.get("draft"):
        raise ValueError("Release metadata does not match the selected published release")
    version = inputs["tag"].removeprefix("v")
    repository = "fortifydocker/fcli-dev" if inputs["tag"].startswith("dev_") else "fortifydocker/fcli"
    timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    variants = []

    def add(name, suffix, publish, sc_version=""):
        variants.append({
            "name": name, "target": "fcli-ubi9-sc" if sc_version else "fcli-" + name,
            "sc_version": sc_version, "publish": publish,
            "tags": image_tags(repository, version, suffix, timestamp,
                               inputs["latest"] and not sc_version),
        })

    if inputs["production"]:
        add("scratch", "", True)
        add("ubi9", "-ubi9", True)
        for sc_version in sc_versions(inputs, published_tags, definitions):
            add("ubi9-sc" + sc_version, "-ubi9-sc" + sc_version, True, sc_version)
    if inputs["test"]:
        add("alpine", "-alpine", False)
    return {
        "release_tag": inputs["tag"], "image_name": repository,
        "linux_sha256": archive_digest(release, "fcli-linux.tgz"),
        "windows_sha256": archive_digest(release, "fcli-windows.zip") if inputs["test"] else "",
        "ubi_base": inputs["ubi"], "alpine_base": inputs["alpine"],
        "linux_matrix": {"include": variants},
        "windows_matrix": {"include": [
            {"ltsc": ltsc, "runner": "windows-" + ltsc.removeprefix("ltsc")}
            for ltsc in inputs["windows"]
        ]},
    }


def fetch(url):
    return subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--retry", "2", "--max-time", "120", url],
        text=True)


def main():
    inputs = validate_inputs(os.environ)
    release = json.loads(fetch("https://api.github.com/repos/fortify/fcli/releases/tags/" + inputs["tag"]))
    tags, definitions = [], ""
    if inputs["production"]:
        repository = "fortifydocker/fcli-dev" if inputs["tag"].startswith("dev_") else "fortifydocker/fcli"
        tags = json.loads(subprocess.check_output(
            ["skopeo", "list-tags", "docker://" + repository], text=True))["Tags"]
        if not inputs["sc_versions"] and not published_sc_versions(inputs["tag"], tags):
            definitions = fetch("https://raw.githubusercontent.com/fortify/tool-definitions/refs/heads/main/v1/sc-client.yaml")
    plan = build_plan(inputs, release, tags, definitions)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in plan.items():
            value = json.dumps(value, separators=(",", ":")) if isinstance(value, dict) else value
            output.write(f"{key}={value}\n")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
