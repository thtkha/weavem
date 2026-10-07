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

## Documentation

- [Create and consume a task](docs/authoring-guide.md) — complete author-to-consumer walkthrough.
- [CLI, metadata, and SDK reference](docs/reference.md) — exact syntax and configuration rules.
- [Artifact contract](docs/artifact-contract.md) — publication and execution boundaries.
- [Limitations](docs/limitations.md) — supported behavior and known gaps.

## Getting started after cloning

You need **CPython 3.12 on Linux x86_64**, with `venv` and pip available.
The commands below use Bash. Start at the root of your cloned `weavem` repository,
where `pyproject.toml` lives:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install .
python -m weavem task --help
```

The last command should list `new`, `validate`, `test`, `build`, `list`, and `info`.
If creating the environment fails, install your operating system's Python 3.12 venv
support before continuing. Package installation needs access to your configured
package index, or dependencies supplied through your organization's offline setup.

When you open a new shell, activate `.venv/bin/activate` again from the checkout.
`python -m weavem` and the installed `weavem` command expose the same CLI. Installing
the framework does not populate a task store or create any application tasks.

**Choose your next step:**

- **Start a project:** see [Create a project and flows](#create-a-project-and-flows).
- **Create a task:** follow [Create a task and use it in another project](docs/authoring-guide.md).
- **Use tasks someone supplied:** go to [Use existing tasks](#use-existing-tasks).
  You need their extracted task store and any declared runtime dependencies.
- **Work on Weavem itself:** see [Development and examples](#development-and-examples).

### Native builds and private installations

To author compiled tasks, install the native build dependencies into the same
activated environment:

```bash
python -m pip install ".[native]"
```

You also need a C compiler and development headers matching Python 3.12. Consumers
of compatible, prebuilt native tasks do not need Cython or a compiler.

Consumers can install a privately supplied Weavem wheel instead of cloning this
repository. Weavem and each task's runtime dependencies must already be installed;
a task folder does not contain the entire Python environment. This project has not
been published to PyPI.

## Create a project and flows

With Weavem installed in your active environment, start from the directory where
you want the new project (it need not be inside the framework checkout):

```bash
weavem project new my_project
cd my_project
weavem task new tasks/normalize_text
weavem flow new process_documents
```

The project contains `weavem.toml`, `tasks/`, `flows/`, and a `.gitignore`.
The flow command creates `flows/process_documents.py`; run it from the project root:

```bash
python -m flows.process_documents
```

The initial flow does no work. Implement and test your task, build it with
`weavem task build tasks/normalize_text`, then edit the flow to resolve that task
by its ID and version with `weavem.task`. More flows can reuse the same published
tasks without copying their implementations. Follow the [authoring guide](docs/authoring-guide.md)
for a complete task implementation and composition example.

Scaffolding does not install dependencies, create a virtual environment, initialize
Git, or start a server. Running a flow may start Prefect's local server. Existing
project folders and flow files are not overwritten.

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
