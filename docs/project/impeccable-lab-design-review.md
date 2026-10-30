# Impeccable lab: design review and alternative briefs

**Status:** source-reviewed baseline and experiment briefs, not a released design.
**Baseline:** `f0a6fa6` on `feature/editor-experience`, reviewed 2026-10-30.
**Audience:** owner and contributors evaluating the isolated Impeccable lab.
**Method:** design assessment A, separate from the leader's detector/browser
assessment B. This file is not a completed dual-assessment Impeccable critique.
No fresh rendering, screen-reader session, or usability study was performed in
this lane. Scores below are provisional source-review judgments.

## Product and implementation constraints

Weavem's editor is an **Operate** surface: flow authors find tasks, supply inputs,
wire explicit arguments, save ordinary Python into the selected project's
`flows/` directory, and inspect actual execution. It is not the execution engine
or a hosted automation platform. The UI is optional; saved flows must remain
runnable through Python and the CLI.

The implementation is React 19, TypeScript, Vite, React Flow, and Tailwind 4.
`Button` and `Field` are presentation/native-semantics primitives; callers own
state and effects. CSS tokens live in `ui/src/theme.css`; native canvas, resizer,
fullscreen, and scrollbar styling lives in `ui/src/styles.css`. Tailwind Preflight
is intentionally omitted. Do not change frameworks or add component libraries.

The user chose an isolated comparison lab and explicitly permits visual freedom
in the alternatives. The practical version must retain the approved palette and
workbench structure. Alternatives are candidates, not replacement authority for
the current editor. No branch is selected for promotion yet.

## Baseline critique

### Specificity and strengths

The editor is recognizably a local engineering workbench, not a marketing page
with a graph attached. Visible task identity, provenance, argument mapping, and
revision-bound execution evidence express Weavem's real distinction.

- Canvas and inspector share authored edges; field-path selection saves ordinary
  Python indexing instead of an editor-only expression language.
- Parameters, Connections, Result, and Details give the inspector a task-oriented
  structure. Native disclosures preserve mounted draft controls.
- The model distinguishes current authoring from Last run evidence, unknown
  fields from declared/observed hints, and synthetic metadata from runnable tasks.

The biggest opportunity is **recognition before configuration**: help authors
know which mode they are in, what they must do next, and which input a connection
supplies without making them parse several adjacent technical controls.

### Provisional heuristic score

| Heuristic | Score / 4 | Source-review rationale |
| --- | --- | --- |
| System status | 3 | Save state, session state, run state, and locked editing are explicit; status is spread across several locations. |
| Match with the user's world | 3 | Task/flow/argument vocabulary matches Python; draft/catalog/project distinctions still take learning. |
| Control and freedom | 2 | Undo/redo, export, and cancel exist; the Save-as modal does not use the replacement dialog's keyboard management. |
| Consistency | 3 | Shared primitives and tokens exist; connection controls and ordinary fields do not always share the same presentation. |
| Error prevention | 3 | Replacement confirmation and run validation protect work; mapping still needs explicit author attention. |
| Recognition over recall | 2 | Several mapping controls and toolbar actions compete; a first-time author must infer the sequence. |
| Efficiency | 3 | Shortcuts, reusable tasks, resizing, and collapsed metadata serve experienced users. |
| Minimalist presentation | 3 | The palette is restrained; repeated badges, small labels, and control borders add visual noise. |
| Error recovery | 2 | Structured errors exist; footer-level errors can be distant from the failing dialog or field. |
| Help and documentation | 2 | Accurate contextual hints exist, but discovery of the first runnable workflow is weak in the UI. |
| **Total** | **26 / 40** | **Provisional: usable foundations, meaningful interaction gaps.** |

### Priority observations

1. **P1 — Save-as is not a complete modal interaction.**
   `App.tsx:1304` creates an ARIA modal, but the focus trap, Escape behavior,
   focus restoration, and background inertness at `869–900`, `983`, and `992`
   apply only to replacement confirmation. Reuse the existing accessible
   behavior and show Save-as failures inside the dialog. Command: `harden`.
2. **P2 — First value is hidden behind mode distinctions.**
   `App.tsx:1048–1055`, `1189`, and `1296–1300` explain pieces of sample/project,
   editing/running, and storage state in different places. Keep the sample
   honest and give the disconnected author one concise next step near the
   primary work area. Commands: `onboard`, `clarify`.
3. **P2 — The toolbar's information architecture can overwhelm its canvas.**
   `EditorToolbar.tsx:31–46` contains authoring, four history/clipboard actions,
   project/import actions, run parameters, and execution. Grouping exists, but
   wrapping can change the perceived hierarchy. Preserve accessible labels and
   shortcut discoverability; make the primary route unmistakable before hiding
   low-frequency actions. Commands: `layout`, `distill`.
4. **P2 — Connection editing presents several decisions at once.**
   `App.tsx:1236–1252` combines peer selection, target argument, field-source
   chooser, manual JSON path, Apply, and Delete per wire. Each serves a real
   purpose, but the visual reading order should be source → field → target
   argument, with manual JSON as an available advanced path. Do not replace the
   model or discard unknown keys. Commands: `shape`, `layout`, `clarify`.
5. **P2 — Small metadata competes with larger controls.**
   Baseline `theme.css:28–32` defines 10px captions and 11px helpers; library
   descriptions are 11px in `styles.css:317–321`. Raise functional metadata to
   at least 11px and prose helpers to 12px, then recheck density and overflow.
   This is a legibility recommendation, not a pixel-based WCAG verdict.
   Commands: `typeset`, `polish`.

### Personas, cognitive load, and emotional journey

- **New flow author:** the sample looks complete but cannot run. The first
  useful step must explain connecting a local project, not imply an unavailable
  cloud workspace or pretend the demo executed.
- **Experienced Python developer:** task identity and JSON fallback are useful;
  excessive instructional prose and decorative motion would become friction.
  Preserve keyboard workflows and compact access to raw values.
- **Keyboard/low-vision author:** opaque modal behavior and tiny labels impair
  confidence before visual sophistication can help. Keep the same actions
  reachable without drag, color perception, or fine pointer precision.

The main emotional valley is the transition from an appealing sample graph to
disabled execution. The meaningful success moment is saving and running a real
local flow, then finding its result and exact revision—not an animation or fake
success indicator. The toolbar and per-wire forms contain more than four visible
choices; deliberate grouping and context are needed, not a blanket four-item cap.

## Document and extract: incumbent system

This is a scoped extraction record, not an overwrite of root `DESIGN.md` and not
a claim that Impeccable's full document/sidecar workflow has completed.

| Role | Observed baseline |
| --- | --- |
| Canvas / panel | `#0c0f09` / `#080a06` |
| Task surface / control | `#212818` / `#262e1b` |
| Text / secondary text | `#edf1e7` / `#c6d2b4` |
| Action / action hover | `#90a96e` / `#aabd90` |
| Border / hover border | `#374227` / `#485733` |
| Danger fill / danger text | `#754645` / `#efb1ae` |
| Type | Local Inter if installed, then system sans; system monospace for identifiers/data. No font download. |
| Type roles | Caption 10px, helper 11px, field 12px, section 13px, title 15px. |
| Shape / spacing | Controls 7px, fields 6px, cards 8px radii; 4px token unit with mostly 8/12/16px group spacing. |
| Depth | Tonal layers and thin borders; restrained offset shadows. |
| Motion | Short control transitions and disclosure feedback; reduced-motion CSS disables animation/transition. |
| Layout | Resizable library/canvas/inspector; editing from 1100px; export notice below it. |
| Scrollbars | Native scrolling, 6px Chromium styling, thin Firefox, system styling in forced colors. |

Reusable components already present are Button variants, Field, EditorToolbar,
ParameterEditor, FieldMapping, ResultViewer, RunInspection, inspector disclosures,
and resize handles. Keep these; do not create a second component system.

Useful extraction targets are repeated semantic execution colors and a dedicated
control-boundary token. A shared modal behavior is justified by the two existing
dialogs' identical interaction need, not merely by visual resemblance. Avoid
extracting task-specific connection state into a generic form engine. The
practical branch owns any implementation and corresponding regressions.

## Shape: comparison briefs

All candidates serve the same job and states. Compare one task selected, a
connection with field mapping, empty selection, invalid parameters, sample vs
connected project, completed result, failed result, and read-only Last run.
Use the same fixture data and viewport to avoid judging different content.

### Practical — the approved olive workbench, made dependable

- **Thesis:** preserve the user's existing visual authority. The difference
  should be easier reading and fewer interaction traps, not a new brand.
- **Hierarchy:** task identity before metadata; editable value before helper;
  current editing before recorded evidence. Keep Run at the canvas boundary.
- **Changes:** accessible dialogs, readable functional type, visible input
  boundaries, faithful missing/null output, and truthful empty/error guidance.
- **Proof:** keyboard completion, revision-correct execution evidence, no lost
  parameter edits, and the existing GUI/CLI flow contract unchanged.

### Calm — a light field notebook for long authoring sessions

- **Thesis:** use quiet daylight surfaces and clear typographic grouping instead
  of nested dark cards. The memorable difference is an open, paper-like canvas
  beside a compact reference index, not a marketing/editorial layout.
- **Topology:** retain all three resizable regions and the established Run anchor.
  Make library task entries flatter, reserve a restrained surface for the
  selected task, and organize inspector groups through whitespace rather than
  repeated strong containers. Do not turn task entries into invented tabs.
- **Palette:** canvas `#e8e9e1`, panel `#f3f1e9`, task/result surface `#fffdf7`,
  ink `#202b29`, muted ink `#4c5d56`, action `#28685b`, action text `#fffdf7`,
  and control boundary `#718079`. These are experiment proposals, not incumbent
  tokens. Keep warning/danger separately distinguishable with text labels.
- **Type and density:** use the existing local/system font stack; 12px controls,
  12px prose/helpers, 11px compact metadata, 14px section headings, 16px task
  headings. Use 12px within groups and 20px between inspector sections. Preserve
  code identifiers in monospace. Do not download a showcase font.
- **Feedback:** no entrance choreography. Use 120–180ms color/state transitions;
  selection is a clearly outlined task or wire, not a glow. Preserve native
  scrolling and reduced-motion/forced-colors support.
- **Commands to demonstrate:** `quieter`, `distill`, `typeset`, `layout`,
  `colorize`, then `polish`. Keep ordinary workflows intact; distill redundant
  decoration and repetition, not essential metadata or actions.

### Expressive — an instrument desk with unmistakable action hierarchy

- **Thesis:** a crisp, blue-black workbench with a bright cyan action/selection
  language. The memorable difference is precise instrument-like grouping and
  a deliberate execution focal point, not neon decoration or fake telemetry.
- **Topology:** retain the resizable three-region workflow. Make the toolbar
  read as authoring → history → execution groups; use bolder task titles and
  strong selected-node contrast. Keep low-frequency actions available through
  More. Result evidence must remain distinct from the current graph.
- **Palette:** canvas `#111a26`, panel `#0b121b`, task surface `#1b2b3b`,
  control `#24374a`, boundary `#71899b`, ink `#edf5fa`, muted `#b7cbd8`,
  accent `#78d4dc`, and on-accent `#0c2028`. Keep danger and warning semantic,
  never borrowed as idle decoration. No gradients or decorative status lights.
- **Type and density:** existing local/system sans; task titles 16px, section
  headings 14px, controls/body 12px, metadata 11px. Use stronger weight and
  deliberate 16–24px separation rather than inflating all controls.
- **Feedback:** one short, non-looping authored selection/execution transition
  at most; no perpetual moving wires, pulsing backgrounds, or particle canvas.
  Execution motion must follow real run state. A clearly labelled, opt-in
  component showcase may exercise `overdrive` separately without implying it
  belongs in everyday authoring. Reduced motion keeps a static equivalent.
- **Commands to demonstrate:** `bolder`, `colorize`, `layout`, `typeset`,
  `animate`, `delight`; exercise `overdrive` only in the isolated showcase,
  then `polish` the actual editor separately.

Proposed color pairs were calculated from the stated hex values: calm ink on
surface 14.35:1, muted on panel 6.17:1, action text on action 6.41:1, boundary on
panel 3.67:1; expressive ink on task surface 13.08:1, muted on task surface
8.62:1, on-accent 9.78:1, boundary on control 3.34:1. These are arithmetic
checks only; rendered states and every actual adjacent surface still need review.

## Onboard and clarify: first-value path

Do not add an account wizard, compulsory tour, simulated execution, or a second
tutorial runtime. Use the existing controls and concise, dismissible guidance.

| Situation | Useful instruction | Truth boundary |
| --- | --- | --- |
| Synthetic sample | “Explore this sample graph. Connect a local project to save and run a real flow.” | The sample does not execute. |
| Connected, empty graph | “Add a task from the library, supply its inputs, then save your flow.” | Unbound tasks cannot run. |
| Nothing selected | “Select a task to inspect its parameters and connections.” | A wire also has its own inspector. |
| Unmapped wire | “Choose the target argument for this connection before running.” | A line alone is not an executable mapping. |
| Unknown output | “Output fields are unknown. Use the whole result, enter a path, or run for an observed sample.” | Observations are examples, not a guaranteed schema. |
| No prior run | “No recorded run for this flow yet. Return to Edit flow to save and run it.” | Do not manufacture a historical result. |
| Run complete | “Inspect the result for this run, or return to editing.” | Results belong to the recorded source revision. |
| Unsupported visual Python | Explain that the flow is runnable but cannot be safely rewritten visually. | Preserve handwritten Python. |

The desired first-value proof is: connect project → add/bind tasks → supply
arguments → save → run → find result → run the saved flow without the UI.
Existing UI hints should teach only the current step. The leader's lab record
must distinguish implemented copy from proposals in this table.

## Review gates and recommendation

Compare candidates at 1100, 1280, and 1600 CSS px with the same fixture; verify
the export fallback below 1100px, 200% zoom behavior, long task IDs, long error
messages, large values within the bounded preview contract, keyboard focus,
reduced motion, and forced colors. No mobile-authoring claim is made.

Retain the practical hardening unless regression evidence argues otherwise.
Judge calm/expressive aesthetics through the real task sequence, not a screenshot
alone. Recommend **reconsider** for alternative palettes until owner review, and
**reject by default for everyday use** for any overdrive effect that competes
with graph reading. A playful prototype is evidence about a tool capability,
not proof that the effect fits the product.

No new backend/API or persisted-flow-format change is proposed. No benchmark,
WCAG conformance, rendered success, or implementation completion is claimed by
this document. Questions skipped: the approved lab brief already settled the
audience, isolation, visual freedom, and selection boundary; later owner review
selects what, if anything, becomes continuation work.
