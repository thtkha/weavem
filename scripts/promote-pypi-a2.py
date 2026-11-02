#!/usr/bin/env python3
"""Promote the original GitHub a2 wheel to PyPI; never build or replace it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile
from email.parser import BytesParser
from email.policy import compat32

REPOSITORY = "thtkha/weavem"
VERSION = "0.1.0a2"
TAG = f"v{VERSION}"
SOURCE_COMMIT = "13c2b3876e55690be06da1deb5db8ab2df516f65"
WHEEL = f"weavem-{VERSION}-py3-none-any.whl"
WHEEL_SHA256 = "518877f1dc2c20c34ed3c0aeb9144a4e99d8a6ab4547db103130c475b9aa2f95"
MANIFEST_SHA256 = "ed38bcb8c9c2924363d4a69e5962e70224467f98b5bbabd66e666c60b838a390"
PYPI_JSON = f"https://pypi.org/pypi/weavem/{VERSION}/json"


class PromotionError(RuntimeError):
    """A fixed release identity, environment or publication invariant failed."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*argv: str, project: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=project, text=True, capture_output=True, check=False)
    if result.returncode:
        # Do not echo remote errors, credentials, or untrusted response bodies.
        raise PromotionError(f"{argv[0]} command failed; inspect its authenticated configuration")
    return result.stdout.strip()


def context(project: Path) -> dict[str, str]:
    expected = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_SERVER_URL": "https://github.com",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise PromotionError("promotion requires manual dispatch on thtkha/weavem main at github.com")
    origin = command("git", "remote", "get-url", "origin", project=project)
    if origin not in {f"https://github.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}.git"}:
        raise PromotionError("origin is not the canonical HTTPS repository")
    source = command("git", "rev-parse", f"{TAG}^{{commit}}", project=project)
    if source != SOURCE_COMMIT:
        raise PromotionError("the existing a2 tag no longer identifies the original source commit")
    head = command("git", "rev-parse", "HEAD", project=project)
    if head != os.environ.get("GITHUB_SHA"):
        raise PromotionError("checkout does not match the dispatched main commit")
    return {"repository": REPOSITORY, "tag": TAG, "source_commit": source, "workflow_commit": head}


def verify(dist: Path, *, original: bool = False) -> dict[str, str]:
    expected = {WHEEL, "SHA256SUMS"} if original else {WHEEL}
    if not dist.is_dir() or {p.name for p in dist.iterdir()} != expected:
        raise PromotionError("candidate directory has missing or unexpected files")
    if any(not p.is_file() or p.is_symlink() for p in dist.iterdir()):
        raise PromotionError("candidate directory must contain only regular files")
    wheel = dist / WHEEL
    if digest(wheel) != WHEEL_SHA256:
        raise PromotionError("wheel differs from the pinned original GitHub a2 bytes")
    if original:
        manifest = dist / "SHA256SUMS"
        if digest(manifest) != MANIFEST_SHA256:
            raise PromotionError("checksum manifest differs from the original release")
        if manifest.read_text(encoding="utf-8") != f"{WHEEL_SHA256}  {WHEEL}\n":
            raise PromotionError("checksum manifest does not identify the one original wheel")
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            prefix = f"weavem-{VERSION}.dist-info/"
            if len(names) != len(set(names)):
                raise PromotionError("wheel has duplicate entries")
            if [n for n in names if n.endswith(".dist-info/METADATA")] != [prefix + "METADATA"]:
                raise PromotionError("wheel metadata identity is ambiguous")
            metadata = BytesParser(policy=compat32).parsebytes(archive.read(prefix + "METADATA"))
            required = {"Name": "weavem", "Version": VERSION,
                        "Requires-Python": "<3.16,>=3.12", "License-Expression": "Apache-2.0"}
            for name, value in required.items():
                if metadata.get_all(name) != [value]:
                    raise PromotionError(f"wheel {name} metadata differs from the fixed release")
            licenses = {"LICENSE", "NOTICE", "TRADEMARKS.md"}
            if set(metadata.get_all("License-File", [])) != licenses:
                raise PromotionError("wheel license metadata is incomplete")
            if not all(prefix + "licenses/" + name in names for name in licenses):
                raise PromotionError("wheel is missing required license files")
    except (zipfile.BadZipFile, KeyError, UnicodeError) as error:
        raise PromotionError("wheel contents are invalid") from error
    return {"wheel": WHEEL, "version": VERSION, "sha256": WHEEL_SHA256,
            "source_commit": SOURCE_COMMIT, "repository": REPOSITORY}


def download(args: argparse.Namespace) -> dict[str, str]:
    context(args.project)
    release = json.loads(command("gh", "release", "view", TAG, "--repo", REPOSITORY,
                                 "--json", "tagName,isDraft,isPrerelease,assets"))
    assets = release.get("assets", [])
    if (release.get("tagName") != TAG or release.get("isDraft") is not False
            or release.get("isPrerelease") is not True
            or not isinstance(assets, list) or len(assets) != 2
            or not all(isinstance(a, dict) for a in assets)
            or {a.get("name") for a in assets} != {WHEEL, "SHA256SUMS"}):
        raise PromotionError("GitHub release identity or asset set has changed")
    if args.dist.exists() or args.publish_dir.exists():
        raise PromotionError("download and publication directories must not already exist")
    args.dist.mkdir(parents=True)
    command("gh", "release", "download", TAG, "--repo", REPOSITORY,
            "--pattern", WHEEL, "--pattern", "SHA256SUMS", "--dir", str(args.dist))
    verify(args.dist, original=True)
    args.publish_dir.mkdir(parents=True)
    shutil.copyfile(args.dist / WHEEL, args.publish_dir / WHEEL)
    return verify(args.publish_dir)


def fetch_pypi() -> dict | None:
    try:
        with urlopen(PYPI_JSON, timeout=20) as response:
            body = response.read(1024 * 1024 + 1)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise PromotionError(f"PyPI metadata request failed with HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise PromotionError("PyPI metadata is unavailable; no upload decision was made") from None
    if len(body) > 1024 * 1024:
        raise PromotionError("PyPI metadata exceeded the response limit")
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise PromotionError("PyPI metadata is malformed") from None
    if not isinstance(result, dict):
        raise PromotionError("PyPI metadata is malformed")
    return result


def needs_upload(data: dict | None) -> bool:
    if data is None:
        return True
    info, files = data.get("info"), data.get("urls")
    if not isinstance(info, dict) or info.get("name") != "weavem" or info.get("version") != VERSION:
        raise PromotionError("PyPI metadata identifies a different distribution")
    if (not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict)
            or files[0].get("filename") != WHEEL
            or not isinstance(files[0].get("digests"), dict)
            or files[0]["digests"].get("sha256") != WHEEL_SHA256
            or files[0].get("yanked") is not False):
        raise PromotionError("PyPI a2 already exists with conflicting or incomplete files; stop")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["context", "download", "verify", "pypi-status", "confirm-pypi"])
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--publish-dir", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "context":
            result = context(args.project)
        elif args.action == "download":
            if args.dist is None or args.publish_dir is None:
                parser.error("download requires --dist and --publish-dir")
            result = download(args)
        elif args.action == "verify":
            if args.dist is None:
                parser.error("verify requires --dist")
            result = verify(args.dist)
        elif args.action == "pypi-status":
            upload = needs_upload(fetch_pypi())
            result = {"upload": upload, "wheel": WHEEL, "sha256": WHEEL_SHA256}
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as output:
                    output.write(f"upload={'true' if upload else 'false'}\n")
        else:
            for attempt in range(9):
                if not needs_upload(fetch_pypi()):
                    break
                if attempt == 8:
                    raise PromotionError("PyPI a2 is not visible yet; retain the workflow evidence before retrying")
                time.sleep(10)
            result = {"published": True, "wheel": WHEEL, "sha256": WHEEL_SHA256}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PromotionError, json.JSONDecodeError, OSError) as error:
        print(f"a2 promotion stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
