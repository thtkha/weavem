# Native maintenance history

> **Historical record — not current instructions.** Preserved for the project owner and retrospective review. Versions, pending work, and commands below describe the recorded revision. See the [history index](index.md) for context and the [user documentation](../../users/index.md) for current usage.

This page preserves dated maintainer evidence and header-bundle maintenance notes moved out of the author-facing native tutorial. Historical statements describe the revisions and dates named in their text; they are not the current release contract. For supported environments and the current user workflow, see [Native authoring](../../users/native-authoring.md).

## Historical release rules and evidence

The following text is retained from the former native guide. It is historical, including its references to pending automation and earlier commits; use the current release workflow and user docs for present behavior.

### Latest-Python release rule

A Weavem release must install and pass the complete suite plus native environment
check on the **latest stable CPython at release time**. The supported-version CI
matrix alone is not enough. `.github/workflows/verify.yml` includes a separate
`latest-python-release-gate` selecting `3.x`, checking for the newest stable
interpreter, and performing a normal dependency install and tests.

The current pin is `prefect==3.9.0`, retaining `fastapi==0.143.0`. The completed
local 3.12–3.15 matrix resolves the old dependency-metadata blocker; it does not
replace remote CI. Results are recorded in the
[current compatibility evidence](release-readiness-2026-10-26.md), separately
from the dated 3.12–3.14 evidence below.

The workflow passed all five GitHub-hosted lanes for commit `14dfe1e`:
[Verify Weavem run 40304972425](https://github.com/thtkha/weavem/actions/runs/40304972425).
That result covers the tested commit, not subsequent changes. There is no
automated publication job and no claim that repository branch protection has
been configured. Any future publishing job must depend on this gate; maintainers
must not manually waive it while promising latest-stable support.

### Private distribution and verification

For colleagues, distribute a wheel built from the verified revision and its
checksum. Native authoring is included in normal installation; an offline transfer
also needs a wheelhouse for the wheel's declared dependencies. There is no public
package publication in this change.

Current local verification covers CPython 3.12.3, 3.13.16, 3.14.8, and 3.15.0;
see the [current compatibility evidence](release-readiness-2026-10-26.md).

### Earlier validation: 2026-10-12

The earlier implementation was verified in separate CPython 3.12.3, 3.13.16,
and 3.14.8 environments. Its evidence is retained under
`.artifacts/managed-native-work/`, separate from the historical
[native developer simulation](developer-simulation.md). These results describe
that earlier candidate, not the current dependency pins or Python 3.15 support.

Verified on 2026-10-12:

- **90 tests passed on each interpreter** (270 successful test executions).
  Logs: `logs/full-12.log`, `logs/full-13.log`, and `logs/full-14.log`.
- An installed private wheel on Python 3.14 built a native text-normalization
  task, ran its source and compiled behavioral tests, published the candidate,
  and published a flow pinned to that task.
- A separate, freshly installed recipient environment ran the copied release
  store after the author directory was moved. The task loaded from `.so`, no
  `implementation.py` was present in the recipient store, and the actual Prefect
  flow completed with the expected `invoice help` result.
- Both sides used deliberately invalid `CC`, `CXX`, and `CPATH` settings, with
  isolated Python imports: the journey did not depend on the checkout or the
  author's system compiler settings. The recipient did not compile anything.
- `pip check`, Python syntax checks, workflow YAML parsing, and `git diff --check`
  passed. GitHub-hosted CI had not run at that point.

The retained recorder is `installed-journey.py`; its evidence is in
`logs/installed-author.log` and `logs/installed-recipient.log` under the same
artifact directory. The initial matrix attempt found stale installed framework
copies in subprocesses; reinstalling the final wheel resolved that verification
setup issue before the successful complete rerun.

## Maintaining the header bundles

`scripts/prepare-native-headers.py` is a maintainer tool, not something an author
runs. It must run with the target interpreter and consume already verified upstream
archives, original headers, generated `pyconfig.h`, and license text. It checks
archive hashes, normalizes tar metadata, records the runtime configuration, and
preserves header contents. It neither configures a guessed ABI nor downloads
anything. Each bundle records its exact upstream URL and checksum.

New Python support requires an ordinary dependency install, a verified header
source, full tests, installed-wheel author/consumer verification, and an updated
support matrix. Changing `requires-python` alone is not evidence of support.

## References

- [Python 3.15 stable release](https://www.python.org/downloads/release/python-3150/).
- [Prefect package metadata](https://pypi.org/project/prefect/).
- [Zig Python packaging](https://github.com/ziglang/zig-pypi).
- [Python build standalone](https://github.com/astral-sh/python-build-standalone).
- [CPython ABI compatibility](https://docs.python.org/3/c-api/stable.html).
- [Python sysconfig](https://docs.python.org/3/library/sysconfig.html).
