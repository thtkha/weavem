"""Read-only project metadata, independent of task execution and publication."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tomllib

from .bindings import binding_store, read_bindings
from .config import resolve_project
from .contracts import ContractError, Manifest, SourceSpec, StoreError
from .flow_contracts import FlowSpec


def _regular(path: Path) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ContractError(f"symlinked metadata/source path is not allowed: {path}")
    if not path.is_file():
        raise ContractError(f"missing metadata/source file: {path}")


def _source(definition: Path, relative: str) -> None:
    path = definition.parent / relative
    _regular(path)
    if not path.resolve().is_relative_to(definition.parent.resolve()):
        raise ContractError(f"source escapes definition directory: {path}")


def _task_files(root: Path, excluded: tuple[Path, ...]):
    if root.is_symlink() or not root.exists():
        return
    # A project may itself live inside a global work directory (e.g. CI).
    # Prune configured artifact subtrees, not ancestors of the discovery root.
    excluded = tuple(path for path in excluded if path.is_relative_to(root.resolve()))
    def failed(error):
        raise error
    for directory, children, files in os.walk(root, followlinks=False, onerror=failed):
        parent = Path(directory)
        if any(parent.resolve().is_relative_to(path) for path in excluded):
            children[:] = []
            continue
        children[:] = sorted(name for name in children
                             if not name.startswith('.')
                             and not (parent / name).is_symlink())
        if 'task.toml' in files:
            yield parent / 'task.toml'


class Project:
    """A local project handle; metadata() rereads definitions on every call."""

    def __init__(self, root: Path, config_path: Path | None):
        self._target = config_path if config_path is not None else root

    @classmethod
    def open(cls, path: str | Path | None = None) -> Project:
        """Select a directory/config file, or discover from cwd when omitted."""
        config = resolve_project(path)
        return cls(config.root, config.config_path)

    def metadata(self) -> dict:
        """Return a schema-1 JSON-compatible snapshot, or raise ContractError.

        No payload code is imported and no payload compatibility/integrity check
        is performed. Inspect a stable checkout: this is not a filesystem transaction.
        """
        try:
            return self._metadata()
        except (OSError, ValueError) as exc:
            raise ContractError(f"cannot inspect project {self._target}: {exc}") from exc

    def _metadata(self, *, include_flows: bool = True) -> dict:
        config = resolve_project(self._target)
        bindings = read_bindings(config)
        paths = set(_task_files(config.root / 'tasks',
                               (config.store_path.resolve(), config.work_dir.resolve())))
        # Check lexical binding paths before read_bindings' resolved paths could
        # hide a symlink. Reuse its validation rather than duplicating its schema.
        raw = {}
        if config.config_path is not None:
            _regular(config.config_path)
            raw = tomllib.loads(config.config_path.read_text())
        for alias, binding in bindings.items():
            if binding.path is not None:
                lexical = config.root / raw['tasks'][alias]['path'] / 'task.toml'
                _regular(lexical)
                paths.add(binding.path / 'task.toml')
        tasks = []
        for path in sorted(paths):
            _regular(path)
            try:
                spec = SourceSpec.from_toml(path)
                _source(path, spec.source_path)
            except ContractError as exc:
                raise ContractError(f"task definition {path}: {exc}") from exc
            tasks.append({'path': str(path.resolve()), 'metadata': spec.to_mapping()})

        flows = []
        from .flow_sources import flow_definitions
        for path in (flow_definitions(config).values() if include_flows else ()):
            _regular(path)
            try:
                data = tomllib.loads(path.read_text())
                spec = FlowSpec.from_mapping(data.get('flow', data))
                _source(path, spec.source)
                missing = sorted(set(spec.tasks) - bindings.keys())
                if missing:
                    raise ContractError(f"undefined task aliases: {', '.join(missing)}")
            except (ContractError, ValueError) as exc:
                raise ContractError(f"flow definition {path}: {exc}") from exc
            flows.append({'path': str(path.resolve()), 'metadata': spec.to_mapping()})

        releases = {}
        for alias, binding in sorted(bindings.items()):
            if binding.release is None:
                continue
            try:
                task_id, version = binding.release.split('==', 1)
                ref = binding_store(config, binding).resolve(task_id, version)
                manifest = Manifest.from_json_bytes(ref.manifest_path.read_bytes())
                digest = hashlib.sha256(manifest.to_json_bytes()).hexdigest()
                if digest != binding.manifest_sha256:
                    raise ContractError('pinned manifest digest mismatch')
                location = str(ref.root.resolve())
                releases[location] = {'kind': 'task', 'root': location,
                                      'manifest_sha256': digest,
                                      'metadata': manifest.to_mapping()}
            except (ContractError, StoreError, OSError) as exc:
                raise ContractError(f"task binding {alias}: {exc}") from exc
        return {
            'schema': 1,
            'project': {'root': str(config.root),
                        'config_path': str(config.config_path) if config.config_path else None,
                        'store_path': str(config.store_path), 'work_dir': str(config.work_dir)},
            'tasks': tasks,
            'flows': flows,
            'bindings': [{'alias': b.alias, 'path': str(b.path) if b.path else None,
                          'release': b.release, 'source': b.source,
                          'manifest_sha256': b.manifest_sha256}
                         for _, b in sorted(bindings.items())],
            'releases': [releases[key] for key in sorted(releases)],
        }
