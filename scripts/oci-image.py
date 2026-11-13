"""Verify the runnable image and attestations in a single-platform OCI archive."""
import argparse
import hashlib
import json
import subprocess
import tarfile


def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def inspect_archive(path):
    with tarfile.open(path) as archive:
        def read(descriptor):
            algorithm, digest = descriptor["digest"].split(":", 1)
            if algorithm != "sha256" or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Unsupported OCI blob digest")
            data = archive.extractfile("blobs/sha256/" + digest).read()
            if sha256(data) != descriptor["digest"]:
                raise ValueError("OCI blob digest mismatch")
            return json.loads(data)

        layout = json.load(archive.extractfile("index.json"))
        if len(layout["manifests"]) != 1:
            raise ValueError("Expected one release image in the OCI layout")
        root = layout["manifests"][0]
        index = read(root)
        images = [item for item in index["manifests"]
                  if item.get("platform") == {"architecture": "amd64", "os": "linux"}]
        if len(images) != 1:
            raise ValueError("Expected exactly one linux/amd64 runtime image")
        runtime = images[0]
        manifest = read(runtime)
        config = read(manifest["config"])
        predicates = set()
        for descriptor in index["manifests"]:
            if descriptor["digest"] == runtime["digest"]:
                continue
            attestation = read(descriptor)
            reference = descriptor.get("annotations", {}).get("vnd.docker.reference.digest")
            subject = attestation.get("subject", {}).get("digest")
            if (subject or reference) != runtime["digest"]:
                raise ValueError("Attestation does not refer to the runtime image")
            for layer in attestation["layers"]:
                statement = read(layer)
                subjects = statement.get("subject", [])
                if subjects and not any(s.get("digest", {}).get("sha256") == runtime["digest"].split(":")[1]
                           for s in subjects):
                    raise ValueError("Attestation statement subject mismatch")
                predicates.add(statement["predicateType"])
        if not any("spdx" in p for p in predicates) or not any("slsa.dev/provenance/" in p for p in predicates):
            raise ValueError("Release image requires an SBOM and provenance")
        return {
            "index_digest": root["digest"], "runtime_digest": runtime["digest"],
            "config_digest": manifest["config"]["digest"],
            "attestations": sorted(predicates), "config": config,
        }


def verify_docker_archive(path, image):
    with tarfile.open(path) as archive:
        manifests = json.load(archive.extractfile("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("Expected one image in the Docker test archive")
        manifest = manifests[0]
        config = archive.extractfile(manifest["Config"]).read()
        if sha256(config) != image["config_digest"]:
            raise ValueError("Docker test archive uses a different image configuration")
        layers = []
        for name in manifest["Layers"]:
            digest = hashlib.file_digest(archive.extractfile(name), "sha256").hexdigest()
            layers.append("sha256:" + digest)
        if layers != image["config"]["rootfs"]["diff_ids"]:
            raise ValueError("Docker test archive uses different filesystem layers")


def verify_loaded_image(reference, image):
    loaded = json.loads(subprocess.check_output(["docker", "image", "inspect", reference]))[0]
    config = image["config"]
    if loaded["Config"] != config["config"] or loaded["RootFS"]["Layers"] != config["rootfs"]["diff_ids"]:
        raise ValueError("Loaded test image differs from the release image")
    if loaded["Os"] != "linux" or loaded["Architecture"] != "amd64":
        raise ValueError("Loaded test image has the wrong platform")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--docker-archive")
    parser.add_argument("--image")
    args = parser.parse_args()
    image = inspect_archive(args.archive)
    if args.docker_archive:
        verify_docker_archive(args.docker_archive, image)
    if args.image:
        verify_loaded_image(args.image, image)
    print(json.dumps({key: value for key, value in image.items() if key != "config"}, indent=2))


if __name__ == "__main__":
    main()
