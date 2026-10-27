# Task and flow artifact contracts

This page defines schema-1 release artifacts: what build produces, what publish
stores, and what a consumer must preserve. It is independent of the Weavem
package version and of an individual task or flow version. For source metadata
and commands, see the [reference](reference.md).

## Terms

- **Source** is editable author code plus its TOML metadata and tests.
- **Candidate** is a validated, unpublished directory created by `build`.
- **Release** is the manifest and named payload copied unchanged into a store by
  `publish`.
- **Store** is a local directory tree of releases. It can be copied or extracted
  beside another project; an archive is transport only, never runtime input.

Source edits never change an existing candidate or release. A candidate should be
retained until publication and verification finish. A release is immutable: changed
behavior requires a new task/flow version.

## Task release

### Layout

The default store is `<project>/task-store/`. A task release occupies:

```text
task-store/
└── <task-id>/<version>/<python-cache-tag>/
    ├── manifest.json
    └── <module-leaf>.py             # Python backend
    # or <module-leaf><extension-suffix>  # Cython backend
```

Publication writes exactly `manifest.json` and its named payload. Python may
later create a derived `__pycache__/` directory; it is not release identity and
is not required for distribution. A task release has no supported packaged helper
modules or resources. Keep the original manifest, payload name, and layout when
copying it.

### `manifest.json`

Generated task manifests use canonical JSON (sorted keys, compact separators,
UTF-8, newline terminated). A reader rejects duplicate or unknown fields. Build
writes every field below; fields marked “derived” are not author configuration.

| Field | Meaning |
| --- | --- |
| `schema` | Artifact-schema version. Generated value is integer `1`; it is not the task version or Weavem package version. |
| `task_id` | Exact task identity from source metadata. |
| `version` | Exact task release version from source metadata. |
| `backend` | `python` or `cython`, identifying the payload form. |
| `module_leaf` | Generated safe module name. It is derived from task ID, version, and the canonical source/config digest. |
| `export` | Name of the callable loaded from the payload. |
| `artifact_name` | Payload filename. It must be exactly `<module_leaf>.py` for `python`, or `<module_leaf><ext_suffix>` for `cython`. |
| `artifact_sha256` | Lowercase SHA-256 digest of the payload bytes. |
| `artifact_size` | Payload byte length. |
| `source_digest` | Lowercase SHA-256 over canonical source metadata and source bytes; used in generated identity, not as a replacement for the payload digest. |
| `python_cache_tag` | CPython cache tag used to select the artifact directory and checked at runtime. |
| `platform` | Platform string recorded from the build interpreter and checked at runtime. |
| `ext_suffix` | `null` for a Python payload; the build interpreter's extension suffix for a Cython payload. |
| `dependencies` | Exact `distribution==version` runtime pins copied from source metadata. |
| `description` | Optional descriptive metadata copied from source. It does not alter runtime validation. |
| `inputs` | Descriptive input strings copied from source. They are not machine-enforced types. |
| `output` | Descriptive output string copied from source. It is not machine-enforced. |
| `build` | String-to-string facts recorded by the builder. A Python build records `backend`; a Cython build records `backend`, `python`, `compiler`, `headers`, `target`, and `debug_symbols`. Treat it as build provenance, not a portable environment lockfile. |

`schema`, task/flow `version`, and the installed Weavem package version answer
different questions: the first governs this JSON structure; the second is the
immutable release identity; the third selects framework behavior and dependencies.

### Build and runtime checks

Task build snapshots the one implementation file and `tests/`, compiles source,
runs a non-empty standard-library `unittest` suite, and rejects a test that
mutates its source snapshot. It then copies the Python module or compiles the
Cython extension, smoke-imports the artifact, and checks that its export is a
callable rather than an already-decorated Prefect task. Cython build additionally
reruns the authored behavior tests against the compiled artifact without the
author implementation present.

### Native build provenance and binary hygiene

For the supported native lane, Weavem uses its pinned managed Zig compiler and
verified bundled headers when they match the interpreter; a Python installation
with complete matching headers is the supported fallback. The native probe checks
that the selected headers/compiler can compile and import an extension before
author code is compiled. Weavem does not guess an ABI or install OS compiler or
header packages.

The managed compiler targets Linux x86_64 with glibc 2.28, strips debug symbols,
uses a deterministic build environment, remaps the private work directory, and
rejects a binary containing an absolute source, staging, or build-work path.
Those measures reduce accidental path leakage; they do not promise byte-for-byte
reproducibility across builds, hosts, or toolchains. Retain the candidate that
passed tests and publish that exact candidate instead of rebuilding it separately
for each recipient.

Before an artifact is loaded, Weavem checks regular non-symlink paths, manifest
identity, payload size and digest, interpreter cache tag, platform, native
extension suffix where applicable, installed dependency pins, and an optional
policy. These checks occur when a task executes. They do not sandbox payload
code or authenticate its publisher.

### Publication and distribution

Publication validates a candidate, copies its exact bytes through a private
destination directory, then atomically renames it into the store. Repeating a
publication with identical bytes succeeds; different bytes at the same
`task_id==version` fail. Cooperative locks coordinate cooperative local writers,
not hostile writers or distributed filesystems.

To use a copied/extracted store, the consumer needs Weavem, a compatible runtime,
and every declared task dependency installed independently. Native releases also
need a matching compatible Python/platform. The consumer does **not** need the
author source tree or native compiler. A copied store is not a Python environment
lockfile.

## Flow release

### Layout

Flows share a task store but live under a reserved namespace:

```text
task-store/
└── _flows/<flow-id>/<version>/<python-cache-tag>/
    ├── manifest.json
    └── <module-leaf>.py
```

`_flows` cannot collide with a valid task ID because task IDs start with an ASCII
letter. A flow release has one Python payload; flow lifecycle commands do not
package helper modules or resources.

### `manifest.json`

Flow manifests require exactly these fields; unknown or missing fields fail:

| Field | Meaning |
| --- | --- |
| `schema` | Artifact-schema version. Generated value is integer `1`; separate from flow version and package version. |
| `kind` | Literal `"flow"`, distinguishing this manifest from a task manifest. |
| `flow_id` | Exact flow identity from source metadata. |
| `version` | Exact immutable flow release version from source metadata. |
| `module_leaf` | Generated safe module name derived from the flow source and the recorded dependency pins. |
| `export` | Name of the Prefect `Flow` exported by the payload. |
| `artifact_name` | Payload filename, exactly `<module_leaf>.py`. |
| `artifact_sha256` | Lowercase SHA-256 digest of the flow payload bytes. |
| `artifact_size` | Flow payload byte length. |
| `python_cache_tag` | Build interpreter cache tag; checked when loading a release. |
| `platform` | Build platform string; checked when loading a release. |
| `task_dependencies` | Array of immutable dependency pins, each with exactly `alias`, `task_id`, `version`, and `manifest_sha256`. |

Each `task_dependencies` entry means: calls using `alias` resolve to that exact
task ID/version only if the consumer store contains a task manifest whose
canonical SHA-256 equals `manifest_sha256`. Consumer bindings cannot replace it.

### Build, publication, and execution

Flow build first requires every alias in source `tasks` to select an already
published release. It checks this **before** tests or workspace creation. It then
tests a snapshot under those pins, rejects empty suites/source mutation, writes a
candidate, and smoke-imports it. It cannot prove every branch of arbitrary Python
uses only declared aliases; runtime guards enforce the alias boundary on execution.

Flow publish requires all pinned tasks in the destination store and does not copy
them automatically. A consumer therefore receives the whole relevant store:
the flow release **and** its task releases. It can then load the flow without an
author checkout, a Git repository, or a network registry.

Flow release exports must be synchronous Prefect flows using the local
`ThreadPoolTaskRunner`; async/generator flows and distributed execution are not
supported. The loader verifies the flow manifest, payload bytes, interpreter and
platform, and all task pins before import and again when it executes the release.

## Cache and filesystem rules

Python may create `__pycache__/` as derived data. It is not release identity and
Weavem never executes a cache file instead of the verified payload. Flow loading
permits only a regular `__pycache__/` directory containing direct, regular,
non-symlink `.pyc` files. Other unexpected entries, symlinks, or nested cache
directories fail flow validation. Preserve only the manifest and named payload
when distributing a release.

If a publisher is killed, a private directory or cooperative lock can remain.
An operator must first establish that no publisher is active before clearing stale
state. Weavem does not promise distributed transactions, crash-durable recovery,
or automatic garbage collection.

## Trust boundary

Hashes detect accidental or unauthorized byte changes after a manifest is known;
they do not sign, authenticate, or make code safe. A task or flow runs with the
consumer process's privileges. Keep release stores read-only to consumers where
stronger operational isolation is needed, and run only artifacts from publishers
you trust.
