# Installed project editor integration

Status: implementation in progress, not released. Approved 2026-10-30.
Baseline: selected Expressive layout with the approved olive palette, `3430e8e`.
Target: `prototype/node-editor`; no main merge, push, version bump or release.

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

Pending implementation and integrated validation; historical Impeccable tests do
not prove this change. See the lane handoffs and final results appended here.
