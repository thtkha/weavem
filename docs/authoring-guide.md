# Develop locally, then publish and reuse

This walkthrough creates a text-normalization task and a flow, then uses their
releases in a second project. The names are examples, not framework conventions.
Use Bash with Weavem installed in an activated Python 3.12 environment. See the
[installation instructions](../README.md#getting-started-after-cloning) first.

## 1. Create a project and edit its task

Start in the directory where you want your application projects:

```bash
weavem project new author
cd author
weavem task new tasks/normalize_text
weavem flow new process_documents
```

Replace `tasks/normalize_text/task.toml` with:

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

Replace `tasks/normalize_text/implementation.py` with:

```python
def run(text: str) -> str:
    return " ".join(text.split()).lower()
```

Replace `tasks/normalize_text/tests/test_task.py` with:

```python
import unittest
from implementation import run

class NormalizeTests(unittest.TestCase):
    def test_whitespace_and_case(self):
        self.assertEqual(run("  Hello   WORLD  "), "hello world")
```

Select this source explicitly and run its checks:

```bash
weavem task use normalize --path tasks/normalize_text
weavem task validate tasks/normalize_text
weavem task test tasks/normalize_text
```

`normalize` is a project-local dependency alias. Another alias can select an
existing published task; local and released bindings can coexist in one project.

## 2. Compose and run a local flow

Replace `flows/process_documents.py` with:

```python
from weavem import flow, task

normalize = task("normalize")

@flow
def process_documents(text: str) -> str:
    return normalize(text)
```

Edit its sidecar `flows/process_documents.toml`:

```toml
[flow]
schema = 1
flow_id = "text.process_documents"
version = "1.0.0"
source = "process_documents.py"
export = "process_documents"
tasks = ["normalize"]
```

Replace `tests/flows/process_documents/test_flow.py` with:

```python
import unittest
from unittest.mock import patch
from flows import process_documents as module

class ProcessTests(unittest.TestCase):
    def test_result(self):
        # Test the real task implementation without starting an orchestration run.
        with patch.object(module, "normalize", module.normalize.fn):
            self.assertEqual(module.process_documents.fn(" Hello WORLD "), "hello world")
```

Now run:

```bash
weavem flow validate process_documents
weavem flow test process_documents
PREFECT_SERVER_ANALYTICS_ENABLED=false weavem flow run process_documents \
  --params '{"text": " Hello WORLD "}'
```

Expected result: `"hello world"`. Actual `flow run` uses Prefect and may start its
local loopback server; the unittest deliberately avoids orchestration.

Edit the local task and rerun. You do not need to publish or bump its version.
Native source may need local compilation; Python source does not. Missing local
source is an error, never an invitation to use a published task silently.

```text
author/
├── weavem.toml
├── tasks/normalize_text/
│   ├── task.toml
│   ├── implementation.py
│   └── tests/test_task.py
├── flows/
│   ├── __init__.py
│   ├── process_documents.py
│   └── process_documents.toml
└── tests/flows/process_documents/test_flow.py
```

## 3. Build, then publish the task

Restore the example behavior before continuing if you changed it experimentally.

```bash
TASK_CANDIDATE="$(weavem task build tasks/normalize_text | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
weavem task publish "$TASK_CANDIDATE"
```

The first command tests/builds a candidate under `.artifacts/` and prints its path
as JSON. The second copies those exact bytes into `task-store/`. It does not
rebuild source, delete the candidate, or publish anything else.

Repeated publication of the same candidate is safe. Changed bytes at an existing
ID/version are rejected: assign a new version and build another candidate instead.
Native rebuilds need not be byte-identical; retry publication of the original candidate.

Select the published release explicitly:

```bash
weavem task use normalize --release text.normalize==1.0.0
```

This replaces only the chosen binding in `weavem.toml`, recording its source and
canonical manifest digest. The flow's Python code does not change.

For another folder, use `--from ../shared-releases`. This is an explicit source,
not a search path. `--from task-store` means the project's configured default store.

## 4. Build and publish the flow

```bash
weavem flow test process_documents
FLOW_CANDIDATE="$(weavem flow build process_documents | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
weavem flow publish "$FLOW_CANDIDATE"
```

Every declared task must already be published. If a binding is still local, build
stops **before** tests or packaging. It names the dependency to release first and
never auto-publishes or changes your selections.

Build tests a flow snapshot under its recorded task pins. Publish requires those
same tasks in its destination store. If publishing to another folder, publish the
task candidates there first, then publish the flow. `--to PATH` selects a destination.

```text
author/
├── tasks/                         # editable source
├── flows/                         # editable source + flow metadata
├── tests/
├── .artifacts/                    # candidates and disposable work
└── task-store/
    ├── text.normalize/1.0.0/cpython-312/
    └── _flows/text.process_documents/1.0.0/cpython-312/
```

## 5. Consume releases without the author project

From the author project:

```bash
cd ..
weavem project new consumer
cp -R author/task-store consumer/task-store
cd consumer
weavem task list --json
weavem flow list --json
PREFECT_SERVER_ANALYTICS_ENABLED=false weavem flow run \
  text.process_documents==1.0.0 --release --params '{"text": " Hello WORLD "}'
```

Expected result: `"hello world"`, with no task or flow author source in the consumer.
Only the whole extracted store and a compatible installed environment are needed.
You can move the original author folder out of the way and repeat this command.
A ZIP can transport the folder, but must be extracted before use.

To compose a **new local flow** using the same released task:

```bash
weavem task use normalize --release text.normalize==1.0.0
weavem flow new custom_report
```

Edit the new flow to call `task("normalize")`, declare `normalize` in its sidecar,
and update its tests just as above. The released flow needs no consumer alias setup;
its own pins are authoritative and cannot be overridden by local bindings.

New author edits or newer releases do not change either exact selection. An upgrade
is an explicit choice. To return to source development in the author project, use
`weavem task use normalize --path tasks/normalize_text`; another flow release will
again require switching to a published dependency first.

## Cleanup and trust

Keep `task-store/`: it contains the reusable releases. Candidates under `.artifacts/`
may be removed once no longer needed; don't remove an unpublished candidate you
intend to share. Both paths are configurable; see the [reference](reference.md).

Run only trusted code. Digests detect changes but do not authenticate publishers or
sandbox execution. Weavem checks declared dependencies; it does not install them.
