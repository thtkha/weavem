# Reference

Run commands from a project containing `weavem.toml`, or pass `--project PATH`.
`[weavem] store` selects the default `task-store`; `work_dir` selects `.artifacts`
by default.

## Tasks and bindings

```bash
weavem task use ALIAS --path tasks/foo
weavem task use ALIAS --release ID==VERSION [--from SOURCE]
```

The first writes `[tasks."ALIAS"] path = "tasks/foo"`. The second validates an
existing artifact and writes `release`, `source`, and canonical `manifest_sha256`.
`--from task-store` (the default) means the configured store; another value is an
explicit project-relative store path. A released binding always requires its digest.

```bash
weavem task validate DIR
weavem task test DIR
weavem task build DIR --work-dir .artifacts
weavem task publish CANDIDATE --to STORE
weavem task list [--store STORE] [--json]
weavem task info ID==VERSION [--store STORE] [--json]
```

Build prints JSON containing a persistent candidate root. It does **not** publish.
Publish preserves that candidate on success, idempotence, and conflict. Older
`task build --store ...` usage migrates to `task build`, then `task publish`.

At runtime `task("alias")` uses a project binding. `task("id", "version")` remains
an exact-store API and is useful outside released flows.
For alias calls, omit `store=`; choose the source with `task use --from` instead.

## Flows

A source flow uses `flows/name.py` and `flows/name.toml`:

```toml
[flow]
schema = 1
flow_id = "name"
version = "0.1.0"
source = "name.py"
export = "name"
tasks = ["normalize"]
```

Build/test require tests are in `tests/flows/name/` and must contain at least one unittest.

```bash
weavem flow validate NAME
weavem flow test NAME
weavem flow build NAME --work-dir .artifacts
weavem flow publish CANDIDATE --to STORE
weavem flow run NAME --params '{"value": 2}'
weavem flow run ID==VERSION --release --store STORE --params '{}'
weavem flow list [--store STORE] [--json]
weavem flow info ID==VERSION [--store STORE] [--json]
```

`flow run NAME` runs local source. `--release` runs a stored release. Build only
accepts declared aliases bound to published releases; it never publishes tasks.

## Scaffolding and paths

```bash
weavem project new DIRECTORY
weavem task new DIRECTORY [--id ID] [--version VERSION] [--backend python|cython]
weavem flow new NAME
```

Global `--project PATH` goes before the subcommand. Project/source/candidate arguments
are relative to the shell working directory; configured store/work paths, `--to`,
`--from`, and `task use --path` are anchored to the selected project root. Absolute
store paths are also accepted. Local task paths must remain inside that project.

Flow scaffolding creates `flows/NAME.py`, `flows/NAME.toml`, and
`tests/flows/NAME/test_flow.py`; it refuses existing targets. Edit the placeholder
implementation, metadata, and tests before releasing meaningful work.

Flow `validate` accepts local bindings; flow `build` requires published dependencies.
Both build and publish print JSON with `root` and `manifest` paths. Handled CLI
failures print a diagnostic to stderr and return 2; success returns 0. Application
exceptions may propagate as ordinary Python/Prefect failures.

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
`task(task_id, version=None, *, store=None, policy=None, project=None, **task_options)`
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
  available on Prefect objects. Weavem tasks default to `NO_CACHE`; explicitly enabling Prefect result caching
  can skip execution-time integrity/policy checks and is outside this verified lane.

A custom adapter implements `resolve(task_id, version) -> ArtifactRef`, `list()`
returning an iterable of references, and `publish(candidate_dir) -> ArtifactRef`.
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

## Released flow SDK

```python
from weavem import load_flow
process = load_flow("text.process", "1.0.0", store="task-store")
result = process(text="Example")
```

This returns a real Prefect Flow with the authored signature and options. Its
recorded task aliases resolve only in the supplied store, regardless of project
bindings. A released flow cannot override those pins. Use `load_local_flow` from
`weavem.flows` to load a source flow by name and selected project.
Flow lifecycle errors use `weavem.flows.FlowError`.

## Managed native environment

`weavem doctor [--work-dir PATH]` verifies the bundled compiler, selects verified
headers (or the interpreter's complete headers), and compiles/imports a probe.
It prints JSON and uses the same configured work directory as task builds.
`task build` automatically performs this check and reruns the authored tests
against the compiled extension. `task test` remains a source test, not publication.
See [native authoring](native-authoring.md).
