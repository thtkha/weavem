# CLI, metadata, and SDK reference

Applies to Weavem 0.1.0. Start with the [authoring guide](authoring-guide.md) for a
complete workflow. This page distinguishes accepted syntax from project conventions;
it does not propose additional commands or services.

## Command line

`weavem` and `python -m weavem` expose the same interface. Global `--project PATH`
comes **before** `task`. `PATH` selects an existing directory or config file.

| Command | Options | Result |
| --- | --- | --- |
| `weavem task new TASK_NAME` | `--id ID`, `--version VERSION`, `--backend python\|cython` | Creates a source directory; refuses an existing path. |
| `weavem task validate DIRECTORY` | None | Validates source metadata and source-file presence. |
| `weavem task test DIRECTORY` | `--work-dir PATH` | Runs syntax and non-empty unittest checks on a snapshot. |
| `weavem task build DIRECTORY` | `--store PATH`, `--work-dir PATH` | Tests, builds, smoke-loads, and publishes; prints artifact-reference JSON. |
| `weavem task list` | `--store PATH`, `--json` | Lists artifact references, not imported callables. |
| `weavem task info ID==VERSION` | `--store PATH`, `--json` | Reads the resolved manifest, without executing its payload. |

`new` defaults to the directory basename for ID, `0.1.0` for version, and `python`
for backend. Its starter callable is currently named `double`; replace the starter
implementation/tests and update `export` for your real task. That function name is
not a convention for application tasks.

Source directory arguments are relative to the **shell's working directory**, not
`--project`. Store/work paths are relative to the **selected project root**. Example,
from a workspace containing an `author/` directory:

```bash
weavem --project author task build author/tasks/normalize_names --store ../consumer/task-store
```

The source is `author/tasks/normalize_names`; publication is to the sibling
`consumer/task-store`. The source folder must already exist. See [configuration](#configuration)
for how a project is selected when `--project` is absent.

Successful commands exit `0`; handled CLI validation/build/store failures print
`weavem: ...` to stderr and exit `2`. Argparse usage errors also exit `2`. Unexpected
exceptions can produce tracebacks; do not assume all failures use one exit code.
There are no `install`, `register`, `publish`, `flow new`, ZIP-loading, or remote-store
commands in this release. Local publication is part of `task build`.

## Author metadata

Use a `[task]` table in `task.toml` with these canonical keys. Unknown fields are rejected.

| Key | Required/default when omitted | Rule |
| --- | --- | --- |
| `task_id` | Required | ASCII letter first, then letters/digits/`_`/`.`/`-`; at most 128 characters. |
| `version` | Required | 1–128 ASCII characters; letter/digit first, then letters/digits/`_`/`.`/`+`/`-`. Exact string, not a version constraint. |
| `schema` | `1` | Integer `1` only. |
| `backend` | `"python"` | `"python"` or `"cython"`. |
| `source` | `"implementation.py"` | One relative filename, not an absolute path or multi-module package. Use a `.py` implementation module. |
| `export` | `"run"` | Python identifier naming a bare callable in the implementation. Scaffold explicitly overrides this with its starter export. |
| `dependencies` | `[]` | Exact installed **distribution** pins, for example `requests==2.32.0` as a syntax illustration, not a version recommendation. |
| `description` | Omitted | Optional string. |
| `inputs` | `[]` | Array of non-empty descriptive strings. |
| `output` | `"Any"` | Non-empty descriptive string. |

Namespaced IDs such as `text.normalize_names`, semantic versions such as `1.0.0`,
and an export named `run` are **recommended conventions**, not fixed names required
by the framework. Generated module names have an additional 200-character ceiling;
keep IDs and versions short rather than using their separate maximum lengths together.
Versions are not automatically sorted, upgraded, or resolved to "latest".

`inputs` and `output` do not create a runtime type checker. Validate inputs in task
code. Use distribution names for dependencies, which may differ from import names.
No extras, markers, ranges, direct URLs, automatic installs, or bundled dependency
environments are supported. Standard-library modules are not dependencies to pin.
The build does not provision dependencies: install them before testing/building and
on the consumer before execution.

For compatibility, the parser also accepts `source_path` in place of `source` and a
root-level table in place of `[task]`. If both source keys exist, `source` wins. New
authored files should use only the canonical form above; `id` is not an alias for
`task_id`. Generated manifests are separate build outputs, not author configuration.

## Provision task dependencies

Use an activated consumer environment with Weavem already installed, from the consumer
project root. Only provision dependencies from a publisher you trust, using your
organization's approved package index or offline wheelhouse. This is an explicit
user-managed installation step, not something Weavem performs at task invocation.

For the tutorial task (whose empty pins make this a no-op), run this Python code:

```python
import json
import subprocess
import sys
from importlib.metadata import version

result = subprocess.run(
    [sys.executable, "-m", "weavem", "task", "info",
     "text.normalize_names==1.0.0", "--json"],
    check=True, capture_output=True, text=True,
)
pins = json.loads(result.stdout)["dependencies"]
if pins:
    subprocess.run([sys.executable, "-m", "pip", "install", *pins], check=True)
for pin in pins:
    distribution, expected = pin.split("==", 1)
    assert version(distribution) == expected, pin
```

Replace the exact task pin with the one you are consuming. Expected: installation
succeeds and all installed versions match. Stop on installation or assertion failure;
do not edit the manifest to fit a different environment. Authors provision those same
pins from their source metadata before source tests, using `python -m pip install`
with each declared `distribution==version` as an argument. No dependencies are needed
for the tutorial's standard-library-only implementation. Finally run the consuming
flow: dependency checks alone do not prove ABI compatibility or task behavior.

## Configuration

Use `weavem.toml` to establish a project root:

```toml
[weavem]
store = "task-store"
work_dir = ".artifacts"
```

Selection: explicit `--project` / SDK `project`, otherwise nearest ancestor containing
`weavem.toml`, otherwise current working directory. Paths in config, explicit store/work
arguments, and environment overrides are resolved relative to that selected root;
absolute paths remain absolute. The project selector itself resolves from the current
working directory. Path values support `~`, not shell-variable interpolation in TOML.

| Setting | Priority, highest first |
| --- | --- |
| Store | Explicit store argument → `WEAVEM_STORE` → config `store` → `task-store` |
| Build/test workspace | Explicit `work_dir` / `--work-dir` → `WEAVEM_ARTIFACTS_DIR` → config `work_dir` → `.artifacts` |

Empty environment values are ignored. Compatibility aliases `store_path` and
`artifacts_dir` are accepted in config; canonical keys take precedence when both
are present. Use the canonical keys in new projects. No `.weavem` directory is needed.
Keep the store when cleaning temporary work; it contains your consumable task artifacts.

## Python SDK

```python
from pathlib import Path
from weavem import flow, task

normalize_names = task(
    "text.normalize_names", "1.0.0",
    store=Path("task-store"),
    name="normalize-names", retries=2,
)
```

This resolves an artifact you supply; it does not install or create the example task.
`task(task_id, version, *, store=None, policy=None, project=None, **task_options)`
returns a genuine Prefect Task. Task invocation—not wrapper creation—resolves and
validates the artifact and loads the export. Store path configuration is selected
when the wrapper is created; changing the working directory afterwards does not
retarget that wrapper.

- `store`: path string, `Path`, or `TaskStore` adapter. Omit to use project configuration.
- `project`: directory or config path; omit for automatic selection.
- `policy`: callable receiving a `Manifest` and returning literal `True` to allow.
  False-like values, other truthy values, and exceptions deny execution. Omit for no
  additional policy. It is not a sandbox or publisher-authentication mechanism.
- Other keywords are passed to Prefect's task decorator, not to your task function.
  Pass task inputs when calling the returned Task.
- `flow(...)` forwards to Prefect's real flow decorator. `.with_options(...)` remains
  available on Prefect objects. Persistent caching is outside the verified MVP;
  follow the guide's explicit no-cache example for local work.

A custom adapter implements `resolve(task_id, version) -> ArtifactRef`, `list()`
returning an iterable of references, and `publish(completed_staging_dir) -> ArtifactRef`.
Import these from `weavem.store`; an `ArtifactRef` contains a local artifact-directory
`root`. Adapters must materialize local files and cannot bypass runtime checks.
The built-in `LocalStore` is enough for folder-based distribution. Do not build a
registry or adapter merely to share a folder.

## Errors and trust boundaries

The SDK exposes errors from `weavem.contracts`: `ContractError`, `ManifestError`,
`StoreError`, `IntegrityError`, `CompatibilityError`, and `PolicyError`. Build failures
use `weavem.build.BuildError`. Handle errors at the application boundary; do not turn
validation failures into successful results or import unverified author code as a fallback.
Exceptions from task implementations remain task failures under Prefect.

Discovery is metadata-only, **not** an integrity, compatibility, or execution-policy
approval. Successful `task info` does not prove a task is safe or runnable. Only run
trusted publishers' artifacts. See the [artifact contract](artifact-contract.md) and
[limitations](limitations.md) for runtime checks, immutability, and caching boundaries.
