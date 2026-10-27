# Native developer simulation: build locally, then share `.so` tasks

> **Historical record — not current instructions.** Preserved for the project owner and retrospective review. Versions, pending work, and commands below describe the recorded revision. See the [history index](index.md) for context and the [user documentation](../../users/index.md) for current usage.

**Verdict: native task authoring and folder-based sharing work. The next work
should improve native setup and release confidence—not add a storage server.**

**Historical snapshot:** subsequent managed-native work supersedes the setup and
compiled-test limitations below; see [native authoring](../../users/native-authoring.md). The
recorded results remain unchanged.

This replaces the previous Python-only simulation. That workspace was deleted
at the user's request. This is a new executed journey with fresh author and
recipient environments, not a proposed workflow. An agent played both developers;
this is not an independent human usability study.

## Straight pros and cons

| Pros — demonstrated | Cons — observed or explicit limits |
| --- | --- |
| Normal installation now includes pinned Cython and setuptools. No native extra is required. | Every consumer also installs those tools: approximately 21 MB of recorded package files here. |
| Both task releases are real ELF `.so` files, loaded by Python's `ExtensionFileLoader`. | Compilation still needs a C compiler and matching Python headers. Missing headers produce a raw compiler error, not helpful setup guidance. |
| Local source edits changed the next native flow result without a publication or version bump. | Native local execution compiles source. Local runs took about 11–18 seconds including Prefect startup; no speed advantage was demonstrated. |
| A separate recipient ran the flow and reused one native task without author source or compilation. | Verified on the same Linux x86_64 host and CPython 3.12 only. This does not establish portability across Linux distributions, Python ABIs, or architectures. |
| Copying one release folder was sufficient for these tasks with no extra dependencies; no registry, GitHub, or warehouse was needed. | Task-specific Python packages and native shared libraries must be provisioned separately. We copied the entire small store; selective dependency export remains unresolved. |
| Build candidates, published releases, and editable source stayed separate. Premature flow release was rejected. | Publication remains several explicit build/publish/pin commands, with candidate paths extracted from JSON. |
| Republishing the original native candidate succeeded, and an incompatible overwrite was blocked. | Rebuilding unchanged source produced different binary bytes. Publishing that rebuild under the same version failed; source identity alone does not make native builds reproducible. |
| The recipient received compiled task implementations, not author task `.py` files. | The flow remains readable Python. Native binaries are not secrecy guarantees: `strings` exposed build-directory paths in both binaries. |
| Tests, candidate integrity checks, and real recipient executions passed. | Task build runs source tests before compilation and then an import/callability smoke check. It does not rerun the whole task test suite against the compiled export. |
| Private wheel installation works. | Public `pip install weavem` still failed: no matching distribution. The exact public-package onboarding story remains blocked. |

### What I recommend next

1. **Keep the default native Python dependencies.** Implemented in this change.
   The small install-size cost is reasonable for an opinionated authoring framework.
2. **Make native prerequisites understandable before compiling.** Add an explicit
   native environment check with actionable compiler/header diagnostics. Do not
   silently run privileged OS package installation from pip or Weavem.
3. **Strengthen native release verification.** Run the authored behavioral tests
   against the compiled export, not only the Python source. Define whether build
   paths/debug information should be removed from distributed binaries and whether
   reproducible native builds are required. Until then, retain and promote the
   original candidate rather than rebuilding it for each destination.
4. **Choose a supported distribution route.** A documented private wheel is
   sufficient for colleagues now. Public PyPI publication is a separate decision.
5. **Then reduce release/handoff friction.** Improve candidate selection and
   eventually export a selected flow together with its pinned tasks. Defer RustFS
   until a real multi-user storage need exists.

If the immediate goal is **private reuse among developers on a standardized
Linux/Python environment**, this approach is viable now with documented setup.
If the goal is **any colleague, any laptop, one command, no build knowledge**,
this version is not ready. If the goal is **speed**, benchmark a representative
workload first; producing a `.so` is not evidence of faster application execution.

## Execution record

| Field | Value |
| --- | --- |
| Status | Verified |
| Owner | Weavem maintainer via the repository below |
| Escalation | [Weavem issues](https://github.com/thtkha/weavem/issues) |
| Last verified | 2026-10-09 |
| Last executed | 2026-10-09, local Linux x86_64, CPython 3.12, Europe/Helsinki |
| Applies to | Uncommitted `weavem-v1` working tree; package version `0.1.0` |
| Risk | Low — synthetic data, local stores, no production services |
| Expected duration | Allow 10–20 minutes plus downloads and example authoring |
| Change record | Replacement simulation plus default native dependency contract; no commit/push |

> **Verification claim:** the native local-wheel journey passed end to end.
> Public installation failed. OS headers were supplied explicitly; this was not
> a zero-prerequisite install. The flow itself was not compiled.

## Purpose and scope

The developer wants to create a useful project, develop against local source,
build native task releases into a local folder, and later give those releases to
someone else. Success requires the recipient to execute and reuse them without
the original author project or a compilation step.

The sample has two tasks: normalize a support message and classify it into a
`billing` or `general` queue. One flow combines them. It is a toy classifier,
not production business logic or a performance benchmark.

Out of scope: remote storage, real secrets, another machine, offline installation,
untrusted execution, distributed flows, and cross-platform native packaging.

## The developer's journey

### “I install Weavem.”

A fresh public-index attempt returned:

```text
ERROR: Could not find a version that satisfies the requirement weavem (from versions: none)
ERROR: No matching distribution found for weavem
```

We built a wheel from the current working tree and installed it normally into
separate `author-env` and `recipient-env` environments. Neither was editable;
no `PYTHONPATH` made framework source available to the simulation. Dependencies
were downloaded independently. Both environments passed `pip check`.

This host lacks working `ensurepip`, so fresh environments used
`python3.12 -m venv --without-pip` followed by the retained upstream
`get-pip.py` bootstrap file. No old environment was reused.

**Change made before this run:** `pyproject.toml` now requires
`Cython==3.3.0` and `setuptools==84.0.0` alongside Prefect. The old `[native]`
extra remains an empty compatibility alias. A plain wheel install supplied both
packages without a separate install command. Two packaging regression tests lock
this contract.

Installed wheel: `weavem-0.1.0-py3-none-any.whl`, SHA-256:

```text
85891b13306e6334025dfdd7794f43b4d73e78b490b6b2d6a16e085c59406291
```

The framework wheel is Python; it builds platform-specific task `.so` releases.
The source base is `bb9fdf925d88ba689ba5ec8141563c31244d0f2b` **plus uncommitted
changes**. The exact wheel and source snapshot are retained; that commit alone
is not the tested version.

### “I create a project and choose native tasks.”

From the new simulation root, then the author directory:

```bash
weavem project new author
cd author
weavem task new tasks/normalize --backend cython
weavem task new tasks/classify --backend cython
weavem flow new triage
weavem task use normalize --path tasks/normalize
weavem task use classify --path tasks/classify
```

The implementation, metadata, and tests were edited before the bindings were
created. The transcript above groups the CLI actions; the recorder preserves
that intervening file-edit sequence. Native support is a default **installation
capability**, not a silent change of backend: these tasks explicitly select
`cython`. `task new` without that flag still defaults to Python.

Both task metadata files use version `1.0.0`, export `run`, source
`implementation.py`, and no extra runtime dependencies. Their IDs are
`support.normalize` and `support.classify`. The flow declares both aliases and
ID `support.triage`, version `1.0.0`.

```text
author/
├── weavem.toml
├── tasks/
│   ├── normalize/       # task.toml, implementation.py, tests/test_task.py
│   └── classify/        # same structure; backend = "cython"
├── flows/              # triage.py, triage.toml, __init__.py
└── tests/flows/triage/test_flow.py
```

Task scaffolds still start with `double` placeholder code. We replaced it, rather
than treating generated boilerplate as a finished application. Exact original
scaffolds and authored files are retained.

### “Validate and test pass. Why does build fail?”

The source task checks passed, but the first native build deliberately ran
without supplying headers:

```bash
weavem task build tasks/normalize
```

It exited `2` with:

```text
fatal error: Python.h: No such file or directory
```

Cython and setuptools were installed correctly. This host had a compiler but
no installed Python development headers. That is an OS prerequisite, not a
missing Python dependency.

For this experiment only, we downloaded Ubuntu's matching
`libpython3.12-dev=3.12.3-1ubuntu0.17` package, extracted it beneath the simulation's
`bootstrap/headers/`, and set the author's `CPATH` to its Python and parent include
directories. No system packages were installed. The exact setting is in
`logs/20-author-build-environment.json`.

This local extraction is a recorded environment workaround, **not** a proposed
Weavem package-manager feature. Normal author machines should provision a compiler
and matching development headers through their supported OS setup process.

### “I fix my task without publishing.”

The first normalizer lowercased text and collapsed spaces. With
`" Invoice: HELP "`, the colon prevented the classifier from matching `invoice`:

```json
{"text": "invoice: help", "queue": "general"}
```

We changed the local normalizer and added a punctuation regression test:

```python
import string

def run(text: str) -> str:
    return " ".join(word.strip(string.punctuation) for word in text.lower().split())
```

The classifier remained:

```python
def run(text: str) -> str:
    return "billing" if "invoice" in text.split() else "general"
```

The flow calls the two aliases and returns the cleaned text and selected queue.
Running the local flow again returned:

```json
{"text": "invoice help", "queue": "billing"}
```

No explicit build, publication, or version bump was needed. Unlike Python-only
source execution, native local execution did perform compilation internally.
Flow unit tests used `.fn` and patched task wrappers as in the authoring guide;
actual flow commands exercised Prefect orchestration.

### “I publish native releases to my own folder.”

Trying to build the flow while its tasks were local failed immediately:

```text
weavem: flow task normalize is local; publish it and select its exact release first
```

We built each task, read its candidate `root` from the CLI's JSON output,
published it to `releases/`, and selected its exact version. Then we built and
published the flow to the same folder. From the author directory, the equivalent
shell sequence is:

```bash
NORMALIZE="$(weavem task build tasks/normalize | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
weavem task publish "${NORMALIZE}" --to releases
weavem task use normalize --release support.normalize==1.0.0 --from releases
CLASSIFY="$(weavem task build tasks/classify | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
weavem task publish "${CLASSIFY}" --to releases
weavem task use classify --release support.classify==1.0.0 --from releases
TRIAGE="$(weavem flow build triage | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
weavem flow publish "${TRIAGE}" --to releases
```

`NORMALIZE`, `CLASSIFY`, and `TRIAGE` are candidate paths returned by their builds.
The recorder ran each CLI command separately and parsed its JSON in Python;
these shell substitutions present the same sequence for a human reader.

```text
author/
├── tasks/                       # editable source, still present
├── flows/
├── tests/
├── weavem.toml                  # now exact release bindings and manifest hashes
├── .artifacts/                  # retained unpublished candidates
└── releases/
    ├── support.normalize/1.0.0/cpython-312/  # manifest.json + native .so
    ├── support.classify/1.0.0/cpython-312/   # manifest.json + native .so
    └── _flows/support.triage/1.0.0/cpython-312/ # manifest.json + Python flow
```

Native evidence:

| Release | Payload size | Verification |
| --- | ---: | --- |
| `support.normalize==1.0.0` | 365,664 bytes | ELF header, `.so` suffix, native loader, expected output |
| `support.classify==1.0.0` | 192,616 bytes | ELF header, `.so` suffix, native loader, expected output |

Each task candidate contained exactly its manifest and native payload. The flow
manifest pinned both task releases. Running the published flow returned the
correct billing result. Republishing the identical flow candidate succeeded.

After the handoff, we also retried the **original native task candidate**: it
published successfully. Rebuilding the unchanged normalizer under the preserved
author directory kept the same source digest but produced a different binary
hash. Publishing that new candidate as `support.normalize==1.0.0` was rejected:

```text
weavem: task version already published with different bytes: support.normalize==1.0.0
```

The existing release was unchanged. This is correct immutable-store behavior,
but it means “build again from the same source” is not a safe publication retry.
The original and rebuilt candidates are both retained. Embedded build paths are
visible; the experiment did not isolate every cause of binary differences.

### “Can my colleague use this without my project?”

We created `recipient/` using the separately installed CLI and copied the complete
`author/releases/` folder to `recipient/task-store/`. All six files matched by
SHA-256. We renamed the original project to `author-preserved/`, making its old
absolute path unavailable without deleting the new evidence.

These tasks declare no extra Python dependencies and need no additional native
libraries beyond this host's runtime. Release folders do not install dependencies:
real applications can require separately provisioned Python packages or OS/shared
libraries on the recipient. This simulation did not test that provisioning.

The recipient had no header include configuration. Its `CC` and `CXX` variables
pointed to `/compiler-intentionally-unavailable`, deliberately making ordinary
compilation fail. This is a build-path check, not a security sandbox or proof
that the OS compiler was physically uninstalled.

From the recipient project:

```bash
weavem task list --json
weavem flow list --json
weavem flow run support.triage==1.0.0 --release \
  --params '{"text":" INVOICE: Where is it? "}'
```

Returned:

```json
{"text": "invoice where is it", "queue": "billing"}
```

The recipient then bound the published normalizer under a new alias:

```bash
weavem task use clean_message --release support.normalize==1.0.0
weavem flow new preview
```

We authored a new local `preview` flow that returns `"Preview: "` plus the result
of `task("clean_message")`, updated its sidecar, and replaced the scaffold test.
Its test passed. Running it with `" HELLO, colleague! "` returned
`"Preview: hello colleague"`.

An independent direct import checked both received binaries using
`ExtensionFileLoader` and called their exports successfully. The recipient's
`tasks/` source directory stayed empty. No native build was needed there, although
the default installation now includes Cython and setuptools for every recipient.

## Orientation and evidence

New retained workspace, relative to the Weavem repository:
`.artifacts/simulation/native-2026-10-09/`. It is gitignored and will not accompany
a clone. This report is versioned documentation; raw evidence remains local.

Important contents:

- `author-preserved/`: authored source, tests, release folder, candidates.
- `recipient/`: copied store and newly composed preview flow.
- `author-env/`, `recipient-env/`, `builder/`: isolated environments.
- `distribution/`: exact installed wheel.
- `framework-source/`, `framework-pyproject.toml`: tested framework snapshot.
- `scaffold-original/`, `normalize-before-edit.py`, `local-bindings.toml`: intermediate states.
- `simulate.py`: exact fixture edits, commands, assertions, and recording logic.
- `check-native-rebuild.py`: original-candidate retry and unchanged-source rebuild check.
- `bootstrap/`: pip bootstrap and locally extracted header package.
- `logs/`: command records, timings, failures, checksums, dependency footprint.
- `regression/`, `author-prefect/`, `recipient-prefect/`, `tmp/`: verification state.

Historical candidate paths in `candidates.json` name `author/`. Their current
location is the corresponding path under `author-preserved/`.

## Prerequisites and inputs for reviewing this run

Use Bash on the original Linux x86_64 machine, with access as the workspace owner.
Retained virtual environments require CPython 3.12 at their original locations.
No credentials or remote account are needed. Flow execution needs local-loopback
socket permission; the agent ran those commands outside its socket-restricted
sandbox with approval.

`SIM` is the absolute simulation path, derived below from the repository root.
The recheck uses the already installed recipient environment, not a new install.
For a fresh authoring exercise, follow the linked authoring guide and the OS
prerequisites in the README; this dated record includes a machine-specific header
workaround rather than a universal Linux bootstrap script.

## Safety and stop conditions

These releases are trusted synthetic code. Native code can execute arbitrary
instructions: checksums are not isolation. No production service, public listener,
remote publication, or irreversible state change is involved.

Stop if the wheel checksum differs, the retained workspace is absent, a selected
store is outside this simulation, or a command unexpectedly fails. Keep the
failure evidence. Do not edit published binaries or rerun the recorder over
existing projects to force a pass.

## Preflight checks

From the Weavem repository root:

```bash
SIM="${PWD}/.artifacts/simulation/native-2026-10-09"
test -d "${SIM}/author-preserved" && test -d "${SIM}/recipient"
sha256sum "${SIM}/distribution/weavem-0.1.0-py3-none-any.whl"
cat "${SIM}/logs/acceptance.json"
```

Expect the wheel hash printed earlier, 40 successful recorded commands, three
expected failures, two native tasks, and all boolean acceptance fields true.
Installation/bootstrap commands are counted separately. A mismatch is a stop
condition, not a reason to regenerate the historical evidence.

## Procedure: check the recipient again

### Step 1 — Run the received native-backed flow

**Goal:** Reconfirm that the received release works without author source or a
working configured compiler.

**Run from:** This repository root in Bash, after defining `SIM` in preflight.

**Action:**

```bash
(
  cd "${SIM}/recipient" || exit 1
  unset PYTHONPATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH
  unset WEAVEM_STORE WEAVEM_ARTIFACTS_DIR PREFECT_API_URL PREFECT_API_KEY
  export CC=/compiler-intentionally-unavailable
  export CXX=/compiler-intentionally-unavailable
  export PREFECT_HOME="${SIM}/recipient-prefect"
  export PREFECT_SERVER_ANALYTICS_ENABLED=false
  export PREFECT_LOGGING_LEVEL=WARNING
  export TMPDIR="${SIM}/tmp"
  "${SIM}/recipient-env/bin/weavem" flow run support.triage==1.0.0 --release \
    --params '{"text":" INVOICE: Where is it? "}'
)
```

**Expected result:** Exit `0` and
`{"text": "invoice where is it", "queue": "billing"}`. First recipient execution
took 14.36 seconds; this is startup-inclusive elapsed time, not a benchmark.

**If this fails:** Preserve the output and consult troubleshooting. Do not rebuild
or replace the received binaries as part of this recheck.

**Evidence to retain:** New output without overwriting the original
`logs/46-recipient-run.json`.

**Repeatability:** Safe for these side-effect-free tasks. Each run adds local
Prefect records; arbitrary application tasks do not inherit this retry guarantee.

## Verification

The new simulation passed 40 recorded commands and three intentional rejection
checks: missing headers, unpublished flow dependencies, and different native bytes
under an existing version. Source tests, native
builds, local and published flow executions, copied-store checksums, separate
installation checks, and direct native-loader checks all passed after the
explicit header workaround. Public-index installation failed separately.

The packaging tests assert both default native dependencies and compatibility
of the old empty `native` extra, including the metadata of a freshly built wheel.
An initial full-suite run exposed a test's hardcoded `.artifacts` path when the
artifact directory was redirected. The test now checks the resolved configured
directory and its unchanged contents; no runtime behavior was changed for that fix.
The final complete suite passed **82 tests in 230.784 seconds**; its output is in
`logs/regression-suite-final.log`. The four focused dependency/path tests also
passed. The exact documented recipient command was rerun successfully, strict
documentation lint reported zero findings, relative links resolved, and Python
AST checks and `git diff --check` passed.
No application speedup, cross-machine binary
portability, or complete source secrecy is claimed.

## Rollback and recovery

There is no production state to roll back. The only prior state deliberately
removed was the old Python-only simulation, as requested. The new author project
is preserved under its renamed directory; relative bindings still work there.

Forward recovery: keep a failed attempt and reproduce in a new named workspace
using the authoring guide. Do not overwrite this run. Retry an identical
publication with the existing candidate. For changed bytes, choose a new version
and build again rather than deleting the old release. Logs and candidate paths
can be translated from `author/` to `author-preserved/` without rebuilding.

## Troubleshooting

| Symptom | Diagnosis | Safe next action |
| --- | --- | --- |
| No matching Weavem distribution | `logs/06-public-install.log` | Install the verified private wheel; do not assume PyPI publication occurred |
| `Python.h` missing | `logs/20-missing-headers-build.json` | Provision matching OS headers; Cython installation alone does not fix this |
| Compiler missing | Inspect compiler availability and `CC` | Provision a compiler for authors; do not enable compilation merely to consume a published release |
| Local dependency blocks flow build | Inspect project bindings | Publish the task and select its exact release, then retry flow build |
| Socket permission denied | Prefect cannot start its local server | Use approved loopback access; do not expose a public service |
| Native import fails elsewhere | Check CPython ABI, OS, architecture, and native library requirements | Stop and obtain a compatible release; compatibility beyond this host was not tested |
| Candidate path absent | Old path has the `author/` prefix | Look beneath `author-preserved/`; do not delete or rebuild the release |

## Cleanup

The old `.artifacts/simulation/2026-10-09/` workspace was removed. Its pip bootstrap
file and recorder were reused as inputs, not its environments, releases, or results.
The new native simulation is retained for inspection. No additional cleanup,
commit, or push was performed. Framework and test-runner internal temporary-file
cleanup still occurs normally. No credentials or system packages were changed.

## Ownership and escalation

Use [Weavem issues](https://github.com/thtkha/weavem/issues) for a reproducible
mismatch. Include the wheel hash, platform, command label, selected store,
compiler/header setup, and sanitized stdout/stderr. The repository maintainer
owns follow-up; no infrastructure team or production on-call is involved here.

## References

- [Installation and native prerequisites](../../../README.md#getting-started-after-cloning).
- [Authoring guide](../../users/authoring-guide.md): complete task/flow authoring example.
- [CLI and metadata reference](../../users/reference.md).
- [Artifact contract](../../users/artifact-contract.md).
- [Limitations](../../users/limitations.md).
- [Dependency contract](../../../pyproject.toml).
- [Packaging regression tests](../../../tests/test_packaging.py).
- Native compilation source: `src/weavem/build.py`, `_build_cython` and `build`.

## Document maintenance

The maintainer should rerun a new dated simulation after changing native setup,
compiled testing, ABI support, or distribution. Preserve this record's stated
limitations until new evidence supersedes them. Recheck before applying these
commands to a different wheel. No outstanding storage decision blocks this
local native workflow.
