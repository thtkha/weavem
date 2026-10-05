# Weavem

Weavem is a framework for building, distributing, and running versioned tasks in
Prefect flows. Task implementations stay separate from the projects that use them.

- **Tasks** are reusable functions published as built artifacts, with their own
  identity, version, and metadata.
- **Flows** compose tasks and application logic. Prefect supplies execution, retries,
  states, and orchestration.
- **`task-store/`** contains the built tasks available to a project.
- **`.artifacts/`** holds disposable build and verification files—not the default task store.

A company can distribute task folders privately. GitHub, a registry, and access to
an author's source checkout are not required.

## Current scope

This local MVP supports CPython 3.12 on Linux x86_64, with Python and Cython task
backends. The API and artifact schema are provisional. It does not include a domain
task library, remote registry, visual editor, or deployment platform.

See [supported behavior and limitations](docs/limitations.md).

## Install

Install Weavem into the Python environment that will author or run tasks. From this
source checkout:

```bash
python -m pip install .
```

Native-task authors additionally need the native build dependencies, a C compiler,
and Python development headers:

```bash
python -m pip install ".[native]"
```

Consumers can instead install a privately supplied Weavem wheel. They do not need
Cython or a compiler to run compatible, prebuilt native tasks. Weavem and each task's
runtime dependencies must already be installed; distributing a task folder does not
package the entire Python environment. This project has not been published to PyPI.

## Use existing tasks

Place the supplied, already-extracted `task-store/` beside your flow code:

```text
project/
├── flow.py
└── task-store/
    └── <task-id>/<version>/<python-tag>/
        ├── manifest.json
        └── <canonical-module-name>.so    # or .py
```

Keep the supplied directory structure, manifests, and module filenames intact.
There is no consumer-side scaffold, build, or registration step. An archive may be
used to transport the folder, but Weavem reads the extracted files—not the archive.

Inspect what is available:

```bash
weavem task list --json
weavem task info company.process_records==1.2.0 --json
```

Replace that illustrative ID/version with one present in your store. Discovery reads
metadata without importing task implementations.

### Compose a flow

Resolve each task by its exact ID and version, then call it with the inputs described
by its interface. For example, if your company supplies a records-processing task:

```python
from weavem import flow, task

process_records = task("company.process_records", "1.2.0", retries=2)

@flow
def processing_flow(records):
    return process_records(records)
```

The task above is illustrative, not a built-in Weavem task. `task(...)` returns a real
Prefect Task; `@flow` creates a real Prefect Flow. Prefect options and `.with_options(...)`
remain available. Ordinary Python and direct Prefect tasks can be used alongside them.

## Author tasks

Start with a name:

```bash
weavem task new my_task
```

This creates an editable source folder:

```text
my_task/
├── task.toml
├── implementation.py
└── tests/test_task.py
```

The initial ID is the folder name, the version is `0.1.0`, and the backend is `python`.
Replace the starter implementation and tests, then edit `task.toml` to describe your
task. Its `export` must name the bare callable you want consumers to invoke.

For a compiled `.so`, set `backend = "cython"`. Optional `--id`, `--version`, and
`--backend` flags can override scaffold defaults; none is required. Source directories
can also be nested, such as `weavem task new tasks/my_task`.

Validate, test, and publish the built artifact locally:

```bash
weavem task validate my_task
weavem task test my_task
weavem task build my_task
```

`build` runs source checks/tests, builds the selected backend, verifies that its
export can be loaded, and publishes into the configured store. A source folder alone
is not a consumable task. See the [author metadata and artifact contract](docs/artifact-contract.md).

## Distribute and update tasks

Distribute built task directories, not author workspaces. A copied folder, private
file share, or extracted bundle is sufficient; no Weavem service is required.
Consumers must use a compatible Python/platform environment and install the declared
dependencies separately.

Treat a published task version as immutable. Change the implementation under a new
version, distribute that version, and update a flow's exact pin when ready. Updating
author source alone does not change an existing artifact. Task versions are independent
of Weavem package versions and flow-project releases.

`task-store/` is gitignored in this repository. Other projects can exclude their stores
from version control as well. Only use artifacts from trusted publishers: integrity
checks detect altered bytes but do not authenticate the publisher or sandbox task code.

## Storage and configuration

Without configuration, Weavem uses `task-store/` and `.artifacts/` in the working
directory. A selected project or the nearest ancestor `weavem.toml` establishes the
project root instead. Relative configured paths are anchored to that root.

```toml
# weavem.toml — optional
[weavem]
store = "task-store"
work_dir = ".artifacts"
```

Both locations can point elsewhere, including shared sibling directories or absolute
paths. Precedence is explicit SDK/CLI arguments, then `WEAVEM_STORE` /
`WEAVEM_ARTIFACTS_DIR`, then configuration, then defaults. The CLI's global `--project`
option selects a directory or config file explicitly.

For custom storage, the SDK accepts a `TaskStore` adapter that supplies local artifact
references. An optional execution policy is separate from storage and Prefect options.
The runtime retains identity, integrity, compatibility, dependency, and policy checks
regardless of where an artifact came from. No remote adapter ships in this MVP.

## Local operation

Weavem requires no account and performs no package downloads or telemetry itself.
Prefect follows its own user configuration; Weavem does not rewrite it. For isolated
local work, set `PREFECT_SERVER_ANALYTICS_ENABLED=false`. Prefect may start a local
loopback server. Persistent result caching is outside the verified MVP; see
[limitations](docs/limitations.md#execution-and-trust).

## Development and examples

With native build prerequisites and dependencies installed:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests keep generated workspaces under `.artifacts/` or `WEAVEM_ARTIFACTS_DIR`, disable
Prefect analytics, and use its public test harness. Integration tests need local
loopback sockets.

A small [cross-project demonstration](examples/local-cross-project/README.md) is
available for checking the author-to-consumer path. It is a test fixture, not the
framework's application model.

## License

[Apache License 2.0](LICENSE).
