# Route-map editor/display design

## Problem

The route-map HUD currently exposes completed and remaining route colors in presets and editor schema, but the renderer still draws the route as a single line. The editor preview also uses a straight two-point example, which makes it hard to judge map scale, and there is no dedicated route scale control in the inspector.

## Proposed approach

Implement the route-map update as a focused change across the renderer, editor schema, and editor UI:

1. Split the rendered route into completed and remaining segments based on the current projected position on the route.
2. Add a route-map scale percentage field with a slider in the editor.
3. Replace the editor preview example route with an oval track-style loop and show preview progress around 60%.

## Design

### 1. Route rendering behavior

- Keep `completed_rgba` and `remaining_rgba` as the public route-map color fields.
- Use the existing `RouteProjection` result to determine the nearest point on the route and the segment index for the current position.
- Build two projected polylines:
  - start of route through projected position: completed
  - projected position through end of route: remaining
- Insert the projected position as the exact split point so the color handoff aligns with the position marker arrow.
- When GPS is unavailable:
  - do not draw the marker arrow
  - render the entire route using `remaining_rgba`
- Preserve existing route-map panel, shape clipping, north marker, and bearing label behavior.

### 2. Route scale behavior

- Add a new route-map style field: `zoom_percent`.
- Semantics: percentage relative to the current auto-fit route size.
  - `100` = current behavior
  - `90` = route draws 10% smaller than current behavior, leaving more margin
- Default value: `90`
- Editor adjustment range: `70` to `140`
- Step: `1`
- YAML representation remains a plain integer.

### 3. Editor schema and inspector controls

- Extend the route-map schema in `editor_preview.py` with `zoom_percent`.
- Provide explicit metadata for the field so the inspector can render it as a slider rather than a generic number input.
- The slider should display a live-updating percentage value and continue using the existing live preview refresh path.
- Keep `completed_rgba` and `remaining_rgba` exposed as direct RGBA controls; do not add alias fields.

### 4. Editor preview example data

- Replace the current straight two-point `route_points` example with a track-style loop that includes:
  - a long straight
  - a curved turn
  - a return straight
  - a curved closing turn
- Use a preview sample position that lands around 60% progress along the example route.
- The preview route exists only for the editor and does not affect render-time route data from activity input.

### 5. Validation and tests

- Renderer tests:
  - completed and remaining segments use separate colors
  - missing GPS renders the full route as remaining
  - scale values smaller than `100` produce a visibly more inset route projection
- Editor tests:
  - route-map schema exposes `zoom_percent` with slider metadata
  - preview state includes the track-style example route instead of a straight line
- Preset / save tests:
  - broadcast-runner preset includes `zoom_percent: 90`
  - editor save round-trips `zoom_percent`

## Files expected to change

- `src/race_overlay/hud.py`
- `src/race_overlay/hud_presets.py`
- `src/race_overlay/editor_preview.py`
- `src/race_overlay/editor_assets/app.js`
- `tests/test_hud.py`
- `tests/test_editor.py`
- `tests/test_hud_presets.py`

## Out of scope

- Changing real activity route sourcing
- Reworking non-route-map widgets
- Adding new route-map shape types
