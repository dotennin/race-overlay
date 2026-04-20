# HUD Render Parity Design

## Goal

Make the production video output match the live HUD preview's visual proportions, switch non-map HUD widgets to transparent-by-default panels, and add concise render progress logs that make cache generation visible in the console.

## Current State

- The editor preview and CLI render already share `render_hud_frame`, which must remain the only HUD renderer.
- Widget coordinates are authored against a 1280×720 reference canvas, but configurable widget geometry and text sizing are still effectively fixed pixel values.
- The shipped preset relies on `theme.panel_rgba` for most widgets, so cards render with translucent backgrounds by default.
- `uv run race-overlay render` only prints a final completion line, which hides where time is being spent during per-video cache generation.

## Approved Requirements

1. Final rendered videos should preserve the same visual proportions as the live preview.
2. `route_map` keeps its panel by default, but all other HUD widgets should default to transparent backgrounds unless a panel is explicitly requested.
3. Render output should show concise progress logs by stage and by video, including cache generation steps, without noisy per-frame spam.

## Chosen Approach

Keep the single-renderer architecture and fix the mismatch inside `render_hud_frame` rather than introducing preset-only tweaks or a second render path.

The renderer will treat 1280×720 as the design reference canvas and derive a scaling context from the actual output frame size. Widget geometry and drawing metrics will be scaled from that shared context so the preview and the final burned-in video stay visually aligned.

Transparency becomes an explicit widget-level behavior instead of an accidental side effect of the preset theme. Logging will be added through a lightweight progress callback so `pipeline.py` can report useful milestones while `cli.py` remains responsible for terminal output.

## Renderer Consistency

### Single-renderer rule

The editor preview and the batch render pipeline must continue to call the same `render_hud_frame` entry point. No preview-only drawing branch and no render-only typography branch are allowed.

### Scaling model

The renderer will compute scale factors from the actual frame size relative to the 1280×720 reference:

- geometry values (`x`, `y`, `width`, `height`, padding) scale with the corresponding axis
- text sizes, stroke widths, and corner radii scale with one stable shared factor so type and lines do not distort
- existing widget anchor semantics stay unchanged
- the legacy `HudLayout` path remains behaviorally unchanged

This fixes the root cause of "text is too small in final video" by scaling the actual rendered HUD rather than manually increasing one preset.

## Widget Panel Defaults

Panel visibility becomes an explicit widget style concern.

- `route_map` defaults to `show_panel: true`
- every other configurable widget defaults to `show_panel: false`
- any widget may opt back into a visible panel via `style.show_panel: true`

This makes transparency the general default while preserving route-map readability. The change is intentional and applies as the new default behavior for configurable widgets.

## Console Logging

Rendering should report progress at the level users actually need for confidence and troubleshooting:

- config and activity loading
- clip discovery / clip start
- clip status decisions, including skips
- frame cache generation
- overlay cache generation
- final composition output
- per-clip completion and overall completion

Logs should be concise, deterministic, and readable in a normal terminal session. They should identify the clip being processed and the cache/output paths involved, but must not print one line per frame.

## Code Boundaries

### `hud.py`

- add internal scaling helpers for configurable widgets
- route every configurable widget through the shared scaling context
- centralize panel-default resolution so widget draw functions do not each invent their own fallback

### `pipeline.py`

- accept a simple progress callback
- emit stage-based progress messages for each clip and cache artifact
- keep rendering/composition logic unchanged apart from progress reporting hooks

### `cli.py`

- pass a terminal writer callback into `run_pipeline`
- preserve Typer as the console output boundary

## Error Handling

- Invalid widget configuration still fails through the existing validation path.
- Missing or invalid preview dimensions remain explicit errors.
- Progress logging must surface skip reasons clearly when a clip falls outside the activity window.
- No silent fallback should reintroduce opaque panels or preview/render divergence.

## Testing Strategy

The implementation plan should cover failing tests first for:

1. scaled HUD rendering on larger-than-reference output sizes
2. transparent-by-default panel behavior for non-map widgets
3. `route_map` retaining its panel by default
4. CLI-visible progress messages during frame cache, overlay cache, compose, and skip paths

Tests should continue to assert the single-renderer contract by verifying that editor-saved HUD configuration renders through the production pipeline without a second translation layer.

## Out of Scope

- adding user-facing render scale knobs
- redesigning the browser editor UI
- changing the legacy `HudLayout` renderer
- verbose per-frame logging

These can be revisited later if the new default behavior proves insufficient, but they are not needed to solve the current parity, transparency, and logging issues.
