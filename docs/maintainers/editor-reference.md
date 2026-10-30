# Unreleased visual editor reference

> **Scope:** source-tree reference for the `prototype/node-editor` branch and its unreleased candidate distributions.
> It documents an unreleased editor feature and does not alter the released user
> contract. Start with the human-facing [editor guide](../../ui/README.md) and
> use the [local execution walkthrough](../../examples/editor-local/README.md)
> for the end-to-end sample.

The editor is local-first and code-first. Its UI reads task/flow information,
saves the supported visual subset as ordinary Python flow files, and invokes the
same local-flow loader as the CLI. It is not a new JavaScript execution engine,
a hosted API, a sandbox, or a general Python round-trip formatter.

## Installed assets and execution environment

Candidate wheels and sdists contain the production static UI under `weavem/_ui`.
Consumers launch `python -m weavem editor --project PATH` without Node, npm, a
frontend development server, or an API service deployment. Contributors stage
assets using `python scripts/stage-editor.py` after `npm --prefix ui ci`; explicit
`--ui-dir PATH` remains available for frontend development. No npm runs during
Python installation or editor startup. Missing assets fail with a diagnostic.
These are source-branch contracts, not features of published `0.1.0a2`.

The bridge and worker use the launching Python interpreter (`sys.executable`).
Workers preserve the caller's ordinary environment and Prefect profile; no task
dependencies or virtual environments are provisioned automatically. Session
metadata includes `environment.pythonExecutable`, `pythonVersion`, and
`weavemVersion`; the UI exposes them under **Project environment**. The project is
selected at startup, not by an arbitrary filesystem path sent from the browser.

On an untouched startup the UI connects and lists real flows without opening or
running one. Restored/imported/unsaved drafts remain user-owned; project replacement
requires the existing confirmation path. A failed connection leaves recovery and
retry available rather than substituting synthetic project tasks.

## Authored-flow discovery and persistence

`[weavem].flow_paths` is an ordered nonempty list of directory strings, defaulting
to `["flows"]`. An explicit list replaces rather than extends the default. Relative
paths anchor at the project root; absolute paths are allowed by trusted project
configuration. Paths are normalized and deduplicated in order, with symlinked roots
rejected. Each root contributes only its direct `*.toml` sidecars. Discovery does
not import Python. CLI flow operations, `Project.metadata()`, editor persistence,
and worker resolution share the same resolver in `flow_sources.py`.

A sidecar's stem is the bare local flow name. Duplicate stems across roots stop
resolution with both paths named. An invalid sidecar is diagnostic in the editor
list, while public project metadata remains fail-fast. The editor's internal
task-only catalog does not weaken that public metadata contract.

New definitions use the first root. Existing updates preserve their directory,
declared source filename, flow identity/version/export, sidecar and optional layout
location. The source filename can differ from the local name; an export differing
from the local name remains source-only, as does unsupported Python. Ordinary flow
metadata remains required; no second editor-only runtime metadata is introduced.
Source/sidecar/layout revisions, directory/process locking, atomic writes and
recovery journals remain in force. Journals are named after the metadata stem,
including when the source filename differs. Symlink rejection and stale revision
checks reduce accidental unsafe writes, but do not sandbox trusted configured paths
or hostile concurrent filesystem mutations.

## Task interface hints

`editor_hints.py` reads and parses eligible task source with Python's AST. It
does not import a task, evaluate an annotation, or execute code merely to draw a
form. A source-derived form requires one undecorated top-level exported function
or async function that is not subsequently rebound. Sources must be regular,
inside the task directory, and no larger than 1 MiB.

| Source detail | Editor hint |
| --- | --- |
| `str`, `int`, `float`, `number`, `bool` | String, number, or boolean control |
| Other or unknown annotation | JSON control, with annotation text when available |
| JSON-safe literal default | Default value |
| Non-literal default | Advisory display text only |
| `Literal[...]` with JSON-safe literals | Choice list |
| `Optional[...]`, `Union[..., None]`, or `T \| None` | Nullable hint |
| Locally declared `TypedDict` | Nested field hints (depth is bounded) |
| Function docstring | Description, bounded to 4,096 characters |
| Return annotation | Advisory output hint and eligible `TypedDict` fields |

The editor intentionally does not expose positional-only arguments, `*args`, or
`**kwargs` as named form controls. If source is unavailable or ineligible—for
example, for a compiled/released task—the editor may use the task metadata's
`inputs` strings. That metadata is descriptive; it does not prove a callable
signature, a value shape, or compatibility between two tasks. Unknowns remain
unknown and use JSON rather than a fabricated field form.

## Drafts, graphs, and saved flows

These formats are not interchangeable.

| Format | Role | Current schema | Compatibility |
| --- | --- | --- | --- |
| Editor draft (`weavem.editor-draft`) | Browser editing state: catalog, nodes, positions, notes, parameters, connections, viewport | 3 | Reader accepts drafts 1, 2, and 3; it writes schema 3 |
| Executable graph (`weavem.graph`) | Validated intermediate representation used while saving supported visual flows | 1 or 2 | Schema 1 remains valid for whole-result wires; schema 2 is required when any wire selects an upstream field |
| Flow source and metadata | Authoritative Python source and TOML sidecar in a configured root (`flows/` by default) | Flow metadata schema is independent | Saved by the editor only for its supported Python subset |
| Layout (`<root>/<name>.layout.json`) | Non-executable positions, labels, notes, and viewport | 1 | Optional; it cannot change runtime behavior |

A draft connection can omit `argument` only as legacy editing state. A runnable
connection needs exactly one valid named target argument. One target argument
cannot receive both a literal parameter and a wire, and a target argument cannot
receive two wires. Graphs are acyclic.

### Field-path semantics

A wire normally passes the whole upstream result. A selected `sourcePath` is an
array of string keys and non-negative integer indexes, at most 32 parts long.
For example, `["customers", 0, "email"]` becomes ordinary Python indexing of the
upstream value. It does not evaluate a browser expression. An omitted or empty
path means the whole value. A nonempty path requires executable-graph schema 2;
using it with schema 1 is invalid. Missing keys or indexes fail during execution.

The UI can offer declared fields from an annotation and observed fields from a
non-truncated bounded result preview. Neither is a runtime schema or type proof.

## Bounded result previews

The worker returns a preview, not a complete result dataset. `safe_preview` only
structurally traverses exact built-in `list`, `tuple`, and `dict` containers plus
scalar built-ins; it avoids custom container/serialization protocols. It limits:

- structural depth to 6;
- values/items across a preview to 100;
- an individual string to 4,096 UTF-8 bytes;
- the converted value budget to 5,500 bytes; and
- the serialized preview envelope to 15 KiB.

The result is either a JSON envelope with `kind: "json"`, `value`, `preview`, and
`truncated`, or a textual envelope with `kind: "text"`, `preview`, and
`truncated: true`. Cycles, unsupported values, non-finite floats, and exhausted
limits can truncate or fall back to text. The textual fallback bounds Python's
`repr(value)`; it does not promise that a trusted task object's custom `__repr__`
is side-effect-free. A preview is not safe to use as source data and must not be
treated as a complete response.

## Structured task errors

`TaskError` is the optional public error contract. Its constructor accepts
positional or keyword optional fields:

```python
TaskError(code, message, input=None, remediation=None, retryable=None)
```

`code` and `message` must be non-empty strings. `input` and `remediation` are
strings or `None`; `retryable` is `bool` or `None`. It is exported from
`weavem`, so task code can use it as follows:

```python
from weavem import TaskError

raise TaskError(
    "customer.not_found",
    "No customer exists with this ID",
    "customer_id",
    "Choose an existing customer ID",
    False,
)
```

The CLI catches a top-level `TaskError`, writes a human line and a JSON object
containing `error` to **stderr**, then exits with status 2. The editor worker
serializes it into its node/run error details. If a `TaskError` is chained inside
another exception, serialization follows the cause/context chain and preserves
the structured fields while reporting the outer exception type. Other exceptions
produce only a bounded `type` and `message` representation. The CLI's normal
success output is separate; callers must not assume failure JSON is on stdout.

`retryable` is advice for a person or client. It neither retries work nor changes
Prefect retry settings, and it does not make an idempotence claim.

## Last-run inspection records

Before a worker starts, the bridge captures an immutable JSON snapshot of the
opened flow: name, revision, source and metadata (when available), hashes,
graph, layout, catalog/bindings, parameters, and start time. It writes
`inspection.json`; active/terminal status, logs, and bounded result data live in
`inspection-state.json`, both under the configured artifact directory's
`editor-runs/<run-id>/` folder.

A snapshot is preserved exactly or rejected. Each inspection file is limited to
8 MiB and nesting is limited to 64 levels. The state file also has an 8 MiB
limit; logs are separately capped at 64 KiB and gain an explicit truncation
marker. The browser's **Last run** chooses the most recently started valid record
for that flow, based on the immutable snapshot timestamp/record ordering rather
than later state writes.

Records survive a bridge restart as inspection evidence. They do not restore a
process, streaming connection, cancellation control, or a previous execution
environment. A status recorded as running after restart is presented as last
observed rather than live. Re-running uses current local code and dependencies;
records provide diagnosis, not reproducible replay.

## Contributor checks

Use the frontend check names in `ui/package.json`: `typecheck`, `lint`, `test`,
`build`, and `test:e2e`. `node scripts/verify-editor.mjs` is the repository-level
runtime smoke check after the frontend build and Playwright browser setup. It
creates its own loopback bridge and retains evidence in
`.artifacts/node-editor/live/`. Keep evidence private: snapshots, parameters,
logs, error messages, and previews can contain sensitive information, and the
editor does not guarantee secret detection or redaction.

For current UI conventions, contribution boundaries, and the user-oriented
explanation, return to the [editor guide](../../ui/README.md#frontend-contribution-conventions).
