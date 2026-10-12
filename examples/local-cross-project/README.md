# Cross-project demonstration

This small fixture checks that one project can build tasks and another can execute
only the resulting artifacts. Its arithmetic functions are deliberately trivial;
they are not built-in framework functionality or a proposed application structure.

The author provides Python and native variants. Its configuration selects the publication destination
`consumer/task-store/`. The consumer resolves that visible local store without
importing implementation code from the author. Temporary build files go under the
repository's `.artifacts/tmp/` directory.

With Weavem installed and the native build prerequisites available, run from the
repository root:

```bash
for task in double native_double; do
  candidate="$(weavem --project examples/local-cross-project/author task build \
    "examples/local-cross-project/author/tasks/$task" | python -c 'import json,sys; print(json.load(sys.stdin)["root"])')"
  weavem --project examples/local-cross-project/author task publish "$candidate"
done
cd examples/local-cross-project/consumer
PREFECT_SERVER_ANALYTICS_ENABLED=false python flow.py
```

The flow returns `(42, 42)`, once from each backend. The IDs `demo.double` and
`demo.native_double` belong only to this fixture.

If these exact versions are already present, they can be consumed without rebuilding.
Do not overwrite published files with another build; native rebuilds need not produce
byte-identical binaries. For a changed task, update its source metadata version and
the consumer's corresponding pin.

For a private handoff, copy the complete built `task-store/` into another compatible
consumer project. No author source, GitHub connection, or registration step is needed.
See the main [README](../../README.md) for the general workflow and configuration.
