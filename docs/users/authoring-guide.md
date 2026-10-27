# Build a task, a flow, and a reusable local release

This tutorial is for someone who has installed the official Weavem wheel and
wants to build a small project from scratch. It creates a Python task,
`text.normalize` version `1.0.0`, and a flow, `text.process_documents` version
`1.0.0`. It then publishes them to a local folder and runs the copied releases
from a separate project.

It uses no account, hosted registry, Git repository, or Weavem source checkout.
The same instructions are suitable for a developer or an agent: follow the
commands in order, copy each labelled file exactly, and stop at the first error.

## Before you begin

Follow [Install Weavem](getting-started.md) first. Start this page in a
writable workspace with:

- the workspace virtual environment activated;
- `WEAVEM_WHEEL` set to the **absolute** path of the downloaded
  `weavem-0.1.0a2-py3-none-any.whl`;
- `PREFECT_HOME` set under the workspace, such as
  `workspace/.artifacts/prefect`; and
- `PREFECT_SERVER_ANALYTICS_ENABLED=false`.

Keep `.artifacts/` while following the tutorial. It contains disposable test
work and the unpublished candidates promoted below. Keep `task-store/`: it is
the reusable release store, not disposable build output.

## 1. Create the author project

Run this from the workspace. `author` is an ordinary project directory; it does
not need to be a Git checkout.

<!-- weavem-run -->
```bash
set -euo pipefail
weavem project new author
cd author
weavem task new tasks/text_normalize
weavem flow new process_documents
```

The scaffold supplies editable source, metadata, and tests. Replace all three
task files with the following. `run` is the public task export. It delegates to
an internal class and method, which is a normal way to keep task code organized.

Replace `tasks/text_normalize/task.toml` with:

<!-- weavem-file: tasks/text_normalize/task.toml -->
```toml
[task]
schema = 1
task_id = "text.normalize"
version = "1.0.0"
backend = "python"
source = "implementation.py"
export = "run"
dependencies = []
```

Replace `tasks/text_normalize/implementation.py` with:

<!-- weavem-file: tasks/text_normalize/implementation.py -->
```python
class TextNormalizer:
    def normalize(self, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        return " ".join(text.split()).lower()


def run(text: str) -> str:
    """Return normalized, lowercase text."""
    return TextNormalizer().normalize(text)
```

Replace `tasks/text_normalize/tests/test_task.py` with:

<!-- weavem-file: tasks/text_normalize/tests/test_task.py -->
```python
import unittest

from implementation import run


class NormalizeTests(unittest.TestCase):
    def test_normalizes_whitespace_and_case(self):
        self.assertEqual(run("  Hello   WORLD  "), "hello world")

    def test_rejects_non_text(self):
        with self.assertRaises(TypeError):
            run(42)
```

Bind the alias used by the flow to this editable task, then validate and test
it. `validate` checks metadata and source shape. `test` runs the authored
behavioral tests. Neither creates a release.

<!-- weavem-run -->
```bash
weavem task use normalize --path tasks/text_normalize
weavem task validate tasks/text_normalize
weavem task test tasks/text_normalize
```

Expected success messages include:

```text
task validate passed: tasks/text_normalize
task test passed: tasks/text_normalize
```

## 2. Write and run the local flow

Replace the generated flow and its sidecar metadata. The `tasks` list contains
the project-local aliases that the flow is allowed to call. The alias is
`normalize`; the release identity remains `text.normalize`.

Replace `flows/process_documents.py` with:

<!-- weavem-file: flows/process_documents.py -->
```python
from weavem import flow, task


normalize = task("normalize")


@flow
def process_documents(text: str) -> str:
    return normalize(text)
```

Replace `flows/process_documents.toml` with:

<!-- weavem-file: flows/process_documents.toml -->
```toml
[flow]
schema = 1
flow_id = "text.process_documents"
version = "1.0.0"
source = "process_documents.py"
export = "process_documents"
tasks = ["normalize"]
```

The flow test calls the real task implementation without starting a Prefect run.
The command-line run below does use Prefect and may start a local loopback
service under `PREFECT_HOME`.

Replace `tests/flows/process_documents/test_flow.py` with:

<!-- weavem-file: tests/flows/process_documents/test_flow.py -->
```python
import unittest
from unittest.mock import patch

from flows import process_documents as module


class ProcessDocumentsTests(unittest.TestCase):
    def test_normalizes_text(self):
        with patch.object(module, "normalize", module.normalize.fn):
            self.assertEqual(module.process_documents.fn(" Hello WORLD "), "hello world")
```

<!-- weavem-run -->
```bash
weavem flow validate process_documents
weavem flow test process_documents
output="$(weavem flow run process_documents --params '{"text":" Hello WORLD "}')"
printf '%s\n' "$output"
test "$(printf '%s\n' "$output" | tail -n 1)" = '"hello world"'
```

The project now looks like this (generated caches are omitted):

```text
author/
├── weavem.toml
├── tasks/text_normalize/
│   ├── task.toml
│   ├── implementation.py
│   └── tests/test_task.py
├── flows/
│   ├── __init__.py
│   ├── process_documents.py
│   └── process_documents.toml
└── tests/flows/process_documents/test_flow.py
```

## 3. Build and publish immutable version 1.0.0

`build` first runs the task tests and creates an unpublished candidate. `publish`
then copies those exact bytes to `task-store/`; it does not rebuild source. Keep
the candidate until promotion and verification are complete.

<!-- weavem-run -->
```bash
TASK_CANDIDATE="$(weavem task build tasks/text_normalize --work-dir .artifacts/candidates | python -c 'import json, sys; print(json.load(sys.stdin)["root"])')"
weavem task publish "$TASK_CANDIDATE"
weavem task use normalize --release text.normalize==1.0.0
```

The release binding in `weavem.toml` records the exact version and manifest
digest. A published flow cannot use a local task binding, so the explicit switch
above is required before building the flow.

<!-- weavem-run -->
```bash
FLOW_CANDIDATE="$(weavem flow build process_documents --work-dir .artifacts/candidates | python -c 'import json, sys; print(json.load(sys.stdin)["root"])')"
weavem flow publish "$FLOW_CANDIDATE"
weavem task info text.normalize==1.0.0
weavem flow info text.process_documents==1.0.0
```

After publishing, `task-store/` holds both immutable releases. Its internal
cache-tag directory is interpreter-specific, so show it as `<cache-tag>`:

```text
author/task-store/
├── text.normalize/1.0.0/<cache-tag>/
│   ├── manifest.json
│   └── _weavem_text_normalize_....py
└── _flows/text.process_documents/1.0.0/<cache-tag>/
    ├── manifest.json
    └── _weavem_flow_....py
```

Do not edit a published folder. A changed task needs a new version and a new
candidate. Re-publish the retained original candidate to another destination if
its bytes are unchanged.

## 4. Copy and use the whole store in a separate project

Create a separate environment and project. This is intentionally not the
author's virtual environment. Install the same downloaded framework wheel and
copy the **entire extracted** store, including both task and flow namespaces.
A ZIP can transport the store, but extract it before use.

<!-- weavem-run -->
```bash
cd ..
weavem project new consumer
cd consumer
python -m venv ../.consumer-venv
source ../.consumer-venv/bin/activate
python -m pip install "$WEAVEM_WHEEL"
python -m pip check
cp -a ../author/task-store ./task-store
weavem task list --json
weavem flow list --json
```

Run the published flow by its exact ID and version. It uses the task pins stored
in the flow release, not a consumer alias or source folder.

<!-- weavem-run -->
```bash
output="$(weavem flow run text.process_documents==1.0.0 --release --params '{"text":" Hello WORLD "}')"
printf '%s\n' "$output"
test "$(printf '%s\n' "$output" | tail -n 1)" = '"hello world"'
python - <<'PY'
import pathlib
import sys
from weavem import task

assert task("text.normalize", "1.0.0").fn("  HELLO world  ") == "hello world"
module = next(module for name, module in sys.modules.items() if name.startswith("_weavem_text_normalize_"))
assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path("task-store").resolve())
print("consumer loaded the published task from task-store")
PY
```

This ends in `consumer` with the consumer environment active. The author source
is not a fallback: the commands above load releases from `consumer/task-store/`.
The native tutorial continues from this exact state and later proves the same
property for a compiled `.so`.

## What to do next

- Keep developing source in `author`; switch the alias back with
  `weavem task use normalize --path tasks/text_normalize`.
- To make a new released task version, change its version in `task.toml`, then
  test, build, and publish a new candidate.
- To publish a flow, pin every declared task to already-published releases first.
- For native task version `1.1.0` and a compiled-artifact handoff, continue with
  [Native authoring](native-authoring.md).

Weavem does not install task-specific Python packages or native libraries, and it
does not sandbox task code. Run only code and copied stores that you trust.
