# Run a local canvas flow

| Field | Value |
| --- | --- |
| Status | Source-verified |
| Owner | Weavem maintainers, [repository](https://github.com/thtkha/weavem) |
| Escalation | [Repository issues](https://github.com/thtkha/weavem/issues) |
| Last verified | 2026-10-29 — source inspection; see the project note for execution evidence |
| Last executed | See [prototype verification record](../../docs/project/node-editor-prototype.md) |
| Applies to | Source checkout of `prototype/node-editor`; Linux x86_64; local machine only |
| Risk | Medium — real tasks execute with your user permissions |
| Expected duration | 5–15 minutes; first native compilation can take longer |

## Purpose and successful outcome

Open the project's saved three-node flow and execute native/Python tasks without
writing or wiring anything. Success means all three nodes complete and the last result is
`Document: 2 words, 12 characters`.

## Scope

Use this walkthrough for the experimental source branch, not the published
`0.1.0a2` wheel. This sample does not read documents, contact services, or publish
anything. The first native run compiles an extension. Remote execution,
scheduling, credentials, and production deployment are not included.

## Safety and stop conditions

Only run trusted project code. Tasks execute as your operating-system user;
integrity checks and loopback access are not a sandbox. No privileged package
installation is performed. Stop if the selected project is not this sample,
the server listens outside `127.0.0.1`, or a task requests credentials. Export
important drafts before replacing them. Cancellation cannot undo side effects;
this sample has none beyond compilation and runtime diagnostics.

## Ownership and escalation

The local operator owns the Python environment and task permissions. Report
defects through [repository issues](https://github.com/thtkha/weavem/issues), with
the branch/revision, failing step, versions, and redacted errors. Do not attach
credentials, private metadata, or complete customer-data logs.

## Prerequisites and inputs

- A checkout containing `ui/` and `src/weavem/editor_server.py`.
- Bash on supported Linux x86_64, standard CPython 3.12–3.15, Node.js 24 with npm,
  and a desktop browser at least 1100 pixels wide.
- An activated virtual environment with this checkout installed using
  `python -m pip install -e .`. Installation needs access to the package registry;
  no administrator permissions are required. Use the existing project environment
  if already installed. Do not replace a shared system Python installation.
- The sample project is `examples/editor-local`; it already binds all three tasks
  in `weavem.toml`. No runtime variables or credentials are needed.
- Port 8765 must be free. If occupied, use `--port 8766` in the startup step and
  open the URL printed by that server, not an unrelated listener.

## Repository orientation

Run terminal commands from the **Weavem repository root**, identified by
`pyproject.toml`, `ui/package.json`, and this `examples/` directory.
`weavem.toml` selects local task folders. Each folder has metadata, implementation,
and behavioral tests. The browser selects a saved Python flow; a loopback bridge starts a
fresh Python process and uses the same local-flow loader as the CLI. Run diagnostics and
native candidates go into the sample's gitignored `.artifacts/` by default.
The standard Weavem work-directory setting/environment override still applies.

## Preflight checks

From the repository root, in the activated environment:

```bash
git branch --show-current
python --version
node --version
python -c "import weavem; print(weavem.__file__)"
python -m weavem doctor
```

Expected: the prototype branch, supported Python, Node 24, this checkout's
`src/weavem/__init__.py`, and a successful native environment check. If any check
fails, stop and correct the environment before compiling. Keep the redacted
diagnostic output; do not run privileged installation commands automatically.

## Procedure

### Step 1 — Build the editor

**Goal:** Create the static frontend served by the Python bridge.
**Run from:** Repository root, Bash, ordinary local user.
**Action:**

```bash
npm --prefix ui ci
npm --prefix ui run build
```

**Expected result:** Both commands succeed and `ui/dist/index.html` exists.
**If this fails:** Stop; retain npm output and confirm Node 24 and registry access.
**Evidence to retain:** Build output and Node/npm versions.
**Repeatability:** Safe to repeat; regenerates frontend assets, not project data.

### Step 2 — Start the local bridge

**Goal:** Select the project and Python interpreter explicitly.
**Run from:** Repository root, same activated Python environment.
**Action:**

```bash
python -m weavem editor --project examples/editor-local
```

**Expected result:** A printed `http://127.0.0.1:8765/` URL; keep the terminal open.
Open that exact URL in the browser. The visual-only Vite URL on port 5173 cannot
execute tasks.
**If this fails:** Stop; use the troubleshooting table. Do not expose the service
on all interfaces to resolve a connection issue.
**Evidence to retain:** Printed project path and URL, not the session token.
**Repeatability:** Start one server only; stop the previous one with Ctrl+C first.

### Step 3 — Open the ready-to-run project flow

**Goal:** Connect to tasks authorized by the selected project.
**Run from:** Browser, printed loopback URL.
**Action:** Choose **Connect project**, then **Replace draft** if prompted.
If **Connect project** is hidden, open **More** first.
Select `document_summary` in **Open flow** and confirm **Replace draft**.
Export the previous draft first if you need it.
**Expected result:** **document_summary**, with three connected nodes,
their input parameters, and both argument mappings already filled in. The flow
comes from `flows/document_summary.py` and its normal TOML metadata; task aliases
resolve against `weavem.toml`.
**If this fails:** Stop; preserve your draft and verify the startup project path.
**Evidence to retain:** Project name shown by the connection status.
**Repeatability:** Reconnection replaces the draft only after confirmation.

### Step 4 — Inspect the saved flow (optional)

**Goal:** See what will run; no editing is required.
**Run from:** Browser workbench.
**Action:** The saved chain is `text.normalize → text.count_words → text.summarize`.
Select normalize to inspect `{"text":"  Hello Weavem  "}`. Its result feeds
count's `text` argument; count's result feeds summarize's `stats` argument.
You can skip inspection and press **Run flow** immediately after Step 3.
**Expected result:** Three nodes and two wires, with argument mappings visible in the inspector.
**If this fails:** Do not run an unmapped graph. Select the wire again and correct
the argument. Metadata descriptions do not automatically supply mappings.
**Evidence to retain:** **Export draft** saves layout, parameters, and mappings.
**Repeatability:** Edits are reversible; adding the same task twice adds instances.

### Step 5 — Run and inspect

**Goal:** Execute the saved ordinary Python flow through the real runtime.
**Run from:** Browser workbench, connected project.
**Action:** Choose **Run flow**. Native preparation is automatic, without a confirmation. Observe
node statuses and **Run log**. Select `text.summarize` to read **Run result**.
**Expected result:** The run completes; the last preview contains
`Document: 2 words, 12 characters`. The first native run can take longer. Graph
editing is locked while execution is active.
**If this fails:** Do not repeatedly retry an unknown task. This sample is safe
to retry once after fixing its reported error; retain the run ID and diagnostics.
Use **Cancel run** if the sample remains active without progress for five minutes.
**Evidence to retain:** Run ID, final preview, and run diagnostics under `.artifacts/`.
**Repeatability:** Sample task behavior is safe to repeat; other projects may not be.

### Step 6 — Run the same source without the editor

**Goal:** Prove the flow is ordinary Weavem code, not browser-only state.
**Run from:** Repository root, the same activated Python environment.
**Action:** Close the browser and stop the bridge with Ctrl+C. Then run:

```bash
python -m weavem --project examples/editor-local flow run document_summary
```

**Expected result:** The final JSON result is
`{"summarize": "Document: 2 words, 12 characters"}`. No browser or editor server
is required. A fresh process may prepare local native code again.
**If this fails:** Confirm the selected project and Python environment match
Step 2; preserve the concrete error rather than reinstalling tools blindly.
**Evidence to retain:** CLI result alongside the GUI run ID.
**Repeatability:** This sample is safe to run again.

## Verification

- All three nodes show completed; no failed or skipped node remains.
- The final preview equals the expected sentence, possibly surrounded by Python
  string representation quotes.
- Save, reload, and reopen preserve mappings. Reconnecting is needed after
  restarting the server because the session token changes.
- The project's artifact directory contains an `editor-runs/` diagnostic folder.
  Local execution compiles and loads a temporary `.so`, then removes its temporary
  build directory using the existing runtime behavior. A reusable native binary
  requires the separate task build/publish workflow; this run does not publish one.

## Rollback and recovery

Use **Cancel run** to stop a current run, then Ctrl+C in its server terminal to
stop the bridge. For forward recovery, use **Open draft → select exported JSON**
to restore edits. Reloading a browser does not cancel its Python run; reconnect to recover active
run controls while the same backend remains alive. Saved Python flows reopen from
the project; exported drafts recover unsaved edits. Never clear corrupt browser storage as the first
recovery step: preserve the original file/error. A process restart ends the
in-memory run index; retained diagnostics remain on disk. Task side effects in
other projects require task-specific recovery; cancellation is not rollback.

## Troubleshooting

| Symptom | Diagnosis and safe action |
| --- | --- |
| Missing UI build | Repeat Step 1 from this checkout; confirm `ui/dist/index.html`. |
| Disconnected or no execution bridge | Open Step 2's printed URL, not Vite; reconnect once. |
| Task not bound | In your own project, bind it with `weavem task use ALIAS --path tasks/NAME`; reload the catalog. The sample already has bindings. |
| Missing argument or unexpected keyword | Correct explicit mappings and applied JSON parameters; task signatures are checked during execution. |
| Native compilation failed | Retain diagnostics and rerun `python -m weavem doctor`; do not install OS packages silently. |
| Another run is active | Reconnect to the same backend to recover controls, then cancel or finish it. If the backend is unresponsive, stop its terminal with Ctrl+C and restart Step 2. Check side effects before retrying other projects. |
| Stale release pin | Reconnect and inspect the project's explicitly selected release; do not bypass integrity checks. |
| Server restart or 403 | Reconnect to obtain the new session; do not copy tokens into URLs. |

Stop after a second unexplained failure and report the redacted evidence through
the repository issue queue.

## Cleanup

Stop this bridge with Ctrl+C after use. No temporary accounts, external services,
or production changes need recovery. Keep exported drafts and diagnostic artifacts
until reviewed; this walkthrough does not delete them automatically.

## Evidence and audit record

Record the revision, Python/Node/browser versions, run ID, and redacted final
preview. Diagnostics include flow parameters, bounded previews, and task output;
they are not safe credential stores. Do not commit `.artifacts/` or private data.
Execution evidence for this implementation is recorded in the project note.

## References

- [Editor controls, storage, and testing](../../ui/README.md)
- [Design contract](../../DESIGN.md)
- [Task development guide](../../docs/users/authoring-guide.md)
- [Prototype verification record](../../docs/project/node-editor-prototype.md)

## Document maintenance

Weavem maintainers own this guide. Recheck it when CLI flags, graph mappings,
task bindings, native behavior, supported Python versions, or browser controls
change. This source-branch prototype is not a promise about released packages.
