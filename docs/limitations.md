# Supported behavior and limitations

This is a local MVP, not a complete task ecosystem. Its API and artifact schema are
still provisional.

## Supported environment

- CPython 3.12.x on Linux x86_64.
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
  ranges, and lockfiles are not implemented.
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
- Persistent Prefect result caching is not verified for the lazy adapter. Keep it
  disabled in this MVP: a cache hit skips current policy/integrity checks, and custom
  cache keys must distinguish exact task identities and versions.

## Not included

There is no built-in domain task library, visual editor, CI generator, deployment
automation, gateway, or Weavem control plane. Public release, license/ownership
confirmation, broader platform support, and production Prefect verification remain
separate follow-up work.
