# Branch status and continuation

**Recorded 2026-10-30 at integrated code checkpoint `2665388`.** This is a
project-owner/contributor handoff, not a release manifest. Later verification,
fixes or documentation may advance tips; inspect Git before acting.

## Where to continue

- Released framework usage: [official manual](../users/index.md), covering
  published `0.1.0a2`; its wheel does not contain this new editor integration.
- Current unreleased editor: **`prototype/node-editor`**. Read the
  [current handoff](../../BRANCH_HANDOFF.md), [editor guide](../../ui/README.md),
  [walkthrough](../../examples/editor-local/README.md), and
  [integration record](editor-integration.md). Fresh combined checks are in progress.
- Framework development: [maintainer index](../maintainers/index.md) and
  [context policy](../maintainers/context-policy.md).

| Branch | Audited code | Status / next action |
| --- | --- | --- |
| `main` | `f7758af` | Released-framework baseline, untouched; no editor main merge or release authorized. |
| `prototype/node-editor` | `2665388` | Authoritative integrated editor continuation. Selected Expressive palette/layout and all three product-editor lanes integrated; pending final checks and owner review. |
| `work/editor-discovery` | `d7ca07f` | Integrated as `3da6b59`, `d5e2679`, plus leader catalog fix `2665388`. Continue on prototype. |
| `work/editor-packaging` | `6612db9` | Integrated as `d079781`, `6d3173d`; fresh installed-package/full-Python checks underway. |
| `work/editor-frontend` | `1b9dcbf` | Integrated as `f9c1b66`; fresh frontend/browser checks underway. |
| `experiment/impeccable-expressive` | `8e37c00` | Owner-selected composition/palette now integrated into prototype; historical lane, not current application. |
| `experiment/impeccable-practical`, `experiment/impeccable-calm` | Historical comparison | Unselected alternatives, retained; no automatic merge or deletion. |
| `feature/editor-experience` | `e1bd04c` | Earlier combined six-area checkpoint, integrated into the later prototype history. Not current continuation. |
| `feature/task-interfaces` | `98e5c47` | Historical constituent lane; integrated by cherry-pick and later fixes. |
| `feature/editor-interactions` | `a26d170` | Historical constituent lane; integrated by cherry-pick and later fixes. |
| `feature/run-inspection` | `83e2e76` | Historical constituent lane; integrated by cherry-pick and lifecycle fixes. |
| `feat/editor-layout`, `feat/editor-connections`, `feat/editor-parameters` | Historical | Earlier prototype constituents; no new work or deletion authorized. |
| `feat/editor-scrollbars`, `feat/editor-tailwind`, `feat/inspector-sections` | Historical | Earlier prototype constituents; selected inspector sections retained. |
| `feat/inspector-tabs` | `632dbd6` | Unselected alternative, retained for comparison. |

Cherry-picked implementations do not necessarily appear merged by ancestry.
Original-to-integrated lane IDs are in the root handoff. Inspect refs with
`git log --oneline prototype/node-editor` and `git worktree list`; no push or
fetchability promise is implied. No branch deletion or history rewrite is part
of this integration. A preview URL in historical records is not a live-service
promise. The [old Expressive handoff](expressive-branch-handoff.md) is preserved
as history rather than current operating guidance.

The following dated sections retain earlier decisions and evidence. Their old
branch/preview status is historical; the current table and handoff take precedence.

## Decisions that constrain continuation

1. **Code first:** task authors write working Python, not mandatory UI schemas,
   components, or styling. The GUI saves ordinary source in the same configured flow
   directories used by code authors (`flows/` by default). CLI/Python run without the GUI/bridge.
2. **Suggest, do not invent:** derive supported inputs/defaults/returns/docstrings
   statically. Keep unknowns unknown. Distinguish declared structures from observed
   sample results; do not execute code merely to discover its interface.
3. **n8n-like authoring, not a new central platform:** visual field selection
   becomes Python key/index access. Weavem's library and Prefect are runtime
   dependencies; the editor is not a required central service in the data path.
4. **Six approved improvements:** parameter forms/field mapping; undo/redo and
   selection copy/paste; Edit flow / Last run; standard result viewers; optional
   structured failures; consistent toolbar. Read-only Last run is intentionally
   small, not a monitoring product or automatic replay engine.
5. **Boundaries:** Prefect retains retries/orchestration. No task-bundled UI code,
   plugin marketplace, mandatory UI metadata, database, registry, or new dependency
   was introduced. Arbitrary Python remains runnable but not arbitrarily rewritable.
6. **Reuse selectively:** WorkflowBuilder supplied useful UX/architecture ideas;
   its SDK/Temporal graph runtime was not adopted. Inspector sections were chosen
   over the tab alternative by owner preference; no measured superiority is claimed.
7. **Local and explicit:** execution bridge stays loopback-only. Verified bytes
   are not a sandbox. Cancellation/Undo cannot reverse task side effects. Last-run
   source snapshots do not guarantee reproducibility of mutable code/services.
8. **Review gate:** the selected experience is now integrated into prototype;
   fresh checks and owner review remain required before any main merge. No main merge, release,
   publication, history rewrite, cleanup, or branch deletion is implicit.

## Historical experience verification and evidence

The [prototype record](node-editor-prototype.md#editor-experience-feature-branch-ready-for-review)
records the implementation acceptance: 226 full Python regression tests, fresh
focused checks after fixes, 37 frontend unit tests, 56 Chromium tests, and actual
native GUI/CLI/Python parity. Counts overlap. These are bounded local Linux/
CPython 3.15 results, not remote CI, cross-browser, or fresh-machine certification.
Retained ignored evidence is under `.artifacts/node-editor/experience/`. It is
optional local evidence, not required reading to recover the design or next step.

## Historical documentation pass and gates

This pass persists the working agreement and branch handoffs, consolidates the
current guide/reference, and extends the example. Main, prototype, and historical
branches remain unchanged. Only the integration and three active lanes receive
new documentation commits; do not claim the policy is already committed on main.

Remaining feature gate: owner review of the combined UI and behavior. Re-run
checks when code changes; use the canonical guide/reference and tracked records
rather than the original conversation. The preview remains stopped unless
explicitly requested. Update this ledger after merges or branch lifecycle changes.

## Documentation validation — 2026-10-30

The consolidation pass ran the nine documentation verifier regression tests,
strict walkthrough lint, and local path/anchor checks across this checkout and
all three active lane worktrees. It also saved the documented mapped sample in
a disposable cloned project and verified both baseline and final results through
the saved Python loader and CLI, including local native preparation. Final output:
`{"summarize": "2: 2 words, 12 characters"}`.

Evidence is retained under `.artifacts/node-editor/docs-consolidation/`: the
headless verification script, result JSON, runtime log, link-check script and log,
and documentation test log. No editor preview was started, no new wheel was built
or released, and the extended browser click-through was not rerun. The walkthrough
therefore remains **Source-verified**, not end-to-end GUI Verified. No code files
changed in this pass.


## Historical Impeccable selection — 2026-10-30

The owner chose `experiment/impeccable-expressive` as the design candidate, with
its cyan/blue palette explicitly rejected in favor of the approved sage/olive
colors. Preserve its layout, hierarchy and interactions; verify consistency and
alignment after recoloring. Original/practical/calm previews are retired, while
branches and comparison evidence remain historical. Only static preview4183 is
active. The selected branch is not yet merged to `feature/editor-experience`,
`prototype/node-editor` or main. See [lab report](impeccable-lab.md) and the
branch-root `BRANCH_HANDOFF.md` for current verification and next review gate.


Selected Expressive implementation **`98aae6d`**, with final followup **`8e37c00`**, applies the approved olive palette
without losing its composition. The palette/alignment pass verifies40 unit and
67 Chromium tests plus typecheck/lint/build; source detector empty, rendered scene
has only the unsuppressed system-font taste heuristic. It corrects control
baselines, select/JSON font consistency and narrow execution grouping; no runtime
or saved-flow contract changed. See the selected section of the lab report and
BRANCH_HANDOFF.md. The UI is still branch-only; original continuation is untouched.

Final mapping-control followup `8e37c00` removes a browser-default input in wire
inspection; the fresh complete Chromium suite passes **67/67**. Documentation
commit(s) record this state without implying promotion to another branch.
