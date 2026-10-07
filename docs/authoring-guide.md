# Create a task and use it in another project

This tutorial builds a text-normalization task, then uses it in a separate project.
By the end, a Prefect flow will print `['ada lovelace', 'grace hopper']` using only
the built task store—not imports from the author's source directory.

The task is a small example, not built-in framework functionality. In your own
projects, tasks hold reusable behavior and tests; flows compose that behavior and
choose orchestration options such as retries.

## Before you start

Complete the [installation steps](../README.md#getting-started-after-cloning), then
return to the Weavem checkout root with its virtual environment activated. This guide
uses Bash on the supported CPython 3.12/Linux x86_64 environment. Prefect needs
permission to open local loopback sockets. No compiler is needed until the optional
native-build section.

Follow the steps in the same shell and stop if a command fails. Use a new tutorial
workspace so you won't overwrite existing work. The example uses synthetic data;
keep credentials and private data out of source files, metadata, and task artifacts.

## Set up two projects

Start **at the Weavem checkout root**, containing `pyproject.toml` and `src/weavem/`.
`WEAVEM_REPO` records that checkout; `LAB` is a new disposable workspace under it.
Change the `LAB` assignment before running it if another storage location is needed.
The `.artifacts` directory is already ignored by this repository.

```bash
export WEAVEM_REPO="${PWD}"
test -f "${WEAVEM_REPO}/pyproject.toml"
test -d "${WEAVEM_REPO}/src/weavem"
python3.12 -c 'import platform, sys; assert sys.implementation.name == "cpython"; assert sys.platform == "linux"; assert platform.machine().lower() in {"x86_64", "amd64"}'
export LAB="${WEAVEM_REPO}/.artifacts/authoring-guide"
test ! -e "${LAB}"
mkdir -p "${LAB}"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="${LAB}/tmp"
export PIP_CACHE_DIR="${LAB}/pip-cache"
export WEAVEM_ARTIFACTS_DIR="${LAB}/work"
export PREFECT_HOME="${LAB}/prefect"
export PREFECT_SERVER_ANALYTICS_ENABLED=false
mkdir -p "${TMPDIR}" "${WEAVEM_ARTIFACTS_DIR}"
unset WEAVEM_STORE PREFECT_API_URL PREFECT_API_KEY
python -m weavem task --help
python -m weavem project new "${LAB}/author"
python -m weavem project new "${LAB}/consumer"
```

The CLI help should list `new`, `validate`, `test`, `build`, `list`, and `info`.
The empty project configs establish independent roots rather than inheriting an
ancestor config. Environment changes apply to this shell only.
`python -m weavem` uses the activated interpreter and is equivalent to the installed `weavem` entry point.

## 1. Scaffold and replace the starter files

```bash
cd "${LAB}/author"
python -m weavem task new normalize_names
```

This creates `normalize_names/task.toml`, `implementation.py`, and `tests/test_task.py`.
The scaffold contains a small starter function; **replace all three files** below.
Do not leave its old export or tests behind. `run` is our chosen name, not a required
framework keyword. The export in metadata must match the callable.

Write `normalize_names/task.toml`:

```toml
[task]
schema = 1
task_id = "text.normalize_names"
version = "1.0.0"
backend = "python"
source = "implementation.py"
export = "run"
dependencies = []
description = "Strip whitespace and case-fold a list of names"
inputs = ["names: list[str]"]
output = "list[str]"
```

Write `normalize_names/implementation.py`:

```python
def run(names):
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise TypeError("names must be a list of strings")
    return [name.strip().casefold() for name in names]
```

Write `normalize_names/tests/test_task.py`:

```python
import unittest
from implementation import run


class NormalizeNamesTests(unittest.TestCase):
    def test_normalizes_names(self):
        self.assertEqual(run([" Ada Lovelace ", "GRACE HOPPER"]),
                         ["ada lovelace", "grace hopper"])

    def test_empty_list(self):
        self.assertEqual(run([]), [])

    def test_rejects_invalid_inputs(self):
        for value in (None, "Ada", [42]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                run(value)
```

Keep task code undecorated: no `@task` or `@flow` on `run`. Only one implementation
module is packaged; helper functions can live in that module. Do not import sibling
author modules or assume the author's working directory exists on the consumer.
Standard-library imports require no dependency pins. Installed third-party packages
must be declared as exact distribution pins; see [reference](reference.md#author-metadata).

## 2. Validate, test, and build

Run from `${LAB}/author`:

```bash
python -m weavem task validate normalize_names
python -m weavem task test normalize_names
python -m weavem task build normalize_names
python -m weavem task list --json
python -m weavem task info text.normalize_names==1.0.0 --json
```

Each command should exit zero. `validate` and `test` are silent on success;
`build` prints JSON containing `root` and `manifest`. `list` returns an array of
artifact paths; `info` shows `task_id`, `version`, `export`, and descriptive metadata.
The store is `${LAB}/author/task-store/`; temporary build files use `${LAB}/work/`.

`validate` checks metadata and source presence, not source correctness. `test` checks
syntax and runs a non-empty unittest suite in a source snapshot. `build` repeats
those gates and verifies the packaged export before publication. A passing source
test alone does not prove a consumer can load the artifact.

## 3. Transfer built files, not source

Run from `${LAB}/author`. The destination store must not already exist:

```bash
test ! -e "${LAB}/consumer/task-store"
cp -R task-store "${LAB}/consumer/task-store"
mv normalize_names normalize_names.source-backup
cd "${LAB}/consumer"
python -m weavem task info text.normalize_names==1.0.0 --json
```

Discovery should still find version `1.0.0`. The author source was renamed only
to demonstrate separation; it is retained for recovery. Keep all generated filenames
and manifests unchanged. The consumer does not need `task new`, `build`, registration,
or an archive loader. A private extracted folder is enough.

## 4. Create and run a flow

Write `${LAB}/consumer/flow.py`:

```python
from prefect.cache_policies import NO_CACHE
from weavem import flow, task

normalize_names = task("text.normalize_names", "1.0.0", cache_policy=NO_CACHE)


@flow(persist_result=False)
def prepare_names(names):
    return normalize_names(names)


if __name__ == "__main__":
    result = prepare_names([" Ada Lovelace ", "GRACE HOPPER"])
    assert result == ["ada lovelace", "grace hopper"]
    print(result)
```

Run from `${LAB}/consumer`, with the same activated environment:

```bash
python flow.py
```

The flow should print `['ada lovelace', 'grace hopper']` alongside Prefect's logs and exit zero. We explicitly
disable task caching because cached results can skip current artifact/policy checks.
See [Prefect caching](https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/caching.mdx) for the underlying no-cache policy.
The consumer uses the default store in its own project. The two projects share an
installed framework environment here, **not author source imports**. For a separate
machine, install Weavem and task dependencies there before transferring the store.

## What you have built

- Source tests pass before publication, including invalid-input cases.
- Consumer discovery shows `text.normalize_names` at `1.0.0`.
- `python flow.py` asserts the exact output after the author directory is renamed.
- The consumer contains flow code, optional project config, and the built store;
  it has no copy of the task implementation source workspace.

For your own tasks, decide on the input/output contract and failure behavior before
writing code. Test meaningful outcomes, empty inputs, and invalid data—not only that
a function can be called. Keep task dependencies and run commands documented so
another developer can use the built folder without your author workspace.

## Publish updates and optional native tasks

For any update, first restore the author folder using the recovery command below.
Edit implementation/tests and set version to `1.1.0`; keep backend `python` for a
Python update, then repeat step 2. Preserve the existing `1.0.0` artifacts.

For an optional native variant instead, install author dependencies from the checkout
in the activated environment:

```bash
python -m pip install "${WEAVEM_REPO}[native]"
```

A C compiler and development headers matching CPython 3.12 must be provisioned through
your operating system's package manager. If they are unavailable, keep the Python
backend. Change `backend` to `cython` **and version to `1.1.0`** in the source metadata,
then repeat step 2. Both backend versions use the same callable interface. A native
rebuild need not produce identical bytes; never assume it can replace `1.0.0`.

To deliver the new version without overwriting the old one, run from `${LAB}/author`:

```bash
test ! -e "${LAB}/consumer/task-store/text.normalize_names/1.1.0"
cp -R task-store/text.normalize_names/1.1.0 "${LAB}/consumer/task-store/text.normalize_names/"
```

Change the consumer's task pin to `1.1.0`, then run `python flow.py` from the consumer
and require the same asserted output. Then temporarily restore the `1.0.0` pin and
run the flow again: its original output must still pass. Finally select the intended
version and rerun. If the business behavior intentionally changed, keep version-specific
expected assertions for each check rather than expecting identical output.
Consumers need compatible prebuilt binaries,
not the compiler. Native execution is subject to [platform limits](limitations.md).

## Rollback and recovery

If creation is partial, stop and inspect the existing tutorial directory. Do not
rerun scaffolding over edited files. Continue at the first unfinished step, or choose
a new `LAB` directory and restart setup.

Restore the renamed author directory when ready to edit it, from any directory:

```bash
test ! -e "${LAB}/author/normalize_names"
mv "${LAB}/author/normalize_names.source-backup" "${LAB}/author/normalize_names"
```

The original `normalize_names/task.toml` is available again. If the backup is absent,
stop and inspect the author directory rather than moving another path.
To roll back an update, change the flow pin back to `1.0.0` and run the flow again;
retain that built version until rollback is no longer needed. Do not modify published
bytes to repair a failure. Fix source and publish another version.

## Troubleshooting

| Symptom | Check and safe response |
| --- | --- |
| `No module named weavem` | Activate `${WEAVEM_REPO}/.venv/bin/activate`; run `python -m pip show weavem`. Return to setup if absent. |
| Source tests fail or are empty | Check `normalize_names/tests/test_task.py`, `test_` method names, and the import of `run`. Fix source/tests, repeat step 2. |
| Export missing or already a Prefect Task | Match `export = "run"` to a bare function in `implementation.py`; remove task decorators. Rebuild only after source tests pass. |
| Task not found | Run `pwd` and `python -m weavem task list --json` in the consumer. Confirm the copied store and exact ID/version; check `WEAVEM_STORE` is unset. |
| Different bytes already published | Keep the existing version. Assign a new source version, build, distribute that version, and update the pin. |
| Missing dependency or incompatible artifact | Compare the manifest's dependency pins, Python tag and platform with the consumer environment. Provision that environment or request a compatible build; do not edit the manifest. |
| Permission error or local server timeout | Confirm local loopback sockets are allowed. Do not work around this by pointing the tutorial at a production Prefect server. |

If the documented checks do not explain the failure, stop and report the command,
Weavem version, Python/platform, current step and sanitized error to the Weavem
maintainers through the GitHub Issues tab of the repository linked in the README.

## Cleanup

The tutorial files, copied stores, and temporary work are under `LAB`. Close this
shell to discard the tutorial-specific environment settings. You can delete the
`LAB` directory once you no longer need its source or built tasks; keep it if you
want to continue experimenting. The framework environment remains in the checkout's
`.venv/`. In a real project, keep deliverable task stores separate from disposable
build work so cleanup does not remove the tasks your flows need.

## About this guide

The task metadata and source tests have been checked, along with CLI syntax and
documentation links. The full tutorial, including build and flow execution, has not
yet been run end-to-end. See the [reference](reference.md) for exact syntax and the
[artifact contract](artifact-contract.md) for publication and execution rules.
