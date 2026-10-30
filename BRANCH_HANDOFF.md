# Integrated project editor handoff

**Continue on `prototype/node-editor`.** Recorded 2026-10-30 at integrated code
checkpoint `2665388`. This is unreleased source/candidate work: the published
`0.1.0a2` distribution and main are unchanged. No release, push, or branch cleanup
is implied.

## Implemented

The selected Expressive layout and approved olive palette are integrated; the
Motion lab, automatic synthetic catalog, and experiment branding are removed.
The editor connects to its real project on startup and presents a flow chooser;
it never automatically opens or executes a flow. Existing browser drafts retain
recovery and replacement safeguards.

An installed candidate contains prebuilt static assets. `weavem editor --project
PATH` serves them through the local Python bridge without Node, npm, or a second
frontend service. Run it from the project's Python environment: workers use that
same interpreter, installed dependencies, and normal Prefect environment. The
**Project environment** disclosure shows the project, interpreter, Python, and
Weavem version. It does not create environments or install missing dependencies.

CLI, metadata, editor, and workers share metadata-led flow discovery. Defaults
remain `flows/`; `[weavem].flow_paths` selects ordered replacement directories.
New flows use the first root; updates keep their original source/sidecar/layout
locations. Duplicate sidecar stems fail explicitly rather than picking a winner.

## Integrated lanes

| Lane | Original lane commits | Integrated commits |
| --- | --- | --- |
| Discovery | `d3e1a13`, `d7ca07f` | `3da6b59`, `d5e2679` |
| Packaged assets/runtime gate | `74721c9`, `6612db9` | `d079781`, `6d3173d` |
| Real-project startup/UI cleanup | `1b9dcbf` | `f9c1b66` |
| Leader catalog integration | — | `2665388` |

The leader integration makes editor task catalogs independent of flow validity:
invalid sidecars can be listed with diagnostics, while public `Project.metadata()`
keeps its fail-fast contract. See the [integration record](docs/project/editor-integration.md)
for scope, verification gates, and current status.

## Verification and next action

**Integrated verification is in progress.** Lane checks are not a substitute for
the fresh combined Python/frontend/browser/installed-package checks. Retain failed
and passing evidence under `.artifacts/node-editor/product-editor/evidence/`.
The leader records final outcomes after the verification agents return; do not
infer a completed release gate from this documentation commit.

Use the [editor guide](ui/README.md), [walkthrough](examples/editor-local/README.md),
and [reference](docs/maintainers/editor-reference.md). The old selected-design
handoff remains a [historical record](docs/project/expressive-branch-handoff.md),
not the current operating instructions. Historical branches and evidence remain
intact; no preview is promised by this handoff.
