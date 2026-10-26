# Weavem

Weavem is a local-first framework for developing reusable **tasks** and composing
**flows** with Prefect. Develop against source, then deliberately build and publish
immutable releases for other projects.

- **Tasks** are functions with metadata, tests, and Python or native implementations.
- **Flows** compose tasks and application logic using Prefect's execution model.
- **`task-store/`** holds published tasks and flows available to a project.
- **`.artifacts/`** holds unpublished candidates and disposable build/test work.

A company can share an extracted release folder privately. GitHub, a central
registry, and the author's source checkout are not required.

This branch implements the next developer workflow; it is still a provisional 0.x
API, not a stable 1.0 release. The supported release lane is **standard,
GIL-enabled CPython 3.12–3.15 on Linux x86_64 with glibc 2.28+**. A release
may claim that lane only after its ordinary dependency install, native build,
and latest-stable-Python CI gate have passed; custom, free-threaded, and debug
Python builds remain outside it.

## Getting started after cloning

From the cloned repository root, with supported Python venv/pip support installed:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
weavem --help
```

Activate that environment again in new shells. Installation requires your package
index or a provisioned offline wheelhouse; Weavem does not install task dependencies
on invocation. A privately supplied Weavem wheel can be installed instead of cloning.

Weavem installs its native authoring tools by default: pinned Cython, setuptools,
and a bundled Zig C compiler. Verified CPython header bundles—including the
CPython 3.15 bundle—ship in the wheel. For the supported standard CPython
distributions, native authoring needs no system compiler, development-header
package, sudo, Docker, or build-time download.

```bash
weavem doctor
weavem task new tasks/my_task --backend cython
```

`doctor` compiles and imports a tiny native module, reporting the selected header
bundle and compiler. Builds run this check automatically. Python distributions
outside the verified header signatures must provide their own matching headers;
unsupported free-threaded/debug builds fail clearly. See [native authoring](docs/native-authoring.md)
for the tested matrix and exact support boundaries.

Native task builds run your tests against both the Python source and the compiled
export. Release binaries exclude debug information and Weavem's absolute build
paths. Keep the original candidate for promotion to additional destinations;
cross-toolchain bit-for-bit reproducibility is not promised.

The older `.[native]` extra remains a no-op compatibility alias. Recipients can
run compatible prebuilt native tasks without compiling them, though their default
installation also contains the authoring tools. Release folders do not provision
task-specific Python packages or native shared libraries.

Weavem pins `prefect==3.9.0` and retains `fastapi==0.143.0` for the compatible
runtime path. A release promising latest-stable Python support must not ship
until the latest-Python CI lane passes with a normal install; bypassing pip's
Python requirement is not a supported workaround.

## The developer workflow

1. **Create** a project, tasks, and flows.
2. **Choose dependencies** explicitly: editable local source or an exact published release.
3. **Develop and test** without publishing each edit.
4. **Build** an unpublished candidate.
5. **Publish** the exact candidate to a folder, without rebuilding it.
6. **Reuse** released tasks and flows in another project without author source.

Start from the directory where you want application projects:

```bash
weavem project new my_project
cd my_project
weavem task new tasks/normalize_text
weavem flow new process_documents
weavem task use normalize --path tasks/normalize_text
```

The task implementation and tests are starter code: replace them and edit the
metadata. The new flow is an empty scaffold, not an automatically connected pipeline.
The [authoring guide](docs/authoring-guide.md) walks through the complete, runnable
author-to-consumer story, including exact file contents.

**Release rule:** every task dependency of a published flow must already be published
and exactly pinned. Weavem stops on a local/unpublished dependency; it does not
silently publish dependencies or switch their bindings.

**Migration:** `task build` no longer publishes and no longer accepts `--store`.
Use `task build` followed by `task publish CANDIDATE --to STORE`. Existing task
schema-1 artifacts and `task("id", "version")` consumers remain supported.

## Documentation

- [Executed native developer simulation](docs/developer-simulation.md): `.so` builds, a colleague handoff, and direct pros and cons.
- [Authoring guide](docs/authoring-guide.md): develop, publish, and copy releases into a second project.
- [Reference](docs/reference.md): CLI, metadata, explicit bindings, path rules, and SDK.
- [Artifact contract](docs/artifact-contract.md): integrity, publication, and flow dependency pins.
- [Limitations](docs/limitations.md): support boundaries and execution risks.
- [Current compatibility evidence](docs/release-readiness-2026-10-26.md): Python 3.12–3.15 checks and remaining release gates.
- [Python/native cross-project fixture](examples/local-cross-project/README.md).

## Local configuration

```toml
[weavem]
store = "task-store"
work_dir = ".artifacts"
```

Use relative or absolute paths. Explicit CLI/SDK settings take precedence over
`WEAVEM_STORE` / `WEAVEM_ARTIFACTS_DIR`, then project settings, then defaults.
Global `weavem --project PATH ...` selects a project explicitly. No `.weavem` folder
or registration service is needed. Only local folder stores ship in this branch;
RustFS and warehouse synchronization are separate future work.

Weavem itself needs no account or network service. Prefect follows its own settings
and may start a loopback server. For local work, use
`PREFECT_SERVER_ANALYTICS_ENABLED=false`. Weavem tasks default to no result caching
so execution reaches dependency/integrity checks; opting into caching can skip them.
Hashes are not publisher authentication, and task/flow code is not sandboxed.

## Work on the framework

Install an editable checkout for the full test suite:

```bash
python -m pip install -e .
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use `.artifacts/` (or `WEAVEM_ARTIFACTS_DIR`), disable analytics, and exercise
Prefect's local test harness. Full integration tests need local loopback sockets
and native build prerequisites. They do not require a second machine.

## Read project metadata from Python

```python
from weavem import Project

metadata = Project.open(".").metadata()
```

Read task/flow definitions, bindings and referenced release metadata directly from
local files. No server, export command or task execution is involved. See the
[metadata API reference](docs/reference.md#local-project-metadata-python-api)
for the snapshot format and strict error behavior.

## License and trademarks

The code is licensed under [Apache License 2.0](LICENSE), with attribution in
[NOTICE](NOTICE). Proprietary products and commercial services can use the code
under that license.

The **Weavem™** brand is governed separately by our [trademark policy](TRADEMARKS.md):

> If you keep it proprietary, use your own brand. If you want to call it Weavem,
> contribute back to the commons.

Using Weavem as another product's primary brand requires prior written permission,
conditioned on publishing the covered Weavem-derived implementation under an agreed
open-source license. Publishing source alone does not grant branding permission.
Truthful descriptions such as “Built with Weavem” remain allowed without implying
endorsement. These branding conditions do not change the Apache code license.
