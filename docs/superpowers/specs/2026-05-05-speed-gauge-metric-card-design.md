# Speed Gauge Metric Card Design

## Problem

The current HUD has `metric_card` support for simple label + value layouts, and `speed-chip` is just one preset instance of that widget type. It cannot render the dashboard-style circular speed gauge shown in the supplied reference image.

The requested change should make that look available through the existing `speed-chip` variant flow instead of introducing a separate widget type.

## Assumptions

- The user wants this delivered as a new `metric_card` variant that `speed-chip` can opt into.
- The first implementation should target the `speed_mps` binding and render the displayed value in `KM/H`.
- The reference is the visual target, not a pixel-perfect requirement.
- Existing saved HUDs that use `variant: compact` must remain unchanged.

## Goals

- Add a new `metric_card` variant for a circular speed gauge HUD.
- Keep `metric_card` as the single widget type for this chip so YAML, presets, editor schema, preview, and final render stay aligned.
- Make the gauge visually close to the reference: dark inner panel, segmented colored outer arc, centered slanted speed value, and `KM/H` unit lockup.
- Expose the variant in the editor so users can apply it to `speed-chip` without hand-editing YAML.
- Preserve existing variants and widget behavior.

## Non-Goals

- Adding a brand-new `speedometer` widget type.
- Building a fully configurable gauge system with arbitrary tick labels, ranges, or multi-metric semantics.
- Retroactively changing all existing metric cards to the new look.

## Current Findings

### Rendering

`hud.py` renders `metric_card` in `_draw_metric_card()`. Today it only branches between `compact` and the default layout. That is the correct insertion point for a new variant because final render and preview both use the same backend renderer.

### Editor exposure

`editor_preview.py` drives the widget inspector schema. `metric_card.style.variant` currently only exposes `["compact"]`, so the new variant needs to be added there for editor discoverability.

### Preset usage

`speed-chip` appears in both the preset helpers and the default `overlay.yaml` as a `metric_card` with `bindings.value = "speed_mps"` and `style.variant = "compact"`. That means the feature can land cleanly by changing only the chosen widget instance when desired.

## Considered Approaches

### A. Add a new `metric_card` speed-gauge variant

Extend `_draw_metric_card()` with a dedicated branch such as `variant: "speed_gauge"` and add that option to the editor schema.

**Pros**
- Fits the user's requested direction exactly.
- Preserves one config/rendering path.
- Low migration risk because existing cards keep their current variants.

**Cons**
- The renderer needs some specialized drawing logic inside `metric_card`.

### B. Create a dedicated new widget type

Add a `speedometer` widget with its own schema and defaults.

**Pros**
- Cleaner renderer separation.

**Cons**
- Adds unnecessary schema/editor complexity.
- Conflicts with the request to treat this as a `speed-chip` variant.

### C. Approximate the gauge with existing card primitives only

Keep `metric_card` unchanged and try to mimic the reference by adjusting fonts, panels, and labels.

**Pros**
- Smallest code change.

**Cons**
- Cannot deliver the circular gauge look.

**Chosen approach:** A.

## Design

### 1. Variant shape and scope

Add `variant: "speed_gauge"` to `metric_card`. This variant should be intended for speed display and should format the visible number from `speed_mps` into whole `KM/H`.

The variant remains inside `metric_card` so the widget inventory, YAML structure, preview API, and editor inspector do not need a new type path.

### 2. Gauge visual treatment

Inside the widget bounds, render:

- a dark rounded-square or circular base panel that matches the current HUD palette
- a thin metallic outer rim
- a segmented progress arc sweeping around the upper-left through lower-left edge
- color progression from green to yellow to orange to red near the high end
- a small triangular needle marker near the active arc position
- a large centered speed number
- a smaller `KM/H` unit label near the lower-right of the value

The central label text from standard `metric_card` should not render in this variant; the reference works better as a pure instrument readout.

### 3. Value mapping

The ring fill should be computed from the current speed converted to km/h and normalized against a fixed default gauge ceiling. For the first pass, use a renderer-owned default ceiling of `30 km/h` and clamp overflow to the end of the arc.

This keeps the implementation predictable and avoids introducing new editor controls until there is a concrete need for them.

### 4. Styling and typography

Use the existing title/value/unit font helpers so the variant stays consistent with theme overrides. The large numeral should use the theme value font, which already defaults to `broadcast_value`, making it a natural fit for the slanted reference style.

If the current unit placement helper is not sufficient, the variant may position `KM/H` explicitly rather than reusing the normal suffix layout.

### 5. Editor and preset wiring

Expose `speed_gauge` in the `metric_card` variant options in `editor_preview.py`.

Do not silently migrate existing `speed-chip` widgets. Instead:

- preserve current saved configs
- allow the editor to switch any `metric_card` to `speed_gauge`
- update only sample/default configurations that should showcase the new style if that keeps tests and UX consistent

## Error Handling

- If `speed_gauge` is used on a widget without a numeric metric value, render a safe placeholder state instead of throwing.
- Unknown variant names should continue to fall back through existing validation/render behavior.
- Preview and final render must remain visually aligned because both go through `hud.py`.

## Testing Strategy

Add or extend tests for:

- editor schema exposure of `metric_card.variant = speed_gauge`
- preset or sample widget config coverage if defaults are updated
- renderer output for the new variant, using an image-based assertion pattern already used in the HUD tests
- value formatting and clamping for low, mid, and above-max speed values

Run the existing suite with `uv run pytest -q`.

## Delivery Shape

This should ship as one contained feature touching:

- `hud.py` for rendering
- `editor_preview.py` for inspector schema
- preset/sample config files only where the new variant should be visible by default
- tests covering editor exposure and render behavior
