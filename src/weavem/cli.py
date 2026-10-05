"""Small, intentionally local Weavem command-line interface."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .build import BuildError, build, test, validate
from .contracts import (CompatibilityError, ContractError, IntegrityError, Manifest, PolicyError, SourceSpec, StoreError)
from .config import resolve_project
from .store import LocalStore


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


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weavem")
    parser.add_argument("--project")
    task = parser.add_subparsers(dest="command", required=True).add_parser("task")
    sub = task.add_subparsers(dest="task_command", required=True)
    new = sub.add_parser("new", help="Create a task folder with editable task.toml")
    new.add_argument("directory", metavar="TASK_NAME", help="Task name or source directory")
    new.add_argument("--id", dest="task_id", help="Override task ID (default: folder name)")
    new.add_argument("--version", default="0.1.0", help="Initial version (default: 0.1.0)")
    new.add_argument("--backend", choices=("python", "cython"), default="python",
                     help="Build backend (default: python)")
    new.set_defaults(func=_new)
    command = sub.add_parser("validate")
    command.add_argument("directory")
    command.set_defaults(func=lambda a: validate(a.directory))

    command = sub.add_parser("test")
    command.add_argument("directory")
    command.add_argument("--work-dir")
    command.set_defaults(func=lambda a: test(a.directory, work_dir=a.work_dir, project=a.project))

    command = sub.add_parser("build")
    command.add_argument("directory")
    command.add_argument("--store")
    command.add_argument("--work-dir")
    command.set_defaults(func=lambda a: build(a.directory, store=_store(a)[0],
                                             work_dir=a.work_dir, project=a.project))

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
    try:
        args = make_parser().parse_args(argv)
        result = args.func(args)
        if result is not None and args.task_command == "build":
            print(json.dumps(_json_ref(result), sort_keys=True))
        return 0
    except (BuildError, CompatibilityError, ContractError, IntegrityError, PolicyError, StoreError, ValueError, OSError) as exc:
        print(f"weavem: {exc}", file=sys.stderr)
        return 2
