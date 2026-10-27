# Reference

This reference describes the released Weavem `0.1.0a2` interface. Start with
the [authoring guide](authoring-guide.md) for a complete working example. The
[artifact contract](artifact-contract.md) is the authoritative reference for
generated release files and their integrity rules.

Run project commands from a directory containing `weavem.toml`, or put the
global selector before the command: `weavem --project PATH ...`.

## CLI

All project and source arguments below are interpreted from the shell's current
directory unless noted otherwise. Configured paths and `--from`/`--to` paths are
anchored to the selected project root. Commands that fail through Weavem's
handled error boundary print `weavem: ...` to standard error and exit `2`.
Successful commands exit `0`; a task or flow implementation exception is an
ordinary Python/Prefect failure and does not have a Weavem error code.

| Command | What it does |
| --- | --- |
| `weavem project new DIRECTORY` | Creates a new local project, including `weavem.toml`, `tasks/`, `flows/`, a project README, and a `.gitignore`. Refuses an existing path. |
| `weavem doctor [--work-dir PATH]` | Verifies the managed native compiler, headers, and a compile/import probe. Prints JSON. |
| `weavem task new DIRECTORY [--id ID] [--version VERSION] [--backend python\|cython]` | Creates one editable task folder. The initial export is `run(value)`, a pass-through starter. |
| `weavem task use ALIAS --path DIRECTORY` | Selects an editable task folder inside the project for an alias. |
| `weavem task use ALIAS --release ID==VERSION [--from STORE]` | Validates a stored task and pins the alias to that exact release and canonical manifest digest. `--from task-store` is the configured default. |
| `weavem task validate DIRECTORY` | Reads and validates `task.toml` and the referenced source-file location. It does not compile, run tests, build, or publish. |
| `weavem task test DIRECTORY [--work-dir PATH]` | Snapshots the source and tests, compiles the source, and runs a non-empty standard-library `unittest` suite. It does not build a distributable artifact or publish. |
| `weavem task build DIRECTORY [--work-dir PATH]` | Performs source checks/tests and creates an unpublished candidate. For `cython`, it also compiles and reruns the authored tests against the compiled export. Prints JSON with `root` and `manifest`. |
| `weavem task publish CANDIDATE [--to STORE]` | Validates and copies the existing candidate bytes into a local store. It never rebuilds source. Prints JSON with the stored `root` and `manifest`. |
| `weavem task list [--store STORE] [--json]` | Lists task artifact directories in a local store. |
| `weavem task info ID==VERSION [--store STORE] [--json]` | Reads stored task metadata without importing its payload. |
| `weavem flow new NAME` | Creates `flows/NAME.py`, `flows/NAME.toml`, and `tests/flows/NAME/test_flow.py`. `NAME` must be a non-keyword Python identifier. |
| `weavem flow validate NAME` | Validates flow metadata and declared bindings without running the flow. Local task bindings are source-validated; released bindings are validated as artifacts. |
| `weavem flow test NAME [--work-dir PATH]` | Runs a non-empty standard-library `unittest` suite from `tests/flows/NAME/`. Local bindings are allowed. It does not package or publish. |
| `weavem flow build NAME [--work-dir PATH]` | Requires every declared alias to be a published, pinned release before tests or workspace creation. Tests a snapshot under those pins and creates an unpublished flow candidate. |
| `weavem flow publish CANDIDATE [--to STORE]` | Publishes a prebuilt flow candidate. The destination store must already contain every pinned task. |
| `weavem flow run NAME [--params JSON]` | Loads and runs editable `flows/NAME.py`; `--params` is a JSON object of keyword arguments. |
| `weavem flow run ID==VERSION --release [--store STORE] [--params JSON]` | Loads and runs an exact stored flow release. Its recorded task pins, not consumer bindings, select dependencies. |
| `weavem flow list [--store STORE] [--json]` | Lists stored flow artifact directories. |
| `weavem flow info ID==VERSION [--store STORE] [--json]` | Reads stored flow metadata without importing flow code. |

`validate` and `test` print a `... passed: ...` message only after success.
`build` and `publish` print JSON because their `root` value is input to the next
step. Keep that candidate until publishing and verification are complete.

## Configuration

### Project bindings

`weavem.toml` establishes a project root and can select paths:

```toml
[weavem]
store = "task-store"
work_dir = ".artifacts"

[tasks.normalize]
path = "tasks/text_normalize"
```

`[tasks."alias"]` selects **exactly one** source:

```toml
# Editable source. It must remain inside the project root.
[tasks.normalize]
path = "tasks/text_normalize"

# Or an immutable release. `weavem task use` writes the digest.
[tasks.normalize]
release = "text.normalize==1.0.0"
source = "task-store"
manifest_sha256 = "<64 lowercase hexadecimal characters>"
```

Do not hand-edit a release digest to make a different artifact fit. A local
binding never falls back to a release if its source is missing. Release bindings
can point at a sibling store with `source = "../shared-store"`.

### Selection and path precedence

The selected project is, in order: an explicit `--project`/SDK `project` path;
the nearest ancestor containing `weavem.toml`; or the current directory. A
project selector itself resolves from the shell's current directory.

| Value | Highest to lowest priority |
| --- | --- |
| Task/flow store | Explicit `--store` or SDK `store` → `WEAVEM_STORE` → `[weavem].store` → `task-store` |
| Test/build work directory | Explicit `--work-dir` or SDK `work_dir` → `WEAVEM_ARTIFACTS_DIR` → `[weavem].work_dir` → `.artifacts` |

Empty environment values are ignored. `store_path` and `artifacts_dir` are
accepted legacy configuration keys; the canonical `store` and `work_dir` win if
both are present. Paths may use `~`; TOML does not expand shell variables.

`.artifacts/` is disposable work space and retained unpublished candidates.
`task-store/` is an immutable release store, not disposable cache. No `.weavem`
directory, server, or registry is required.

## Source metadata

### Task `task.toml`

New task metadata belongs in a `[task]` table. Unknown keys fail validation.

```toml
[task]
schema = 1
task_id = "text.normalize"
version = "1.0.0"
backend = "python"
source = "implementation.py"
export = "run"
dependencies = []
description = "Normalize one text value"
inputs = ["text: text to normalize"]
output = "normalized text"
```

| Field | Required/default | Meaning and constraint |
| --- | --- | --- |
| `schema` | defaults to `1` | Source-metadata schema. Only integer `1` is accepted. It is not the task version or Weavem package version. |
| `task_id` | required | Stable task identity. ASCII letter first; then ASCII letters, digits, `_`, `.`, or `-`; at most 128 characters. |
| `version` | required | Exact published identity, not a range or “latest”. It is 1–128 ASCII characters: letter/digit first, then letters, digits, `_`, `.`, `+`, or `-`. Change it before publishing changed bytes. |
| `backend` | `"python"` | `"python"` copies a Python payload; `"cython"` compiles a native extension. |
| `source` | `"implementation.py"` | One safe relative filename in the task folder. The task lifecycle packages one implementation module, not an arbitrary package tree. |
| `export` | `"run"` | A Python identifier naming the module-level callable Weavem exposes. It must not already be a Prefect `Task`. |
| `dependencies` | `[]` | Exact installed distribution pins, each `distribution==version`. They are checked, not installed or solved. |
| `description` | omitted | Optional descriptive string for people and tooling. |
| `inputs` | `[]` | Descriptive, non-empty strings. They are not runtime type declarations. |
| `output` | `"Any"` | Non-empty descriptive string. It is not runtime type enforcement. |

Use `text.normalize` at `1.0.0` for the Python tutorial task. A native revision
of the same task should use a new immutable version, such as `1.1.0`; it is not
an in-place replacement for `1.0.0`.

For compatibility, a root-level task table is accepted, as is `source_path` in
place of `source`; if both source keys occur, `source` wins. New files should use
`[task]` and `source`. `id` is not an alias for `task_id`.

Write a module-level export function even if your implementation uses classes:

```python
class Normalizer:
    @classmethod
    def normalize(cls, text: str) -> str:
        return " ".join(text.split()).lower()


def run(text: str) -> str:
    return Normalizer.normalize(text)
```

This makes the release boundary explicit. The framework allows one implementation
module and one exported callable; it does not package arbitrary helper modules,
resources, or application packages with a task.

### Flow sidecar `flows/NAME.toml`

Flow metadata belongs in `[flow]`; unknown fields fail validation.

```toml
[flow]
schema = 1
flow_id = "text.process_documents"
version = "1.0.0"
source = "process_documents.py"
export = "process_documents"
tasks = ["normalize"]
```

| Field | Required/default | Meaning and constraint |
| --- | --- | --- |
| `schema` | defaults to `1` | Flow-source schema. Only integer `1` is accepted; it is separate from the flow version and package version. |
| `flow_id` | required | Stable flow identity using the same conservative ID syntax as a task ID. |
| `version` | required | Exact release identity, not a range or “latest”. |
| `source` | required | A safe `.py` filename in `flows/`; its basename must be a Python identifier. |
| `export` | required | A non-keyword Python identifier naming a real Prefect `Flow`. |
| `tasks` | `[]` | Unique project task aliases that the source flow may use. Build/publish turn released aliases into immutable pins. |

The tutorial flow is `text.process_documents` at `1.0.0`. A changed, published
flow needs a new version (for example, `1.1.0`) and pins the exact task releases
selected when it is built.

## Validation, testing, building, and publishing

These stages deliberately answer different questions:

| Stage | Task | Flow | Does not do |
| --- | --- | --- | --- |
| Validate | Metadata and referenced source location are valid. | Metadata/bindings are valid; release bindings are artifact-validated. | Run source tests, package, publish. |
| Test | Source snapshot compiles and its non-empty `unittest` suite passes. | Non-empty flow suite passes; local bindings are allowed. | Create a distributable release or publish. |
| Build | Repeats source tests; produces a candidate and smoke-imports it. Native tasks also test the compiled export. | Requires all declared aliases to be published first, tests under exact pins, then creates/smoke-tests a candidate. | Publish or replace a stored release. |
| Publish | Copies the exact valid candidate to a local store. | Copies the exact valid candidate only if its pinned tasks exist in the destination store. | Rebuild source, auto-publish dependencies, or overwrite different bytes. |

The store accepts an idempotent repeat of identical bytes. Different bytes at an
existing task or flow ID/version fail. A candidate is not a release until
`publish` succeeds.

## Python SDK

The public package API is `flow`, `task`, `load_flow`, and `Project`:

```python
from pathlib import Path
from weavem import Project, flow, load_flow, task

# Use a project alias in editable or project-bound code.
normalize = task("normalize")

# Or request an exact stored task outside a released flow.
normalize_release = task("text.normalize", "1.0.0", store=Path("task-store"))

@flow
def local_process(text: str) -> str:
    return normalize(text)

published_process = load_flow(
    "text.process_documents", "1.0.0", store="task-store"
)

metadata = Project.open(".").metadata()
```

### `task`

`task(task_id, version=None, *, store=None, policy=None, project=None,
**task_options)` returns a real Prefect `Task`.

- With `version=None`, `task_id` is a selected project alias. Do not pass
  `store`; select its source with `weavem task use`.
- With an exact `task_id` and `version`, `store` selects the local store. This
  form is for direct exact release use, not for a task inside a released flow.
- Resolution, dependency checks, integrity checks, and payload loading occur on
  invocation, not merely while constructing the Prefect task.
- `policy` receives a generated task manifest and must return literal `True` to
  allow execution. Any other return value or exception denies execution. It is
  a local allow/deny hook, not a sandbox or publisher-authentication system.
- `task_options` go to Prefect's task decorator. Function arguments go to the
  returned task when it is called.

Weavem uses Prefect's `NO_CACHE` default so a normal invocation reaches its
adapter checks. Explicitly enabling Prefect result caching can skip invocation
and its current checks; that configuration is outside the supported verification
boundary.

### `flow`

`flow(*args, **kwargs)` forwards directly to Prefect's real `flow` decorator.
Use it on a synchronous flow function. A releasable flow export must be a
Prefect `Flow`, use the local `ThreadPoolTaskRunner`, and must not be async or a
generator. `.with_options(...)` remains the Prefect API.

### Released flow SDK

`load_flow(flow_id, version, *, store=None, project=None)` returns a real
Prefect `Flow` from an exact stored release. The supplied store must contain the
flow and every dependency pinned in its manifest. Consumer project bindings
cannot override those pins. The returned flow keeps the authored signature and
Prefect options.

### Local project metadata (Python API)

`Project.open(path=None)` selects a local project (or discovers one from the
current directory). `.metadata()` returns a JSON-compatible, schema-1 snapshot
without importing task/flow payloads, starting Prefect, compiling, writing files,
or making network calls.

The snapshot contains:

| Key | Contents |
| --- | --- |
| `schema` | Metadata-snapshot schema, currently `1`; independent of package/task/flow versions. |
| `project` | Absolute root, optional config path, selected store path, and work directory. |
| `tasks` | Authored task metadata and absolute `task.toml` paths. |
| `flows` | Authored flow metadata and absolute sidecar paths. |
| `bindings` | Selected aliases plus path/release/source/digest fields; unused alternatives are `null`. |
| `releases` | Task releases referenced by released bindings, including their canonical manifest metadata and digest. |

It validates metadata and released-binding digests but not a payload's bytes,
ABI, dependencies, or safety. It is a filesystem read, not an atomic snapshot;
invalid definitions or pins fail the entire call. There is no `Project.task()`
execution API and no Weavem API server.

## Provision task dependencies

Install each declared task dependency in the author environment before testing
and in the consumer environment before running. Weavem accepts only exact
distribution pins; it does not install, download, solve, bundle, or lock those
dependencies. Distribution names can differ from Python import names.

## Errors and trust

The SDK raises `ContractError`/`ManifestError` for malformed metadata,
`BuildError` or `FlowError` for lifecycle failures, `StoreError` for local-store
failures, `IntegrityError` for altered or invalid artifacts, `CompatibilityError`
for runtime/dependency mismatches, `NativeError` for managed compiler/header
failures, and `PolicyError` for a denied policy. These are exception classes, not
a documented machine-readable error-code protocol.

`task info`, `flow info`, and `Project.metadata()` are metadata inspection only.
They do not establish that a payload is safe, compatible, or executable. Hashes
detect changed bytes; they do not identify a publisher. An artifact runs with the
Python process's privileges. Share and run only artifacts from publishers you
trust. See [artifact contract](artifact-contract.md) and
[limitations](limitations.md) for release layout, runtime checks, and support
boundaries.

## Native environment

`weavem doctor` is the explicit native environment check. It uses the configured
work directory and reports actionable compiler/header diagnostics; it does not
silently install OS packages. `task build` runs the same check for a Cython task.
The managed build strips debug symbols, remaps its private work path, and rejects
a binary containing absolute author/build paths. These are release-hygiene checks,
not a reproducible-build guarantee: retain and publish the original candidate
rather than rebuilding it for another destination.
See [native authoring](native-authoring.md) for supported environments and native
artifact compatibility.
