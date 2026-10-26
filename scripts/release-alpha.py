#!/usr/bin/env python3
"""Prepare, verify, and publish a single immutable Weavem alpha wheel.

This deliberately does not build a wheel. CI builds one candidate once, calls
``prepare`` to attach its checksum, tests those exact bytes, then calls
``publish`` on the tag workflow. Publishing never replaces release assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from email.parser import BytesParser
from email.policy import compat32
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass

ALPHA_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+a\d+)$")


class ReleaseError(RuntimeError):
    """A candidate or publication invariant was not satisfied."""


@dataclass(frozen=True)
class Candidate:
    dist: Path
    wheel: Path
    version: str
    sha256: str
    checksums: Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseError(f"command failed ({' '.join(args)}): {detail}")
    return result


def project_version(project: Path) -> str:
    with (project / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    try:
        return str(config["project"]["version"])
    except KeyError as exc:
        raise ReleaseError("pyproject.toml is missing project.version") from exc


def wheel_metadata(wheel: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            records = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(records) != 1:
                raise ReleaseError(f"{wheel.name} must contain exactly one .dist-info/METADATA")
            message = BytesParser(policy=compat32).parsebytes(archive.read(records[0]))
            names = message.get_all("Name", [])
            versions = message.get_all("Version", [])
            if len(names) != 1 or len(versions) != 1:
                raise ReleaseError(f"{wheel.name} METADATA must contain exactly one Name and Version")
            name = names[0]
            version = versions[0]
    except zipfile.BadZipFile as exc:
        raise ReleaseError(f"{wheel.name} is not a valid wheel") from exc
    if not name or not version:
        raise ReleaseError(f"{wheel.name} METADATA must contain Name and Version")
    return str(name), str(version)

def checksum_entries(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ReleaseError(f"missing {path}")
    entries: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", raw)
        if not match:
            raise ReleaseError(f"invalid SHA256SUMS entry: {raw!r}")
        digest, name = match.groups()
        if name in entries:
            raise ReleaseError(f"duplicate checksum entry for {name}")
        entries[name] = digest
    return entries


def validate_candidate(dist: Path, project: Path, tag: str | None, *, require_checksums: bool) -> Candidate:
    dist = dist.resolve()
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(f"expected exactly one wheel in {dist}, found {len(wheels)}")
    wheel = wheels[0]
    source_version = project_version(project)
    if tag is not None:
        match = ALPHA_TAG.fullmatch(tag)
        if not match:
            raise ReleaseError(f"alpha tag must be vX.Y.ZaN, got {tag!r}")
        if match.group("version") != source_version:
            raise ReleaseError(f"tag {tag} does not match pyproject version {source_version}")
    name, metadata_version = wheel_metadata(wheel)
    if name.lower().replace("-", "_") != "weavem":
        raise ReleaseError(f"wheel METADATA Name must be weavem, got {name!r}")
    if metadata_version != source_version:
        raise ReleaseError(f"wheel METADATA Version {metadata_version} does not match pyproject {source_version}")
    expected_filename = f"weavem-{source_version}-py3-none-any.whl"
    if wheel.name != expected_filename:
        raise ReleaseError(f"wheel filename must be {expected_filename}, got {wheel.name}")
    digest = sha256(wheel)
    checksums = dist / "SHA256SUMS"
    if require_checksums:
        entries = checksum_entries(checksums)
        if entries != {wheel.name: digest}:
            raise ReleaseError("SHA256SUMS must contain exactly the candidate wheel and its SHA-256")
    return Candidate(dist, wheel, source_version, digest, checksums)


def prepare(args: argparse.Namespace) -> int:
    candidate = validate_candidate(args.dist, args.project, args.tag, require_checksums=False)
    candidate.checksums.write_text(f"{candidate.sha256}  {candidate.wheel.name}\n", encoding="utf-8")
    print(json.dumps({"wheel": candidate.wheel.name, "sha256": candidate.sha256, "version": candidate.version}, sort_keys=True))
    return 0


def check(args: argparse.Namespace) -> int:
    candidate = validate_candidate(args.dist, args.project, args.tag, require_checksums=True)
    print(json.dumps({"wheel": candidate.wheel.name, "sha256": candidate.sha256, "version": candidate.version}, sort_keys=True))
    return 0


def git(*args: str, project: Path) -> str:
    return run("git", *args, cwd=project).stdout.strip()


def validate_publication_context(tag: str, project: Path) -> str:
    if os.environ.get("GITHUB_EVENT_NAME") != "push":
        raise ReleaseError("publish requires a GitHub push event")
    if os.environ.get("GITHUB_REF") != f"refs/tags/{tag}":
        raise ReleaseError(f"publish requires GITHUB_REF=refs/tags/{tag}")
    head = git("rev-parse", "HEAD", project=project)
    tagged = git("rev-parse", f"{tag}^{{}}", project=project)
    if head != tagged:
        raise ReleaseError(f"checked-out commit {head} is not tag {tag}'s commit {tagged}")
    expected = os.environ.get("GITHUB_SHA")
    if expected and expected not in {head, git("rev-parse", tag, project=project)}:
        raise ReleaseError("GITHUB_SHA is not the checked-out tagged commit")
    run("git", "merge-base", "--is-ancestor", head, "origin/main", cwd=project)
    privacy = run("gh", "api", f"repos/{github_repository()}", "--jq", ".private")
    if privacy.stdout.strip() != "true":
        raise ReleaseError("alpha publication requires a private GitHub repository")
    return head


def release_notes(candidate: Candidate, tag: str, source_sha: str) -> str:
    run_url = ""
    if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_RUN_ID"):
        run_url = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    ci_line = f"- CI run: {run_url}" if run_url else "- CI run: this tagged workflow"
    return f"""# Weavem {tag}\n\nWeavem alpha release.\n\n## Install\n\nDownload `{candidate.wheel.name}` and install it directly:\n\n```bash\npython -m pip install ./{candidate.wheel.name}\nweavem doctor\n```\n\n## Verified artifact\n\n- Wheel SHA-256: `{candidate.sha256}`\n- Source commit: `{source_sha}`\n{ci_line}\n\n## Support limits\n\nThis alpha supports standard, GIL-enabled, non-debug CPython 3.12–3.15 on Linux x86_64 with glibc 2.28 or newer. Free-threaded and custom Python builds are excluded. The bundled compiler and verified headers are installed with Weavem; `weavem doctor` reports actionable environment problems. The API is provisional and this release does not sandbox task code. This is a private GitHub Release, not a PyPI publication.\n"""


def github_repository() -> str:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        raise ReleaseError("publish requires GITHUB_REPOSITORY")
    return repository


def gh_release(tag: str) -> dict[str, object] | None:
    """Read one release, including drafts, without hiding API failures."""
    repository = github_repository()
    result = run(
        "gh", "api", f"repos/{repository}/releases?per_page=100", "--paginate", "--jq", ".[] | @json",
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseError(f"could not inspect existing releases: {detail}")
    try:
        # One JSON object per line works across pages and older GitHub CLIs.
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (json.JSONDecodeError, TypeError) as exc:
        raise ReleaseError("GitHub releases response was malformed") from exc
    if not all(isinstance(record, dict) for record in records):
        raise ReleaseError("GitHub releases response was malformed")
    matches = [record for record in records if record.get("tag_name") == tag]
    if not matches:
        return None
    if len(matches) != 1:
        raise ReleaseError(f"multiple releases use tag {tag}")
    raw = matches[0]
    try:
        return {
            "tagName": raw["tag_name"], "isDraft": raw["draft"],
            "isPrerelease": raw["prerelease"],
            "targetCommitish": raw["target_commitish"], "assets": raw["assets"],
            "url": raw["html_url"], "body": raw.get("body", ""),
        }
    except (KeyError, TypeError) as exc:
        raise ReleaseError("GitHub release response was malformed") from exc

def download_and_verify(tag: str, name: str, digest: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    run("gh", "release", "download", tag, "--repo", github_repository(), "--pattern", name, "--dir", str(destination))
    downloaded = destination / name
    if not downloaded.is_file() or sha256(downloaded) != digest:
        raise ReleaseError(f"release asset {name} does not match the tested SHA-256")


def verify_existing_assets(release: dict[str, object], candidate: Candidate, directory: Path) -> set[str]:
    expected = {candidate.wheel.name: candidate.sha256, "SHA256SUMS": sha256(candidate.checksums)}
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ReleaseError("release response has invalid assets")
    names = {asset.get("name") for asset in assets if isinstance(asset, dict)}
    if not all(isinstance(name, str) for name in names):
        raise ReleaseError("release asset has no name")
    expected_names = set(expected)
    unexpected = names - expected_names
    if unexpected:
        raise ReleaseError(f"existing release has unexpected assets: {sorted(unexpected)}")
    for name in names:
        download_and_verify(str(release["tagName"]), name, expected[name], directory)
    return {name for name in names if isinstance(name, str)}


def publish(args: argparse.Namespace) -> int:
    if args.tag is None:
        raise ReleaseError("publish requires --tag")
    candidate = validate_candidate(args.dist, args.project, args.tag, require_checksums=True)
    source_sha = validate_publication_context(args.tag, args.project)
    release = gh_release(args.tag)
    artifacts_root = Path(os.environ.get("WEAVEM_ARTIFACTS_DIR", candidate.dist.parent / ".artifacts")).resolve()
    artifacts_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-publish-", dir=artifacts_root) as temp:
        directory = Path(temp)
        if release is None:
            notes = directory / "notes.md"
            notes.write_text(release_notes(candidate, args.tag, source_sha), encoding="utf-8")
            run("gh", "release", "create", args.tag, "--repo", github_repository(), "--verify-tag", "--draft", "--prerelease", "--title", f"Weavem {args.tag}", "--notes-file", str(notes))
            release = gh_release(args.tag)
            if release is None:
                raise ReleaseError("draft release was not created")
        if release.get("tagName") != args.tag or not release.get("isPrerelease"):
            raise ReleaseError("existing release does not belong to this alpha prerelease")
        body = str(release.get("body", ""))
        # target_commitish may be a branch name for an existing tag. The tag's
        # peeled commit was checked above; bind release notes to that exact SHA.
        if f"- Source commit: `{source_sha}`" not in body.splitlines() or "actions/runs/" not in body:
            raise ReleaseError("existing release does not identify this tagged source commit and CI run")
        present = verify_existing_assets(release, candidate, directory / "before")
        expected = {candidate.wheel.name, "SHA256SUMS"}
        if not release.get("isDraft") and present != expected:
            raise ReleaseError("published release has incomplete assets and will not be repaired")
        local = {candidate.wheel.name: candidate.wheel, "SHA256SUMS": candidate.checksums}
        for name, path in local.items():
            if name not in present:
                # Deliberately no --clobber: another writer causes a safe failure.
                run("gh", "release", "upload", args.tag, "--repo", github_repository(), str(path))
        release = gh_release(args.tag)
        if release is None:
            raise ReleaseError("release disappeared during publication")
        present = verify_existing_assets(release, candidate, directory / "after")
        if present != expected:
            raise ReleaseError("release asset set is incomplete after upload")
        if release.get("isDraft"):
            run("gh", "release", "edit", args.tag, "--repo", github_repository(), "--draft=false", "--prerelease")
        elif not release.get("isPrerelease"):
            raise ReleaseError("existing published release is not a prerelease")
    print(json.dumps({"tag": args.tag, "wheel": candidate.wheel.name, "sha256": candidate.sha256, "source_sha": source_sha}, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("action", choices=("prepare", "check", "publish"))
    command.add_argument("--dist", type=Path, default=Path("dist"))
    command.add_argument("--project", type=Path, default=Path("."))
    command.add_argument("--tag", help="required for publish; optional tag/version check otherwise")
    return command

def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return {"prepare": prepare, "check": check, "publish": publish}[args.action](args)
    except ReleaseError as exc:
        print(f"release-alpha: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
