# Expressive Impeccable candidate

**Branch:** `experiment/impeccable-expressive` · **Status:** isolated owner-review
candidate, not selected or merged into the continuation branch.

## Baseline and ownership

- Started from practical checkpoint `d193682`, including the approved lab plan,
  product context, and practical interaction fixes.
- Candidate implementation: `7265cd0`; shared practical followups were
  cherry-picked as `c0c73e0` (from `14499b4`) and `976b47e` (from `3f983af`).
- This lane owns the expressive frontend, candidate `DESIGN.md`, and this handoff.
  The main worktree, published package, backend, and public flow formats are
  unchanged. Leader owns the combined lab report, static preview, and promotion.

## What to review

The blue-black/cyan **instrument desk** emphasizes the saved flow name, compact
history controls, a clear execution focal point, larger task titles, and a
readable inspector. The library, canvas, and inspector remain resizable; all
authoring, result, connection, import/export, history, and execution controls
retain the same model and semantics.

`Motion lab` is an explicit, opt-in native dialog. It illustrates a whole
upstream result becoming the `customer.email` input. Native View Transitions
morph only the sample value. It never calls a run API or reads/writes the
author's graph. Unsupported and reduced-motion paths work instantly; Escape,
background inertness, focus restoration, and normal keyboard interaction use
native dialog behavior. The actual editor has no decorative animation loop.

### Impeccable command mapping

| Command | Demonstration | Judgment |
| --- | --- | --- |
| `bolder` | Larger task identity and decisive execution hierarchy, not gratuitous effects. | Reconsider after owner comparison. |
| `colorize` | New semantic blue-black/cyan token palette; no gradients or fake status. | Reconsider: subjective replacement of the approved olive palette. |
| `layout` | Flow-name row, compact history group, separated execution, calmer inspector rhythm. | Keep the useful grouping if it wins task-based review. |
| `typeset` | 16px task titles, 14px section titles, 12px prose/controls, 11px metadata. | Keep legibility improvements, assess density at 1100px. |
| `animate` | User-triggered native field-value morph in the isolated sample. | Keep as a demonstration, not a requirement for ordinary mapping. |
| `delight` | The sample makes an otherwise abstract field mapping directly understandable. | Reconsider as optional teaching; avoid interrupting experts. |
| `overdrive` | Native View Transition resizing/clipping with instant fallback and reduced motion. | Reject as default workbench spectacle; useful browser-capability trial. |
| `polish` | Computed control boundaries, placeholder contrast, text floor, semantic tokens, and full interaction regression checks. | Keep quality gates independently of the new look. |

The motion direction was constrained by the approved isolated experiment brief:
a meaningful field/connection transition, not a shader, perpetual moving wires,
new runtime, sound, or device access. This was not a new aesthetic approval.

## Verification and evidence

Evidence root on the authoring machine:
`.artifacts/node-editor/impeccable-lab/evidence/expressive/` in the original
worktree, not this worktree's own artifact root.

- Unit tests: **40 passed** (`unit-final.log`).
- TypeScript, ESLint, and frontend build pass; final bundle is approximately
  476 kB JavaScript / 149 kB gzip. No dependency was added.
- Initial complete Chromium suite: **61 passed** (`full-browser.log`), covering
  ordinary graph editing, source-only flows, histories, mappings, runs, scrollbar
  mechanics, panel geometry, fullscreen, and three new expressive checks.
- After both shared followups and the semantic raw-JSON assertion update, the
  final complete Chromium suite passes **64/64** (`full-browser-final.log`,
  59.1 seconds). `full-browser-shared-token-failure.log` preserves the earlier
  63-pass/1-failure run caused only by a practical-palette literal in that new
  shared test. It now probes `--color-panel` and `--color-ink` instead.
- Manual rendered inspection captured `editor.png` and `motion-lab.png` at
  1600×1000; final screenshots were refreshed after shared fixes. Additional
  `forced-colors.png` captures the system-color path. `visual-final.json` records
  a running native transition animation, zero page errors, and successful focus
  return. The sample selected-field endpoint and static fallback work.
- Final source detector returns **[] / exit 0** (`detector-source.json`).
- Rendered detector after the cascade fix reports only `overused-font` for the
  existing local Inter/system stack, not a low-contrast or tiny-text defect.
  This is documented as an intentional product-UI choice, not suppressed.
- Computed toolbar/search borders are `rgb(113, 137, 155)` against
  `rgb(27, 43, 59)`, not merely a stronger unused token. The earlier failed
  cascade is preserved in `detector-before-layer-fix.json`.
- Palette-specific existing browser assertions now resolve semantic tokens via
  a browser color probe. Port size (13px), wire alignment, control heights,
  interaction expectations, and native scrollbar geometry stay strict.

Two setup mistakes are preserved rather than presented as red/green proof:
`before.log` timed out because the new worktree had no built `dist`; it did not
reach the intended missing-showcase assertion. `build-wrong-cwd.log` records an
npm invocation from the repository root; it was corrected with `--prefix ui`.
The showcase regression therefore has fresh passing behavior evidence, not a
claimed initial behavior-failure run.

## Limitations and next action

This lane tested Chromium, not Firefox, Safari, a screen reader, or physical
touch hardware. It did not rerun real native Python execution; the leader owns
cross-interface parity evidence. The desktop editing cutoff remains 1100 CSS
pixels; narrower windows retain export recovery, not mobile authoring.

The isolated skin intentionally overrides existing unlayered toolbar rules from
a separate stylesheet. Promotion would require deciding whether to fold these
styles into the shared system; do not prematurely refactor the continuation UI
to adopt an unselected aesthetic. The workbench should remain useful with the
Motion lab removed entirely.

Leader serves this branch's built `ui/dist/` at its assigned static preview URL.
No long-lived preview was left running by this lane. Compare with practical and
calm on the same fixture and viewport, then let the owner select the changes to
keep. Do not merge, publish, or infer that the experimental palette is approved.
