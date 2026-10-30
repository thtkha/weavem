# Run a local canvas flow

| Field | Value |
| --- | --- |
| Status | Source-verified |
| Owner | Weavem maintainers, [repository](https://github.com/thtkha/weavem) |
| Escalation | [Repository issues](https://github.com/thtkha/weavem/issues) |
| Last verified | 2026-10-30 — source inspection; see the project note for execution evidence |
| Last executed | See [prototype verification record](../../docs/project/node-editor-prototype.md) |
| Applies to | Source checkout of `feature/editor-experience`; Linux x86_64; local machine only |
| Risk | Medium — real tasks execute with your user permissions |
| Expected duration | 15–25 minutes; first native compilation can take longer |

> **Verification claim:** The commands and interface paths below are
> source-verified against this branch. The complete browser walkthrough has not
> been rerun after this document update; the prototype verification record
> contains prior execution evidence.

## Purpose and successful outcome

Open the project's saved three-node flow, save an editable copy, change a
parameter, add an explicit nested-field mapping, and run the saved Python flow
through the browser, CLI, and Python. Success means all three nodes complete,
the copy records `count["words"]` as the `prefix` input, and each execution path
returns `{"summarize": "2: 2 words, 12 characters"}`.

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

- A checkout containing `ui/` and `src/weavem/editor_server.py` on
  `feature/editor-experience`.
- Bash on supported Linux x86_64, standard CPython 3.12–3.15, Node.js 24 with npm,
  and a desktop browser at least 1100 pixels wide.
- An activated virtual environment with this checkout installed using
  `python -m pip install -e .`. Installation needs access to the package registry;
  no administrator permissions are required. Use the existing project environment
  if already installed. Do not replace a shared system Python installation.
- The sample project is `examples/editor-local`; it already binds all three tasks
  in `weavem.toml`. No credentials are needed.
- Choose an unused Python identifier for the saved copy. This guide uses
  `editor_walkthrough_tk`; replace `tk` with your own short suffix if that name
  already exists. The later `FLOW_NAME` shell variable must match this exact name.
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

Expected: the `feature/editor-experience` branch, supported Python, Node 24, this checkout's
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

### Step 5 — Save an editable project-flow copy

**Goal:** Preserve the supplied sample while creating ordinary local source that
the editor, CLI, and Python can all load.
**Run from:** Browser workbench, connected project with `document_summary` open.
**Action:** In the toolbar, choose **Save as**. In **New flow name**, enter
`editor_walkthrough_tk`, then choose **Save as** in the dialog. If that name is
already listed in **Open flow**, choose a different unused identifier instead;
do not overwrite it.
**Expected result:** The status says `Saved flow editor_walkthrough_tk`. The
project now contains `flows/editor_walkthrough_tk.py`,
`flows/editor_walkthrough_tk.toml`, and
`flows/editor_walkthrough_tk.layout.json`. The original `document_summary` is
unchanged.
**If this fails:** Stop if the name is not a Python identifier. Use letters,
numbers, and underscores only, beginning with a letter. If the name already
exists or changed on disk, choose a new name or reload the existing flow; the
editor does not silently overwrite a conflicting flow.
**Evidence to retain:** The saved flow name and its status message.
**Repeatability:** Create-only for a new name. After it exists, use **Save** to
update that copy.

### Step 6 — Edit a saved parameter and establish a baseline run

**Goal:** Change code-authoritative flow input through the guided editor, then
record an observed count result for the mapping step.
**Run from:** Browser workbench, with the saved copy open.
**Action:** Select `text.normalize`. In **Parameters**, use **Guided fields** if
needed. Replace the `text` value with `  Local editor  `, including the two
spaces at each end, and choose **Apply parameters**. Choose **Save**, then
choose **Run flow**. Wait for all nodes to complete.
**Expected result:** The saved source now gives `normalize` the edited literal.
The baseline result remains `Document: 2 words, 12 characters`, because the
task trims the spaces and the `prefix` parameter still has its `Document` value.
The completed count node exposes an observed JSON result with `words` and
`characters` fields.
**If this fails:** Do not continue with an incomplete or failed baseline. Read
the failed node's structured error and correct the parameter JSON before saving
or retrying once.
**Evidence to retain:** The completed run ID and the count node's observed
result.
**Repeatability:** Safe for this sample. **Run flow** saves the current editable
draft before it starts; use **Save** first to make the persistence point
explicit.

### Step 7 — Map a nested upstream field to a second input

**Goal:** Add a second `text.count_words` → `text.summarize` connection that
passes only `count["words"]` to `prefix`, while retaining the existing whole
count result for `stats`.
**Run from:** Browser workbench, after the successful Step 6 baseline.
**Action:**

1. Select `text.summarize`. In **Parameters**, click **Use default** beside
   `prefix`, then click **Apply parameters**. This removes the explicit literal
   so a connection can supply `prefix`.
2. Select `text.count_words`. In **Connections → Outgoing connections**, choose
   **Add connection**. Set **Connect to** to **Summarize** (the node labelled `text.summarize`), then choose
   **Connect**. This sample has only one available target argument, so the new
   connection maps to `prefix` automatically.
3. In `text.count_words`'s **Outgoing connections** row for the new `prefix`
   connection, use the **Upstream value** picker to choose
   **Observed: `["words"]`**. If the observed choice is unavailable, enter
   `["words"]` in **Field path (JSON)** and choose **Apply field path**.
4. Confirm the new connection's target argument is `prefix`, then choose
   **Save**.

**Expected result:** `text.summarize` has two incoming mappings: the existing
whole count result to `stats`, and `count["words"]` to `prefix`. The saved
Python source expresses the latter as an indexed value, equivalent to
`prefix=statistics["words"]`.
**If this fails:** If the new connection reports **Mapping required**, select
that connection, enter `prefix` in **Target argument**, and choose **Apply
mapping** before setting its field path. If the path is rejected, use only a
JSON array of string keys or non-negative integer indexes. Do not guess a field
for another task: observed values are examples, not a contract.
**Evidence to retain:** The two incoming mappings on `text.summarize` and the
saved status.
**Repeatability:** Saving updates only the named copy. This mapping is safe in
this sample because `summarize` formats its prefix with an f-string, so the
numeric word count renders as `2`; a task's descriptive `str` input alone does
not guarantee that an arbitrary numeric mapping is valid.

### Step 8 — Prove the mapping is undoable and redoable

**Goal:** Check that a graph edit changes the same draft history used for saved
flow source, without executing an intermediate mapping.
**Run from:** Browser workbench, immediately after Step 7 and before another
run.
**Action:** In `text.count_words`'s **Outgoing connections**, select the new
`prefix` connection rather than an overlapping canvas wire. Then choose
**Undo**. Undo clears the selection: select **Count words** again, then select
its outgoing row whose target argument is `prefix`. Its **Field path (JSON)** is
now `[]`, which means whole upstream result. Choose **Redo**, then reselect
**Count words** and that same `prefix` connection to inspect `["words"]`.
Choose **Save** after the redo.
**Expected result:** Undo and Redo affect the explicit field-path edit, not the
completed run record. The final saved mapping remains `["words"]`.
**If this fails:** Stop rather than running a graph whose selected field is
unclear. Use **Redo** only if it restores `["words"]`; otherwise select the
connection and repeat Step 7 from the existing count result.
**Evidence to retain:** The final field path and saved status.
**Repeatability:** Safe to repeat. A new edit after Undo intentionally clears
the redo history.

### Step 9 — Run the mapped copy and inspect its persisted last run

**Goal:** Execute the saved ordinary Python flow through the real runtime and
inspect evidence captured for that exact saved revision.
**Run from:** Browser workbench, connected project.
**Action:** Choose **Run flow**. Native preparation is automatic, without a
confirmation. Observe node statuses and **Run log**. Select `text.summarize` to
read **Run result**. After completion, choose **Last run** next to **Edit flow**.
**Expected result:** The run completes; the last preview contains
`2: 2 words, 12 characters`. **Last run** shows the run ID, saved flow revision,
inputs, executed graph, executed connections, result, and saved source. It is
read-only evidence; choose **Edit flow** to return to the canvas.
**If this fails:** Do not repeatedly retry an unknown task. This sample is safe
to retry once after fixing its reported error; retain the run ID and diagnostics.
Use **Cancel run** if the sample remains active without progress for five minutes.
**Evidence to retain:** Run ID, final preview, **Last run** revision, and run
diagnostics under `.artifacts/`.
**Repeatability:** Sample task behavior is safe to repeat; other projects may not be.

### Step 10 — Run the same saved source headlessly

**Goal:** Prove the saved copy is ordinary Weavem code, not browser-only state.
**Run from:** Repository root, the same activated Python environment.
**Action:** The browser and bridge may remain open, but neither command uses
them. Set `FLOW_NAME` to the name chosen in Step 5, then run the CLI and Python
forms:

```bash
export FLOW_NAME="editor_walkthrough_tk"
python -m weavem --project examples/editor-local flow run "${FLOW_NAME}"
python - <<'PY'
import json
import os

from weavem.flows import load_local_flow

target = load_local_flow(os.environ["FLOW_NAME"], project="examples/editor-local")
print(json.dumps(target(), sort_keys=True))
PY
```

**Expected result:** Each command's final JSON value is
`{"summarize": "2: 2 words, 12 characters"}`. No browser or editor server is
required. A fresh process may prepare local native code again.
**If this fails:** Confirm the selected project and Python environment match
Step 2, and confirm `FLOW_NAME` matches the saved copy. Preserve the concrete
error rather than reinstalling tools blindly.
**Evidence to retain:** CLI and Python results alongside the GUI run ID.
**Repeatability:** This sample is safe to run again. The Python snippet uses the
same local-flow loader that the CLI uses.

## Verification

- All three nodes show completed; no failed or skipped node remains.
- The final preview, CLI result, and Python result each contain
  `{"summarize": "2: 2 words, 12 characters"}`.
- `text.summarize` retains the whole result mapping to `stats` and the
  `["words"]` mapping to `prefix` after **Save**, reload, and reopen.
- **Last run** identifies the same saved flow revision and shows its executed
  connections. Reconnecting is needed after restarting the server because the
  session token changes.
- The project's artifact directory contains an `editor-runs/` diagnostic folder.
  Local execution compiles and loads a temporary `.so`, then removes its temporary
  build directory using the existing runtime behavior. A reusable native binary
  requires the separate task build/publish workflow; this run does not publish one.

## Rollback and recovery

Use **Cancel run** to stop a current run, then Ctrl+C in its server terminal to
stop the bridge. For forward recovery, use **Open draft → select exported JSON**
to restore edits. Reloading a browser does not cancel its Python run; reconnect
to recover active run controls while the same backend remains alive. Saved Python
flows reopen from the project; exported drafts recover unsaved edits. Never
clear corrupt browser storage as the first recovery step: preserve the original
file/error. A process restart ends the in-memory run index; retained diagnostics
and the persisted **Last run** record remain on disk. Task side effects in other
projects require task-specific recovery; cancellation is not rollback.

## Troubleshooting

| Symptom | Diagnosis and safe action |
| --- | --- |
| Missing UI build | Repeat Step 1 from this checkout; confirm `ui/dist/index.html`. |
| Disconnected or no execution bridge | Open Step 2's printed URL, not Vite; reconnect once. |
| Task not bound | In your own project, bind it with `weavem task use ALIAS --path tasks/NAME`; reload the catalog. The sample already has bindings. |
| Missing argument or unexpected keyword | Correct explicit mappings and applied JSON parameters; task signatures are checked during execution. |
| **Save as** rejects the chosen name | Use an unused Python identifier beginning with a letter. Do not delete or overwrite another flow merely to reuse its name. |
| `prefix` remains a literal or the new wire says mapping required | Select `text.summarize`, remove the explicit `prefix` with **Use default**, apply parameters, then map the new connection to `prefix`. |
| `words` is not offered by **Upstream value** | Complete the Step 6 baseline first. Otherwise enter `["words"]` manually and choose **Apply field path**; do not substitute a guessed field. |
| **Last run** says no recorded run | Run and complete the saved copy first. A browser draft alone has no persisted execution record. |
| Native compilation failed | Retain diagnostics and rerun `python -m weavem doctor`; do not install OS packages silently. |
| Another run is active | Reconnect to the same backend to recover controls, then cancel or finish it. If the backend is unresponsive, stop its terminal with Ctrl+C and restart Step 2. Check side effects before retrying other projects. |
| Stale release pin | Reconnect and inspect the project's explicitly selected release; do not bypass integrity checks. |
| Server restart or 403 | Reconnect to obtain the new session; do not copy tokens into URLs. |

Stop after a second unexplained failure and report the redacted evidence through
the repository issue queue.

## Cleanup

Stop this bridge with Ctrl+C after use. This walkthrough creates the named saved
flow copy; keep it for review or remove it later through your normal source-control
workflow. No temporary accounts, external services, or production changes need
recovery. Keep exported drafts and diagnostic artifacts until reviewed; this
walkthrough does not delete them automatically.

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
