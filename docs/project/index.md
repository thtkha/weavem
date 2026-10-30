# Project records

**Audience: the project owner.** Read this section to understand what was tried,
what was observed, and why the project reached its present state. It is not a
second user manual or a contributor setup guide.

For current usage, open the [user documentation](../users/index.md). For changing
or releasing the framework, open the [maintainer documentation](../maintainers/index.md).

## Current orientation

The user manual currently covers **0.1.0a2**, distributed as a private GitHub
alpha rather than through public PyPI. The [package metadata](../../pyproject.toml)
is the source of truth for the checkout's version and declared dependencies;
the [release](https://github.com/thtkha/weavem/releases/tag/v0.1.0a2) records its
published assets.

The framework is local-first: editable development is separate from immutable
task/flow publication, and an extracted filesystem store is sufficient for reuse.
Native authoring tools are default dependencies. See the
[current support limits](../users/limitations.md) for the actual shipped boundary,
not the recommendations in an earlier experiment.

## Active branches and decisions

The [branch status and continuation index](branches.md) records authoritative
work, implementation lanes, historical branches, the unselected inspector
alternative, review gates, and decisions that must survive agent handoffs.

## Reports and evidence

The [node-editor prototype](node-editor-prototype.md) records the current
interactive-UI experiment. It is not part of the released Python user manual.

The [history index](history/index.md) organizes the preserved simulations,
acceptance trials, compatibility investigations, and release-readiness evidence.
Keep successes, failures, and original evidence paths together; a later passing
run does not erase an earlier failed one.

New owner-facing planning notes or decision records belong in this section.
Separate proposed work from shipped behavior, and add a dated entry to the
history index when an evaluation is complete. Do not promote a historical
recommendation to current policy merely by moving its file.

- [Impeccable comparison lab](impeccable-lab.md) — isolated editor experiments and verification.
