# HUD Default Styling and Live Preview Design

## Problem

The current configurable HUD already supports schema-backed widgets, theme defaults, and browser preview, but it misses the visual direction requested for the next default experience:

1. `route_map` does not default to the darker broadcast-style mini-map shown in the reference.
2. Default HUD typography does not match the desired title/value/unit hierarchy or the slanted broadcast-style numerals.
3. `Heart rate` renders the `BPM` unit too far from the value instead of tucking it near the lower-right edge of the digits.
4. `progress_bar` does not default to the denser ruler style shown in the reference and does not expose enough color control for that UI.
5. The web editor still relies too heavily on `change` / settled interactions, so font, size, variant, and RGBA edits do not reflect in preview while the user is actively typing or adjusting channels.

The next revision should treat these as one coordinated visual refresh: new HUDs should look closer to the supplied references by default, while existing saved configurations remain safe and production rendering stays aligned with browser preview.

## Approved Scope

- Update **global defaults for newly created HUD theme typography**, not just one preset instance.
- Update **default rendering for all new `route_map` and `progress_bar` widgets**, not just the built-in `broadcast-runner` copies.
- Introduce **bundled HUD font resources** so the default numerals can get closer to the broadcast look in the references.
- Make editor preview updates happen **during input**, not only after blur, save, or pointer settle.

## Goals

- Keep one schema-backed rendering pipeline for browser preview and final video output.
- Add bundled font resources and new default font-family roles for broadcast-style title/value/unit rendering.
- Refresh `route_map` defaults to a darker circular mini-map with green route emphasis, blue/white heading arrow, north marker, and bottom bearing text.
- Refresh `progress_bar` defaults to the denser ruler UI while keeping fill/rail/tick colors configurable and defaulting the fill to green.
- Tighten unit placement rules so `BPM` and similar suffixes visually attach to the value.
- Preserve explicit save semantics in the editor while making local preview respond immediately to live edits.
- Safely migrate existing `broadcast-runner` configs only when a field still matches legacy defaults or a new field must be backfilled.

## Non-Goals

- Adding an editor-only renderer or preview-only CSS approximation.
- Reworking unrelated HUD widgets that are not affected by typography role defaults or unit placement.
- Forcing all existing custom overlays onto the new look by destructive migration.
- Replacing the existing widget/theme schema model with a second parallel config format.

## Current Findings

### Rendering pipeline

`hud.py` is already the single source of truth for configurable HUD rendering. `editor_preview.py` posts the current draft HUD payload to `/api/preview`, which reuses that renderer to generate a preview PNG. This is the correct architecture to preserve.

### Typography limitations

- Theme defaults already expose `title_*`, `value_*`, and `unit_*` roles, but the built-in families remain limited to `sans`, `serif`, and `mono`.
- Default preset values still lean on DejaVu families, so the result cannot closely match the reference screenshots.
- Left-aligned stat blocks place units using a fixed horizontal offset from the value bounds, which leaves `BPM` visually detached.

### Widget-style limitations

- `route_map` already supports `show_north_marker`, `show_bearing_label`, and `show_heading_arrow`, but its default visuals are still too plain for the requested look.
- `progress_bar` defaults are still built around the earlier ruler treatment and do not expose dedicated rail/fill/tick colors for the new UI.

### Editor refresh gap

- Drag and resize already use a throttled refresh path.
- Inspector controls still lean on `change` handlers, so text, numeric, enum, and RGBA updates do not re-render while the user is actively editing.

## Considered Approaches

### A. Upgrade the existing schema-backed defaults in place

Keep the current renderer, schema, editor preview API, and YAML format. Add bundled font assets, expand schema defaults where necessary, refresh widget defaults, and move editor controls to input-driven preview updates.

**Pros**
- Keeps preview and final render perfectly aligned.
- Matches the approved scope for global defaults and widget defaults.
- Limits risk by building on existing test coverage and migration hooks.

**Cons**
- Requires touching renderer, schema, preset migration, and editor preview code together.

### B. Patch only the built-in preset

Refresh only the preset instances without changing theme/widget defaults or generic widget rendering.

**Pros**
- Smaller code change.

**Cons**
- Fails the approved scope because new custom HUDs and new widget instances would still inherit the old defaults.

### C. Add new variants and leave current defaults alone

Introduce new font and widget variants but keep the current defaults unchanged.

**Pros**
- Backward compatibility is straightforward.

**Cons**
- Conflicts with the explicit request that new HUDs and new widgets default to the new style.
- Adds more editor complexity because users must opt in everywhere.

**Chosen approach:** A.

## Architecture

### 1. Bundled HUD font resources

Add checked-in font assets under `src/race_overlay/assets/fonts/` and extend the font loader in `hud.py` so theme/widget roles can resolve new built-in families:

- `broadcast_ui` → a condensed upright family for labels and supporting text.
- `broadcast_value` → a condensed italic/bold family for hero numerals and primary values.

The implementation should ship with these files:

- `src/race_overlay/assets/fonts/BarlowSemiCondensed-Regular.ttf`
- `src/race_overlay/assets/fonts/BarlowSemiCondensed-Medium.ttf`
- `src/race_overlay/assets/fonts/BarlowSemiCondensed-BoldItalic.ttf`

Schema defaults for new HUDs should move to the new families while preserving per-role overrides and explicit user-authored values.

### 2. Typography role defaults and unit attachment

Keep title/value/unit as separate theme roles, but refresh the defaults:

- titles smaller and lighter
- values larger, heavier, and broadcast-styled
- units smaller and visually attached to the lower-right of the value

`stat_block`, `metric_card`, `hero_metric`, and `context_card` should all continue using the shared role helpers. `stat_block` needs an updated unit-placement rule so `BPM` sits closer to the digits instead of floating too far to the right.

If later fine-tuning is needed, the renderer may add a small style-level unit offset, but the first pass should solve the reference layout through default renderer behavior rather than mandatory per-widget tweaks.

### 3. Route-map default style refresh

Keep the existing `route_map` widget type and navigation affordances, but make the default look closer to the reference:

- dark translucent circular panel treatment
- bright green route stroke
- brighter current-position marker
- blue/white heading arrow
- `N` at the top
- bearing text near the bottom edge

The widget should remain north-up. The arrow direction should continue using the projected route tangent, which already matches the intended semantics for a forward heading indicator.

### 4. Progress-bar default style refresh

Refresh the generic `progress_bar` defaults so new widgets render with:

- a dark rounded rail
- dense vertical tick marks
- a left-to-right filled segment
- reference-style value labeling

The schema should expose dedicated color controls for:

- fill/accent color
- rail color
- tick color
- optional text color override if needed

The default fill remains green. Existing widgets that already override their visual style should retain those overrides after migration.

### 5. Input-driven editor preview refresh

Keep the editor's explicit Save YAML flow, but make preview react during editing:

- use `input` events for text, integer, enum, and RGBA controls
- retain throttling so frequent updates do not flood the preview API
- keep drag/resize on the current throttled path with an immediate flush on pointer-up

The browser preview should continue sending the full draft HUD document to `/api/preview`, so the preview remains a true backend render rather than a front-end simulation.

## Migration Strategy

`config.py` already routes schema HUD payloads through `migrate_broadcast_runner_config`. Extend that migration conservatively:

1. Detect `preset == "broadcast-runner"`.
2. Compare theme roles and widget styles against legacy/default baseline values.
3. Migrate only fields that still match old defaults or are newly introduced.
4. Preserve explicit user changes, especially geometry, color overrides, and custom family choices.

This keeps older configs usable while allowing newly created overlays and untouched defaults to adopt the new look.

## Error Handling

- Invalid font family names still fail validation.
- Invalid color arrays still fail validation.
- Missing bundled font files should fail loudly during development/tests rather than silently changing the visual baseline.
- Preview refresh failures should continue surfacing through the existing status message path in the editor.

## Testing Strategy

Add or extend tests for:

- new font family validation and editor schema exposure
- default theme role values for new HUDs
- route-map default rendering behavior and text labels
- progress-bar default style fields and rendering labels
- stat-block unit placement regression coverage
- safe `broadcast-runner` migration behavior
- editor preview refresh during `input`-driven control changes

Run the existing suite with `uv run pytest -q`.

## Delivery Shape

This should ship as one coordinated implementation because the renderer defaults, preset defaults, migration rules, and editor refresh semantics all need to agree on the same visual baseline.
