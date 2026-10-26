# Native authoring that owns its build tools

Weavem now supplies a pinned compiler and verified Python headers rather than
expecting authors to assemble a C development environment. For the tested Linux
CPython distributions, installing the Weavem wheel is the setup step: there is no
separate native extra, compiler installation, Docker setup, or build-time download.

**Supported release-candidate environment:** managed builds target standard,
GIL-enabled CPython 3.12–3.15 on Linux x86_64 with glibc 2.28+. The candidate uses
`prefect==3.9.0` and retains `fastapi==0.143.0` for the compatible runtime path.
Normal dependency installation, full tests, native builds, and installed-wheel
checks passed locally on all four interpreter minors on 2026-10-21 and in a fresh
2026-10-26 rerun. See the
[current compatibility evidence](release-readiness-2026-10-26.md) for the matrix
and fresh verification status. Remote CI, including the latest-Python gate, must
also pass before release. Never bypass package Python requirements to advertise
compatibility.

## The author experience

Install a privately supplied wheel or install this checkout using a supported
Python environment. Public PyPI publication has not happened. From the checkout:

```bash
python -m pip install .
weavem doctor
weavem project new my_project
cd my_project
weavem task new tasks/score --backend cython
```

Replace the placeholder implementation, metadata, and tests, then follow the
[authoring guide](authoring-guide.md) to bind, build, and publish. Native selection
is explicit; Python remains the default scaffold backend.

`weavem doctor` is optional. It selects headers, compiles a tiny extension, imports
it in a child process, and reports the compiler/header identity as JSON. Every
native build performs the same check automatically. It never invokes sudo, apt,
a container engine, or a downloader.

## What installation supplies

- `Cython==3.3.0`: translates the task into C.
- `setuptools==84.0.0`: retained as the opinionated Python packaging tool.
- `ziglang==0.17.0`: the bundled C compiler and its Linux target support.
- `prefect==3.9.0` with `fastapi==0.143.0`: the pinned compatible flow runtime.
- Audited compressed CPython header bundles inside the Weavem wheel, with hashes,
  provenance, configuration signatures, and upstream licenses.

The compiler wheel is approximately 101 MB to download. This is an intentional
tradeoff: a larger predictable install instead of requiring users to repair their
OS development environment. Initial installation still needs a package index or
an offline wheelhouse containing **all** dependencies.

Header selection is not based only on the Python version. A bundled pack must
match implementation/minor version, SOABI, minimum patch, and every captured
`pyconfig.h` configuration key in the running interpreter's `sysconfig` data.
The bundle checksum is checked before extraction. A complete interpreter-provided
header set can be used when no pack matches. Missing or mismatched headers produce
an unsupported-distribution message; Weavem does not fabricate `pyconfig.h`.

The bundled header packs cover these source configurations:

| Interpreter | Header origin |
| --- | --- |
| CPython 3.12.3, Ubuntu standard build | Ubuntu `libpython3.12-dev` 3.12.3-1ubuntu0.17 |
| CPython 3.13.16, standard build | Astral python-build-standalone 20261003 |
| CPython 3.14.8, standard build | Astral python-build-standalone 20261003 |
| CPython 3.15.0, standard build | Astral python-build-standalone 20261009 |

The 3.15 manifest records the exact archive provenance, checksum, and configuration
signature; the local four-version matrix exercises this bundle. This is not a
promise for every custom Python distribution. Normal GIL-enabled, non-debug
CPython, Linux x86_64 and glibc 2.28+
are the runtime boundaries. Free-threaded, trace-ref/debug, musl, Windows, and
macOS builds are not supported. Native artifacts remain tied to their Python minor
ABI and platform; a 3.12 `.so` is not upgraded into a 3.14 `.so` by copying it.

## What a native build guarantees

1. Validate metadata and snapshot source and authored tests.
2. Run the authored tests against the Python source.
3. Verify the managed compiler/header combination with a compile/import probe.
4. Compile using the managed compiler, not a caller's `CC`, `CPATH`, or C flags.
5. Copy the same test suite into a separate workspace with **no Python
   implementation file**, load the compiled extension under the source module's
   import name, and run the suite again.
6. Reject failed compiled behavior, payload mutation, empty tests, import failures,
   and detected absolute Weavem build/source paths in the native payload.
7. Create an unpublished candidate only after these checks pass.

Write behavioral tests importing the source module normally, such as
`from implementation import score`. You do not write a second native test suite.
Tests that depend on the implementation being a `.py` file may legitimately fail
against a native module. Additional helper implementation modules are not bundled;
the existing single-module task contract still applies.

`task test` tests source. `task build` verifies both representations for a native
task. A build-time import check alone is no longer considered behavioral proof.
Local source invocation can compile without running tests, preserving the fast
edit/run loop; release build is the mandatory verification boundary.

## Binary and publication policy

Release binaries are built without native debug symbols, with normalized compiler
paths, and scanned for the actual temporary/source directories used by Weavem.
A path match fails the build. This is **not** comprehensive secret scanning: string
literals intentionally placed in your source can still appear in the binary.
Compiled code is neither encryption nor an execution sandbox.

Repeated builds from identical inputs are tested for identical output on the same
supported environment. Cross-machine, cross-header, or cross-toolchain bit-for-bit
reproducibility is not promised. Compiler, header selection, target, and debug
policy are recorded in the task manifest's build facts.

Keep and promote the original candidate. `publish` does not rebuild it and still
rejects different bytes under an existing release identity. Recipients need no
compilation, but must supply task-specific Python dependencies and required native
runtime libraries themselves.

## Latest-Python release rule

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

The workflow is prepared locally, not pushed or executed on GitHub. There is no
automated publication job and no claim that repository branch protection has been
configured. Any future publishing job must depend on this gate; maintainers must
not manually waive it while promising latest-stable support.

## Private distribution and verification

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
  passed. GitHub-hosted CI has not run yet.

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
