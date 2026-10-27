# Weavem

Weavem is a local-first Python framework for developing reusable **tasks** and
composing **flows** with Prefect. Develop against editable source, then build and
publish immutable releases to an ordinary folder for reuse in other projects.

- A **task** is a callable with metadata and behavioral tests, released as Python
  or a native extension (`.so`).
- A **flow** composes tasks and application logic. A published flow pins its tasks.
- `task-store/` holds published releases. `.artifacts/` holds build/test work and
  unpublished candidates. Both locations are configurable.

## Start using Weavem

**[Official user documentation](docs/users/index.md)** is the shared starting point
for developers and coding assistants. You do not need to clone this repository
to use a released wheel.

1. [Install and check your environment](docs/users/getting-started.md).
2. [Create, test, run, publish, and reuse a project](docs/users/authoring-guide.md).
3. [Build a native task release](docs/users/native-authoring.md).

Current documented release: **[0.1.0a2](https://github.com/thtkha/weavem/releases/tag/v0.1.0a2)**,
a private GitHub alpha, not a public PyPI package or a stable API.
Supported environment: standard GIL-enabled, non-debug **CPython 3.12–3.15 on
Linux x86_64 with glibc 2.28+**. See [support limits](docs/users/limitations.md).

Weavem supplies its native compiler and verified headers. Initial installation
needs access to its Python dependencies, or a complete offline wheelhouse.
Task-specific Python packages and shared libraries remain your responsibility.

No Weavem account, registry, Docker, or central server is required. Prefect may
start a local loopback service and write local state. Task code is **not sandboxed**;
run only code from publishers you trust. A checksum detects changed bytes, not
publisher identity.

## Documentation

- [Developer users](docs/users/index.md) — installation, authoring, reuse,
  reference, and troubleshooting. This is the official user manual.
- [Maintainers and contributors](docs/maintainers/index.md) — changing, testing,
  and releasing the framework.
- [Project owner](docs/project/index.md) — project context and preserved
  historical reports, separate from current instructions.

See the [documentation directory](docs/index.md) for the audience map and filing rules.

## Getting started after cloning

If your goal is to **use** Weavem, follow the [release installation guide](docs/users/getting-started.md).
If your goal is to **change Weavem itself**, follow the
[contributor setup](docs/maintainers/index.md#work-on-the-framework).
Cloning is not a task registration or runtime requirement.

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
