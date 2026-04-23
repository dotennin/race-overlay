# Overlay Defaults and Editor Refresh Design

## Problem

The current HUD/editor stack works, but the default experience still feels like a collection of controls rather than a coherent overlay design system. The specific issues to solve in this pass are:

1. The current `overlay.yaml` expresses the desired baseline better than the built-in defaults, but the code still generates older defaults.
2. The drag-overlay title collides with HUD titles and adds visual noise during direct manipulation.
3. The route-map lacks the right set of appearance controls: users want semi-transparent background control, shape as a constrained selection instead of free text, and clear "completed vs remaining" path coloring.
4. The editor exposes RGBA values as numeric channels instead of a real color-picking workflow, and some theme controls (`Panel RGBA`, `Accent RGBA`) do not communicate a meaningful visual role.
5. The distance progress bar does not align current-distance and total-distance text cleanly.
6. The editor layout duplicates actions between Layers and Widget details, and the left-side layer controls currently create more clutter than value.

The goal is to use one coordinated design to refresh defaults, simplify controls, and make the editor feel intentionally canvas-first without splitting YAML, preview, and renderer behavior.

## Goals

- Promote the current repo `overlay.yaml` layout/styling into the built-in default `broadcast-runner` baseline used by generated configs and fresh editor sessions.
- Remove drag-overlay title collisions by simplifying overlay chrome.
- Expand route-map styling so it supports:
  - semi-transparent background by default
  - shape selection via constrained options
  - split coloring for completed vs remaining route segments
  - user-editable colors through the editor
- Convert editable color fields in the editor to real color-picker workflows with alpha control.
- Remove or replace theme controls that do not produce a clear visual effect.
- Fix progress-bar distance label alignment.
- Redesign the editor around a canvas-first layout where Layers is for selection only and detailed edits happen in the inspector.

## Non-Goals

- Adding a second editor or alternate rendering engine.
- Turning the editor into a general design tool with arbitrary layer grouping, snapping, or timeline editing.
- Expanding route-map shapes into decorative or novelty forms without strong readability value.
- Broadly refactoring unrelated presets beyond what is needed for default/migration consistency.

## Current Findings

### Built-in defaults already live behind `broadcast-runner`

The repo currently uses `broadcast_runner_preset()` as the default HUD source for:

- `ProjectConfig.hud`
- `write_default_config()`
- legacy field migration fallbacks

That means "make the current `overlay.yaml` the default" should be implemented by updating the preset/migration layer rather than special-casing one file.

### Route-map shape is currently too open-ended

`route_map.style.shape` is a free-text field in the editor schema, while the renderer only meaningfully supports:

- `circle`
- a rounded rectangle fallback for non-circle values

The current UI therefore suggests more freedom than the renderer actually provides.

### Theme color controls are semantically weak

`panel_rgba` is still used by panel-backed widgets in the renderer, but the current editor layout and preview experience do not make its effect obvious. `accent_rgba` is even weaker because it does not currently drive a strong visible affordance in the refreshed editor/HUD flow.

The issue is not only implementation; it is also semantic clarity. The editor exposes low-level color knobs without clearly telling the user what visual system they belong to.

### Layers duplicates inspector functionality

The current Layers panel provides:

- selection
- visibility toggle
- z-order arrows

Visibility is already editable in Widget details, and the z-order arrows do not provide enough value to justify the noise they add. The result is a cluttered left rail that competes with the canvas.

## Selected Direction

Use **A: Canvas-first studio** as the editor direction.

This keeps the live preview as the primary surface, reduces Layers to selection/navigation, and moves all property editing into a clearer inspector model. It matches the product's current strength — direct manipulation on canvas with explicit YAML saves — while removing duplicated controls.

## Detailed Design

### 1. Default baseline: promote the current `overlay.yaml`

Treat the checked-in `overlay.yaml` as the source of truth for the next default `broadcast-runner` experience.

Implementation intent:

- Update `broadcast_runner_preset()` so its theme/widget defaults match the current `overlay.yaml` baseline where the file expresses intended defaults.
- Keep `preset: broadcast-runner` as the default preset name.
- Ensure `write_default_config()` and fresh editor sessions inherit the new baseline automatically through the preset.

This keeps defaults centralized in code rather than teaching the app to special-case one repo file.

### 2. Route-map appearance model

Replace the loose route-map styling model with a constrained, editor-friendly one.

#### Shape selection

Change `shape` from free text to a selection input with these supported values:

1. `circle`
2. `rounded-rect`
3. `square`

These three cover the practical readability space for this HUD without encouraging shapes the renderer cannot present cleanly.

#### Background styling

The route-map should expose a dedicated background color with alpha, defaulting to semi-transparent.

Recommended field model:

- `background_rgba`
- `show_panel`

This is clearer than a separate opacity-only knob because it works naturally with the editor color-picker flow and makes the route-map self-contained even if broader theme-level panel color controls are removed or reduced.

#### Route progress colors

Split the route line into two semantic segments:

- **completed path** — default green
- **remaining path** — default `rgb(13, 144, 195)`

Recommended style fields:

- `completed_rgba`
- `remaining_rgba`
- `marker_rgba`
- `heading_arrow_rgba` only if the current fixed arrow color no longer feels coherent after previewing the redesign

The first implementation should prioritize the completed/remaining split because that is the user-visible need. Marker/arrow customization can remain conservative unless it materially improves consistency.

### 3. Overlay interaction cleanup

The draggable overlay chrome should become quieter.

Behavior:

- Do **not** show an always-on overlay title badge.
- Keep selection via outline + resize handles.
- If additional identification is needed, use Layers selection and inspector heading rather than a floating canvas label.

This directly removes the title overlap problem and keeps the canvas closer to the final render.

### 4. Editor color-input model

Any editable color field that remains in theme or widget style should use a color picker first, not four standalone numeric inputs.

Recommended UX:

- native color swatch / picker for RGB selection
- adjacent alpha control
- synchronized numeric fallback display only if needed for precision/debugging

This applies to:

- `Text RGBA`
- route-map background / completed / remaining colors
- progress-bar fill / rail / tick colors
- any other retained RGBA style field

### 5. Theme control simplification

The editor should stop exposing controls whose visual meaning is not clear.

Recommended direction:

1. Remove `Accent RGBA` from the editor schema and theme model unless a strong, shared accent system is intentionally reintroduced in the renderer.
2. Re-evaluate `Panel RGBA`:
   - if the redesign still relies on a shared panel surface across multiple widgets, keep it only if the preview makes its effect obvious
   - otherwise remove it and move meaningful color control down to widget-level fields where the user can see immediate cause/effect

The default design assumption for this project is **prefer deletion over keeping ambiguous knobs**.

### 6. Progress-bar alignment refresh

The distance ruler should align current-distance and total-distance text on a coherent visual baseline.

Design intent:

- title remains visually attached to the current-distance readout
- current value and total value should align by cap-height/baseline relationship rather than feeling vertically offset
- right-aligned total value should feel anchored to the same typographic system as the current value, not like an unrelated label

This is a renderer/layout refinement, not a schema expansion.

### 7. Editor layout redesign

Adopt the selected **Canvas-first studio** layout.

#### Left column: Layers rail

Layers becomes a compact selection rail:

- shows widget order and names
- highlights selected widget
- no per-row visibility button
- no per-row z-order arrows

If visibility remains editable, it lives in Widget details only.

#### Center column: dominant canvas

The center stays dedicated to:

- live preview
- direct drag/resize interaction
- explicit Save YAML action

The canvas should feel less boxed-in by control chrome and more like the primary working surface.

#### Right column: grouped inspector

The inspector becomes the single place for:

- widget geometry
- widget visibility
- widget style
- theme defaults

Within the inspector, route-map controls should be grouped semantically:

- shape/background
- path colors
- navigation markers

This is preferable to exposing a long flat list of unlabeled fields.

## Data Flow and Migration

### Default generation

- `race-overlay init` should emit the refreshed `broadcast-runner` defaults.
- opening a new/default config in the editor should reflect the same baseline.

### Existing config migration

Preserve the existing selective migration strategy for `broadcast-runner`, but extend it for the new fields:

- backfill new route-map fields when a config still resembles the old default
- preserve clearly user-edited geometry/style values
- avoid destructive migration for customized layouts

### Editor state/schema

- route-map `shape` becomes enum-backed in the editor schema
- retained RGBA fields become color-picker-backed UI controls
- removed theme fields disappear from both schema and persisted config output

## Error Handling

- Unsupported route-map shapes should fail validation with a clear enum-based error.
- Invalid RGBA values still fail validation explicitly.
- If route progress cannot be split because the route is too short or current projection is unavailable, the route-map should still render using a safe fallback instead of failing the whole frame.
- If an older config still carries removed theme keys, migration should either translate them intentionally or reject them clearly; no silent ignore behavior.

## Testing Strategy

Add or update coverage for:

- default config generation after the preset refresh
- broadcast-runner migration behavior with the new route-map styling fields
- route-map split coloring for completed vs remaining path
- route-map shape enum validation and editor schema exposure
- overlay rendering without drag-title label chrome
- editor color-picker schema/UI behavior for retained RGBA fields
- removal or translation of `Panel RGBA` / `Accent RGBA` depending on the final compatibility choice
- progress-bar distance label alignment regression coverage
- Layers panel rendering without duplicated action buttons

Run the full `uv run pytest -q` suite after implementation.

## Risks and Mitigations

- **Risk: deleting theme color controls breaks customization expectations.**
  - Mitigation: keep only controls with clear visual meaning and add migration coverage for old configs.
- **Risk: route-map color customization balloons into too many knobs.**
  - Mitigation: prioritize `background`, `completed`, and `remaining` colors; expand only if preview evidence supports it.
- **Risk: editor redesign reduces discoverability for secondary actions.**
  - Mitigation: keep the canvas-first layout but ensure inspector headings and layer selection are explicit and readable.
- **Risk: using the current repo `overlay.yaml` as the default accidentally bakes in one-off edits.**
  - Mitigation: mirror its intentional baseline values into the preset, not the file wholesale; preserve the preset as the canonical source.

## Implementation Seams

The implementation plan should split across these seams:

1. preset/default generation and migration
2. HUD schema + renderer updates
3. editor schema/control rendering
4. editor layout/UI simplification
5. tests covering defaults, rendering, and editor behavior
