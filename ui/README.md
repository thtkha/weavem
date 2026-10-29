# Weavem node-editor prototype

A local **Python flow editor and runner**, on the `prototype/node-editor`
branch. This is not part of the released `0.1.0a2` user experience. The demo
tasks are synthetic examples, not a built-in executable task catalog.

## Run a real canvas flow

Follow the [local execution walkthrough](../examples/editor-local/README.md).
It builds this frontend and starts `weavem editor --project examples/editor-local`
from the source checkout. Open the printed **127.0.0.1** URL, connect the project,
open `document_summary` from **Open flow**, and press **Run flow**. Parameters and argument
mappings are already supplied for the real native/Python chain.
The active Python environment executes the tasks. There is no account, hosted
service, automatic dependency installation, or JavaScript task runtime.

## Ordinary project flows

The connected editor discovers the project's normal `flows/<name>.py` modules
and `flows/<name>.toml` metadata. **New flow**, **Open flow**, **Save**, and
**Save as** work in that same directory. **Run flow** saves valid changes before
invoking the normal local-flow loader; save conflicts prevent execution. No
executable browser graph or editor service is required by the resulting Python.

The visual subset is intentionally narrow: module-level Weavem task bindings,
a bare `@flow`, sequential keyword task calls using JSON literals or earlier
results, and a dictionary return of terminal-node results. Supported Python is
inspected with AST parsing, never imported merely to draw it. Source node/edge
comments preserve stable visual identities but have no runtime effect. Other
Python remains intact and runnable with JSON flow arguments, but visual rewriting
is disabled. The editor does not promise arbitrary-Python round-tripping.

Optional `flows/<name>.layout.json` holds positions, labels, notes, and viewport;
it is not executable. The source and existing project bindings determine behavior.
External source/metadata edits invalidate a loaded revision: reload or save a new
flow rather than overwriting somebody else's work. Existing draft JSON imports
remain unsaved visual drafts until explicitly saved as a Python flow.

The example is `flows/document_summary.py`. Run it without a browser:

```bash
python -m weavem --project examples/editor-local flow run document_summary
```

From Python, load the same selected project explicitly:

```python
from weavem.flows import load_local_flow

result = load_local_flow("document_summary", project="examples/editor-local")()
print(result)
```

The execution bridge is deliberately **loopback-only**, unlike the visual-only
development server below. It serves the UI and execution routes from the same
origin and checks host, origin, and a per-session request token. It does not
accept a browser-selected project path, interpreter, or arbitrary Python code.
This is not a sandbox: trusted tasks have your user permissions and may perform
side effects. Supported native tasks prepare automatically without a compilation confirmation.
Preparation failures report their actual cause; no privileged OS packages are installed. Published tasks retain the normal integrity/compatibility checks.
Because each run starts a fresh process, a local native task can compile again on
each run; published native tasks reuse their selected binary without compilation.

Visual authoring supports sequential acyclic graphs, branches, and joins.
Each wire passes the whole source result into one explicitly named argument;
literal JSON parameters supply other arguments. Conflicting assignments,
unmapped wires, cycles, stale release pins, and unbound tasks prevent execution.
Missing callable arguments and incompatible values can still fail at runtime:
descriptive metadata is not a type schema. Positional-only arguments, result-field
selection, loops, parallelism, nested flows, scheduling, and publication are not
supported by this prototype.
Argument names `return_state` and `wait_for` are reserved by Prefect and rejected;
use an export with different parameter names for this canvas runner.

Each run uses a fresh child process and the same saved-flow loader as the CLI.
Authored retries and Prefect settings are preserved rather than replaced by
editor defaults. Explicitly choose your Prefect profile before starting the bridge. Graph edits are locked while it runs.
Failure stops the run and skips unexecuted nodes; cancellation is best-effort
process termination, **not rollback**. Run diagnostics live under the project's
configured artifact directory in `editor-runs/`; browser logs are a bounded tail
and results are bounded previews. Logs, parameters, and previews may contain
sensitive data. Full results are not intentionally persisted by this runner;
task code can still write files itself.
Reloading the page can reconnect to the active run while the same bridge remains
alive. Restarting the backend does not restore running processes. Cancellation
cannot undo side effects; check them before retrying a non-demo project.

## Run the visual-only development server

Use a source checkout of this branch and **Node.js 24 with npm**. Python is not
needed for the demo. From the repository root:

```bash
cd ui
node --version
npm ci
npm run dev
```

Open **http://localhost:5173** on this machine. Leave that terminal running; stop
it with Ctrl+C. The dev server listens on all interfaces for LAN testing; your
host firewall controls access. It is a development server, not an authenticated
production deployment. Do not expose it to the public internet.

Expected: a dark workbench with a labelled demo task library, a sample graph,
and a properties inspector. If the port is already in use, stop the other server
or choose an explicit alternative: `npm run dev -- --port 5174`. Do not silently
connect to an unrelated process. No application data is sent to the dev server.
If this host reports `ENOSPC` file-watcher limits, use
`WEAVEM_UI_POLL=1 npm run dev` to opt into polling. Do not change system limits
or stop unrelated processes just to open this prototype.
Initial npm installation requires an approved registry; a built static UI needs
no external fonts, accounts, telemetry, or application API.

## Try the authoring loop

1. Search the library, then click a task's add button or drag it onto the canvas.
   Multiple instances of the same task are allowed.
2. Select a node. Change its label or notes in the inspector. Draft parameters
   must be a JSON object; use **Apply parameters** to accept a valid edit.
3. Drag between ports, or use the inspector's **Connect to node** selector and
   **Connect nodes** button. The handles are generic input/output connectors—not
   type checks. Map each connection's destination argument before running it.
   Unmapped wires and cycles can be saved as drawings but cannot execute.
4. Move/zoom the graph. Delete nodes or connections through their controls, or
   use the canvas keyboard actions. Removing a node also removes its connections.
5. Use **Export draft** to download a `.weavem-draft.json` file. **Open draft**
   restores its catalog, configuration, node positions, connections, and viewport.
6. Reload to restore the same browser's autosaved draft. Use **New draft** for
   an empty canvas with the current catalog. Replacing work requires confirmation.

The inspector exposes descriptive metadata. A released badge means the imported
snapshot identifies a release; the browser does not validate its binary, ABI,
policy, publisher, or behavior. Run preflight and the Python runtime perform
execution checks; saving creates ordinary local flow source, not a published immutable release.
Keyboard focus and button-based alternatives are available; this is not a claim
of audited accessibility conformance. Editing is desktop-first (1100px+). Smaller
windows show a notice while keeping export/recovery available.

## Import real project metadata

In a terminal with Weavem installed, go to your **existing Weavem project**.
Export to a new file; this Python API reads metadata without importing payloads
or executing tasks. The `x` mode refuses to overwrite an existing snapshot.

```bash
python - <<'PY'
import json
from weavem import Project

snapshot = Project.open('.').metadata()
with open('weavem-metadata.json', 'x', encoding='utf-8') as output:
    json.dump(snapshot, output, indent=2)
    output.write('\n')
PY
```

Return to the workbench and choose **Import metadata**. Select that JSON file.
After confirmation, the editor creates an empty draft and builds its library
from authored tasks and released tasks referenced by project bindings. This is
not a scan of every task in `task-store/`, and it does not reconstruct the
Python flows' call order or graph. No extra CLI, backend, or filesystem permission
is needed by the browser. A complete example fixture is in `tests/metadata.json`.

Importing metadata replaces the catalog; there is no merge or automatic version
upgrade. Opening a saved draft instead restores its self-contained catalog.
JSON files over 5 MiB, malformed files, unsupported versions, missing references,
and invalid configuration are rejected without replacing the current draft.

## Storage and recovery

Autosave uses this browser origin's localStorage, not the project directory.
Changing the URL/port/browser creates a separate storage space. It is not a
backup service: export a file to move or retain work. Metadata, source paths,
parameters, and notes remain local in the browser or the files you download.
During a run, the selected saved flow name, revision, and parameters are sent to
the local bridge. Saving sends the editable graph for Python generation. Draft
schema 1 is upgraded on opening without inventing argument mappings; exports use
schema 2. The browser graph is an editing/validation representation, not a separate runtime format.
Neither localStorage nor draft files are secure credential stores; do not enter
passwords, tokens, or customer data.

On storage failure, the workbench reports the problem and export remains
available. Corrupt stored JSON is kept intact and autosave is paused; explicitly
start or open a draft to replace it. A bad import leaves the existing graph
untouched. Preserve the failed file/error for diagnosis; do not clear browser
storage as the first troubleshooting step. Stop and keep an exported copy if
saving or reopening does not reproduce your graph.

## Frontend contribution conventions

The editor uses React, TypeScript, Vite, React Flow, and Tailwind CSS. It still
builds static assets in `dist/`; Node is needed to build/develop, not to serve the
built UI. The local Python bridge remains responsible for task execution. This
migration does not introduce a hosted execution server.

- Use semantic tokens from `src/theme.css` for shared colors, typography, spacing,
  and radii. Keep the current olive palette and approved workbench layout.
- Reuse `Button` for standard actions and `Field` for labelled input groups.
  Both preserve native props, refs and accessibility attributes; callers retain
  control over state and callbacks. Specialized icon/link buttons can remain native.
- Use explicit Tailwind classes for new local layout; use shared `@apply` recipes
  where a control repeats. Never build class names such as `bg-${color}` dynamically.
  Named variants must map to complete classes or existing explicit CSS recipes.
- Keep the documented cascade layers. Do not re-import React Flow CSS outside its
  layer or add Tailwind Preflight casually: either can change approved form/canvas
  behavior. The existing base rules deliberately replace Preflight in this stage.
- Keep canvas/resizer/fullscreen/scrollbar integration CSS where it expresses the
  behavior more clearly. Remove replaced rules instead of keeping competing copies.
- Keep presentation components focused. Do not move graph state, network calls or
  parameter validation into shared controls. Prefer one clear implementation over
  configurable wrappers with speculative options.

When changing shared controls, verify native disabled/focus/keyboard behavior,
compact and expanded panel widths, and unsaved parameter edits. Compare screenshots
against the previous branch before accepting styling changes. The checks below
cover compilation, pure model/control tests, and real browser interaction.

## Verify changes

From `ui/`:

```bash
npm run typecheck
npm run lint
npm test
npm run build
export PLAYWRIGHT_BROWSERS_PATH="$PWD/../.artifacts/node-editor/browsers"
npx playwright install chromium
npm run test:e2e
```

The browser installer downloads test tooling only. It does not install privileged
OS packages. If shared libraries are missing, ask your system administrator to
provide Playwright's documented browser prerequisites; do not run sudo scripts
implicitly. CI installs Chromium and its explicit OS dependencies on its disposable
runner. Build first as shown above: the browser tests serve `ui/dist/` through Vite
preview, not the hot-reload dev server. Local tests need permission to bind a
loopback test server on port 4173.

Expected: type/lint/unit checks and the frontend build pass; Chromium tests pass
real canvas interaction and draft persistence/import cases. Evidence lives in
`../.artifacts/node-editor/`: browser binaries, npm cache, screenshots, test
results, and HTML reports. `ui/dist/` and `ui/node_modules/` are also gitignored.
Keep evidence until review; no cleanup is performed automatically.

For the real-runtime check, activate this checkout's supported Python environment
and run the following **from the repository root**, after the UI build and browser
installation above:

```bash
node scripts/verify-editor.mjs
```

It starts its own ephemeral-port loopback bridge, uses Chromium to connect and
open the saved project flow without editing, runs the local native/Python chain, checks the result and
clean runtime logs, and stops that test bridge afterward. It does not stop an
editor you started separately. Evidence stays in `.artifacts/node-editor/live/`.
The separate Python regression suite also executes a pinned published native
task, tests non-JSON Python object handoff, and checks failure behavior with real
Prefect. The frontend browser suite uses mocked run responses for deterministic
failure/cancel/connection-loss scenarios; those mocks alone do not prove runtime
execution.

For a defect, open a [repository issue](https://github.com/thtkha/weavem/issues)
with Node/npm versions, the failing command, browser version, and redacted error
text. Do not attach private project metadata or credentials.

## Design and boundaries

The [design contract](../DESIGN.md) records the agreed interface and accessibility
choices; the [project note](../docs/project/node-editor-prototype.md) records the
prototype decision. Core draft types are in `src/types.ts`, independent of React
Flow. This editor schema is not a PipelineSpec, task manifest, or flow release
schema. Read-only task metadata is the shared vocabulary; JSON parameters and
explicit argument mappings define the minimum execution graph.

React Flow owns the graph interactions. Weavem/Prefect own execution, not a second
JavaScript execution engine. This prototype has no code generation, nested-flow
nodes, deployment, collaboration, automatic task installation, or release
automation. Dependencies keep their own
licenses; React Flow core is MIT and Pro is not required.

References: [React Flow](https://reactflow.dev/learn),
[accessibility](https://reactflow.dev/learn/advanced-use/accessibility),
[browser testing](https://reactflow.dev/learn/advanced-use/testing).
