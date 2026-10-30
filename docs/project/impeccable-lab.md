# Impeccable comparison lab

Status: **implemented in isolated experiment branches; owner selection pending**. Baseline: `f0a6fa6` on `feature/editor-experience`.
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

Three working candidates exist. Preserve the practical correctness/accessibility
fixes independently of any visual selection. The calm candidate is a warm light
field-notebook treatment with a flatter task library. Expressive is a dark cyan
instrument desk with an opt-in field-mapping transition demonstration.

The practical candidate is the safest next integration candidate. Neither
alternative is automatically recommended over the approved identity; compare
density, readability and task clarity yourself. The motion showcase should stay
optional and is removable without affecting authoring.

## Command-by-command evaluation

Impeccable's design commands are agent playbooks, not twenty-four independent
code generators. The rows below identify the actual work performed or bounded
compatibility trial; a read reference is not claimed as a completed feature.

| Command | Experiment and deliverable | Initial decision |
| --- | --- | --- |
| `init` | Captured confirmed local-first/code-first product truth in PRODUCT.md using the approved brief and existing contracts. | Keep context; no new product interview was needed. |
| `document` | Merged extracted theme frontmatter and color/type sections into existing DESIGN.md, preserving its original contract; alternatives document their own worlds. | Keep accurate machine-readable context. |
| `shape` | Source review creates separate actionable practical, light/calm and expressive direction briefs. | Keep bounded briefs before editing. |
| `critique` | Independent source design assessment plus leader-rendered assessment below. | Useful for prioritization; not a WCAG certificate. |
| `audit` | Source detector, rendered Chromium detector and manual keyboard/contrast/correctness checks. | Keep rendered checks: source-only scan missed real defects. |
| `harden` | Shared accessible dialogs, failure visibility, tab order, result missing/null semantics and control boundaries. | Strongest immediate value. |
| `clarify` | Honest empty Last run state and actionable recovery wording. | Keep; do not invent unknown metadata. |
| `onboard` | Existing catalog/inspector guidance and first-run workflow copy, no modal tour. | Keep lightweight task-oriented guidance. |
| `adapt` | Supported desktop-width composition and narrow-screen export/notice checked; alternative layouts verified. | Keep desktop contract; mobile authoring remains outside scope. |
| `optimize` | Serialized cancellable polling and history reference reuse with immutable retained snapshots. | Keep with regressions; microbenchmark is not a universal speed claim. |
| `extract` | Named control-border/execution-state tokens replace repeated literals; documented incumbent component inventory. | Keep small shared recipes, not new architecture. |
| `typeset` | Functional text floors and more legible hierarchy, with separate alternative type treatments. | Keep readability; choose density after review. |
| `layout` | Alternative hierarchy/spacing/grouping while retaining working resizable panels and graph affordances. | Compare live; not automatically better. |
| `quieter` | Warm light field-notebook alternative. | Owner choice; not a replacement for the approved dark identity. |
| `distill` | Calmer reduction of competing labels/ornament and simpler scanning. | Keep useful reduction, not hidden functionality. |
| `bolder` | Instrument-desk expressive alternative. | Owner choice; assess clarity rather than novelty alone. |
| `colorize` | Separate coherent alternative palettes and semantic contrast, not recoloring the practical baseline. | Compare freely; do not merge palette by accident. |
| `animate` | Limited interaction feedback with reduced-motion fallbacks. | Keep only feedback that improves orientation. |
| `delight` | Small interaction affordances in the expressive candidate. | Optional; avoid fake execution or celebration. |
| `overdrive` | Opt-in labelled Motion lab component, isolated from actual execution. | Showcase first; likely defer as core product scope. |
| `live` | Real loopback helper injection and Chromium overlay connection in isolated React fixture. | Useful plumbing, but not a proven end-to-end authoring workflow here. |
| `generate` | Real browser-minted generation event/context; TSX source preflight/wrap failed with `element_not_in_source`. No accept cycle was completed. | Use ordinary branch previews now; investigate mapper before adoption. |
| `polish` | Final coherent controls, contrast, spacing and error-state checks on each candidate. | Final pass, not a substitute for correctness tests. |
| `craft` | Deprecated alias for ordinary new work. | No separate implementation to test. |

### Administrative tools

- Hook enable/status/disable and a synthetic PostToolUse detector event worked in
  the isolated fixture. Reset removed those local hook entries afterwards.
  Hooks run with process permissions; this trial grants no global approval.
- `doctor` correctly identified an intentionally installed-but-disabled hook.
  Its initial DESIGN.md coverage warning informed the explicit documentation
  merge. Broad schema/visual rewrites were not performed automatically.
- Pin/unpin reported no supported harness despite local Codex/agents skill copies.
  Exit zero did **not** mean a shortcut was installed. No global fallback used.
- A sandboxed helper-status check lost tracking while the helper remained alive.
  Cleanup used inspected exact PIDs. Do not rely on that status alone.

## Independent rendered assessment

Source critique is recorded in [design review](impeccable-lab-design-review.md).
The leader separately inspected the actual browser workbench and both read-only
and executable sample states. The editor expresses its real graph/task model,
not a generic marketing template. Retain that product-specific structure.

The baseline detector produced **44 findings** in the selected-task synthetic
scene (29 undersized text, 12 small text, two placeholder contrast, one font taste
warning). These are overlapping rule hits, not 44 distinct bugs. A raw source scan
returned no matches: rendered and source scans have materially different coverage.
Interim practical output dropped to 11; the final selected-task scan returned one
font warning in each of practical, calm and expressive, with no remaining
small-text or placeholder-contrast findings in that scene.
The "Inter" warning is a taste heuristic on an allowed system-font stack, not an
automatic defect. Detector count alone is not a quality score or acceptance gate.

Independent review caught two incomplete fixes: a pending Save-as could still be
closed with Escape, hiding a later error; specific toolbar selectors overrode the
stronger generic border token. Both require regression checks, not a token-only
claim. The leader also spotted an unthemed native JSON textarea in a screenshot.

## Verification details and limitations

- Baseline keyboard reproductions confirmed escaped Save-as focus, ineffective
  Escape dismissal, and invisible file-input tab stops. New regressions cover them.
- A local synthetic history microbenchmark (250 catalog tasks, 60 entries, 30
  undo/redo pairs) measured baseline 1882.69ms versus candidate 56.96ms in Node24.
  This single local run isolates history work, not whole-browser latency or memory.
- Real practical GUI **Save as**, **Run flow**, and **Last run** succeeded on a copied
  sample project. Run `e31aefb0-bd07-46b0-93fc-5eee1d60f277`, saved flow `lab_summary_2`.
  The same source ran unchanged via Python and CLI, including native task execution:
  `{"summarize": "Document: 2 words, 12 characters"}`.
- The first GUI evidence harness incorrectly omitted the session header on its
  own polling request and received 401. Correcting the harness to follow the
  existing X-Weavem-Token contract passed; this was not an application defect.
- This does not establish public-release readiness, a security audit, arbitrary
  Python round-tripping, screen-reader certification, or physical touch support.

## Evidence

All disposable evidence is under the original checkout's ignored directory
`.artifacts/node-editor/impeccable-lab/evidence/`. It includes per-candidate browser
JSON/screenshots/rendered detectors, baseline build, practical regressions, a history
microbenchmark, redacted tooling protocol trials and real GUI/Python/CLI parity.
These summaries remain tracked because the evidence directory is machine-local.

## Review previews and safe restart

Static comparison previews contain only frontend assets and synthetic browser
state; **Connect project / Run flow cannot execute a project through these URLs**.
Actual execution was verified separately on a temporary loopback bridge, then stopped.

| Candidate | Local URL | Branch |
| --- | --- | --- |
| Original | http://localhost:4180 | `feature/editor-experience` at `f0a6fa6` |
| Practical | http://localhost:4181 | `experiment/impeccable-practical` |
| Calm/light | http://localhost:4182 | `experiment/impeccable-calm` |
| Expressive | http://localhost:4183 | `experiment/impeccable-expressive` |

Different ports have separate browser storage. Start from their synthetic starter
flow for a fair comparison. Inspect a task, edit parameters, wire nodes, resize
panels and try history. The expressive Motion lab is explicitly illustrative.

The environment rejected LAN-wide static serving, so previews bind to loopback.
On another machine use your existing SSH target with local forwards for ports
4180–4183. Do not tunnel or expose the disposable execution bridge by accident.

For a standalone restart of one candidate, from its worktree:

```bash
cd ui
npm run build
python3 -m http.server 4181 --bind 127.0.0.1 --directory dist
```

Use the candidate's assigned port; keep that terminal open and stop it with Ctrl+C.
Do not rebuild an alternative into the original worktree. The original checkout's
continuation branch stays untouched; no experiment has been merged or published.


### Final build and browser measurements

No dependencies were added. Built JS gzip bytes were baseline 145385,
practical 145580, calm 145601 and expressive 146314. CSS gzip bytes were
8685, 8877, 9206 and 10378 respectively. These are local build asset measurements,
not network/load-time benchmarks; server compression is deployment-dependent.

Leader browser checks on all four static previews found no page errors or
horizontal overflow at 1600, 1280, 1100, 1099 and 800 CSS pixels. Supported widths
showed the workbench; narrower widths showed recovery. Reduced-motion and
forced-color media were emulated, not physical-device or screen-reader tests.
Screenshots and browser JSON describe the final rendered built outputs.

The temporary static comparison server PID for this session is 3759848:
`kill -TERM 3759848` stops all four previews. Verify the PID still names
`serve_previews.py` before using it later; PIDs can be reused. Its runtime record
is `evidence/runtime.json`. The Python execution bridge on 4195 and Impeccable
helper/tooling preview were stopped. No live poll, injection, or global hook was
left active.


### Final verification matrix (2026-10-30)

| Candidate | Audited implementation | Units | Chromium | Other checks |
| --- | --- | --- | --- | --- |
| Practical | `3f983af` | 40 passed | **61/61** | typecheck, lint, build, diff check |
| Calm | `b971379` (UI `6ed966a`) | 40 passed | **63/63** | typecheck, lint, build, diff check |
| Expressive | `c3c158a` | 40 passed | **64/64** | typecheck, lint, build, diff check |

Browser logs respectively: `practical/final-e2e.log`,
`calm/e2e-final-all.log`, `expressive/full-browser-final.log`. All three source
scans returned `[]`. Final selected-task rendered scans have one font heuristic
warning each, intentionally unsuppressed. These scenes do not prove every dynamic
state is defect-free. Palette-specific inherited tests now resolve actual semantic
tokens on alternatives while keeping strict geometry, interaction and contrast
requirements. Failed intermediate runs remain preserved.

No implementation work remains in the approved lab scope. The live TSX mapper
and pinning incompatibilities are documented outcomes, not silently omitted tasks.
The next decision belongs to the owner: keep practical fixes, choose any visual
parts, or retain the original. No branch has been merged or released.
