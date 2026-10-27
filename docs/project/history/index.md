# Historical reports and evidence

[Project records](../index.md) · [Current user manual](../../users/index.md)

These are preserved records for the project owner and retrospective review.
Their versions, branch names, pending gates, recommendations, and artifact paths
refer to the revisions they describe. Do not follow them as current setup or
release instructions. The documents keep their original findings; only location,
navigation links, and explicit archive notices changed during organization.

## Developer experience and acceptance

| Record | Context | Outcome recorded |
| --- | --- | --- |
| [Native developer simulation](developer-simulation.md) | Original native author-to-recipient journey; execution date recorded inside | Commands, native build failures, handoff evidence, and the requested pros/cons assessment |
| [Blind acceptance — 2026-10-21](blind-acceptance-2026-10-21.md) | Frozen candidate and independent project workflow | A runtime dependency blocker; retained as a failed trial |
| [Runtime compatibility rerun — 2026-10-21](runtime-compatibility-acceptance-2026-10-21.md) | Follow-up to blind acceptance | Compatibility repair followed by a cache-polluted flow handoff failure |
| [Cache-tolerance acceptance — 2026-10-21](cache-tolerance-acceptance-2026-10-21.md) | Follow-up to the handoff failure | Passing raw-folder handoff and recorded business cases |

Read the three acceptance reports in that order. Later repairs explain the
earlier failures without making those failures disappear.

## Native and release evidence

| Record | Context | How to interpret it |
| --- | --- | --- |
| [Native verification history](native-history.md) | Earlier native tooling, interpreter, and handoff checks | Preserves the complete former maintenance-history document; current header maintenance belongs in the [maintainer guide](../../maintainers/native-headers.md) |
| [Compatibility and release readiness — 2026-10-26](release-readiness-2026-10-26.md) | Local matrices, CI revisions, first-alpha preparation, and remaining gates at that time | Bounded evidence for the named commits, not the current release status |

Published release records remain on GitHub:

- [0.1.0a1](https://github.com/thtkha/weavem/releases/tag/v0.1.0a1), the first alpha.
- [0.1.0a2](https://github.com/thtkha/weavem/releases/tag/v0.1.0a2), the release
  covered by the current manual, with its own
  [successful tagged workflow](https://github.com/thtkha/weavem/actions/runs/40339054745).

An old report saying that publication or a CI gate is pending is a historical
statement, not a contradiction of a later completed release. Local logs,
workspaces, and diagnostic artifacts referenced in these records remain
gitignored under `.artifacts/`; moving a report does not move or delete them.
