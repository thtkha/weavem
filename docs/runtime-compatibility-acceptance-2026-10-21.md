# Runtime compatibility repair and acceptance rerun

> **Historical report.** Versions, failures, and blockers below describe this
> earlier candidate. The cache handoff issue was subsequently fixed and Python
> 3.15 passed local verification with Prefect 3.9.0. See
> [current compatibility evidence](release-readiness-2026-10-26.md); the original
> results below have not been rewritten.

**2026-10-21 — the fresh-install runtime regression is fixed on Python 3.12–3.14.**
Native publishing, copied-store execution, and exact version selection now pass
real orchestration checks. The independent business application also works.
However, its untouched V1 handoff failed after the author accidentally added
bytecode caches to the release store. That failure is preserved, not counted as
a clean acceptance pass. Python 3.15 remains a separate publication blocker.

This follows the [original failed trial](blind-acceptance-2026-10-21.md), whose
report and artifacts remain unchanged.

## What changed

- Added `fastapi==0.143.0` to package requirements, retaining Prefect `3.8.7`.
  This is the tested compatibility combination, not a speculative broad upgrade.
  FastAPI removed the deprecated keyword support that Prefect still uses; the
  [upstream change](https://github.com/fastapi/fastapi/pull/16545) explains why the
  fresh resolver previously produced a valid installation that crashed at runtime.
- Added a wheel-metadata regression assertion so the constraint ships to users.
- Added `scripts/verify-installed-wheel.py`, an internal release check—not a new
  public CLI or API. It verifies installed, non-editable imports, then executes
  plain Prefect, editable local tasks/flows, and published flows from a copied
  store. It checks native ELF payloads, overwrite refusal, preserved V1 bytes,
  and distinct V1/V2 behavior. `.fn` is used only in focused authored tests,
  never as a substitute for the gate's actual orchestration calls.
- Updated CI to build a wheel first, test its installation, and run the gate in a
  separate fresh environment outside the checkout. Failures retain logs, versions,
  and generated evidence. Commands have timeouts; jobs have a 30-minute limit.
  The gate discards inherited Prefect server/database/profile and Weavem store
  settings rather than risking an operator's configured services.

No framework runtime code, public API, CLI, manifest schema, or storage semantics
changed. No new storage service or agent-specific guide was added.

## Fresh-install verification

The repaired wheel was installed normally into fresh environments. Dependencies
were resolved from its requirements, without an extra constraints file. Both
blind-trial environments received only the Weavem wheel and its dependencies;
matrix test environments additionally received the existing wheel-build tooling.

| Check | Python 3.12.3 | Python 3.13.16 | Python 3.14.8 |
| --- | --- | --- | --- |
| Installation, `pip check`, native doctor | Pass | Pass | Pass |
| Existing suite, 102 tests, no skips | Pass | Pass | Pass |
| New gate regression tests, 2 tests | Pass | Pass | Pass |
| Final installed-wheel gate, 30 recorded commands | Pass | Pass | Pass |

The focused tests cover timeout-output preservation and isolation from inherited
operator configuration. The final real gate was also run with dummy external
database/profile/store settings present to verify that isolation works in practice.
The expected immutable-version rejection is a successful negative test, not an
unexpected command failure.

All environments resolved FastAPI `0.143.0`, Prefect `3.8.7`, Pydantic `2.14.1`,
and Starlette `1.9.0`. A separate ordinary Prefect flow, without importing Weavem,
returned `42` in the repaired fresh environment. The former startup failure did
not recur.

These are local results on one Linux x86-64 WSL2 host, not executed GitHub Actions
results or cross-machine portability proof. The host's Python 3.12 lacked
`ensurepip`; its fresh environment was provisioned using `pip --python` without
privileged OS installation. The other fresh environments used normal venv seeding.

## Independent author and consumer journey

Fresh agents received the public human-facing docs and installed wheel, without
the prior conversation. Framework implementation inspection and dependency
changes were prohibited during the trial. The coordinator froze inputs, copied
published releases, and moved the original author project out of its working
path during consumer execution. This is procedural isolation, not a security
sandbox or an independent human usability study.

The author created three reusable tasks and a CSV-report flow. The monetary task
is a compiled native `.so`; the consumer did not compile a replacement.

| Scenario | Observed result |
| --- | --- |
| Author's local and published V1 flow, before final housekeeping | Matching JSON and CSV; total 325 cents for the author's three-order fixture |
| Consumer's own normal flow reusing native V1 | 700 cents for quantity 2, price 350 |
| Different implementation published over V1 | Refused with the expected immutable-version conflict |
| Author's published V2 flow | Total 625 cents: the same three orders plus 100 cents per order |
| Consumer retains V1 and explicitly selects native V2 separately | Normal flows return 700 for V1, 800 for V2, and 100 for a zero-priced V2 order |
| Consumer executes published V2 from the copied store | Correct report CSV and total 1000 cents for its two orders |
| Independent V2 business acceptance on the untouched handoff | **10/10 passed**, zero errors or failures |
| Consumer and independent tester execute untouched published V1 handoff | **Rejected before execution**; no V1 business cases passed |

The independent cases check normalization and aggregation, header-only input,
integers larger than 64 bits, malformed numbers, invalid quantities/prices,
duplicate IDs, and missing/extra CSV fields. Seven invalid-input cases each raised
a useful `ValueError` and left the preexisting output sentinel unchanged.

### Why the V1 handoff failed

After its successful V1 runs, the author invoked `python -m compileall -q .`
across the project. That explicitly wrote `__pycache__` directories inside the
published store, despite the ordinary no-bytecode environment setting.

The flow validator requires exactly the manifest and its named payload. The
extra directory therefore triggers `flow payload differs from manifest`, even
though the payload's hash and size still match. V2 was published later without
that extra directory and worked without a handoff repair.

The existing artifact contract already describes the exact-files layout. This
was an authoring/housekeeping mistake, not another dependency failure. It also
exposed a usability weakness: the error does not distinguish unexpected files
from a genuinely changed payload. No validator relaxation, application patch,
cache deletion, or repair to the original handoff was made during the trial.

### Separate post-trial diagnostic—not a replacement pass

After recording the formal results, the coordinator made a **new** diagnostic
store containing only each manifest and its named payload. All copied bytes are
identical to the originals; no source, manifest, or native binary was edited or
rebuilt, and nothing was removed from the original store.

With both versions present in that diagnostic store, the independent tester used
the same frozen verifier and actual Prefect Flow calls:

- V1: **10/10 passed**, zero failures/errors.
- V2: **10/10 passed**, zero failures/errors.

This supports the extra-directory diagnosis and demonstrates the business
behavior and old/new pin isolation in the canonical copy. It does **not** turn
the untouched V1 handoff into a successful zero-intervention sharing experience.
The formal failed-handoff result remains unchanged.

## Readiness and next work

The original fresh-install blocker is resolved, with a release check capable of
catching the same class of orchestration failure. Native task reuse and explicit
versioned collaboration are demonstrated through real execution, not only metadata
or focused function tests. The docs supported this bounded AI-assisted journey;
adding an `AGENTS.md` would not fix the observed artifact mistake.

I would still hold public publication under the current requirements:

1. **Resolve latest-Python support.** The repaired wheel still declares
   `>=3.12,<3.15`. A Python 3.15.0 installation check rejects it as expected, and
   CI's latest-stable gate remains blocking. Nothing was waived or widened.
2. **Address handoff friction next.** At minimum, distinguish unexpected release
   directory entries from payload corruption. Keep source verification away from
   immutable release folders; a future selected-flow export could copy only
   declared artifacts and pinned dependencies. Those changes are not implemented
   in this repair.
3. **Run the new workflow on GitHub before release.** Local validation passed;
   no remote workflow was triggered because nothing was committed or pushed.

No performance improvement, reproducible native rebuild, cross-platform support,
publisher trust, or execution sandbox is established by these results.

## Evidence and preservation

Compatibility evidence is under the gitignored local directory
`.artifacts/runtime-compatibility/2026-10-21/`:

- `verification-summary.json` — interpreter matrix and executed-script hash.
- `logs/full-{12,13,14}.log` and `logs/gate-unit-final-{12,13,14}.log` — 102-test
  suites plus two focused tests per interpreter, **312 test passes in total**.
- `installed-smoke-final-{12,13,14}/result.json` — final real gate outcomes and
  per-command logs; earlier runs are preserved separately.
- `logs/install-*.log`, `logs/freeze-*.txt`, `logs/latest-python-315.log` — install
  provenance, resolved versions, and the retained Python-support blocker.

Independent-trial evidence is under
`.artifacts/blind-acceptance/2026-10-21-fixed/`:

- `infrastructure/provenance.json` — frozen wheel hash
  `cf38f8f37c507e7a81c4cd04072bd509ee6cf22c753ade16c5aefd06ae31150e`;
  base commit `9b9a49f95a82effa4a8f2ba12ae250e5a21da757` plus the uncommitted
  FastAPI requirement change. Installed framework and dependency snapshots stayed
  unchanged throughout the trial.
- `author/author-handoff*.json`, `consumer/consumer-result*.json`, and their
  observations/evidence — original actor results and command records.
- `evaluation/final_acceptance.json` — formal V1 handoff failure versus V2 pass.
- `evaluation/post-trial-diagnostic.json` — separately labeled canonical-copy
  results, without replacing the formal outcome.
- `infrastructure/canonical-diagnostic-copy.json` — exact copied pairs and omitted
  entries in the new diagnostic copy.
- `infrastructure/final-audit.json` — provenance, payload hashes/sizes, strict
  layout findings, original V1 byte preservation, and pin checks.
- `sealed/author-project-v1/` and `sealed/author-project-v2/` — preserved projects,
  including candidates, working files, and the original cache-polluted release.

Sandbox-denied loopback attempts and ordinary application-authoring mistakes are
retained in the logs and distinguished from framework failures. One author JSON
validation label was reused: the command ledger retains both attempts, but the
second attempt overwrote the first per-label output. This is not a complete
filesystem-operation trace.

Artifacts are local and gitignored; sharing this report alone does not share the
evidence. No cleanup, commit, push, or PyPI publication was performed.
