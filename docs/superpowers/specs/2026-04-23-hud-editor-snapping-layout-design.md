# HUD Editor Snapping and Canvas Layout Design

## Problem

The current overlay stack already has a cleaner editor than before, but four rough edges remain:

1. Route-map styling still treats the path as one color, even though users need a completed/remaining split with a configurable remaining-path color.
2. The editor still exposes color values as low-level channel inputs in several places, instead of a consistent color-picker workflow.
3. The distance progress bar places total-distance text slightly off the current-distance baseline.
4. Dragging and resizing still feel manual; the editor needs snapping to both grid and nearby layout guides.
5. The canvas-first editor still wastes space because the left layer rail is not pulling its weight, and the canvas column does not feel visually centered.

The goal is to make the editor feel like a deliberate overlay workspace: clear route styling, real color controls, useful snapping, and a simpler canvas-first layout.

## Goals

- Make route-map completion state visually obvious:
  - completed path green by default
  - remaining path defaulting to `rgb(13, 144, 195)`
  - both colors user-editable
  - background alpha user-editable
- Replace all user-facing RGBA channel controls with color-picker-first controls.
- Align distance progress-bar total text with the current-distance text baseline.
- Add drag/resize auto-alignment that snaps to both grid and nearby widget/canvas guides.
- Remove the left layer rail as a primary panel and keep the editor centered around the canvas + inspector.

## Non-Goals

- Building a general-purpose layout editor.
- Adding arbitrary theme color systems beyond the HUD fields already exposed.
- Making snapping configurable in the UI during this pass.
- Changing the underlying HUD widget inventory or preset names.

## Current Findings

### Route-map rendering still uses a single path color

The renderer already knows about route-map projection and shape selection, but the route polyline is still drawn as one path color. The editor schema already exposes `background_rgba`, `completed_rgba`, and `remaining_rgba`, but the renderer does not yet split the path into completed and remaining portions.

### RGBA editing is still inconsistent

The editor has a shared `rgba` field kind, but the current control is still channel-heavy and visually noisy. The right fix is a single color picker plus alpha control for every RGBA field, including theme colors and widget style colors.

### Progress-bar labels are close but not aligned

The progress bar already draws label, current value, and total value separately. The current and total values need to share the same Y position so the bar reads as one line instead of two loosely related text blocks.

### Snapping is currently manual

Dragging and resizing update the widget rect directly. There is no snapping to 8px increments, canvas center lines, or neighboring widget edges/centers.

### The left layer rail is not earning its width

The current left column is mostly a selection list. It no longer needs to be a primary workspace area now that the editor is canvas-first. That space is better spent on the canvas and/or inspector.

## Selected Direction

Use a **two-column canvas-first editor**:

- **Left:** the canvas and toolbar
- **Right:** the inspector, which also hosts document info and widget selection

This keeps the preview dominant, removes the dead-weight layer rail, and preserves a clear path for selection + editing without duplicating controls.

## Detailed Design

### 1. Route-map appearance model

Keep the existing `route_map` style fields, but make the renderer actually honor them as distinct visual roles.

#### Shape

Supported shapes remain:

1. `circle`
2. `rounded-rect`
3. `square`

#### Colors

Route-map styling should use:

- `background_rgba` for the panel fill, including alpha
- `completed_rgba` for the traveled segment
- `remaining_rgba` for the not-yet-traveled segment

Default values:

- background: `rgba(6, 10, 18, 148)`
- completed: `rgba(34, 255, 138, 255)`
- remaining: `rgb(13, 144, 195)`

The renderer should split the projected route into two segments at the current route position and draw each segment with its own color. The current-position marker can stay visually distinct and does not need to become user-configurable in this pass.

### 2. Editor color controls

Any field declared as `kind: "rgba"` in the editor schema should render through one shared color-picker control:

- HTML color input for RGB
- alpha input for 0-255 transparency

This applies to:

- theme RGBA fields
- progress-bar RGBA fields
- route-map RGBA fields

The older per-channel RGBA UI should no longer be the primary editor experience.

### 3. Progress-bar text alignment

The distance progress-bar should render current distance and total distance on the same Y baseline.

Implementation intent:

- keep the label on the left
- render current distance immediately after the label
- anchor total distance on the right edge
- use the same text baseline for both values

This keeps the bar readable and removes the “two-step” vertical drift in the current rendering.

### 4. Auto-alignment during drag and resize

Dragging and resizing should snap to two kinds of references:

- **grid snap**: an 8px grid
- **context snap**: canvas center lines and nearby widget edges/centers

Behavior:

- apply snapping while the pointer is moving, not only on release
- choose the closest candidate within a small threshold
- prefer contextual widget/canvas guides over the grid when both are close
- show lightweight guide feedback when a non-grid snap is active

This should work for both moving widgets and resizing them from corner handles.

### 5. Canvas-first layout rewrite

Remove the old left rail as a primary panel. Its selection role moves into the inspector as a compact “Widgets” section.

Proposed sidebar stack on the right:

1. Document
2. Widgets (selection only; no reorder or visibility actions)
3. Theme defaults
4. Widget details

The canvas side keeps:

- live preview
- save/help toolbar
- drag handles

The canvas should occupy the main width of the page and use the available viewport height more effectively so the preview is not visually stranded inside a large dead zone.

## Validation

- Add tests for:
  - route-map schema + renderer split-color behavior
  - color-picker rendering for RGBA fields
  - progress-bar text baseline alignment
  - snapping helper behavior
  - canvas-first layout changes
- Run the editor in the browser and confirm:
  - no left layer rail
  - widget selection is still easy
  - route-map uses the new colors
  - drag snapping feels predictable
  - progress-bar text sits on one line

## Acceptance Criteria

- Route-map completed and remaining segments draw in different colors.
- Remaining route color defaults to `rgb(13, 144, 195)`.
- All RGBA editor fields use color picker + alpha controls.
- Distance progress-bar current and total values share the same Y baseline.
- Dragging and resizing snap to both grid and nearby guides.
- The left layer rail is removed from the main workspace.
- The full test suite passes.
