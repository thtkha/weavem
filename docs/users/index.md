# Weavem user documentation

Build a project locally, turn useful functions into reusable tasks, and compose
those tasks into flows. Publish only when you want an immutable version to reuse
or share. A folder is enough; there is no mandatory registry or Weavem server.

These official user docs describe **Weavem 0.1.0a2**. They are written for people
and are also the source of truth for coding assistants: use the same commands,
file conventions, and reference contracts. No separate AI setup or instruction
file is required. The API is alpha and may change in later releases.

## Start here

Read these pages in order for a complete first project:

| Page | You will finish with |
| --- | --- |
| [1. Install and check your environment](getting-started.md) | A working virtual environment and a native environment check |
| [2. Develop, publish, and reuse](authoring-guide.md) | A real task and flow, tested releases, and a separate consumer environment |
| [3. Build a native task](native-authoring.md) | A new compiled task version, a pinned flow, and verified `.so` reuse |

The example normalizes text using only Python's standard library. Names such as
`text.normalize` are examples, not built-in tasks or required framework names.
Follow all steps in order; scaffolding alone does not create finished behavior.

## Find an answer

- [Reference](reference.md): CLI commands, Python APIs, configuration, metadata,
  dependency provisioning, and errors.
- [Artifact contracts](artifact-contract.md): what a release contains, integrity
  checks, immutable publication, and pinned flow dependencies.
- [Troubleshooting](troubleshooting.md): symptoms, checks, and safe recovery.
- [Supported behavior and limitations](limitations.md): platform, packaging,
  orchestration, and security boundaries.

## The concepts in one minute

| Term | Meaning |
| --- | --- |
| Task source | Your editable implementation module, `task.toml`, and behavioral tests |
| Export | The callable named in task metadata; a function may call internal class methods |
| Alias | A project-local name explicitly bound to source or an exact task release |
| Flow source | A Python flow module, sidecar metadata, and behavioral tests |
| Candidate | A tested, built artifact retained for publication; not yet in the release store |
| Release | Immutable task or flow bytes identified by an ID and version |
| Store | A local folder containing released tasks and flows, including all pinned dependencies |

`validate` checks the definition. `test` runs authored source tests. `build`
creates a candidate and, for a native task, also tests the compiled export.
`publish` copies that candidate into a store without rebuilding it. Successful
metadata inspection alone does not prove that code is safe or runnable.

## Documentation conventions

- Commands state their starting directory. Use Bash and an activated environment.
- Complete file examples say which file to replace; placeholders and optional
  alternatives are explicitly labelled, not meant to be pasted blindly.
- Expected outputs and stop conditions are part of the procedure.
- Relative links work in the repository and in a downloaded Markdown tree.
- Current user instructions live in this directory. Framework contribution and
  project history have separate reading paths in the [documentation directory](../index.md).

The Markdown files are canonical. A future documentation website can render this
same tree; it must not introduce a second, divergent set of instructions.
