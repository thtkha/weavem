# Troubleshooting

[Documentation index](index.md) · [Reference](reference.md) · [Support limits](limitations.md)

Use the Weavem and Python versions installed in the failing environment. Run
commands from the intended project root (the folder with `weavem.toml`) unless
a section says otherwise. Stop on a failed check; do not bypass integrity or
compatibility checks to get a green result.

Start with these non-mutating checks in the activated environment:

```bash
python --version
python -m pip --version
python -m pip check
python -c 'from importlib.metadata import version; print(version("weavem"))'
```

Expect a supported interpreter, pip inside your environment, no broken package
requirements, and the intended Weavem version. If you need help, send the failing
command, these version results, and redacted error text to your Weavem maintainer
or a [repository issue](https://github.com/thtkha/weavem/issues). Do not publish
credentials, task payloads, or customer data.

## Python environment

**`No module named venv` or `ensurepip` unavailable during environment creation**

Your Python distribution is missing environment support. Stop before installing
Weavem. Follow your distributor's instructions to add venv support matching the
interpreter, or use a supported Python distribution that includes it. OS package
installation is an explicit administrator action, not a Weavem or pip step.
After repair, rerun the environment-creation command, then check pip before
continuing. Preserve existing environments if they contain work you need.

**`No module named pip` in an otherwise created environment**

From the workspace containing `.venv`, try:

```bash
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip --version
```

If `ensurepip` is also absent, repair the base interpreter as above. Never fall
back to `sudo pip`, use `--ignore-requires-python`, or copy another machine's venv.
Python documents [venv](https://docs.python.org/3/library/venv.html) and
[ensurepip](https://docs.python.org/3/library/ensurepip.html).

**`weavem: command not found` or an unexpected installed version**

Activate the intended environment, then repeat the initial checks. `python -m
weavem --help` uses that Python's installation even when shell command lookup is
wrong. Install the downloaded wheel into that environment if it is missing.

**pip cannot resolve or download dependencies**

Check access to your approved package index and the full supported platform/Python
combination. An offline wheelhouse must contain all transitive dependencies, not
only the Weavem wheel. Do not disable TLS verification or paste index credentials
into logs. Ask your environment administrator if access is restricted.

## Project selection and bindings

**A task/flow is missing, or the wrong store is selected**

Confirm the working directory and `weavem.toml`. Global `--project PATH` belongs
before the subcommand, for example `weavem --project /path/to/project task list`.
That path is illustrative: replace it with your project. Review explicit options,
`WEAVEM_STORE`, `WEAVEM_ARTIFACTS_DIR`, and project configuration in that order;
see [configuration precedence](reference.md#configuration).

**Creation refuses an existing path**

Scaffolding does not overwrite your files. Edit the existing definition, or choose
a genuinely new name. Do not delete an existing project just to rerun a tutorial.

**A local alias cannot find its source**

Fix its explicit local binding using `weavem task use ALIAS --path PATH`, with
both placeholders replaced. The source must remain inside the selected project.
If you intended a released task instead, explicitly choose its exact release.
Weavem does not silently fall back from missing source to published code.

**A generated flow returns `null`**

The generated flow is empty. Implement the flow, invoke the selected task alias,
list that alias in the flow sidecar's `tasks`, and update its tests. Follow the
[complete tutorial](authoring-guide.md); `flow new` does not auto-wire tasks.

## Tests and builds

**Validation passes but a test fails**

Validation is not proof of behavior. Read the failing assertion or import error,
fix the implementation/test or provision the declared dependencies, then rerun
`task test` or `flow test`. Do not replace a behavioral test with an import-only
check to bypass the failure.

**Source tests pass but a native build fails**

Run `weavem doctor` from the selected project. It writes temporary probe work and
compiles/imports a native module. If doctor succeeds, inspect the build's failure:
compiled behavior, source-only test assumptions, unsupported imports, or modified
payload bytes may still fail release verification.

**Missing or empty tests**

Tasks need unittest tests under their task folder's `tests/`; flows need tests
under `tests/flows/FLOW_NAME/`. At least one test must be discovered. Keep test
imports and the metadata's `export` consistent with the implementation.

## Native builds

**Compiler missing, no matching headers, or unsupported interpreter**

Keep the complete `weavem doctor` error. Confirm the supported standard CPython,
architecture, ABI, and glibc requirements. Reinstall Weavem with its declared
dependencies if its managed compiler is missing; installing with `--no-deps`
is not a complete setup. A custom distribution may require its own complete
matching headers. Do not invent configuration headers or silently install OS
packages. See [native authoring](native-authoring.md).

**Compiled tests fail although Python tests pass**

The same tests are executed against the compiled export without the Python
implementation available as a fallback. Remove assumptions that require the
implementation to be a `.py` file, or fix native-incompatible behavior. Preserve
meaningful behavioral assertions. This failure blocks the candidate deliberately.

## Running flows

**Prefect cannot start, bind a port, write its state, or contacts an unexpected server**

Local flows may need a temporary loopback server and a writable `PREFECT_HOME`.
Sandboxed terminals can deny loopback sockets. Use an authorized local execution
environment rather than opening a public listener. For a local-only project,
follow the [isolated tutorial settings](getting-started.md#3-keep-tutorial-state-local);
for an intentional remote Prefect deployment, follow your organization's Prefect
configuration instead. Weavem does not override those settings for you.

**A task reports missing or mismatched dependency versions**

Install the exact distribution pins declared by the trusted task using your
approved index/wheelhouse, then rerun the flow. Weavem checks packages but does
not install them on invocation. If two tasks require conflicting versions, use
separate environments/projects or publish compatible task versions; do not edit
release manifests to disguise the conflict. See [dependency provisioning](reference.md#provision-task-dependencies).

## Publication and reuse

**A flow cannot build with a local/unpublished task**

Publish every task candidate, select each exact release with `task use --release`,
then build the flow again. The destination store must also contain its pinned
releases before flow publication. The framework does not auto-publish dependencies.

**An existing version has different bytes**

Published releases are immutable. Retry using the original candidate, or increment
the author metadata's version and build a new candidate. For a flow upgrade,
select the new task release and assign the flow a new version too. Never delete
or overwrite a published version merely to make publication succeed.

**A copied store reports integrity, missing payload, or manifest-pin errors**

Stop execution. Re-copy the complete store from its trusted source and verify
that the selected task/flow versions exist. Do not patch payload hashes, manifests,
or pinned digests to accept changed bytes. A ZIP must be extracted first.

**An artifact works for its author but not its recipient**

Check the recipient's Python minor, platform/ABI, exact task dependencies, and any
required shared libraries. Native binaries do not become universal by copying
them. Build a distinct compatible artifact for the recipient if needed, without
overwriting another release. Weavem's pure-Python wheel tag is not a claim that
its compiled task artifacts work on every operating system.

## Cleanup and recovery

Keep source, tests, and published `task-store/` releases. Retain unpublished
candidates you still intend to promote. Once no longer needed, build work and
caches can be removed from their configured work locations; no automatic cleanup
is required by the user guides. Before removing anything, check configuration so
a shared store is not mistaken for disposable work.

A failed command is not a successful publication. Read its error and inspect the
store before retrying. Retrying the same candidate is supported; rebuilding and
publishing different bytes under the same version is not.
