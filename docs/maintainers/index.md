# Maintainer and contributor documentation

[User documentation](../users/index.md) is for people building applications with Weavem.
This section is for changing, verifying, and releasing the framework itself.
Contributor setup and current maintenance procedures live here. Project-owner
evaluations and historical reports live separately in [project records](../project/index.md).

## Work on the framework

Clone the repository with your organization's GitHub access. From the checkout
root, use a supported Python with venv/pip and an approved package index:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . wheel==0.48.0
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -v
```

Stop on setup or test failure. The full suite needs local loopback sockets and
native build capability. The explicit wheel tool is needed by the offline,
non-isolated packaging test; it is not an extra application-user requirement.
Tests use the gitignored `.artifacts/` directory (or
`WEAVEM_ARTIFACTS_DIR`) and isolate Prefect state. No second machine is required
for local tests; separate GitHub jobs verify cross-runner native handoff.

The [cross-project fixture](../../examples/local-cross-project/README.md) is
maintainer test material, not the official first-project tutorial.

## Maintenance procedures

- [Private alpha release runbook](releasing.md).
- [0.1.0a2 release](https://github.com/thtkha/weavem/releases/tag/v0.1.0a2).
- [0.1.0a2 release CI](https://github.com/thtkha/weavem/actions/runs/40339054745):
  supported Python 3.12–3.15, latest-stable gate, and separate-runner native handoff
  succeeded. This is bounded Ubuntu x86_64 evidence, not universal portability.
- [Native header maintenance](native-headers.md).

Do not move published tags or overwrite release assets. A documentation correction
to current source does not modify the documentation embedded in an older tag.
The user docs state the package behavior they cover; future release notes should
link to that release's documentation tree.

## Maintain the user documentation

Keep a single Markdown source tree with the [user index](../users/index.md) as navigation.
Use relative file links, stable headings, complete file examples, and explicit
working directories. A future website should render the same sources without
rewriting tutorials or creating a separate LLM manual.

CLI/SDK and metadata field semantics belong in the [reference](../users/reference.md)
and [artifact contract](../users/artifact-contract.md). Tutorials should link to those
contracts, not maintain alternate definitions. Mark unsupported features as such;
do not document plans as shipped functionality. Keep dated reports historical.

The authoring and native tutorials contain HTML comments marking executable
examples. `weavem-run` marks a Bash block; `weavem-file: relative/path` marks file
contents to write in the current tutorial directory. Unmarked blocks illustrate
concepts or directory trees. These markers do not change how people read Markdown.

The documentation verifier executes those blocks, not a duplicated example.
Activate a separate environment with the wheel installed, **not** the editable
contributor environment. Set `WEAVEM_WHEEL` to the absolute path of that same
wheel. From the checkout root, use a new, absent evidence directory:

```bash
mkdir -p .artifacts
python -I scripts/verify-user-docs.py --docs "$PWD/docs" \
  --wheel "$WEAVEM_WHEEL" --work-dir "$PWD/.artifacts/user-docs-check"
```

Expected: JSON with `"status": "passed"` and a consumer native result of
`"hello world"`. On failure, inspect `result.json`, `tutorial.stdout`, and
`tutorial.stderr` in that evidence directory; correct the failure and choose a
new directory for the next run. Do not overwrite retained evidence. Initial
consumer environment installation needs package-index access or a complete
offline wheelhouse.
Retain verification evidence under `.artifacts/`; do not count a source import
as installed-release verification. CI executes the same tutorial against its
single candidate wheel in the existing installed-wheel verification lanes.

When changing a command, metadata field, public API, release support policy, or
example identity, update its canonical documentation and rerun the corresponding
checks. The docs for a release must describe the released behavior, not future work.

## Project history

Use the [historical records index](../project/history/index.md) for previous
simulations, failed trials, compatibility investigations, and release evidence.
Those records are preserved for review, not maintained as current procedures.

For framework defects, use a [private repository issue](https://github.com/thtkha/weavem/issues)
with the package version, Python version, reproduction, and redacted logs. Do not
include tokens, credentials, or customer data in test fixtures or reports.
