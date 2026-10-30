# Installed project editor integration

Status: lane implementations integrated; combined verification in progress, not released. Approved 2026-10-30.
Baseline: selected Expressive layout with the approved olive palette, `3430e8e`.
Continuation: `prototype/node-editor`, integrated checkpoint `2665388`; no main merge, push, version bump or release.

## Contract and execution plan

- One metadata-led authored-flow resolver serves CLI, Python metadata and editor.
  `[weavem].flow_paths` is an ordered non-empty directory list, defaults to
  `["flows"]`, and replaces that default when configured. Paths are selected
  by trusted project configuration, relative to the project or explicitly absolute.
  Scan sibling TOML definitions directly, never arbitrary Python or recursive code.
  Duplicate local metadata stems are ambiguous; name both paths. Existing saves
  stay at resolved original files, new definitions use the first configured root.
- Bundle production UI assets in wheel and sdist. No npm during Python installation;
  no separate frontend service or daemon. Existing standard-library bridge remains
  loopback-only. Use its launching interpreter and existing dependencies/Prefect
  environment; expose project/interpreter/Python/Weavem diagnostics, no auto-installs.
- Automatically connect and list real flows, without opening or running one.
  Preserve restored/imported/unsaved drafts, corrupt-storage recovery, confirmation,
  revision checks and source-only Python. Remove Motion lab and automatic synthetic
  startup/catalog, not real observed results or useful errors/provenance.
- Source UI scaffolding moves to explicit test fixtures. Keep existing stored draft
  schemas and keys compatible. Normal frontend has no experiment/prototype branding.

## Ownership and integration

Three isolated native-agent lanes: discovery (Python resolution/config/scaffolding),
packaging (assets/build/CI/editor server diagnostics), frontend (all UI startup,
cleanup and tests). Packaging exclusively owns `editor_server.py`; discovery must
send any required route integration as a contract/patch rather than editing it.
The leader owns integration, this record, branch ledger and final review.

## Regression and acceptance gates

Add tests before cleanup. Verify configured locations/defaults/collisions/safe paths,
no-import discovery, saves/scaffolds, metadata/CLI/GUI parity and stale revisions.
Verify fresh/empty/failed connection, same/different/legacy/corrupt stored drafts,
edits while connecting, active runs and no automatic flow opening. Run Python,
frontend units/types/lint/build and full browser suites. Test a candidate wheel
outside checkout with no Node or PYTHONPATH, real save/run parity and package-owned
assets, plus sdist-to-wheel rebuilding without Node. Preserve all failed evidence.
Evidence: original `.artifacts/node-editor/product-editor/evidence/`.

## Current results

Implemented lanes are integrated at `2665388`; the [current handoff](../../BRANCH_HANDOFF.md)
records original and integrated commit IDs. Historical Impeccable results do not
prove this combined change. Fresh full Python, frontend/browser and installed
candidate verification are still in progress; do not call the integration accepted
until the leader records their outcomes.

Discovery lane verification: 42 owned focused checks passed; 55 focused checks
passed with the proposed catalog integration applied in memory, including native
boundary tests. That two-caller integration is now committed at `2665388`. An
earlier full host run reported the then-missing catalog integration plus an
artifact-directory interference failure; the isolated affected scope passed.
Failed evidence is retained, not represented as an integrated green run.

The canonical [editor guide](../../ui/README.md) distinguishes installed-candidate
consumption (prebuilt assets, no Node) from source contribution (Node build/stage).
The published `0.1.0a2` manual remains unchanged. Configured flow roots, automatic
chooser behavior and environment ownership are documented in the guide and
[maintainer reference](../maintainers/editor-reference.md).

## Independent review and documentation reconciliation

The integrated resolver consumers, direct-only scanning, duplicate diagnostics,
configured-path boundaries, original-source save and metadata-stem journal naming
were reviewed against their code and regression tests. One remaining integration
issue was identified: worker tracing still constructs a default `flows/<name>.py`
path even when the actual loader resolves a different root/source filename.
Execution loads the right code, but node-level instrumentation can be missed.
This needs an authoritative resolved trace path and a custom-root node-event
regression before acceptance; the leader owns the fix and final result update.

Current source/candidate guides now describe packaged assets, source staging,
automatic chooser startup, configured roots and Python-environment ownership.
The previous root Expressive handoff is preserved as a historical project record.
Documentation-only verification: nine documentation-verifier regression tests and
local path/heading checks across all docs plus the handoff/UI/example guides passed.
The first documentation check caught a renamed linked heading; its historical
anchor was restored. Evidence: `product-editor/evidence/integration-review/`
beneath the agreed artifact directory. These checks do not claim combined runtime
acceptance or a complete browser walkthrough rerun.
