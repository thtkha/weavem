"""Small, intentionally local Weavem command-line interface."""
from __future__ import annotations
import argparse
import json
import keyword
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib

from .build import BuildError, build, publish, test, validate
from .bindings import manifest_digest, read_bindings
from .contracts import (CompatibilityError, ContractError, IntegrityError, Manifest, PolicyError, SourceSpec, StoreError)
from .config import resolve_project
from .store import LocalStore


def _pin(value: str) -> tuple[str, str]:
    from .contracts import _validate_identity
    if value.count("==") != 1:
        raise ContractError("release requires exact ID==VERSION")
    return _validate_identity(*value.split("==", 1))


def _use_task(args):
    """Edit only the chosen binding table, preserving unrelated project settings."""
    project = resolve_project(args.project)
    config = project.config_path
    if config is None or config.is_symlink():
        raise ContractError("task use requires a regular weavem.toml (create a project first)")
    existing_bindings = read_bindings(project)
    if not args.alias or any(ord(c) < 32 for c in args.alias):
        raise ContractError("task alias must be non-empty printable text")
    if args.path is not None:
        if args.source is not None:
            raise ContractError("--from is only used with --release")
        path = (project.root / Path(args.path).expanduser()).resolve()
        try:
            relative = path.relative_to(project.root)
        except ValueError as exc:
            raise ContractError("local task path must be inside the project") from exc
        validate(path)
        values = {"path": str(relative)}
    else:
        from .runtime import validate_artifact
        task_id, version = _pin(args.release)
        source = args.source or "task-store"
        root = project.store_path if source == "task-store" else project.root / Path(source).expanduser()
        ref = LocalStore(root).resolve(task_id, version)
        validate_artifact(ref, requested_task_id=task_id, requested_version=version)
        values = {"release": args.release, "source": source, "manifest_sha256": manifest_digest(ref.manifest_path)}
    old = config.read_text(encoding="utf-8")
    tables = list(re.finditer(r"(?m)^\s*\[[^\n]+\][ \t]*(?:#[^\n]*)?$", old))
    section = f"[tasks.{json.dumps(args.alias)}]\n" + "".join(
        f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    updated = None
    for index, match in enumerate(tables):
        try:
            parsed = tomllib.loads(match.group() + "\n__binding_marker__ = true\n")
        except tomllib.TOMLDecodeError:
            continue
        if parsed.get("tasks", {}).get(args.alias) == {"__binding_marker__": True}:
            end = tables[index + 1].start() if index + 1 < len(tables) else len(old)
            updated = old[:match.start()] + section + "\n" + old[end:]
            break
    if updated is None:
        if args.alias in existing_bindings:
            raise ContractError("binding uses an inline/nested table; edit it manually before task use")
        updated = old.rstrip() + "\n\n" + section
    tomllib.loads(updated)
    # Use a same-directory atomic replacement; never truncate the user's config.
    fd, temporary = tempfile.mkstemp(prefix=".weavem-config-", dir=project.root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(updated)
        os.chmod(temporary, config.stat().st_mode & 0o777)
        if config.read_text(encoding="utf-8") != old:
            raise ContractError("project config changed while selecting dependency; retry")
        os.replace(temporary, config)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"{args.alias}: {values.get('release', values.get('path'))}")


def _store(args):
    project = resolve_project(getattr(args, "project", None), store=getattr(args, "store", None))
    return LocalStore(project.store_path), project


def _new(args):
    root = Path(args.directory)
    task_id = root.name if args.task_id is None else args.task_id
    # Validate every user-supplied value before creating filesystem state.
    SourceSpec(schema=1, task_id=task_id, version=args.version, backend=args.backend,
               source_path="implementation.py", export="double")
    if root.exists():
        raise BuildError(f"refusing to overwrite existing path: {root}")
    root.mkdir(parents=True)
    tests = root / "tests"
    tests.mkdir()
    (root / "task.toml").write_text(
        f'''# Edit task identity, version, and backend here before building.\n[task]\nschema = 1\ntask_id = "{task_id}"\nversion = "{args.version}"\nbackend = "{args.backend}"\nsource = "implementation.py"\nexport = "double"\ndependencies = []\n''', encoding="utf-8")
    (root / "implementation.py").write_text("def double(value):\n    return value * 2\n", encoding="utf-8")
    (tests / "test_task.py").write_text(
        "import unittest\nfrom implementation import double\n\nclass TaskTests(unittest.TestCase):\n    def test_double(self):\n        self.assertEqual(double(21), 42)\n", encoding="utf-8")


def _new_project(args):
    """Create the small, local filesystem convention used by Weavem projects."""
    root = Path(args.directory)
    if root.exists() or root.is_symlink():
        raise BuildError(f"refusing to overwrite existing path: {root}")
    root.mkdir(parents=True)
    (root / "weavem.toml").write_text("[weavem]\n", encoding="utf-8")
    (root / "tasks").mkdir()
    flows = root / "flows"
    flows.mkdir()
    (flows / "__init__.py").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".artifacts/\ntask-store/\n__pycache__/\n.venv/\n", encoding="utf-8")


def _flow_name(value: str) -> str:
    # A flow file is also an importable Python module and its function name.
    # Accepting only bare identifiers avoids path traversal and awkward imports.
    if (Path(value).name != value or not value.isidentifier() or keyword.iskeyword(value)
            or (value.startswith("__") and value.endswith("__"))):
        raise BuildError("flow name must be a non-keyword Python identifier, not a reserved __dunder__ name")
    return value


def _new_flow(args):
    name = _flow_name(args.name)
    # The scaffold uses the module name as its initial release ID.
    from .contracts import _validate_identity
    _validate_identity(name, "0.1.0")
    project = resolve_project(args.project)
    flows = project.root / "flows"
    if flows.is_symlink() or (flows.exists() and not flows.is_dir()):
        raise BuildError("flows must be a regular project directory")
    init = flows / "__init__.py"
    if init.is_symlink() or (init.exists() and not init.is_file()):
        raise BuildError("flows/__init__.py must be a regular file")
    path = flows / f"{name}.py"
    metadata = flows / f"{name}.toml"
    tests = project.root / "tests" / "flows" / name
    for target in (path, metadata, tests):
        if target.exists() or target.is_symlink():
            raise BuildError(f"refusing to overwrite existing path: {target}")
    for parent in (project.root / "tests", project.root / "tests" / "flows"):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise BuildError("flow tests must be in regular project directories")
    flows.mkdir(parents=True, exist_ok=True)
    if not init.exists():
        init.write_text("", encoding="utf-8")
    path.write_text(
        f'''"""{name} flow."""\nfrom weavem import flow\n\n\n@flow\ndef {name}():\n    return None\n\n\nif __name__ == "__main__":\n    {name}()\n''',
        encoding="utf-8",
    )
    metadata.write_text(
        f'[flow]\nschema = 1\nflow_id = "{name}"\nversion = "0.1.0"\n'
        f'source = "{name}.py"\nexport = "{name}"\ntasks = []\n', encoding="utf-8")
    tests.mkdir(parents=True)
    (tests / "test_flow.py").write_text(
        f"import unittest\nfrom flows.{name} import {name}\n\n"
        "class FlowTests(unittest.TestCase):\n"
        f"    def test_result(self):\n        self.assertIsNone({name}.fn())\n", encoding="utf-8")


def _run_flow(args):
    from .flows import load_flow, load_local_flow
    kwargs = json.loads(args.params)
    if not isinstance(kwargs, dict):
        raise ContractError("--params must be a JSON object of keyword arguments")
    if args.release:
        target = load_flow(*_pin(args.target), store=_store(args)[0], project=args.project)
    else:
        target = load_local_flow(args.target, project=args.project)
    result = target(**kwargs)
    print(json.dumps(result, default=str))


def _flow_metadata(args):
    from .flows import FlowStore
    from .flow_contracts import FlowManifest
    store, _ = _store(args)
    if args.flow_command == "list":
        refs = [_json_ref(ref) for ref in FlowStore(store).list()]
        print(json.dumps(refs, sort_keys=True) if args.json else "\n".join(ref["root"] for ref in refs))
    else:
        ref = FlowStore(store).resolve(*_pin(args.pin))
        manifest = FlowManifest.from_json_bytes(ref.manifest_path.read_bytes())
        print(json.dumps(manifest.to_mapping(), sort_keys=True) if args.json else f"{manifest.flow_id}=={manifest.version}")


def _json_ref(ref):
    return {"root": str(ref.root), "manifest": str(ref.manifest_path)}


def _list(args):
    store, _ = _store(args)
    refs = [_json_ref(ref) for ref in store.list()]
    if args.json:
        print(json.dumps(refs, sort_keys=True))
    else:
        for ref in refs:
            print(ref["root"])


def _info(args):
    if args.pin.count("==") != 1:
        raise BuildError("info requires exact ID==VERSION")
    task_id, version = args.pin.split("==", 1)
    if not task_id or not version:
        raise BuildError("info requires exact ID==VERSION")
    store, _ = _store(args)
    ref = store.resolve(task_id, version)
    # Metadata-only: do not import payload code.
    manifest = Manifest.from_json_bytes(ref.manifest_path.read_bytes())
    if args.json:
        print(json.dumps(manifest.to_mapping(), sort_keys=True))
    else:
        print(f"{manifest.task_id}=={manifest.version}")


def _doctor(args):
    from .native import check_native
    project = resolve_project(args.project, work_dir=args.work_dir)
    print(json.dumps(check_native(project.work_dir), sort_keys=True))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weavem")
    parser.add_argument("--project")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Verify the managed native compiler, headers, and loader")
    doctor.add_argument("--work-dir")
    doctor.set_defaults(func=_doctor)

    project = commands.add_parser("project")
    project_subcommands = project.add_subparsers(dest="project_command", required=True)
    new_project = project_subcommands.add_parser("new", help="Create a Weavem project folder")
    new_project.add_argument("directory", metavar="PROJECT_NAME")
    new_project.set_defaults(func=_new_project)

    flow = commands.add_parser("flow")
    flow_subcommands = flow.add_subparsers(dest="flow_command", required=True)
    new_flow = flow_subcommands.add_parser("new", help="Create a flow module in the selected project")
    new_flow.add_argument("name", metavar="FLOW_NAME")
    new_flow.set_defaults(func=_new_flow)
    from .flows import build_flow, publish_flow, test_flow, validate_source_flow
    for action, function in (("validate", validate_source_flow), ("test", test_flow), ("build", build_flow)):
        command = flow_subcommands.add_parser(action)
        command.add_argument("name")
        command.add_argument("--work-dir")
        command.set_defaults(func=lambda a, fn=function: fn(a.name, project=a.project, work_dir=a.work_dir))
    command = flow_subcommands.add_parser("publish")
    command.add_argument("candidate")
    command.add_argument("--to", dest="store")
    command.set_defaults(func=lambda a: publish_flow(a.candidate, store=_store(a)[0], project=a.project))
    command = flow_subcommands.add_parser("run")
    command.add_argument("target", help="Local flow name, or ID==VERSION with --release")
    command.add_argument("--release", action="store_true")
    command.add_argument("--store")
    command.add_argument("--params", default="{}", help="JSON object of flow keyword arguments")
    command.set_defaults(func=_run_flow)
    for action in ("list", "info"):
        command = flow_subcommands.add_parser(action)
        if action == "info":
            command.add_argument("pin")
        command.add_argument("--store")
        command.add_argument("--json", action="store_true")
        command.set_defaults(func=_flow_metadata)

    task = commands.add_parser("task")
    sub = task.add_subparsers(dest="task_command", required=True)
    new = sub.add_parser("new", help="Create a task folder with editable task.toml")
    new.add_argument("directory", metavar="TASK_NAME", help="Task name or source directory")
    new.add_argument("--id", dest="task_id", help="Override task ID (default: folder name)")
    new.add_argument("--version", default="0.1.0", help="Initial version (default: 0.1.0)")
    new.add_argument("--backend", choices=("python", "cython"), default="python",
                     help="Build backend (default: python)")
    new.set_defaults(func=_new)
    command = sub.add_parser("use", help="Explicitly select a local or released task dependency")
    command.add_argument("alias")
    selection = command.add_mutually_exclusive_group(required=True)
    selection.add_argument("--path", help="Local task directory relative to project root")
    selection.add_argument("--release", help="Exact ID==VERSION")
    command.add_argument("--from", dest="source", help="Source folder relative to project root (default: configured task-store)")
    command.set_defaults(func=_use_task)
    command = sub.add_parser("validate")
    command.add_argument("directory")
    command.set_defaults(func=lambda a: validate(a.directory))

    command = sub.add_parser("test")
    command.add_argument("directory")
    command.add_argument("--work-dir")
    command.set_defaults(func=lambda a: test(a.directory, work_dir=a.work_dir, project=a.project))

    command = sub.add_parser("build")
    command.add_argument("directory")
    command.add_argument("--work-dir")
    command.set_defaults(func=lambda a: build(a.directory, work_dir=a.work_dir, project=a.project))

    command = sub.add_parser("publish")
    command.add_argument("candidate")
    command.add_argument("--to", dest="store")
    command.set_defaults(func=lambda a: publish(a.candidate, store=_store(a)[0], project=a.project))

    command = sub.add_parser("list")
    command.add_argument("--store")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=_list)

    command = sub.add_parser("info")
    command.add_argument("pin")
    command.add_argument("--store")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=_info)
    return parser


def main(argv=None) -> int:
    from .flows import FlowError
    from .native import NativeError
    try:
        args = make_parser().parse_args(argv)
        result = args.func(args)
        action = getattr(args, "task_command", None) or getattr(args, "flow_command", None)
        if result is not None and action in {"build", "publish"}:
            print(json.dumps(_json_ref(result), sort_keys=True))
        return 0
    except (BuildError, FlowError, NativeError, CompatibilityError, ContractError, IntegrityError, PolicyError, StoreError, ValueError, OSError) as exc:
        print(f"weavem: {exc}", file=sys.stderr)
        return 2
