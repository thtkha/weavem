# Cache-tolerant releases: acceptance results

> **Historical report.** The results below describe the cache-fix candidate,
> before the Prefect 3.9.0/Python 3.15 verification. Its final Python-support
> blocker is superseded by [current compatibility evidence](release-readiness-2026-10-26.md).
> Original results and artifacts remain preserved.

**2026-10-21 — passed.** Published flows now survive ordinary Python bytecode
generation. The complete store, including caches, was copied unchanged to a
fresh consumer and used successfully. No cache cleanup, filtering, corrected
handoff, or consumer-side native rebuild was needed.

This resolves the handoff problem found in the
[previous acceptance rerun](runtime-compatibility-acceptance-2026-10-21.md).
Earlier reports, failed handoffs, and environments remain preserved.

## Behavior change

A released flow may contain its manifest, its named payload, and an optional
`__pycache__` directory. That directory may be empty or contain only direct,
regular, non-symlink `.pyc` files.

The loader never reads or executes those cache bytes. It still compiles the
checksum-verified source directly. Even a timestamp-valid cache containing
different executable code cannot replace the verified payload.

Everything else remains strict:

- Unexpected artifact entries, nested cache directories, non-`.pyc` cache files,
  symlinks, and other non-regular cache entries are rejected.
- Manifest validation, payload hash/size, interpreter/platform compatibility,
  exact task pins, and invocation-time revalidation remain enforced.
- Unchanged publication remains idempotent; changed implementations cannot
  overwrite an existing version.
- Errors distinguish unexpected entries, invalid cache layouts, missing/unsafe
  payloads, and payload corruption. The exception remains `IntegrityError`.

No schema, public API, or CLI was added. Task loading already tolerated caches;
its behavior was not changed. The [artifact contract](artifact-contract.md)
documents the flow-specific rules. Publication still copies manifest/payload
pairs; subsequent distribution can copy the whole cache-bearing store unchanged.

## Regression and installed-wheel checks

Seven focused runtime tests were written before the fix. Their pre-fix failures
and post-fix successes are retained. They cover generated and empty caches,
poisoned and invalid cached bytes, candidate/release publication, idempotence,
corruption, unexpected files, missing/unsafe payloads, and invalid cache layouts
including broken links and a FIFO.

The installed-wheel release gate now runs `compileall` over the entire published
store after each version is published. It verifies that each flow really has a
cache, copies the store without exclusions, compares the complete copied file
snapshot, and executes both versions through normal Prefect orchestration.
Its V1-preservation check compares exact snapshots under the original release
roots, detecting additions as well as changed or missing files.

| Fresh wheel installation | Full suite | Installed-wheel gate |
| --- | --- | --- |
| Python 3.12.3 | 113 passed, no skips | Passed, 32 recorded commands |
| Python 3.13.16 | 113 passed, no skips | Passed, 32 recorded commands |
| Python 3.14.8 | 113 passed, no skips | Passed, 32 recorded commands |

That is **339 test passes** across the matrix. All three environments also passed
`pip check` and native doctor. The gate checks actual native ELF payloads,
conflicting publication refusal, and real old/new flow results—not `.fn`
substitutes. Its expected publication-conflict exit is a successful negative test.
Python AST, workflow YAML/Bash syntax, and whitespace checks passed. Independent
code review approved the cache behavior and strengthened snapshot check; no LSP
diagnostics tool was available.

## Fresh author-to-colleague trial

New author, consumer, and acceptance-test agents received public human-facing
docs and installed wheels without the earlier conversation. Framework source
inspection and package changes were prohibited. The author was explicitly asked
to run `python -m compileall -q .` from the whole project root before each handoff,
retain the caches, and rerun the actual published flow afterward.

The author created four tasks—parse orders, native line-total calculation,
summarize customers, and write the report—and one flow, `orders.report`.
The native task is `orders.line_total`.

| Journey | Actual result |
| --- | --- |
| Author V1 editable and published pipeline | Correct summary and CSV; published flow still worked after project-wide `compileall` |
| Complete V1 handoff | All 14 files copied, including bytecode caches; original author working path removed from its location |
| Consumer published V1 report | Two orders, total 800 cents, correct CSV |
| Consumer's own normal flow reusing native V1 | Quantity 2 × price 350 → 700 cents, without compiling |
| Upgrade | Changed V1 candidate rejected; native V2 and flow V2 published with explicit pins |
| Author V2 after project-wide `compileall` | Correct three-order total of 875 cents: V1's 575 plus 100 per order |
| Complete V2 handoff | 19 files, including both flow caches; only five new V2 files added, exact V1 snapshot unchanged |
| Consumer keeps V1 and selects native V2 separately | Normal flows returned 700 for V1, 800 for V2, and 100 for a zero-priced V2 order |
| Consumer runs both published flows after the upgrade | V1 still returned 800 cents; V2 returned 1000 cents, with matching CSVs |

For parallel development, the coordinator supplied an identical V2 working copy
at a different author path while the original V1 path stayed absent. The consumer
was prohibited from accessing any author workspace. Both working projects were
then preserved under `sealed/`. This was source isolation by procedure, not a
filesystem security sandbox.

The independent tester used the unchanged business verifier, public `load_flow`,
and actual returned Prefect Flow calls against the **same raw handoff store**:

| Business acceptance | Passed | Failed/errors |
| --- | ---: | ---: |
| Initial V1, zero handling fee | 10 | 0 |
| V2, 100-cent fee per order | 10 | 0 |
| V1 again after both versions were present | 10 | 0 |

The valid cases check normalization, sorted customer aggregation, header-only
input, and integers larger than 64 bits. Seven invalid-input cases each require
a useful `ValueError` and preservation of an existing output file. These checks
passed in all three runs. V2 applied the fee, including on a zero-priced order;
V1 retained its original behavior after the upgrade.

Sandbox-denied loopback attempts are retained as environment failures. Authorized
reruns passed; startup failures were never counted as business-case successes.

## Evidence and limits

The frozen wheel is `weavem-0.1.0-py3-none-any.whl`, SHA-256:
`aa1600c6d0720d3329d05527e03a78727d669e7f444eab9b06b9f0f43842f98a`.
It represents the uncommitted compatibility/cache changes on base commit
`9b9a49f95a82effa4a8f2ba12ae250e5a21da757`; the hash, not the unchanged package
version alone, identifies this candidate.

Local gitignored evidence:

- `.artifacts/cache-tolerance/2026-10-21/verification-summary.json` — matrix,
  runtime versions, executed-script hash, and static checks.
- The same directory's `logs/regression-before.log`, `logs/regression-after.log`,
  `logs/full-{12,13,14}.log`, and `installed-smoke-{12,13,14}/result.json` —
  regression-first and installed-wheel evidence.
- `.artifacts/blind-acceptance/2026-10-21-cache-tolerance/` — frozen public docs,
  wheel, separate author/consumer environments, and complete unfiltered handoff.
- Its `author/author-handoff*.json`, `consumer/consumer-result*.json`, actor
  observations, and `*/evidence/commands.jsonl` — developer journeys and commands.
- Its `evaluation/final_acceptance.json` — the three independent 10-case runs,
  including outputs, errors, and exact pin/version behavior.
- Its `infrastructure/source-isolation-v1.json`, `v1-release-hashes.json`,
  `v2-handoff.json`, and `final-audit.json` — source-path isolation, full-file
  transfer checks, frozen-input integrity, cache validation, and pin digests.

This is one Linux x86-64 WSL2 host with fresh Python environments, not multiple
machines, an independent human study, or a performance benchmark. Filesystem
permission/read failures can still surface as `OSError`; they remain fail-closed.
Bytecode tolerance is not a sandbox or publisher-authenticity guarantee.

**Conclusion:** the tested folder-sharing footgun is fixed without weakening
payload integrity or requiring another user command. Python 3.15 support remains
outside this change and still blocks the latest-Python release requirement.
GitHub Actions has not been triggered remotely. No cleanup, commit, push, or PyPI
publication was performed. Sharing this report alone does not share the local
gitignored evidence.
