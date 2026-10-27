# Weavem documentation

Choose the section for what you are doing. These audiences share one repository,
but they do not share one reading order.

| Audience | Start here | What belongs there |
| --- | --- | --- |
| Developers using Weavem | [User documentation](users/index.md) | Installation, tasks and flows, publishing/reuse, native builds, reference, and troubleshooting |
| Maintainers and contributors | [Maintainer documentation](maintainers/index.md) | Framework development, tests, release procedures, native tooling, and documentation maintenance |
| Project owner | [Project records](project/index.md) | Project context, evaluation reports, release evidence, and historical decisions |

## Organization rules

- `users/` describes the supported released behavior. It is the official manual
  for human developers and coding assistants, without internal progress reports.
- `maintainers/` explains how to change and maintain Weavem itself. Link to the
  user reference instead of duplicating its contracts.
- `project/` is the owner-facing record of the project's evolution. Its
  `history/` directory preserves dated observations, including failures and
  superseded recommendations; those are not current usage instructions.
- Put a new document in its audience's directory and link it from that section's
  index. Preserve historical reports rather than rewriting them to look current.
- Root-level `LICENSE`, `NOTICE`, and `TRADEMARKS.md` remain the repository's
  canonical legal files. Documentation organization does not change access:
  owner-facing records are still visible to everyone with repository access.

The Markdown files remain canonical. A future documentation site can present
these sections separately without maintaining another copy of the content.
