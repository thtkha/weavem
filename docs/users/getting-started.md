# Install Weavem and check your environment

[Documentation index](index.md) · Next: [your first project](authoring-guide.md)

Use this guide to install **Weavem 0.1.0a2** for application development, without
cloning its source. By the end, you will have an isolated Python environment,
a verified installation, and a workspace ready for the tutorial.

## Before you start

You need:

- Bash on Linux x86_64 with glibc 2.28 or newer.
- Standard GIL-enabled, non-debug CPython 3.12–3.15, with `venv` and pip support.
  Windows, macOS, ARM, musl/Alpine, free-threaded, and debug builds are outside
  this release's supported lane. See [limits](limitations.md).
- Write access to your workspace, temporary/build directories, and release store.
- Permission for Prefect to start a local loopback service. No hosted Prefect
  account is needed for this tutorial.
- Access to PyPI for Weavem and its dependencies, or a trusted release wheel
  with a complete compatible offline wheelhouse.

Check which interpreter `python3` selects:

```bash
python3 --version
python3 -c 'import platform, sys; print(sys.implementation.name, platform.machine(), platform.libc_ver())'
```

Expected: CPython 3.12–3.15, `x86_64`, and glibc 2.28+. If your intended interpreter
has another command, use it instead of `python3` when creating the environment.
Do not bypass package compatibility checks to use a newer or unsupported Python.

## 1. Create a workspace

Create a new workspace from a writable parent directory:

```bash
mkdir weavem-workspace
cd weavem-workspace
mkdir downloads
```

If the name already exists, choose another directory rather than overwriting an
existing project. Keep this terminal open for the following steps.

## 2. Create and install into an environment

**Publication status:** the public promotion of `0.1.0a2` is pending. Use the
GitHub-wheel alternative below until the maintainer confirms the PyPI upload.
The public instructions apply after publication; they are not a claim that an
upload has already happened.

Run these commands from `weavem-workspace`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip --version
```

Expected: pip resolves to `.venv`. If venv creation fails or pip is absent, follow
[environment recovery](troubleshooting.md#python-environment). Do not switch to
global `sudo pip` installation.

### Install from PyPI after publication

```bash
python -m pip install --pre 'weavem==0.1.0a2'
python -m pip check
python -c 'from importlib.metadata import version; print(version("weavem"))'
```

Expected: no broken requirements and version `0.1.0a2`. The explicit version pin
selects this alpha rather than an unrelated later release. No GitHub account,
Weavem account, source clone, registry, or Docker installation is needed.
If pip cannot find this version, stop and check the
[PyPI release page](https://pypi.org/project/weavem/0.1.0a2/); do not substitute a
similarly named package or bypass Python compatibility checks.

The cross-project tutorial creates a second environment using the same wheel.
Retain a copy in this workspace:

```bash
python -m pip download --no-deps --only-binary=:all: --pre \
  --dest downloads 'weavem==0.1.0a2'
export WEAVEM_WHEEL="$PWD/downloads/weavem-0.1.0a2-py3-none-any.whl"
test -f "$WEAVEM_WHEEL"
```

`WEAVEM_WHEEL` is the absolute path used by the tutorial's consumer setup; it is
not a Weavem configuration setting. The PyPI upload uses the same bytes as the
original GitHub `0.1.0a2` wheel. Its embedded README still describes the historical
private release; these current repository instructions explain public distribution.

### Alternative: install the verified GitHub wheel

Open the [0.1.0a2 release](https://github.com/thtkha/weavem/releases/tag/v0.1.0a2)
and save these two assets into `weavem-workspace/downloads/`:

- `weavem-0.1.0a2-py3-none-any.whl`
- `SHA256SUMS`

While the repository remains private, GitHub requires repository access; obtain
the files from the maintainer if necessary. After the repository becomes public,
these assets can be downloaded anonymously. Do not treat that visibility change
as proof that PyPI publication has also finished.

With `.venv` active, run:

```bash
(cd downloads && sha256sum -c SHA256SUMS)
export WEAVEM_WHEEL="$PWD/downloads/weavem-0.1.0a2-py3-none-any.whl"
python -m pip install "$WEAVEM_WHEEL"
python -m pip check
python -c 'from importlib.metadata import version; print(version("weavem"))'
```

Expected: `weavem-0.1.0a2-py3-none-any.whl: OK`, no broken requirements, and
version `0.1.0a2`. Stop on a mismatch or missing asset. Obtain a fresh copy from
the same trusted release; never edit the manifest to make verification pass.
Checksums detect changed bytes, not publisher authenticity.

### Offline installation

An administrator must supply a wheelhouse compatible with this interpreter and
platform containing Weavem **and every transitive dependency**. With
`WEAVEM_WHEEL` set, use
`python -m pip install --no-index --find-links /absolute/path/to/wheelhouse "$WEAVEM_WHEEL"`,
replacing the illustrative path with the supplied wheelhouse. The consumer setup
later in the tutorial needs the same offline options, or pip's corresponding
`PIP_NO_INDEX` and `PIP_FIND_LINKS` environment settings.

## 3. Keep tutorial state local

This tutorial is local-only. Run it in a fresh terminal/environment without
organization-specific Prefect profiles or server configuration. Do not unset
production settings in a shell being used for unrelated operational work.
From `weavem-workspace`:

```bash
unset PREFECT_API_URL PREFECT_API_KEY PREFECT_PROFILES_PATH
unset WEAVEM_STORE WEAVEM_ARTIFACTS_DIR
mkdir -p .artifacts/prefect .artifacts/tmp .artifacts/pip-cache
export PREFECT_HOME="$PWD/.artifacts/prefect"
export PREFECT_SERVER_ANALYTICS_ENABLED=false
export TMPDIR="$PWD/.artifacts/tmp"
export PIP_CACHE_DIR="$PWD/.artifacts/pip-cache"
```

These settings put Prefect state and temporary files in this workspace and disable
server analytics. Existing Prefect configuration can override other settings; use
a clean shell if you previously customized Prefect. A task can still contact
external services if its code does so. Nothing here sandboxes task execution.

Weavem's own work directory remains each project's `.artifacts/` by default.
Published releases go into each project's `task-store/`, not into Prefect's state
folder. Both are configurable through the [reference](reference.md#configuration).

## 4. Verify the native environment

```bash
weavem --help
weavem doctor --work-dir .artifacts/native-check
```

Expected: help lists the project, task, flow, and doctor commands; doctor returns
JSON identifying the compiler, headers, Python version, and target after compiling
and importing a tiny native extension. It installs no OS packages and needs no
system compiler on supported configurations. Stop on failure and consult
[native troubleshooting](troubleshooting.md#native-builds).

The installed tools include the native compiler and header bundles. Your own
tasks' extra Python dependencies, native libraries, service credentials, and data
are **not** automatically bundled or provisioned.

## 5. Continue to a working project

Stay in `weavem-workspace` with `.venv` active and `WEAVEM_WHEEL` set.
Continue to [develop, publish, and reuse](authoring-guide.md). That guide runs
real code with expected results; `doctor` alone does not test your application.

Your starting layout is:

```text
weavem-workspace/
├── downloads/             # wheel and SHA256SUMS
├── .venv/                 # installed author environment
└── .artifacts/            # local state, caches, and native check work
```

In a new terminal, return to this directory, activate `.venv`, and repeat the
variable assignments from steps 2 and 3. Virtual environments and shell variables
are not portable: a colleague recreates an environment rather than copying yours.

No cleanup is required to continue. Preserve downloaded release files and
published stores; remove only work you deliberately no longer need. If setup
fails halfway, keep the error output and files for diagnosis. Ask your Weavem
maintainer for help with the package version, Python version, command, and error
text—never include credentials or private data. GitHub users can report a
[repository issue](https://github.com/thtkha/weavem/issues).
