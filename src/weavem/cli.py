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
               source_path="implementation.py", export="run")
    if root.exists():
        raise BuildError(f"refusing to overwrite existing path: {root}")
    root.mkdir(parents=True)
    tests = root / "tests"
    tests.mkdir()
    (root / "task.toml").write_text(
        f'''# Edit task identity, version, and backend here before building.\n[task]\nschema = 1\ntask_id = "{task_id}"\nversion = "{args.version}"\nbackend = "{args.backend}"\nsource = "implementation.py"\nexport = "run"\ndependencies = []\n''', encoding="utf-8")
    (root / "implementation.py").write_text("def run(value):\n    # Replace this pass-through starter with your task behavior.\n    return value\n", encoding="utf-8")
    (tests / "test_task.py").write_text(
        "import unittest\nfrom implementation import run\n\nclass TaskTests(unittest.TestCase):\n    def test_run(self):\n        self.assertEqual(run(\"hello\"), \"hello\")\n", encoding="utf-8")


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
    (root / "README.md").write_text('''# Your Weavem project

Run these commands in this folder with your Weavem Python environment activated.
Use supported standard CPython 3.12–3.15 on Linux x86_64 (glibc 2.28+).
No account, shared server, or publication is needed for local development.

## What goes where

- `weavem.toml`: project settings and explicitly selected task aliases.
- `tasks/`: suggested home for editable task folders (created below).
- `flows/`: flow Python modules and their `.toml` metadata.
- `tests/flows/`: generated flow tests; each task has its own `tests/` folder.
- `.artifacts/`: disposable build/test work and retained unpublished candidates.
- `task-store/`: immutable published releases, created when you publish locally.
  This store is gitignored, not disposable: retain or copy releases you need.

## Start locally

```bash
weavem task new tasks/my_task
weavem task use my_task --path tasks/my_task
weavem task validate tasks/my_task
weavem task test tasks/my_task
weavem flow new my_flow
weavem flow validate my_flow
weavem flow test my_flow
weavem flow run my_flow
```

Checks print `passed` on success. The untouched flow returns JSON `null`:
it is an empty scaffold, not automatically wired to the task. Stop on errors;
fix the named metadata or failing test before continuing. Creation commands
refuse existing paths; edit existing files instead of rerunning scaffolding.

Replace `tasks/my_task/implementation.py` and its tests with your behavior.
The task metadata's `export` names the callable (`run` initially); keep that
name consistent with your code and test imports. A function can call your
classes and methods internally. Select `--backend cython` at task creation
for native builds, or edit `backend` in `task.toml`. `weavem doctor` checks
the native compiler and headers without installing OS packages.

To connect the task, import `task` from `weavem` in `flows/my_flow.py` and call
`task("my_task")(value)` inside the flow. Also add `"my_task"` to the flow
metadata's `tasks` list and update its behavioral test. Run the checks again.
Use `weavem.task(...)` for execution; `Project.open(".").metadata()` is the
local metadata entry point, not a `Project.task(...)` execution API.

## Build, publish, and share

`weavem task build tasks/my_task` tests and creates an unpublished candidate.
Its JSON output contains `root`: pass that exact path as the positional argument
to `weavem task publish`. This publishes to `task-store/` by default; add
`--to PATH` to choose another folder. Publishing promotes the same bytes,
without rebuilding. Do not edit a published release: change the source version
and build a new candidate instead.

For a releasable flow, first publish every dependency and switch each alias
with `weavem task use my_task --release my_task==0.1.0`. Then run
`weavem flow build my_flow` and pass its candidate `root` to `weavem flow publish`.
Local unpublished dependencies deliberately block flow builds.

Share the published store folder, not `.artifacts/` or your virtual environment.
Recipients install Weavem and any task-specific dependencies themselves.
Native `.so` releases require a matching Python minor and compatible platform;
copying a folder does not make a binary portable to every machine.

Keep source and tests in version control. Retain candidates until promotion
and verification finish; there is no automatic cleanup in these instructions.
Start with the [official user documentation](https://github.com/thtkha/weavem/blob/main/docs/users/index.md)
for installation, the complete walkthrough, native builds, and troubleshooting.
Use the documentation for your installed Weavem version when following release-specific instructions.
''', encoding="utf-8")


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
    from .flow_sources import flow_directories, flow_metadata_path
    flows = flow_metadata_path(project, name).parent
    if flows != flow_directories(project)[0] or (flows / f"{name}.toml").exists():
        raise BuildError(f"refusing to overwrite existing flow: {name}")
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
        f"import unittest\nfrom pathlib import Path\nfrom weavem.flows import load_local_flow\n\n"
        "class FlowTests(unittest.TestCase):\n"
        f"    def test_result(self):\n        self.assertIsNone(load_local_flow({name!r}, project=Path(__file__).resolve().parents[3]).fn())\n", encoding="utf-8")


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

    editor = commands.add_parser("editor", help="Serve the local visual flow editor on loopback")
    editor.add_argument("--project", dest="editor_project", help="Project directory (default: discover from cwd)")
    editor.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    editor.add_argument("--ui-dir", help="Directory containing a built editor index.html")
    def _editor(args):
        from .editor_server import serve_editor
        return serve_editor(args.editor_project if args.editor_project is not None else args.project,
                            port=args.port, ui_dir=args.ui_dir)
    editor.set_defaults(func=_editor)

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
    from .errors import TaskError, serialize_error
    try:
        args = make_parser().parse_args(argv)
        result = args.func(args)
        action = getattr(args, "task_command", None) or getattr(args, "flow_command", None)
        if result is not None and action in {"build", "publish"}:
            print(json.dumps(_json_ref(result), sort_keys=True))
        if action in {"validate", "test"}:
            target = args.directory if args.command == "task" else args.name
            print(f"{args.command} {action} passed: {target}")
        return 0
    except TaskError as exc:
        print(f"weavem: {exc}", file=sys.stderr)
        print(json.dumps({"error": serialize_error(exc)}), file=sys.stderr)
        return 2
    except (BuildError, FlowError, NativeError, CompatibilityError, ContractError, IntegrityError, PolicyError, StoreError, ValueError, OSError) as exc:
        print(f"weavem: {exc}", file=sys.stderr)
        return 2
