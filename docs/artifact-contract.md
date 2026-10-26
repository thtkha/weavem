# Task and flow artifact contracts

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

## Task build and publication boundary

Both backends follow the same lifecycle:

1. Validate author metadata and snapshot the implementation and tests.
2. Check source syntax and run a non-empty `unittest` suite.
3. Reject tests that mutate the implementation snapshot.
4. Copy the Python payload or compile the native payload.
5. Smoke-import the standalone artifact and verify its bare callable export.
   Native builds also replay the authored behavioral tests against the compiled
   export without the Python implementation present, then check that the payload
   was not changed by those tests.
6. Return the completed manifest/payload directory as an unpublished candidate.
7. A separate publish command verifies and copies that exact candidate to the store.
   It preserves the candidate and does not rebuild author source.

An explicit local binding can execute editable source during development. Release
consumers do not repeat the build process, and author edits cannot update published bytes.
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

The canonical release is its manifest and named payload. An optional
`__pycache__/` directory may also be present as a derived Python cache. It may be
empty or contain only regular, non-symlink `.pyc` files directly within that
directory. Cache bytes are not release identity, are ignored as untrusted derived
data, and are never executed instead of the verified payload. Other unexpected
entries, symlinks, and nested cache directories are not part of the artifact
contract. Keep the original manifest, payload filenames, and directory layout when
distributing a store. Published versions are immutable; changed implementations
need a new version.

Task runtime cache handling is unchanged by this convention. The strict cache-layout
validation described for flow releases below is specific to the flow loader.

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
candidate directory without deleting it. The local filesystem implementation is the default. Other adapters
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

## Explicit bindings

Project bindings select either a local source directory or an exact published
ID/version, source folder, and SHA-256 of the canonical task manifest JSON.
`weavem task use` records this digest automatically. A local binding never falls
back to a published release if source is missing. Source edits use a separate
development cache; they cannot replace an already loaded immutable task identity.

## Flow releases

Flows use their own schema-1 manifest, distinguished by `kind: "flow"`. Its fields
are `schema`, `kind`, `flow_id`, `version`, `module_leaf`, `export`, `artifact_name`,
`artifact_sha256`, `artifact_size`, `python_cache_tag`, `platform`, and
`task_dependencies`. Each dependency records `alias`, `task_id`, `version`, and
`manifest_sha256`; there are no author source paths in these pins.

```text
task-store/_flows/<flow-id>/<version>/<python-cache-tag>/
├── manifest.json
└── <canonical-module-name>.py
# optional: __pycache__/*.pyc (derived, untrusted cache only)
```

`_flows` cannot collide with valid task IDs, which must start with an ASCII letter.
Each release is one Python flow file plus its manifest. Flow build checks that every
declared task alias selects an already published release **before** executing tests
or creating workspace files. Tests run on a snapshot under those exact pins; empty
suites and source mutation fail. The same bytes become the candidate, which is also
smoke-imported in an isolated subprocess. Dependencies encountered during tests or
smoke import must be declared aliases; runtime also rejects undeclared aliases.
This is not static proof of every possible branch of arbitrary Python code.

Flow publish requires all pinned tasks in its destination store. It does not copy
them implicitly. Flow loading permits only the optional cache layout described
above: a regular `__pycache__` directory containing direct, regular `.pyc` files (or
no files). The loader ignores those cache files, verifies the manifest, payload,
and pinned dependencies before import and again on invocation, and executes the
verified payload rather than cached bytecode. Other entries,
symlinks, and nested cache directories fail validation. Consumer project bindings
cannot override the release pins. No author source, Git repository, or registry is
needed after copying the whole store.

## Local publication guarantees

Tasks and flows use cooperative directory locks plus private destination-side
copies and atomic rename. Discovery ignores those private copies. Identical retries
are accepted; different content at the same identity/version is rejected. These
guarantees cover cooperating local writers, not distributed filesystem semantics
or malicious writers. A killed publisher can leave a lock/private directory; an
operator must establish no publisher is active before removing stale state. There
is no claim of crash durability, automated garbage collection, or network-store
transactions. Candidates are disposable only after publication; the store is not.
