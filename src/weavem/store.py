"""Minimal local immutable task-artifact store."""
from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import shutil
import time
from typing import Iterable, Protocol, runtime_checkable

from .contracts import Manifest, ManifestError, StoreError, sha256_file


@dataclass(frozen=True)
class ArtifactRef:
    """A locally materialized immutable artifact directory."""
    root: Path

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"


@runtime_checkable
class TaskStore(Protocol):
    def resolve(self, task_id: str, version: str) -> ArtifactRef: ...
    def list(self) -> Iterable[ArtifactRef]: ...
    def publish(self, completed_staging_dir: str | Path) -> ArtifactRef: ...


def _read_manifest(root: Path) -> Manifest:
    try:
        return Manifest.from_json_bytes((root / "manifest.json").read_bytes())
    except (OSError, ManifestError) as exc:
        raise StoreError(f"invalid task artifact at {root}: {exc}") from exc


class LocalStore:
    """Filesystem TaskStore using cooperative locks and rename-only publication."""
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().absolute()

    def _destination(self, manifest: Manifest) -> Path:
        return self.root / manifest.task_id / manifest.version / manifest.python_cache_tag

    def resolve(self, task_id: str, version: str) -> ArtifactRef:
        # The runtime validates everything else, but avoid ambiguous store roots here.
        from .contracts import _validate_identity  # private validation intentionally central
        _validate_identity(task_id, version)
        base = self.root / task_id / version
        if self.root.is_symlink() or any(part.is_symlink() for part in (self.root / task_id, base)):
            raise StoreError("symlinked store ancestry is not allowed")
        if not base.is_dir():
            raise StoreError(f"task not found: {task_id}=={version}")
        candidates = [child for child in base.iterdir() if child.is_dir() and not child.is_symlink()
                      and (child / "manifest.json").is_file() and not (child / "manifest.json").is_symlink()]
        if len(candidates) != 1:
            raise StoreError(f"ambiguous or missing task artifact: {task_id}=={version}")
        manifest = _read_manifest(candidates[0])
        if manifest.task_id != task_id or manifest.version != version:
            raise StoreError("stored manifest identity does not match requested task")
        return ArtifactRef(candidates[0])

    def list(self) -> Iterable[ArtifactRef]:
        if not self.root.is_dir():
            return ()
        refs: list[ArtifactRef] = []
        if self.root.is_symlink():
            raise StoreError("symlinked store root is not allowed")
        for manifest_path in self.root.glob("*/*/*/manifest.json"):
            if any(part.is_symlink() for part in (manifest_path.parent.parent.parent, manifest_path.parent.parent, manifest_path.parent)):
                raise StoreError("symlinked store ancestry is not allowed")
            refs.append(ArtifactRef(manifest_path.parent))
        return tuple(sorted(refs, key=lambda ref: str(ref.root)))

    def publish(self, completed_staging_dir: str | Path) -> ArtifactRef:
        staging = Path(completed_staging_dir).resolve()
        if not staging.is_dir():
            raise StoreError("publish staging directory is missing")
        if (staging / "manifest.json").is_symlink():
            raise StoreError("publish staging manifest must not be a symlink")
        manifest = _read_manifest(staging)
        payload = staging / manifest.artifact_name
        if not payload.is_file() or payload.is_symlink():
            raise StoreError("publish staging payload is missing or not regular")
        if payload.stat().st_size != manifest.artifact_size or sha256_file(payload) != manifest.artifact_sha256:
            raise StoreError("publish staging payload does not match manifest digest")
        files = {entry.name for entry in staging.iterdir()}
        if files != {"manifest.json", manifest.artifact_name}:
            raise StoreError("publish staging directory must contain only manifest and payload")
        destination = self._destination(manifest)
        ancestry = (self.root, self.root / manifest.task_id,
                    self.root / manifest.task_id / manifest.version, destination)
        if any(path.is_symlink() for path in ancestry):
            raise StoreError("symlinked store ancestry is not allowed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = destination.parent / f".{destination.name}.lock"
        acquired = False
        for _ in range(200):
            try:
                os.mkdir(lock)
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.01)
        if not acquired:
            raise StoreError("timed out waiting for cooperative publish lock")
        try:
            if destination.exists():
                existing = _read_manifest(destination)
                if existing.to_json_bytes() == manifest.to_json_bytes() and (destination / manifest.artifact_name).read_bytes() == payload.read_bytes():
                    return ArtifactRef(destination)
                raise StoreError(f"task version already published with different bytes: {manifest.task_id}=={manifest.version}")
            # Cross-filesystem work/store roots cannot rename directly. Copy only the
            # already validated two-file artifact into a private destination-side dir,
            # then publish that complete directory with one atomic rename.
            try:
                os.replace(staging, destination)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise StoreError(f"atomic publish failed: {exc}") from exc
                private = destination.parent / f".{destination.name}.publishing-{os.getpid()}-{time.time_ns()}"
                try:
                    private.mkdir()
                    shutil.copyfile(staging / "manifest.json", private / "manifest.json")
                    shutil.copyfile(payload, private / manifest.artifact_name)
                    copied_payload = private / manifest.artifact_name
                    if ((private / "manifest.json").is_symlink() or copied_payload.is_symlink()
                            or _read_manifest(private).to_json_bytes() != manifest.to_json_bytes()
                            or copied_payload.stat().st_size != manifest.artifact_size
                            or sha256_file(copied_payload) != manifest.artifact_sha256):
                        raise StoreError("cross-filesystem copy does not match validated artifact")
                    os.replace(private, destination)
                    shutil.rmtree(staging)
                except (OSError, StoreError) as copy_exc:
                    shutil.rmtree(private, ignore_errors=True)
                    raise StoreError(f"cross-filesystem atomic publish failed: {copy_exc}") from copy_exc
            return ArtifactRef(destination)
        finally:
            if acquired:
                try:
                    lock.rmdir()
                except OSError:
                    pass
