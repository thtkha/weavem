# Weavem visual flow editor

> **Unreleased editor work.** This guide describes the integrated editor on the
> `prototype/node-editor` branch and its locally built candidate distributions.
> It is not part of the published `0.1.0a2`
> wheel or the released user documentation.

The editor is a local authoring surface for ordinary Weavem flows. It reads a
project's task bindings and saved flow files, then saves the supported visual
subset back into the same configured flow directories used by code authors. The
browser does not execute a
second graph runtime: **Run flow** invokes the same local-flow loader used by the
CLI. A flow saved in the editor can run without the editor; a source-only flow
can run without being visually editable.

Use the complete [local execution walkthrough](../examples/editor-local/README.md)
to start the loopback bridge, open the supplied flow, and run
it. That walkthrough is the canonical procedure; its header records its current
verification status. The public Python API and persisted editor formats are described in the
[editor reference](../docs/maintainers/editor-reference.md).

## Editor experience branch

The editor works with a project selected when the local bridge starts. It never
asks the browser to choose a filesystem path, Python interpreter, or arbitrary
code. The bridge is loopback-only and checks a per-session request token. This
reduces exposure; it is **not** a sandbox. Trusted task code still runs with the
local user's permissions and may have side effects.

### Installed candidate: no frontend tooling

This behavior is unreleased: use a wheel built from this branch, not the published
`0.1.0a2` wheel. In the project's activated Python environment:

```bash
python -m pip install /path/to/locally-built-candidate.whl
python -m weavem editor --project /path/to/project
```

Open the printed loopback URL. The wheel supplies static UI assets; there is no
npm step or separate frontend server for consumers. Keep the terminal open and
stop it with Ctrl+C. Installing Weavem does not install your project's extra task
dependencies. Launch with the same environment you use for headless runs. The
**Project environment** disclosure shows the actual project, Python executable,
Python version, and Weavem version; workers use that interpreter and preserve the
normal Prefect environment/profile. Missing dependencies require an explicit
project-environment fix, not an automatic reinstall or another interpreter.

For an editable checkout, contributors build assets with Node 24:

```bash
npm --prefix ui ci
python scripts/stage-editor.py
python -m weavem editor --project examples/editor-local
```

Staging copies the production build into package-owned `src/weavem/_ui/`. For an
unstaged frontend build, explicitly pass `--ui-dir ui/dist`. A missing packaged
build is an actionable error, not an implicit npm download.

### Choose flow locations

In `weavem.toml`, omit this setting to keep `flows/`, or replace the default:

```toml
[weavem]
flow_paths = ["pipelines", "shared-flows"]
```

The ordered, nonempty list accepts project-relative or explicit absolute directory
paths. Normalized duplicates are removed, preserving order. Only immediate
`*.toml` sidecars are discovered, not nested folders or arbitrary Python files;
reading the catalog never imports flow code. The sidecar stem remains the local
flow name across editor, CLI, and Python metadata. Two roots containing the same
stem are an error naming both paths, not an override mechanism.

New flows use the first configured root. Updating an existing flow preserves its
original root, declared Python source filename, metadata, and layout location.
Each flow still needs its normal metadata sidecar; the layout is optional and
non-executable. Invalid definitions appear with diagnostics in the editor; public
`Project.metadata()` remains strict. Configuration is trusted: an absolute root
allows writes outside the project. Symlinked roots/files are rejected, but this
is not a filesystem sandbox or a defense against a hostile local account.

### Author and run flows

1. Open the printed editor URL. It connects to the selected project automatically
   and lists saved flows without opening or running one. Use **New flow** or
   **Open flow**; restored/imported drafts are retained, not silently replaced.
2. Add bound tasks, supply literal JSON parameters, and connect explicit target
   arguments. A task may occur more than once.
3. Save the flow. The editor writes the ordinary Python flow and its metadata to
   `flows/<name>.py` and `flows/<name>.toml`; optional layout data goes to
   `flows/<name>.layout.json` by default. Configured locations are explained below.
4. Choose **Run flow**. The bridge rejects an outdated loaded revision before it
   starts the normal loader.

The editable subset is intentionally narrow: module-level Weavem task bindings,
a bare `@flow`, sequential keyword task calls with JSON literals or earlier
results, and a dictionary return of terminal results. The editor preserves
unsupported Python and can still run it with JSON flow arguments, but it does
not rewrite it or promise arbitrary-Python round-tripping. It does not provide
nested-flow nodes, loops, parallel scheduling, publication, collaboration, or
a browser execution engine.

A connection supplies one named target argument. Literal parameters and a
connection cannot supply the same argument; cycles, missing argument mappings,
and stale release pins stop a run. Descriptive metadata is not a complete type
system, so a graph that saves can still fail in Python at runtime.

### Work with task parameters and results

For eligible authored Python tasks, the editor parses source without importing
or running it. It can present ordinary parameter names, defaults, docstrings,
`Literal` choices, nullable annotations, locally declared `TypedDict` fields,
and a return annotation. It does not invent UI definitions for task authors.

The following situations remain intentionally general:

- An annotation the inspector cannot safely classify uses a JSON control.
- A compiled or released task without eligible source uses descriptive metadata
  when available, otherwise a general JSON fallback.
- Positional-only arguments, `*args`, and `**kwargs` are not exposed as named
  editor controls.
- Parameter and output hints are advisory. They do not prove the task accepts a
  value or guarantee a downstream result shape.

Select a connection to choose the whole upstream result, a declared field, an
observed field, or a manual JSON path such as `["customers", 0, "email"]`. The
saved Python flow uses ordinary indexing for a selected path. An absent path is
the whole result. A missing key or index fails at execution. Observed fields are
examples from a labelled prior result, not a schema; truncated previews do not
offer observed field choices.

Supported built-in results have expandable tree views. Lists of record-like
values can also use a table view. Other Python values have a bounded textual
preview. See the editor reference for the exact preview limits and persistence
boundaries.

### Edit safely

- Use **Undo** and **Redo**, or Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z (Ctrl/Cmd+Y also
  redoes), outside text fields. History retains 100 edits.
- Use Ctrl/Cmd-click to select several nodes. Ctrl/Cmd+C and Ctrl/Cmd+V copy and
  paste nodes and internal connections using an editor-local clipboard; this
  does not read or write the operating-system clipboard.
- Viewport and panel adjustments, selections, and run results are not history.
  Undo never reverses task side effects.
- **Export draft** and **Open draft** move an editable browser draft. They do not
  publish a task or flow. Browser autosave is local to the URL and browser, not
  a project backup or credential store.

External edits to a loaded flow invalidate its revision. Reload it or save a new
flow instead of overwriting the other change. While a run is active, graph edits
are locked. Cancelling asks the worker process to stop; it cannot roll back a
task's side effects.

### Inspect the last run

**Last run** opens a read-only record for the selected flow without changing the
current draft. It contains the captured definition, parameters, node statuses,
bounded logs, and bounded result previews. The record survives a bridge restart,
but a restart does not restore a worker process, cancellation control, or live
tracking. A record that was running at restart is displayed as last observed,
not as a resumable run. Code, dependencies, services, and data may change after
a record is captured, so it is inspection evidence rather than a replay promise.

Run records can contain source, parameters, logs, result previews, and exception
messages. Keep the configured artifact directory private and gitignored. There
is no automatic secret detection or redaction guarantee.

### Handle structured errors

A task may raise `TaskError` to provide an optional machine-readable error code,
affected input, remediation, and retryability advice. It is still a regular
Python exception; retryability does not authorize repeating side effects or
change Prefect's configured retry policy. The exact constructor and the CLI,
worker, and editor representations are in the
[editor reference](../docs/maintainers/editor-reference.md#structured-task-errors).

The CLI writes both the human message and structured `TaskError` JSON to
**stderr** and exits nonzero. Ordinary exceptions remain valid; they have a
best-effort unclassified representation. Do not parse stdout for editor or CLI
failure details.

## Visual-only development server

The Vite development server is useful for visual work but has no execution
bridge. It opens a disconnected workbench without synthetic demo tasks. From the repository root, use Node.js 24 and
npm:

```bash
cd ui
npm ci
npm run dev
```

Vite prints a local URL, normally `http://localhost:5173/`; open the URL printed
by that process and stop it with Ctrl+C. If port 5173 is occupied, choose an
explicit alternative such as `npm run dev -- --port 5174` rather than connecting
to an unrelated listener. Use the [local execution walkthrough](../examples/editor-local/README.md)
and its Python bridge for real task execution. Do not expose a development server
to the public internet.

## Frontend contribution conventions

The editor uses React, TypeScript, Vite, React Flow, and Tailwind CSS. It builds
static assets in `dist/`; Node is required to develop or build the frontend, not
to consume an installed editor or run a saved Python flow. The local Python bridge retains responsibility for
task execution.

- Use semantic tokens in `src/theme.css` for shared colors, typography, spacing,
  and radii. Preserve the approved olive workbench palette and layout.
- Reuse `Button` for standard actions and `Field` for labelled input groups.
  Both retain native props, refs, and accessibility attributes. Keep graph state,
  network calls, and parameter validation outside shared controls.
- Use explicit Tailwind classes for new local layout. Use shared `@apply` recipes
  only for genuinely repeated controls; never construct class names dynamically.
- Preserve the documented cascade layers. Do not casually re-import React Flow
  CSS or add Tailwind Preflight: either can alter forms and canvas behavior.
- Keep canvas, resizer, fullscreen, and scrollbar integration CSS where it
  expresses behavior more clearly. Delete replaced rules rather than retaining
  competing copies.

## Verify editor changes

From `ui/`, run the frontend checks:

```bash
npm run typecheck
npm run lint
npm test
npm run build
export PLAYWRIGHT_BROWSERS_PATH="$PWD/../.artifacts/node-editor/browsers"
npx playwright install chromium
npm run test:e2e
```

The browser suite requires a Playwright Chromium installation and a loopback port
for its preview server. After the frontend build and browser installation, run
this repository-root runtime smoke check:

```bash
node scripts/verify-editor.mjs
```

It starts and stops its own loopback bridge, opens the saved sample flow, runs the
native/Python chain, and retains evidence under `.artifacts/node-editor/live/`.

Keep browser binaries, reports, screenshots, and runtime evidence in the
project's gitignored `.artifacts/node-editor/` directory until review. The
[local execution walkthrough](../examples/editor-local/README.md) gives the
exact setup and operational checks; the [editor reference](../docs/maintainers/editor-reference.md)
covers compatibility and persistence details.

## Design boundary

The [design contract](../DESIGN.md) records the approved interface and
accessibility choices. The [project note](../docs/project/node-editor-prototype.md)
records prototype history. Core editor data types live in `src/types.ts` and are
independent of React Flow. An editor draft, executable graph, layout file, task
manifest, and published flow release are separate formats with separate roles.
