# Build and share a native task

This page continues [Build a task, a flow, and a reusable local release](authoring-guide.md).
It changes the same task to native backend version `1.1.0`, builds a compiled
`.so`, and publishes a flow version `1.1.0` pinned to that release.

Native authoring is supported for standard, GIL-enabled CPython 3.12–3.15 on
Linux x86_64 with glibc 2.28 or later. It is not supported on Windows, macOS,
musl Linux, free-threaded CPython, or debug CPython. A native release is tied to
its Python minor version and platform: copying a CPython 3.12 Linux `.so` does
not make it usable by CPython 3.13 or another operating system.

Weavem includes the tested Cython, compiler, and header tooling in its normal
installation. It does not use `sudo`, install OS packages, use Docker, or download
a compiler while building. `weavem doctor` reports actionable compiler/header
diagnostics; fix an unsupported Python installation rather than bypassing them.

## 1. Return to the author project

The preceding tutorial ends in `consumer` with `.consumer-venv` active. Return
to the author environment before editing source. Keep both `author/task-store/`
and `consumer/task-store/`; do not delete candidates or releases.

<!-- weavem-run -->
```bash
cd ../author
source ../.venv/bin/activate
```

Update only the task metadata. The implementation and behavioral tests from the
previous tutorial remain valid: `run()` still wraps `TextNormalizer.normalize()`.
The new version makes the altered release identity explicit.

Replace `tasks/text_normalize/task.toml` with:

<!-- weavem-file: tasks/text_normalize/task.toml -->
```toml
[task]
schema = 1
task_id = "text.normalize"
version = "1.1.0"
backend = "cython"
source = "implementation.py"
export = "run"
dependencies = []
```

Check the environment, source contract, and source behavior. A successful
`doctor` reports JSON. Every native build repeats its compiler/header probe, so
running it here gives an early, readable failure without replacing the build
check.

<!-- weavem-run -->
```bash
weavem doctor
weavem task validate tasks/text_normalize
weavem task test tasks/text_normalize
```

## 2. Build and publish the compiled task

For a Cython task, `build` runs the same authored behavioral tests twice: once
against `implementation.py` and again against the compiled export. It creates an
unpublished candidate only if both pass. The produced filename ends with the
platform's extension suffix, normally `.so` on this supported Linux target.

<!-- weavem-run -->
```bash
NATIVE_TASK_CANDIDATE="$(weavem task build tasks/text_normalize --work-dir .artifacts/native-candidates | python -c 'import json, sys; print(json.load(sys.stdin)["root"])')"
weavem task publish "$NATIVE_TASK_CANDIDATE"
weavem task use normalize --release text.normalize==1.1.0
```

`publish` promotes the retained candidate bytes. It does not compile again.
Different bytes cannot replace `text.normalize==1.1.0`; change the version for
another implementation. Build reproducibility across different machines and
toolchains is not promised.

## 3. Publish a flow pinned to the native task

Release the flow as a new version too. Its `tasks` declaration stays the alias
`normalize`; the binding now pins it to `text.normalize==1.1.0`.

Replace `flows/process_documents.toml` with:

<!-- weavem-file: flows/process_documents.toml -->
```toml
[flow]
schema = 1
flow_id = "text.process_documents"
version = "1.1.0"
source = "process_documents.py"
export = "process_documents"
tasks = ["normalize"]
```

<!-- weavem-run -->
```bash
weavem flow validate process_documents
weavem flow test process_documents
NATIVE_FLOW_CANDIDATE="$(weavem flow build process_documents --work-dir .artifacts/native-candidates | python -c 'import json, sys; print(json.load(sys.stdin)["root"])')"
weavem flow publish "$NATIVE_FLOW_CANDIDATE"
output="$(weavem flow run process_documents --params '{"text":" Hello WORLD "}')"
printf '%s\n' "$output"
test "$(printf '%s\n' "$output" | tail -n 1)" = '"hello world"'
```

The author store now contains both releases:

```text
author/task-store/
├── text.normalize/1.0.0/<cache-tag>/...py
├── text.normalize/1.1.0/<cache-tag>/...so
├── _flows/text.process_documents/1.0.0/<cache-tag>/...py
└── _flows/text.process_documents/1.1.0/<cache-tag>/...py
```

## 4. Hand the compiled release to the consumer

Copy the complete store again, not just the `.so`: every release needs its
manifest, and each flow needs its pinned task releases. The recipient builds
nothing. It merely installs Weavem and any dependencies declared by the task.

<!-- weavem-run -->
```bash
cd ../consumer
source ../.consumer-venv/bin/activate
cp -a ../author/task-store/. task-store/
weavem task info text.normalize==1.1.0
weavem flow info text.process_documents==1.1.0
output="$(weavem flow run text.process_documents==1.1.0 --release --params '{"text":" Hello WORLD "}')"
printf '%s\n' "$output"
test "$(printf '%s\n' "$output" | tail -n 1)" = '"hello world"'
python - <<'PY'
import importlib.machinery
import pathlib
import sys
from weavem import task

assert task("text.normalize", "1.1.0").fn("  HELLO world  ") == "hello world"
module = next(module for name, module in sys.modules.items() if name.startswith("_weavem_text_normalize_"))
loaded_from = pathlib.Path(module.__file__).resolve()
assert loaded_from.is_relative_to(pathlib.Path("task-store").resolve())
assert loaded_from.suffix in {pathlib.Path(suffix).suffix for suffix in importlib.machinery.EXTENSION_SUFFIXES}
print(f"consumer loaded native artifact: {loaded_from}")
PY
```

The final Python assertion proves that the consumer loaded the compiled module
from its copied store. It does not import the author's task source or rebuild it.
For a real colleague handoff, send the extracted `task-store/` together with
the matching framework wheel (and an offline dependency wheelhouse if needed),
not the author virtual environment.

## Native limits and safety

- Native task artifacts are platform- and Python-minor-specific. Produce a
  matching release for each supported target.
- Recipients still need task-specific Python dependencies and native runtime
  libraries. Weavem validates declared artifact data; it does not provision
  dependencies.
- Release hashes detect changed bytes, not publisher identity or safe behavior.
  Native code is neither encrypted nor sandboxed. Run only trusted artifacts.
- A function export can call internal classes and methods, as this tutorial
  demonstrates. A task remains a single implementation module; arbitrary
  multi-file application packaging is not supported.

For the full command and metadata contract, use the [reference](reference.md).
Framework header maintenance is documented separately for
[maintainers](../maintainers/native-headers.md); it is not an application-author step.
