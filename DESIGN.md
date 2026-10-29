# Design

## Source of truth

Status: Active · 2026-10-28 · Surface: local node-editor prototype.
Evidence: the owner-approved interactive/dark/React Flow choices; masterplan v8
sections 18, 26 (Visual representation), and 29.7; the existing
[project metadata API](docs/users/reference.md#local-project-metadata-python-api).
The owner-provided `color_shades.jpg` defines the sage/olive palette; the existing workbench layout is preserved.
This is a prototype design contract, not a new supported Python feature.

## Brand

A precise, calm engineering workbench. Trust comes from visible task identity,
version, provenance, local state, and honest prototype labels. Avoid gradients,
glass panels, decorative charts, fake execution status, and invented task types.

## Product goals

Prove that people can find tasks, compose a flow, inspect its metadata, and
save ordinary Python in the project's existing `flows/` directory. Python is
the executable source of truth: the UI is another authoring surface, not another
execution engine. CLI, Python, and GUI use the same saved flow and project
bindings. Optional layout data must not affect execution. Visual round-tripping
supports a conservative Python subset; other code stays intact and runnable,
with visual rewriting disabled. Native preparation is automatic, not a
confirmation dialog. Success is save/run/reopen parity without the UI, explicit
argument wiring, observable execution, and no silent data replacement. Publication, accounts,
and remote execution remain outside this prototype.

## Personas and jobs

Flow authors and data-oriented users exploring visual composition. Framework
maintainers evaluate the metadata/editor boundary. Desktop browsers are primary;
no Python installation is required to open the non-executable demo UI. Running
real tasks requires the project's supported Python environment.

## Information architecture

One workbench: top application/draft toolbar; left searchable task library;
central graph canvas; right node inspector; bottom lightweight state/graph summary.
Library and inspector widths are independently resizable and remembered locally as a
versioned layout preference; the canvas always retains a minimum usable width.
New/import/open/export and project-connection actions are explicit. Run/cancel,
per-node statuses, result previews, and logs expose actual execution. Owner-facing prototype records stay
separate from the released application-user manual.

## Design principles

One task vocabulary, another authoring surface. React Flow owns presentation,
never Weavem execution. Node instances reference task records; duplicate instances
are allowed. Each executable wire names its destination argument and passes the
whole upstream result; task descriptions are not machine-validated type schemas. The canvas and inspector read the same draft edge list: both incoming and outgoing wires remain inspectable, mappable, selectable, and deletable. Reconnecting a wire on an empty canvas disconnects it; invalid, cancelled, and outside-canvas releases preserve it.
Published provenance is metadata, not a claim of verified bytes or trusted code.
Preserve current work when input is invalid; confirm before replacing a draft.

## Visual language

Deep olive canvas (#0c0f09), dark olive panels (#080a06), muted borders (#374227),
off-white text (#edf1e7), secondary text (#c6d2b4), and sage (#90a96e)
for primary actions, wires, focus, and selection. Hover accents use #aabd90.
These colors come from the owner-provided palette; warning/error colors stay distinct. Blue/purple badges distinguish provenance and
backend without implying safety. System sans-serif UI, monospace identifiers.
Use an 8px spacing rhythm, 6–10px corner radii, thin borders, and quiet shadows.
Task cards have clear hierarchy and one meaningful accent; SVG icons are inline.
Motion is limited to interaction feedback. No remote fonts or image assets.

### Scrollbars

Native scrolling uses a slim, rounded olive thumb (`#5e704a`) on a transparent
track, brightening to sage (`#90a96e`) on thumb hover/drag where supported.
Chromium/Edge/WebKit use 6px scrollbars without arrow buttons; Firefox uses
standard thin scrollbars with browser-defined geometry. Apply consistently to
panels, logs, text fields, and horizontal overflow; do not replace browser
scrolling with JavaScript. Forced-colors mode retains system scrollbar styling.

Implementation is limited to CSS plus regression checks for appearance, native
wheel/keyboard/thumb scrolling, narrow panels, and forced-colors fallback.
[Browser styling precedence](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/::-webkit-scrollbar)
requires resetting standard scrollbar properties to `auto` when using the
pseudo-element styling path. Platform overlay/autohide preferences still apply.

## Components

Task library/search/provenance filters, metadata-driven task node with generic
handles, graph controls/minimap, draft toolbar/status, node inspector, JSON
parameter editor, incoming/outgoing connection lists with mapping controls,
reconnectable wire endpoints, and draggable/keyboard panel separators. Run/cancel sits at the
right of the shared draft-action toolbar with play/stop icons and no divider line.
The toolbar aligns with the canvas at the default panel widths and stays anchored
when either panel is resized; resizing the window still adapts its width.
Task-library cards use a pointer (hand) cursor to signal interaction; their existing
drag and Add task behaviors are unchanged.
The canvas header controls only
canvas fullscreen; React Flow retains its bottom-left zoom and fit controls.
Panel boundaries use only the resizer line. Cancel uses a muted red fill with
bright off-white text and icons; idle Run retains the sage accent.
Keyboard connection controls, replacement confirmation, and visible
import/storage errors remain available. Tailwind theme tokens own the shared palette and control styles; native CSS retains canvas and layout integration.
Outgoing connections contain a collapsible Add connection control. Its choices
reflect the same graph and eligibility rules as pointer wiring: existing targets
are marked connected and duplicate wires cannot be added. Wire parameter labels
are hidden on the canvas; mappings remain editable in the inspector and are
preserved for execution and export.
Port dots meet the wires continuously with no dark border. Direction is available
through accessible labels and hover tooltips, not repeated input/output text on
every card.
Execution controls and status labels reuse these components without changing
the sage/olive palette.

### Inspector comparison: collapsible sections

The collapsible inspector variant gives each selected task a compact identity
header followed by Parameters, Connections, Result (when execution data exists),
and Details. Parameters and Connections begin open; Details begins closed.
Native disclosure sections preserve their mounted bodies, so temporarily
collapsing Parameters never loses an unapplied value or JSON validation state.
The panel remembers section openness while moving between task selections.
Details owns node label, notes, and descriptive task metadata. A destructive
action appears once at the bottom of the inspector, outside collapsed Details.
Selecting a wire changes the
header to identify that connection rather than incorrectly describing the
inspector as empty. Connection rows name their peer once and expose one
argument-mapping control; they do not repeat the same mapping as decorative
text. Section headings use 13px, field labels and controls 12px, helper
metadata 11px, and the established 8/12/16px spacing rhythm.

### Styling and component boundaries

Preserve the approved appearance while migrating incrementally. `ui/src/theme.css`
is the semantic palette, typography, spacing, and radius source for both Tailwind
utilities and remaining CSS. Shared control recipes use Tailwind `@apply`; new
one-off layout can use explicit utility classes. Do not construct utility names
from runtime strings or duplicate palette literals in new controls.

Cascade order is theme → base → React Flow → components → utilities. React Flow's
stylesheet is imported into its own layer from the editor stylesheet. Tailwind
Preflight is deliberately omitted: existing base styles and native form behavior
are part of this prototype's approved baseline. Revisiting the reset requires a
separate visual and accessibility review.

Button and Field components own only repeated presentation/native semantics.
Callers own state, actions, validation and execution. ParameterEditor owns pending
JSON state; its field renderer owns only the type-specific control markup. Keep
these mounted when inspector sections collapse. Do not add generic component
factories, inheritance or a parallel graph state model to satisfy DRY/SOLID.

Keep custom CSS for the grid/resizers, React Flow ports and edges, fullscreen,
responsive rules and 6px native scrollbars. Metadata/raw-JSON and browser
scrollbar fallbacks remain intentional compatibility paths. Tailwind is a build
dependency, not a runtime service: static output and the local bridge are unchanged.

## Accessibility

Aim for WCAG 2.2 AA patterns without claiming an audited conformance level.
Use semantic buttons/labels, visible focus, readable contrast, and live status
messages. Keep React Flow keyboard accessibility enabled. Provide button-based
node creation and inspector-based connection/deletion, not drag-only workflows.
Respect reduced-motion preferences; never communicate provenance by color alone.

## Responsive behavior

Full three-panel editing at desktop widths of 1100px and above. Panel widths clamp
to 220–480px (library) and 260–560px (inspector), preserving a 430px canvas.
Below that,
show a clear desktop-workbench notice instead of compressed, unusable controls;
leave an export/recovery action available. No touch-first editor promise.

## Interaction states

Demo/empty/restored drafts are distinct. Invalid imports leave current work
unchanged. Catalog replacement starts a new draft after confirmation. Import
metadata is not graph reconstruction from Python flows. Autosave is local to
this browser; failures remain visible and export remains available. Corrupt
stored content is not silently overwritten by a demo fallback. Connection failures
do not discard the draft. Running locks graph changes; results belong to the
saved source revision. Native preparation is automatic. Reload can reconnect to
the same backend's active run. Observed task states follow actual Python/Prefect
execution; the UI must not change retry, failure, or orchestration semantics.

## Draft parameters

Use guided fields when the connected project supplies static source-signature or
metadata hints. Show defaults without silently applying them; keep JSON editing
available and preserve unknown keys. Mapped inputs name their upstream node
instead of offering an editable value. Canvas connections and inspector fields
share the same draft edges. Invalid or unapplied edits must not silently run.
Hints are suggestions, not runtime type enforcement; inspecting source never
imports or executes task code.

## Content voice

Use tasks, flows, drafts, catalog, local, released, and prototype. Never capabilities.
Say what is known: descriptive metadata, argument mapping, browser autosave,
and actual run state. Do not label editor output published or sandboxed. Synthetic
demo tasks cannot run, and imported paths do not grant filesystem access.

## Implementation constraints

React + TypeScript + Vite + @xyflow/react, Tailwind CSS via its Vite plugin, and
an npm lockfile; no new state, component-library, or backend framework. Weavem owns a versioned JSON-safe draft
model containing catalog, node instances, edges, configuration, and viewport.
Renderer state is converted to/from it; no React Flow serialization contract.
Import only JSON in the browser; no eval, HTML injection, or outbound telemetry.
An explicit loopback-only standard-library Python bridge serves the built UI,
scopes execution to one project and interpreter, checks host/origin/session token,
and starts a fresh process for each run. No JavaScript task execution engine.
Metadata may contain local paths; browser storage and downloaded files are not
secret stores. Tests cover pure data logic and real browser interactions.
Keep task/flow artifact manifests, dependencies, package version and releases
unchanged. The versioned execution graph is distinct from the layout draft and
from a published flow. Draft schema 1 remains readable; unmapped wires cannot run.

## Open questions

Typed ports, result-field selection, credentials management, parallel execution,
loops, nested flows, scheduling, collaboration, publication, and production
deployment remain deferred. Execution is trusted local code, not a sandbox;
cancellation cannot undo side effects.
