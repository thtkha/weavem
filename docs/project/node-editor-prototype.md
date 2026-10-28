# Node-editor prototype

**Status: prototype, not a released framework feature.** Branch:
`prototype/node-editor`. Audience: project owner and prototype contributors.

## Decisions

The first experiment was an interactive, dark desktop draft workbench using
React Flow. The next approved slice adds local canvas execution using existing
Weavem/Prefect tasks, not a JavaScript execution engine. A searchable task library,
graph canvas, and inspector support composition, metadata discovery, save/reopen,
explicit argument mappings, and real run feedback. The palette is unchanged;
the owner will provide colors later.
Real projects enter through the existing
[Project.metadata() API](../users/reference.md#local-project-metadata-python-api).
The initial sample catalog is explicitly demo data.

The GUI-library comparison considered React Flow, Rete.js, LiteGraph.js, and
BaklavaJS. React Flow was chosen for custom React components, conventional web
forms, and its documented keyboard/accessibility support. This choice does not
make React Flow the execution model or the owner of Weavem's future graph format.

The masterplan's visual-authoring invariants remain: tasks are the common
vocabulary, the visual layer owns presentation/composition, and Weavem/Prefect
own execution. The masterplan's old “capabilities” terminology is not introduced
into this prototype. Its PipelineSpec discussion is direction, not a settled
schema to pretend has already shipped.

## Prototype contract

A versioned editor document contains the catalog snapshot, task references,
node instances, JSON parameters, notes, argument mappings, positions, and viewport.
The model is independent of React Flow serialization. Schema 2 reads old schema-1
drafts without inventing argument mappings. A separate `weavem.graph` schema 1
contains executable node/task selections, parameters, and argument edges, not
layout or arbitrary Python. It is not a published flow artifact. No Python flow
is inferred from project metadata, which contains definitions rather than order.

The browser contains no task code, credentials, telemetry, or shared database.
The explicit `weavem editor --project PATH` bridge serves the built frontend from
loopback only, fixes the project/interpreter at startup, and rejects invalid
host/origin/session requests. Browser-imported paths do not authorize code
execution. Only tasks explicitly bound by the selected project can run. Published
task pins and normal integrity/compatibility checks remain enforced. Importing a
new catalog starts a new draft rather
than merging identities or silently upgrading versions. Browser autosave is not
a project source file or a safe secret store. Exported drafts are not publishable
flow artifacts. The browser-only Vite development server remains a non-executing
preview; real execution uses the Python bridge's same-origin loopback URL.

Execution is sequential in dependency order, allowing branches and joins but no
cycles. Every wire supplies a whole upstream result to an explicitly named target
argument. Literal/edge conflicts are rejected before task invocation. An argument
name is not proof of type compatibility or a callable signature match. A fresh
process runs each graph; arbitrary Python objects stay in that process while the
browser receives bounded previews. Full result persistence and automatic retries
are disabled for these runs. Task code can still write data itself.

One run is active at a time. The UI locks graph edits, displays node states,
diagnostic logs, and errors, and supports best-effort process-group cancellation.
Failure skips remaining nodes. Cancellation is not rollback and execution is not
a sandbox. Local native tasks may compile on first use; the UI warns before Run.
Run diagnostics use the configured work directory's `editor-runs/` subtree.

## Where to work

Use the [UI README](../../ui/README.md) for exact startup, import/export,
verification, and recovery instructions. [DESIGN.md](../../DESIGN.md) is the
maintained visual/interaction contract. The UI is a separate npm package; it is
not installed with the released Python wheel.

## Deliberately deferred

Typed task interfaces, field-level result mapping, parallelism, loops, executable
code generation, nested flows, scheduling, hosted authentication, collaboration,
flow publication, remote storage, and public deployment require separate decisions.
No Weavem version bump, tag, or release is part of this experiment.

## Original browser-only slice — 2026-10-27

Node 24.19.0 on the local Linux environment passed TypeScript checking, ESLint,
17 independent-model unit tests, and the static frontend production build.
Chromium passed 17 real-browser scenarios: pointer and keyboard composition,
metadata imported from an actual released-SDK snapshot, draft round-trip and
viewport restoration, invalid JSON, empty-draft replacement confirmation, corrupt
and unavailable browser storage, quota failures, and escaped text rather than
code execution. The test fixture's machine-specific paths were normalized.

The existing Python metadata and documentation checks also passed (19 tests).
Python implementation files, declared dependencies, version `0.1.0a2`, task/flow
artifact schemas, and release conditions were not changed. The source archive
and documentation-verification fixtures include the new documentation only;
the runnable frontend remains a separate npm package.

Browser testing exposed confirmation-dialog and saved-state recovery defects;
they were fixed before the successful final runs. Earlier failing evidence and
final logs/screenshots remain under `.artifacts/node-editor/2026-10-27/`.
The independent UI review's two findings were fixed and re-reviewed. This is
local Chromium evidence, not Firefox/Safari certification or a security audit.
The new frontend CI workflow has not run remotely: this branch is not pushed,
and no commit, tag, or release was created by this prototype task.

## Local execution slice — 2026-10-27

The owner selected **run the canvas graph**, with **local-machine-only execution**.
The implementation adds a standard-library bridge, isolated graph worker,
versioned graph validation, explicit argument wiring, Run/Cancel, per-node state,
bounded result previews, and collapsible diagnostic logs. The real runnable
sample and human-first walkthrough are in
[examples/editor-local](../../examples/editor-local/README.md).

The actual Chromium/native smoke added and wired `text.normalize` (local Cython),
`text.count_words`, and `text.summarize`, then produced
`Document: 2 words, 12 characters`. The accepted run is
`82a62a43-a5f0-4efd-b16b-6fe9eb22a05c`; it had clean runtime logs and no browser
page errors. Canvas completion badges and the final result's unobscured screen
position were checked, not only the backend response. A separate real-Prefect
test builds, publishes, pins, and invokes a native `.so` through the graph runner.
Another passes a non-JSON Python object between tasks without serializing it for
the browser. Native local-development compilation retains the existing temporary
build cleanup; this walkthrough does not claim to publish or retain that binary.

Final UI validation passed TypeScript, ESLint, 19 model tests, the frontend build,
and 25 Chromium scenarios. Browser failure/cancel/connection-loss states use mock
responses; the separate live native smoke uses the real bridge and runtime.
The complete Python regression run passed 182 tests on CPython 3.15. After the
last abnormal-worker-exit guard, the focused bridge suite passed all 11 tests;
these counts overlap and are not an aggregate total. A worker that exits without
a terminal event is failed, even with exit code zero, rather than falsely shown
as successful. Static single-page fallback also rejects symlink escapes.
The executable walkthrough passed strict runbook lint, and documentation links
were checked. Its status remains **Source-verified** because the exact editable
installation procedure was not repeated in a fresh environment; do not confuse
the executed runtime smoke with a fresh-machine distribution guarantee.

Verification caught and corrected overlapping task placement, inaccessible
keyboard mapping, run-submission/edit races, failed-run response handling,
cancellation/terminal races, unbound-task labelling, stale results after edits,
and logs obscuring the inspector. An empty Prefect API URL caused event-worker
errors even when tasks completed; the worker now selects local ephemeral settings
using Prefect's public
[temporary settings context](https://reference.prefect.io/prefect/settings/context/),
and the live smoke rejects those errors rather than filtering their logs. Prefect
control argument names are rejected so they cannot suppress fail-fast behavior.
The independent read-only review approved the reported lifecycle fixes; this is
not a security audit or cross-browser certification.

Evidence is retained under `.artifacts/node-editor/execution-2026-10-27/`, including
the earlier failed runs. `scripts/verify-editor.mjs` reproduces the live browser
check; the UI CI workflow now includes it plus the Python execution tests.
Remote CI has not run because the branch remains uncommitted/unpushed. No new
dependency, version bump, commit, tag, publication, or release is part of this slice.

Known prototype ceilings: graph execution is sequential, argument types/signatures
are not proven during metadata inspection, and there is no active-run reattachment
after a browser reload. Stop the bridge with Ctrl+C if a reload loses its controls;
this cancels work but cannot undo side effects. No sandbox or remote-access mode
is claimed. Published-flow output and richer graph semantics remain deferred.

### Ready-to-run project flow

The sample now saves its complete composition in
`examples/editor-local/flows/editor.json`. **Connect project → Replace draft →
Run flow** loads and executes it without adding nodes or editing parameters.
The prototype entrypoint uses project task aliases; the bridge resolves and
validates them against current bindings without importing payloads. The browser
adds layout only. Projects without this optional file keep the existing empty
catalog/reconnect behavior. Opening a saved project flow still requires explicit
replacement confirmation, so reconnecting cannot silently overwrite edits.
