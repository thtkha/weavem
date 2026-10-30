# Impeccable comparison lab

Status: **in progress**. Baseline: `f0a6fa6` on `feature/editor-experience`.
This is owner-facing experiment evidence, not the released user manual.

## Approved result and boundaries

Compare original, practical improvements, calmer and expressive working editors.
Practical preserves approved palette and workbench behavior. Alternatives may
explore different color, typography, layout, density, and motion. No merge to
main/prototype/continuation, no push/release, no production data, no exposed
executable bridge. Experimental decoration must not pretend a task executed.

## Execution and regression plan

1. Lock modal keyboard behavior, hidden file-input tab order, missing/null result
   distinction, polling serialization and history isolation with focused tests.
2. Correct one issue at a time; preserve original editor and public Python formats.
3. Compare shared task/parameter/result/error fixtures across isolated worktrees.
4. Verify typecheck, lint, units, frontend builds, browser interactions, contrast,
   width/zoom fallback, forced colors and reduced motion; then source/rendered
   Impeccable scans. Real Python parity uses only a disposable local sample.
5. Record limitations and each command's actual use, not merely read its name.

## Locations and branch ownership

- Original: main working directory; remains on `feature/editor-experience`.
- Practical: `experiment/impeccable-practical`.
- Calm: `experiment/impeccable-calm`, created from practical checkpoint.
- Expressive: `experiment/impeccable-expressive`, same checkpoint.
- Worktrees/evidence: original `.artifacts/node-editor/impeccable-lab/`.
- UI performer owns practical UI/tests; design reviewer owns
  `impeccable-lab-design-review.md`; leader owns integration, tools and this report.

## Results

Pending verification. Do not treat the planned command matrix as completed work.
