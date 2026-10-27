# Supported behavior and limitations

Weavem is a local-first framework for versioned task and flow artifacts. This
page defines its current support boundary. It does not weaken the release
integrity rules in the [artifact contract](artifact-contract.md).

## Supported environment

- Standard, GIL-enabled, non-debug CPython 3.12–3.15.
- Linux x86_64 with glibc 2.28 or newer.
- Python and Cython task backends, one implementation module, and one exported
  callable per task release.
- Exact task and flow versions in local filesystem stores, including a copied or
  extracted store.
- Real Prefect tasks and flows. Local `flow run` may use Prefect's local
  loopback services and needs a writable local state/work location.

Native artifacts are environment-specific. A recipient needs a compatible Python
minor/platform and the task's declared runtime dependencies. They do not need the
native compiler or the author source project merely to run an existing release.

## Deliberate boundaries

- A task release packages one implementation module. Multi-module task packages,
  bundled resources, and arbitrary application-package layouts are unsupported.
  Put internal classes and methods in that module and expose a module-level
  function.
- A flow release packages one synchronous Python flow module. Async/generator
  flows, helper modules/resources, nested released-flow composition, and
  distributed/delayed flow execution are unsupported.
- Released flows require Prefect's local `ThreadPoolTaskRunner`; Weavem does not
  support context transport into remote workers for those pins.
- Dependencies are exact installed-distribution checks, not a solver, download
  mechanism, or lockfile. Extras, markers, version ranges, direct URLs, bundled
  environments, and automatic installation are unsupported.
- Stores are local folders. Weavem ships no remote adapter, registry, archive
  loader, signing service, license system, control plane, visual editor, domain
  task library, deployment system, or billing/warehouse integration.
- An archive can transport a release store but must be extracted before use.
  Weavem does not load tasks or flows directly from ZIP files.

## Integrity is not security isolation

- Task and flow code is trusted code. It runs with the consumer process's
  privileges and is not sandboxed.
- SHA-256 validation detects altered bytes; it does not authenticate who built
  them or prove their behavior is safe.
- The optional task policy is an allow/deny hook, not a sandbox or signature
  system.
- Metadata discovery (`info` and `Project.metadata()`) does not import payloads,
  but it also does not prove payload integrity, ABI compatibility, dependencies,
  or safety.
- Local publishing coordinates cooperative writers with locks and atomic rename.
  It does not protect against malicious filesystem actors, distributed filesystem
  semantics, or crash-durable transactions.

Use a trusted distribution channel, verify its release checksums where supplied,
and restrict consumer write access to release stores when that is appropriate for
your environment.

## Execution and caching

- Prefect owns orchestration, deployments, workers, states, retries, and telemetry
  configuration. Weavem does not replace those systems.
- Weavem tasks default to Prefect `NO_CACHE`. If you explicitly enable result
  caching, a cache hit can skip a new task invocation and therefore its current
  integrity/policy checks. Persistent caching is outside the supported lane.
- Runtime checks protect the declared task-alias boundary for flows but cannot
  statically prove every possible branch of arbitrary Python avoids external
  services or undeclared dependencies.
- Editable Python source is loaded again on subsequent invocation. Editable Cython
  source is compiled once per source/config digest per process; process-local
  caches grow with distinct edits until that process exits.

## Lifecycle boundaries

- A flow cannot be built until every declared task alias selects an existing
  published release. Weavem never auto-publishes a local task or silently
  substitutes a local source task.
- A flow cannot be published unless its exact pinned tasks exist in the destination
  store. It never copies dependencies implicitly.
- Published task and flow versions are immutable. Reuse the original candidate for
  an identical retry; use a new version for changed bytes.
- Native builds do not promise byte-for-byte reproducibility across builds or
  toolchains. Build once, retain the candidate, and publish that exact candidate.

## Not supported yet

Windows, macOS, ARM, musl, free-threaded Python, debug/trace-reference CPython,
and arbitrary Python implementations are outside the supported runtime lane.
See [native authoring](native-authoring.md) for native build diagnostics and
header/compiler detail.

For work on the framework itself, see [maintainer documentation](../maintainers/index.md).
Dated test and release reports are separate [project records](../project/history/index.md),
not additional runtime guarantees.
