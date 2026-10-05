# Task artifact contract

Schema 1 defines the boundary between a task author and a consuming flow project.
It is independent of task version numbers and the Weavem package version.

## Author metadata

A task source directory contains `task.toml`, one Python implementation module, and
source tests under `tests/`. The metadata belongs in a `[task]` table.

This is an illustrative configuration **after editing the scaffold**:

```toml
[task]
schema = 1
task_id = "company.process_records"
version = "1.2.0"
backend = "cython"
source = "implementation.py"
export = "run"
dependencies = []
description = "Process records using company-specific rules"
inputs = ["records: list[dict]"]
output = "list[dict]"
```

| Field | Meaning |
| --- | --- |
| `schema` | Author contract version; currently `1`. |
| `task_id` | Stable identity used by consumers. |
| `version` | Exact task version, not a range or a moving alias. |
| `backend` | `python` for a `.py` payload; `cython` for a native extension. |
| `source` | One implementation filename relative to the task source directory. |
| `export` | Name of the exported bare callable; not a decorated Prefect Task. |
| `dependencies` | Required installed distributions, expressed as exact pins. |
| `description`, `inputs`, `output` | Descriptive interface metadata for discovery and tooling. |

`inputs` and `output` do not implement automatic input/output validation. The task
implementation remains responsible for validating its inputs where appropriate.
Task IDs and versions must satisfy the framework's conservative filename-safe syntax.

## Promotion boundary

Both backends follow the same lifecycle:

1. Validate author metadata and snapshot the implementation and tests.
2. Check source syntax and run a non-empty `unittest` suite.
3. Reject tests that mutate the implementation snapshot.
4. Copy the Python payload or compile the native payload.
5. Smoke-import the standalone artifact and verify its bare callable export.
6. Publish the completed manifest/payload directory to the store.

A source directory is not itself a consumable task. Consumers do not repeat the
build process, and changing an author's source cannot update published bytes.
Native module names are chosen at build time; renaming a compiled extension is not
a version-isolation mechanism.

## Published layout

The visible default store is `<project>/task-store/`, or `<working-directory>/task-store/`
when no project config is selected. Each task version occupies:

```text
task-store/
└── <task-id>/<version>/<python-cache-tag>/
    ├── manifest.json
    └── <canonical-module-name>.so    # or .py
```

A published directory contains exactly the manifest and its named payload. Keep the
original filenames and directory layout when distributing it. Published versions
are immutable; changed implementations need a new version.

The manifest records:

- Task ID/version, schema, and descriptive interface metadata.
- Backend, exported symbol, and canonical module name.
- Source/config digest and payload SHA-256/size.
- Interpreter cache tag, platform, and native extension suffix where applicable.
- Dependency pins and build facts.

Unknown schemas are rejected. The manifest is data, not executable configuration.

## Distribution and resolution

A store can be copied or extracted beside a consumer's flow code. An archive is
optional transport, never runtime input. No publication database, author checkout,
Git repository, or network registry is needed to resolve its tasks.

The consumer requests an exact ID/version. Python/platform compatibility and installed
dependencies are required regardless of how the files were delivered. Discovery
reads metadata without importing the implementation.

`TaskStore` is a structural adapter contract with three operations: resolve an exact
task to an `ArtifactRef`, list built artifact references, and publish a completed
staging directory. The local filesystem implementation is the default. Other adapters
must supply locally materialized artifacts; they do not replace runtime validation.

## Execution checks

Before loading and calling a task, the runtime checks artifact paths, manifest/request
identity, payload size/hash, interpreter/platform compatibility, installed dependencies,
and any supplied policy. A supplied policy must explicitly return `True`; denial or
an exception prevents execution. Omitting a policy is supported.

Checks repeat for each executed invocation, including retries and reuse of an imported
module. A process cannot load different artifact identities for the same logical task
ID/version. Publish a new version rather than substituting a different implementation.

Prefect result-cache hits do not execute the adapter. Persistent caching is outside
the verified MVP and cannot be treated as a fresh artifact/policy check.

## Dependencies and trust

Dependency declarations accept only `distribution==installed-version` pins. Missing
or mismatched distributions fail before loading. Extras, markers, version ranges,
direct URLs, automatic downloads, and dependency solving are not supported.

SHA-256 checks detect corruption; they do not authenticate publishers. Task code runs
with the process's privileges and is not sandboxed. Local publication coordinates
cooperating writers; it does not promise protection from malicious filesystem actors
or crash-durable distributed transactions.
