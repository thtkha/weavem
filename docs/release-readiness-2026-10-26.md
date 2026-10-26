# Compatibility evidence and release readiness

The release-hardening changes were committed and pushed on `weavem-v1` as
`14dfe1e859e4baba13b4d2eb334762bf08e69a9e`, based on commit
`9b9a49f95a82effa4a8f2ba12ae250e5a21da757`. The local results below describe the
candidate before that commit; the GitHub result identifies the tested revision.
The package is still a provisional `0.1.0` candidate, not a public PyPI release.
Wheel checksums distinguish candidates that share that package version.

## Current support boundary

- Standard, GIL-enabled CPython 3.12–3.15 on Linux x86_64 with glibc 2.28+.
- Prefect `3.9.0`, FastAPI `0.143.0`, Cython `3.3.0`, setuptools `84.0.0`,
  and ziglang `0.17.0` are the declared default dependency pins.
- Verified header packs ship for the tested interpreter configurations. Other
  standard distributions need matching bundled signatures or their own complete
  headers; support is not inferred from the version number alone.
- Free-threaded/debug/trace-ref Python, musl, Windows, and macOS are unsupported.
  Native task artifacts require the matching Python minor ABI and platform.

## Completed local matrix: 2026-10-21

The candidate wheel was installed normally, without bypassing Python requirements
or applying an external dependency constraints file.

| Interpreter | Full suite | Install, dependency check, doctor | Installed-wheel gate |
| --- | --- | --- | --- |
| CPython 3.12.3 | 114 passed | Passed | Passed, 32 commands |
| CPython 3.13.16 | 114 passed | Passed | Passed, 32 commands |
| CPython 3.14.8 | 114 passed | Passed | Passed, 32 commands |
| CPython 3.15.0 | 114 passed | Passed | Passed, 32 commands |

That is 456 successful test executions, with no skips. Gate commands include
expected negative cases; success means the observed result matches the expected
return code, not that every command returns zero.

The gate uses the installed distribution, not editable imports. It exercises real
Prefect orchestration, local edits, native task builds and compiled behavioral
tests, immutable publication, bytecode-cache tolerance, copied-store execution,
and separate pinned V1/V2 behavior. It does not substitute direct `.fn` calls for
orchestration. All four lanes recorded the declared dependency versions above.

Wheel SHA-256:
`68e3d3926e755da94ffa954c691f95e57c38a74c35b12715e382ed4210071d04`.

Gitignored evidence: `.artifacts/python315/2026-10-21/` contains
`matrix-results.json`, `logs/full-{12,13,14,15}.log`, the installation/check logs,
and each `installed-smoke-*/result.json`. These are recorded October 21 results,
not a fresh October 26 rerun or GitHub-hosted CI results.

## Fresh verification: 2026-10-26

A new wheel was built from the current checkout and installed with normal pip
dependency resolution in four fresh virtual environments. All four interpreters
listed above passed installation, `pip check`, doctor, **114 tests each with no
skips**, and the isolated installed-wheel gate's **32 commands each**. That is
456 fresh test passes and 128 expected gate outcomes. The gate's provenance
records confirm imports from each environment's `site-packages`, not the checkout.

Doctor selected the bundled packs `cpython-312-3-linux-x86_64`,
`cpython-313-16-linux-x86_64`, `cpython-314-8-linux-x86_64`, and
`cpython-315-0-linux-x86_64` respectively, not interpreter-header fallback.
The installed versions matched the declared pins; the fresh resolver selected
Starlette `1.10.0`. The package payloads in the tested wheel were also compared
byte-for-byte with the current source tree.

Fresh wheel SHA-256:
`e16ccfdd316445dddde4b58fb272deea50c23468499135a0769c6d485362101f`.

The authoritative fresh evidence is
`.artifacts/release-review/2026-10-26/session-current-source/`:

- `verification-summary.json` records the candidate, versions, selected headers,
  and per-lane results.
- `matrix-results.json` retains the successful commands and complete installed
  gate outcomes, including expected negative cases.
- `logs/` and `lanes/` retain build, normal-install, dependency, doctor, test,
  and installed-wheel evidence.

Earlier attempts remain separate under the parent review directory. Initial
installation attempts failed because sandbox DNS could not reach PyPI; those
failures were preserved, not counted as passing tests. The completed rerun used
approved network access and normal dependency resolution. No earlier acceptance
evidence was overwritten.

Static checks also passed: syntax parsing of all seven changed/new Python files,
local Markdown file links, workflow YAML and matrix/latest-stable configuration,
header archive checksums and safe member paths, and `git diff --check`. No
dedicated lint/typecheck configuration is defined for this project; syntax and
manual review are not presented as a substitute for a typechecker.

## GitHub CI: commit 14dfe1e

[Verify Weavem run 40304972425](https://github.com/thtkha/weavem/actions/runs/40304972425)
completed successfully for `14dfe1e859e4baba13b4d2eb334762bf08e69a9e`.
All five jobs passed: Python 3.12, 3.13, 3.14, 3.15, and the separate
latest-stable-Python gate. Each ran wheel installation, native doctor, full tests,
and fresh-environment installed-wheel verification.

This closes the remote-CI gate for that commit only. Later changes, including the
packaging-test follow-up below, need their own CI run before release; the earlier
114-test counts are not results for the follow-up test suite.

## Earlier reports and remaining gates

The [original blind trial](blind-acceptance-2026-10-21.md) failed on runtime
dependency compatibility. The [compatibility repair](runtime-compatibility-acceptance-2026-10-21.md)
fixed execution but exposed a cache-polluted flow handoff failure. The subsequent
[cache-tolerance trial](cache-tolerance-acceptance-2026-10-21.md) passed its raw
folder handoff and 30 independent business cases. Those reports retain their
original versions, failures, and evidence; their old Python 3.15 blocker is not
the current dependency status.

These checks use fresh environments on one Linux x86_64 WSL2 host, not separate
machines or an independent human usability study. They do not establish broader
platform portability, publisher authenticity, sandboxing, comprehensive secret
scanning, or cross-toolchain reproducible native builds.

Independent code review found no blocking defects. Architecture review identified
one non-blocking regression-coverage gap in `14dfe1e`: the wheel packaging test
asserted bundled archives and licenses, but not every matching JSON provenance
record. All four archive/JSON/license sets and archive checksums were manually
verified in that candidate. **Resolved in the local test-only follow-up:** the
packaging test now asserts matching sets, archive references, and checksums
without changing interpreter-header fallback.

Focused packaging verification passed **2 tests on each of Python 3.12.3,
3.13.16, 3.14.8, and 3.15.0**. Each lane built a real wheel and checked its
contents; in-memory fixtures confirmed that missing JSON, archive, or license
files, an incorrect archive reference, and a wrong checksum are rejected.
Logs and `summary.json` are retained under
`.artifacts/header-provenance/2026-10-26/`. This test/docs-only follow-up has not
rerun the full suite or remote CI and is not covered by the earlier GitHub run.

Every release needs passing GitHub Actions, including the latest-stable-Python
gate, for its exact candidate revision. No tag, public publication, or
branch-protection configuration is established by these checks. The test/docs
follow-up does not commit, push, publish, or remove existing artifacts.
