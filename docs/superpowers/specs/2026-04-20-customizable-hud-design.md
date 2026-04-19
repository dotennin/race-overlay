# Customizable HUD Redesign

## Goal

Redesign the rendered running HUD so it feels visually close to the provided reference image while also making the HUD easy to customize in the future through both YAML configuration and a browser-based visual editor.

## Current State

- The current renderer draws one hard-coded black telemetry panel plus a mini-map.
- The current config supports activity paths, video globs, timing offsets, field toggles, and per-video overrides.
- The current pipeline already works for batch rendering and should remain the production rendering path.
- There is no layout schema, theme system, widget model, or visual editor today.

## Chosen Approach

Use a declarative HUD system with three layers:

1. **Rendering layer**: keep the current Python + Pillow + FFmpeg render pipeline as the final output path.
2. **Description layer**: introduce a richer HUD schema that describes presets, themes, layout, and widgets.
3. **Editing layer**: add a browser-based editor that previews and edits the same HUD schema, then exports it back to YAML.

This approach is preferred because it preserves the existing stable batch renderer while enabling both code-friendly and user-friendly customization.

## Design Principles

- **One source of truth**: YAML is the durable representation, even when edited through the browser.
- **Preset first**: ship a polished default preset so the redesign is immediately usable.
- **Reference-inspired, not pixel-for-pixel**: match the visual language and hierarchy of the reference image without turning the design into a brittle copy.
- **Backward compatible**: existing configs should continue to render.
- **Fail clearly**: invalid widget config should surface explicit validation errors.

## User Workflow

### Repeatable CLI workflow

1. Keep using `overlay.yaml` as the main project config.
2. Select a HUD preset or adjust widget configuration in YAML.
3. Run the existing render command to batch-produce output videos.

### Visual editing workflow

1. Open a browser editor from the local project.
2. Load the current HUD config and preview it against a representative sample frame.
3. Drag, resize, reorder, show, hide, and style widgets.
4. Export the updated HUD back to YAML.
5. Run the normal CLI render command.

The browser editor is an authoring tool, not a second renderer. The final video output still comes from the existing offline render pipeline.

## Visual Direction

The default preset should move from a single blocky panel to a composed broadcast-style overlay with distinct but coordinated cards:

- a compact route map card in the upper-left
- a horizontal distance-progress strip near the top
- a hero pace card with the strongest visual priority
- secondary metric cards for heart rate, cadence, elapsed time, and speed
- a context card for time, date, and weather-like information

The visual language should use layered translucent panels, stronger typography contrast, more deliberate spacing, rounded cards, and cleaner grouping so the overlay feels closer to the reference image.

## Architecture

## Production renderer

The final renderer remains Python-driven and deterministic:

- `pipeline.py` still coordinates sampling, per-frame HUD generation, and FFmpeg composition
- `hud.py` evolves from one hard-coded layout into a widget renderer
- the renderer consumes a resolved HUD document rather than hand-coded positions

This keeps batch rendering, cache behavior, and video composition stable.

## HUD document model

The HUD config should expand from simple field toggles into a structured document with these concepts:

- `preset`: the chosen named visual preset
- `theme`: colors, opacity, font sizes, stroke styles, corner radii, spacing tokens
- `canvas`: safe margins, anchor grid, default scaling rules
- `layout`: high-level zones or placements used by the preset
- `widgets`: the actual renderable blocks

Each widget should define:

- `id`
- `type`
- `binding` or bindings to telemetry values
- `anchor`
- `x`, `y`, `width`, `height`
- `z_index`
- `visible`
- `style`
- optional preset-specific settings

This model must be rich enough for the browser editor and simple enough for YAML editing by hand.

## Widget system

The renderer should support a small focused widget vocabulary rather than arbitrary drawing:

- `progress_bar`
- `route_map`
- `hero_metric`
- `metric_card`
- `context_card`
- optional decorative label or divider primitives only when needed by shipped presets

Each widget type has a clear contract:

- what telemetry fields it can bind to
- what style tokens it supports
- what fallback behavior it uses when data is missing

Keeping the widget set narrow is important so the first version stays reliable and easy to validate.

## Presets and themes

Ship at least one new built-in preset that represents the redesigned reference-inspired look:

- `broadcast-runner` as the recommended default

Presets define a good starting widget composition and spacing. Themes supply the color and typography system. Users can start from a preset, then edit widget placement and styling without rebuilding the layout from nothing.

## Browser editor

The browser editor should:

- load the current project HUD config
- render a preview using the same widget schema
- expose widget selection, drag, resize, visibility toggles, and style controls
- allow preset switching
- export valid YAML back to disk

The editor should not become a general HTML/CSS authoring environment. It is a structured editor for the HUD schema.

## Backward compatibility

Existing configs remain valid.

If a config only contains the older `hud.fields` switches:

- the loader should map those switches into the default preset's widget visibility model
- unspecified layout and style values should fall back to the default preset

If a config contains the newer `preset/theme/layout/widgets` structure, the renderer should use it directly.

This preserves the current workflow and avoids forcing users to migrate manually before rerendering old projects.

## Validation and error handling

The loader and editor should share one validation model.

Hard errors should include:

- unknown widget types
- unsupported telemetry bindings
- malformed geometry values
- invalid color, font, or style fields
- duplicate widget IDs

Warnings may include:

- overlapping widgets
- widgets placed too close to safe margins
- widgets whose data source is frequently missing

The CLI should stop on invalid HUD configuration rather than silently rendering misleading output.

## Out of Scope

This redesign intentionally excludes:

- fully arbitrary HTML/CSS HUD rendering
- a freeform desktop design app
- timeline animation editing inside the visual editor
- keyframe choreography for widget motion
- support for non-running sport templates in the same redesign

These can be considered later if the structured widget system proves too limiting.

## Testing Strategy

The implementation plan should cover these areas:

### Config and compatibility

- old config files still load
- old field toggles map correctly into default widget visibility
- new HUD schema parses and serializes cleanly

### Rendering

- widget layouts render at expected sizes and positions
- missing optional data uses defined fallback behavior
- reference-inspired preset produces a non-empty composed frame

### Validation

- invalid widget type, binding, and geometry cases fail clearly
- warning-only cases are surfaced without crashing

### Editor integration

- editor export produces YAML the CLI can load directly
- a config modified in the editor renders through the production pipeline without extra translation

## Implementation Boundary

The first implementation should focus on:

- the new schema
- one polished built-in preset
- backward compatibility with existing configs
- the minimal browser editor needed to edit and export that schema

It should not try to become a universal graphics system in the first pass.
