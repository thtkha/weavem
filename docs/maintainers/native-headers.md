# Native header maintenance

**Audience: framework maintainers.** Application developers should use the
[native authoring guide](../users/native-authoring.md); they do not prepare or
replace Weavem's bundled headers.

## Maintaining the header bundles

`scripts/prepare-native-headers.py` is a maintainer tool, not something an author
runs. It must run with the target interpreter and consume already verified upstream
archives, original headers, generated `pyconfig.h`, and license text. It checks
archive hashes, normalizes tar metadata, records the runtime configuration, and
preserves header contents. It neither configures a guessed ABI nor downloads
anything. Each bundle records its exact upstream URL and checksum.

New Python support requires an ordinary dependency install, a verified header
source, full tests, installed-wheel author/consumer verification, and an updated
support matrix. Changing `requires-python` alone is not evidence of support.

The [artifact contract](../users/artifact-contract.md#native-build-provenance-and-binary-hygiene)
defines the current build provenance and binary-hygiene boundary.
[Earlier native verification records](../project/history/native-history.md)
retain the original measurements and provenance notes; they are not current
instructions for selecting a release's supported interpreters.

## References

- [Python 3.15 stable release](https://www.python.org/downloads/release/python-3150/).
- [Prefect package metadata](https://pypi.org/project/prefect/).
- [Zig Python packaging](https://github.com/ziglang/zig-pypi).
- [Python build standalone](https://github.com/astral-sh/python-build-standalone).
- [CPython ABI compatibility](https://docs.python.org/3/c-api/stable.html).
- [Python sysconfig](https://docs.python.org/3/library/sysconfig.html).
