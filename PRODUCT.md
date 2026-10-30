# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Developers and data-oriented flow authors. Developers author Python tasks; visual
users compose explicit parameters and connections without implementing UI widgets.

## Product Purpose

A local-first, code-first task and flow framework. The editor is another authoring
surface for ordinary project Python, not a separate execution engine or mandatory
pipeline service. Success is save/run/reopen parity with CLI and Python.

## Positioning

Reusable tasks and flows can integrate with existing software and Prefect rather
than requiring a central workflow platform. Weavem has runtime dependencies; this
is not a claim of zero installed dependencies.

## Operating Context

This is an unreleased desktop-browser editor experiment. A local bridge selects
one trusted project, reads bindings, saves supported Python flows, and executes
through the normal loader. Static review previews are non-executable.

## Capabilities and Constraints

Task catalog, graph authoring, advisory Python interface hints, explicit argument
and upstream-field mapping, bounded undo/redo, saved flow execution, structured
errors, and bounded result inspection. Unsupported Python remains source-only
rather than being silently rewritten. No new orchestration, accounts, publication,
collaboration, or mobile authoring is introduced by this experiment.

## Brand Commitments

Weavem terminology is tasks and flows. The practical experiment preserves the
owner-approved visual identity; calm and expressive alternatives have explicit
permission to depart from it. See DESIGN.md for actual visual decisions.

## Evidence on Hand

DESIGN.md, ui/README.md, examples/editor-local, metadata fixtures, and source tests.
Synthetic preview data must be identified as synthetic. No customer claims,
performance benchmarks, or production-readiness claims may be invented.

## Product Principles

- Python remains authoritative and runnable without the editor.
- Unknown interfaces stay unknown; observed examples are not guarantees.
- Preserve drafts and unsupported source; execution is not undoable.
- Show truthful state and provenance, not decorative confidence.

## Accessibility & Inclusion

Keyboard access, visible focus, readable contrast, reduced motion and forced-color
fallbacks. Desktop authoring starts at 1100 CSS pixels; narrow screens retain a
clear notice and export recovery, not a claim of mobile editing support.

## Confirmation

Captured from repository contracts and the owner's approved 2026-10-30 lab plan.
No new product positioning or platform was inferred from aesthetic experiments.
