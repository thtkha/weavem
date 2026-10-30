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
prove this combined change. Fresh integrated verification is complete; the final results below supersede
intermediate candidate evidence. This is branch acceptance, not a release.

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
were reviewed against their code and regression tests. Review identified a worker trace path hardcoded to `flows/<name>.py`.
Commit `707ccd6` now resolves the authoritative loader path, including configured
roots and custom source filenames. Regression checks cover completed and failed
node events. The installed gate first reproduced the bug (completed run, skipped
node), then passed against the final candidate; its failed evidence is retained.

Current source/candidate guides now describe packaged assets, source staging,
automatic chooser startup, configured roots and Python-environment ownership.
The previous root Expressive handoff is preserved as a historical project record.
Documentation-only verification: nine documentation-verifier regression tests and
local path/heading checks across all docs plus the handoff/UI/example guides passed.
The first documentation check caught a renamed linked heading; its historical
anchor was restored. Evidence: `product-editor/evidence/integration-review/`
beneath the agreed artifact directory. These checks do not claim combined runtime
acceptance or a complete browser walkthrough rerun.

## Final integrated acceptance (2026-10-30)

- Full Python suite after the trace fix: **240 tests passed** in 346.645 seconds.
- Frontend: typecheck, lint, 40 unit tests, production build, and **77 browser
  tests passed**. `2d9a932` includes a body-stall startup-timeout regression.
- Final wheel and sdist contain three identical production assets; rebuilding the
  sdist without Node preserves those bytes. This is an asset-identity check, not
  a claim that entire wheel archives are reproducible.
- Outside-checkout installed gate: no Node on PATH, isolated Python invocation,
  packaged HTML/JS/CSS and MIME, environment diagnostics, custom `pipelines/`
  save/list/run, invalid-sidecar diagnostics, completed node trace, and API/CLI/
  Python interpreter parity all passed.
- Real Chromium check against the same installed candidate: automatic connection,
  real chooser, source save, native task execution, node results, Last run UI and
  snapshot, reload, CLI and Python parity passed. Run:
  `01a9f98f-31ff-4566-b737-7b2bd419593b`. Screenshots include `last-run.png`.

Evidence beneath `.artifacts/node-editor/product-editor/evidence/`:
`integrated-frontend/` and `integrated-packaging/`. Final packaging files are
`integrated-packaging/final-dist/weavem-0.1.0a2-py3-none-any.whl` and its sdist;
wheel SHA256: `89de8d54f47ada75b7316fd2bda4a1ffd0db165268e5e43672b5cceaa240a6b1`.
Use `final-full-tests.log`, `final-package.log`, `final-installed-editor/result.json`,
and `final-browser/` for final evidence, not the superseded initial candidate.

The isolated consumer reuses existing dependency installations through an explicit
`.pth` file; this does **not** prove a fresh network dependency installation or
another OS/Python platform. Local CPython was 3.14.8. Remote CI was not run,
and no release, tag, push, version bump, or merge to main was performed.
