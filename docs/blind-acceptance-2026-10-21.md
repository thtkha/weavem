# Blind acceptance trial — 2026-10-21

> **Historical report.** The failed trial below is preserved unchanged. Later
> runtime and cache fixes, Python 3.15 verification, and remaining release gates
> are summarized in [current compatibility evidence](release-readiness-2026-10-26.md).

**Verdict: hold PyPI publication.** A fresh install can author, compile, publish,
and discover native task releases, but cannot run a normal local or published
flow in the tested dependency environment. This is a release blocker, not a
reason to add more infrastructure.

The trial is finished; the acceptance journey did **not** pass. No framework or
dependency repair was made to turn the experiment green.

## What we tested

Three fresh agents acted as an author, a colleague receiving releases, and an
independent acceptance tester. The author and consumer received the public docs,
an installed wheel, and a business brief, without the earlier conversation or
access permission to inspect framework implementation code. The tester received
the business contract and published store, not the author's solution.

The application reads an orders CSV, normalizes customer names, calculates money
in integer cents, groups totals by customer, and writes a report. It must reject
invalid rows without overwriting an existing report. Three reusable tasks serve
one flow; the line-total task must be a real native `.so`.

The journey included a deliberate upgrade:

- V1 computes `quantity * unit_price_cents`.
- V2 adds 100 cents **per order**, including a zero-priced order.
- Publishing different bytes over V1 must fail.
- The colleague must explicitly select V2; V1 releases must remain unchanged.

### Frozen setup

| Item | Recorded value |
| --- | --- |
| Source commit | `9b9a49f95a82effa4a8f2ba12ae250e5a21da757` |
| Package | `weavem-0.1.0-py3-none-any.whl`, non-editable installation |
| Wheel SHA-256 | `b6b16a3ec17f8dd38720282c3655e0a1d89a2b3362d8cd3a733204947aab406f` |
| Interpreter | CPython 3.14.8, separate fresh author and consumer environments |
| Machine | Same Linux x86-64 WSL2 host, glibc 2.39 |
| Dependencies | Installed normally from the wheel's requirements; snapshots retained |
| Sharing | Copy of the published folder, without the original author project at its working path |
| External services | No registry, warehouse, storage server, or production data |

This is procedural blindness, **not a filesystem-enforced sandbox**. Agents
shared one machine, and source snapshots remained available to the coordinator.
This tests AI-assisted onboarding, not independent human usability, cross-machine
portability, or hostile-code isolation. Installation used a private wheel, not
public `pip install weavem` from PyPI.

## Results

| Claim | Outcome | Evidence and boundary |
| --- | --- | --- |
| Fresh wheel installation | **Pass** | Both environments installed successfully and passed `pip check`. |
| Docs sufficient to author tasks and a flow | **Pass for this scenario** | Author scaffolded, validated, tested, built, and published using public docs. |
| Native prerequisites and compilation | **Pass** | Native doctor succeeded; both task versions built as stripped x86-64 ELF `.so` files. |
| Authored behavioral tests | **Pass** | Source tests, compiled-export build checks, and focused flow-function tests passed; these are not orchestration tests. |
| Task and flow publication | **Pass** | Three V1 tasks and one V1 flow published; native task V2 and flow V2 added later. |
| Copied-folder discovery and native reuse | **Pass, function-only** | Consumer discovered releases and called the released native functions without rebuilding them. |
| Normal local and published flow execution | **Fail** | Author and consumer both hit the same Prefect startup error before application code. |
| Published-flow held-out business cases | **Blocked** | Each final version report records zero passes, zero behavioral failures, and one infrastructure error. No held-out case executed. |
| Immutable V1 publication | **Pass** | Overwrite rejected; all original V1 file hashes unchanged after V2 publication. |
| Exact dependency pins and explicit upgrade | **Pass, static** | Flow V1 pins native task V1; flow V2 pins native task V2. Original consumer selection remains V1. |
| Old-flow isolation during actual execution | **Unproven** | Both versions fail before execution; metadata separation is not runtime proof. |

The consumer's function-only checks returned:

| Released native function | Result |
| --- | ---: |
| V1: quantity 2, price 350 cents | 700 |
| V2: quantity 2, price 350 cents | 800 |
| V2: quantity 1, price 0 cents | 100 |

These used the released task's real `.fn`, through the documented focused-test
pattern. They do not demonstrate Prefect orchestration, complete CSV reporting,
or runtime flow-version isolation. No successful report CSV or returned flow
summary is claimed.

## The release blocker

The fresh resolver produced this combination in both environments:

| Package | Version |
| --- | --- |
| Weavem | 0.1.0 |
| Prefect | 3.8.7 |
| FastAPI | 0.156.8 |
| Pydantic | 2.14.1 |
| Starlette | 1.9.0 |

Normal execution ends with:

```text
TypeError: Body() got an unexpected keyword argument 'min_items'
```

Prefect's local-server API imports `concurrency_limits_v2.py`, which calls
`Body(..., min_items=1)`. The installed FastAPI `Body` signature does not accept
that keyword. Prefect's installed metadata permits
`fastapi>=0.139.0,<1.0.0`, so this combination satisfies the package resolver and
`pip check` despite failing at runtime.

The coordinator reproduced the failure with an ordinary public `@prefect.flow`
returning `42`, **without importing Weavem**. The independent tester also
reproduced it through public Prefect interfaces. This establishes an upstream
compatibility problem in the installed combination, rather than a bug in the
orders application. It does not establish which replacement versions are safe;
none were tried during this frozen trial.

Weavem still owns its fresh-install experience. Pinning Prefect alone did not
freeze its transitive dependency compatibility, and passing focused tests did
not prove the orchestration runtime starts. An older successful environment is
not evidence that a new install will work today.

The final held-out verifier stopped while importing the Prefect test harness,
before loading either released flow. Its cases cover valid normalization,
header-only input, large integers, malformed numbers, invalid quantities/prices,
duplicate IDs, incorrect CSV columns, and preservation of an existing report on
invalid input. **Those behaviors remain unverified by independent execution.**

## What this says about maturity

The underlying reuse model has tangible value: the author produced versioned
native artifacts, the colleague discovered and reused their compiled functions,
and publishing an upgrade preserved old releases with explicit dependency pins.
This is more than a naming layer over ordinary Python functions.

The docs supported this bounded authoring and sharing journey without a new
agent-specific guide. There is no evidence here that more documentation, another
CLI layer, or RustFS would solve the blocking problem. The manual command and
folder handoff remains visible friction, but it is secondary to execution.

This was not a productivity benchmark against plain Python or Prefect. The
complete application never ran, so we cannot claim faster development, faster
execution, or a proven end-to-end collaboration experience. A `.so` alone proves
neither performance nor portability.

**Revised readiness assessment:** promising private experimentation, but not
ready for the intended public alpha fresh-install promise in this state.

## Next work, in order

1. **Resolve and test dependency compatibility.** Establish a known-working
   runtime combination through an upstream update or justified compatibility
   constraint. Do not pick an untested version solely to silence this traceback.
2. **Add a clean-install release gate.** Install the built wheel in fresh
   environments and actually run local and published flows through Prefect,
   including a copied-store native task. Keep unit/compiled-export tests too;
   `pip check` is not a replacement for either kind of execution.
3. **Rerun this acceptance trial after the fix.** Require both versions' held-out
   business cases and real old/new flow isolation to pass before revisiting PyPI.
4. **Keep Python support explicit.** This experiment covers only 3.14.8. The
   frozen package declares `>=3.12,<3.15`; it does not establish Python 3.15
   support or retest every declared interpreter. Resolve the latest-Python
   support expectation separately rather than widening metadata without tests.

No storage service, API server, registry, or larger architecture change is needed
to address the observed blocker.

## Preserved evidence

All paths below are relative to the gitignored local trial directory:
`.artifacts/blind-acceptance/2026-10-21/`. These files are preserved locally;
they are **not** included merely by sharing this Markdown report through Git.

| Evidence | Location |
| --- | --- |
| Frozen inputs, wheel/doc/install hashes | `infrastructure/freeze.json`, `infrastructure/provenance.json` |
| Installation logs and dependency snapshots | `infrastructure/install-{author,consumer}.log`, `infrastructure/{author,consumer}-freeze.txt` |
| Author briefs, results, observations | `author/BRIEF.md`, `author/author-handoff*.json`, `author/author-observations*.md` |
| Preserved V1/V2 author projects and candidates | `sealed/author-project-v1/`, `sealed/author-project-v2/` |
| Copied published releases | `handoff/release-store/` |
| Consumer results and project | `consumer/consumer-result*.json`, `consumer/consumer-observations*.md`, `consumer/order-consumer/` |
| Recorded commands and stdout/stderr | `{author,consumer,evaluation}/evidence/commands.jsonl` and adjacent labeled files |
| Final independent acceptance results | `evaluation/final_acceptance.json`, `evaluation/results-final-{v1,v2}/report.json` |
| Held-out contract and verifier | `evaluation/contract.json`, `evaluation/fixtures.json`, `evaluation/verify_published_flow.py` |
| Plain-Prefect control and diagnosis | `infrastructure/prefect_baseline.py`, `infrastructure/prefect-baseline.stderr`, `infrastructure/runtime-diagnosis.json` |
| Source isolation and V2 transfer | `infrastructure/source-isolation-v1.json`, `infrastructure/v2-handoff.json` |
| Final provenance, integrity, and pin audit | `infrastructure/final-audit.json` |

There are 60 author, 25 consumer, and 5 independent-evaluator recorder entries.
These include discovery, validation, and repeated diagnostics, not just builds.
The expected overwrite rejection (`p2_005_expected_reject_v1_overwrite`, exit 2)
counts as successful immutability evidence. One author handoff JSON check used
the wrong working directory and was retried; it is not a framework failure.

The evaluation harness was corrected to preserve output directories, report
infrastructure errors correctly, and avoid treating an arbitrary exception as
successful invalid-input validation. Earlier attempt outputs remain available.
The author removed one temporary comparison script after its failed attempt;
its recorded command and output survive. Consequently this is not a complete
filesystem-operation trace. Historical author paths in logs now refer to the
preserved `sealed/` snapshots, not an active author working directory.

The final audit passed: original tracked repository files, frozen public docs,
wheel, installed Weavem files, dependency version snapshots, and original V1
release bytes are unchanged. All six published manifests' payload hashes and
sizes match, both native payloads are ELF files, and flow pin digests match the
selected task manifests. These are integrity checks, not sandbox guarantees.

**Repository change:** this report only. Trial application code and verification
scripts live under the preserved gitignored trial directory. No framework fix,
dependency change, cleanup, commit, push, or PyPI publication was performed.
