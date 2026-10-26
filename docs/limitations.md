# Supported behavior and limitations

This is a local MVP, not a complete task ecosystem. Its API and artifact schema are
still provisional.

## Supported environment

- standard, GIL-enabled CPython 3.12–3.15 on Linux x86_64 with glibc 2.28+.
- Python and Cython backends, with one implementation module and one exported callable
  per task artifact.
- Exact task versions and a local filesystem store, including independently copied
  or extracted stores.
- Real Prefect tasks and flows. Dependency/tool versions are specified in
  [`pyproject.toml`](../pyproject.toml).

Native artifacts are environment-specific. A consumer needs a matching interpreter/
platform and the declared runtime dependencies, but does not need the native compiler
or the author's source project.

## Packaging and storage

- Dependencies are checked, not solved, downloaded, or bundled. Environment provisioning
  remains separate from task distribution.
- Multi-module task packages, bundled resources, task-pack version semantics, version
  ranges, and general dependency solving are not implemented. Release bindings do
  record exact manifest digests; this is not a Python-environment lockfile.
- Storage can be replaced through the injected protocol, but no remote adapter, plugin
  registry, archive loader, signing service, or license system ships with the MVP.
- Released task versions must not be overwritten with different bytes.

Python artifacts contain readable Python. Native compilation is not cryptographic
source protection. Private distribution means files need not be published—not that
consumers cannot inspect them.

## Execution and trust

- Task code is trusted code, not a sandbox. Do not run artifacts from untrusted sources.
- Hash validation detects altered bytes; it does not establish publisher authenticity.
- There is no guarantee against adversarial concurrent changes to local files. Keep
  stores read-only to consumers when stronger operational isolation is needed.
- Prefect owns orchestration, configuration, and telemetry settings. Weavem does not
  replace its scheduler, workers, states, retries, or deployments.
- Persistent Prefect result caching is not verified for the lazy adapter. Weavem defaults tasks to `NO_CACHE`. If explicitly enabled, a cache hit skips current policy/integrity checks, and custom
  cache keys must distinguish exact task identities and versions.

## Not included

There is no built-in domain task library, visual editor, CI generator, deployment
automation, gateway, or Weavem control plane. Public release, license/ownership
confirmation, broader platform support, and production Prefect verification remain
separate follow-up work.

## Flow release boundaries

- Single-file synchronous flow exports only; async/generator flows and packaged
  helper modules/resources are not supported by the flow lifecycle commands.
- Only the local Prefect `ThreadPoolTaskRunner` is supported for released flows.
  Distributed/delayed execution and context transport to other processes are not
  supported. Nested released-flow composition is not part of this first story.
- Declared flow task dependencies must already be published and must exist in the
  destination store. Weavem never auto-publishes them or substitutes local source.
- Arbitrary Python cannot be statically proven to declare every dependency or to
  avoid external services. Tests and runtime guards enforce the framework's alias
  boundary, not a sandbox around application code.
- Local Python source changes are picked up on subsequent task invocations; native
  source is compiled once per source/config digest per process, without publication.
  Caches are process-local and grow with distinct source versions until exit.
- RustFS, remote release repositories, automated publication, warehouse metadata
  syncing, and billing remain outside this implementation. GitHub Actions
  verification passed for commit `14dfe1e`; every release candidate still needs
  passing CI for its exact revision.

## Managed native authoring

See [native authoring](native-authoring.md) for header-signature, glibc, compiler,
and compiled-test boundaries. Header bundles are not inferred from version alone.
Free-threaded, debug/trace-ref, musl, Windows, and macOS builds are unsupported.
The current dependency pins are Prefect 3.9.0 and FastAPI 0.143.0; the earlier
Python 3.15 dependency blocker is resolved in local verification. See the
[current compatibility evidence](release-readiness-2026-10-26.md) for local and
GitHub CI results and the exact-revision release rule.
