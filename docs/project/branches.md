# Branch status and continuation

**Recorded 2026-10-30.** This is a project-owner/contributor handoff, not a release
manifest. Commit IDs below identify audited code; later documentation commits may
advance the branch tips. Check Git before acting on this record.

## Where to continue

- Released framework usage: [official user manual](../users/index.md), covering
  `0.1.0a2`. Do not assume the source editor ships in that wheel.
- Combined unreleased editor: **`feature/editor-experience`**, application
  checkpoint `e1bd04c`, then the documentation consolidation pass. Start with the
  [editor guide](../../ui/README.md), [walkthrough](../../examples/editor-local/README.md),
  and [source API reference](../maintainers/editor-reference.md).
- Framework development and working agreements: [maintainer index](../maintainers/index.md)
  and [context policy](../maintainers/context-policy.md).

| Branch | Audited code | Status / next action |
| --- | --- | --- |
| `main` | `f7758af` | Released-framework documentation baseline; untouched in this pass. No editor feature merge authorized here. |
| `prototype/node-editor` | `0b6144f` | Python-backed editor checkpoint; awaiting final user review of the experience branch before any feature merge. |
| `feature/editor-experience` | `e1bd04c` | Authoritative combined review application. All six areas wired together; later commits in this pass are docs only. Preview intentionally stopped. |
| `feature/task-interfaces` | `98e5c47` | Constituent lane, integrated by cherry-pick with later leader fixes. Handoff docs tip `63bdc85`. Continue on combined branch, not this partial application. |
| `feature/editor-interactions` | `a26d170` | Constituent history/toolbar lane, integrated by cherry-pick with later leader fixes. Handoff docs tip `550a894`. |
| `feature/run-inspection` | `83e2e76` | Constituent snapshot/view lane, integrated by cherry-pick with lifecycle fixes. Handoff docs tip `c09e5d4`. |
| `feat/editor-layout` | `99f9811` | Historical; ancestor of prototype. No new work or deletion authorized. |
| `feat/editor-connections` | `dbc5907` | Historical; ancestor of prototype. |
| `feat/editor-parameters` | `4129edd` | Historical; ancestor of prototype. |
| `feat/editor-scrollbars` | `ef5847c` | Historical; ancestor of prototype. |
| `feat/editor-tailwind` | `d691407` | Historical; ancestor of prototype. |
| `feat/inspector-sections` | `00f5587` | Selected inspector direction; ancestor of prototype. |
| `feat/inspector-tabs` | `632dbd6` | Unselected alternative, not an ancestor of prototype. Preserve for comparison, not as unfinished work to merge automatically. |

Git ancestry alone will not mark the three new lanes merged: their reviewed
implementation commits were cherry-picked and then integrated, not merged as
branch ancestry. Each lane's `BRANCH_HANDOFF.md` records ownership, interfaces,
baseline, checks, known integration gaps and continuation. From any local clone
containing these refs, inspect them without checking out another branch:

```bash
git show feature/task-interfaces:BRANCH_HANDOFF.md
git show feature/editor-interactions:BRANCH_HANDOFF.md
git show feature/run-inspection:BRANCH_HANDOFF.md
git log --oneline feature/editor-experience
git worktree list
```

Branch refs in this record are local; this pass does not push them. Do not promise
a colleague can fetch them before an explicit push. The recorded code SHA and
history explain what was inspected even if branch tips move later.

## Decisions that constrain continuation

1. **Code first:** task authors write working Python, not mandatory UI schemas,
   components, or styling. The GUI saves ordinary source in the same `flows/`
   directory used by code authors. CLI/Python run without the GUI/bridge.
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
8. **Review gate:** combine changes on the feature branch, present for owner
   review, then merge into prototype only after approval. No main merge, release,
   publication, history rewrite, cleanup, or branch deletion is implicit.

## Verification and evidence

The [prototype record](node-editor-prototype.md#editor-experience-feature-branch-ready-for-review)
records the implementation acceptance: 226 full Python regression tests, fresh
focused checks after fixes, 37 frontend unit tests, 56 Chromium tests, and actual
native GUI/CLI/Python parity. Counts overlap. These are bounded local Linux/
CPython 3.15 results, not remote CI, cross-browser, or fresh-machine certification.
Retained ignored evidence is under `.artifacts/node-editor/experience/`. It is
optional local evidence, not required reading to recover the design or next step.

## Documentation pass and remaining gates

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
