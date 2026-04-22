# HUD Navigation, Typography, and Editor Refresh Design

## Problem

The current HUD and editor deliver the basic data, but they fall short in six visible ways:

1. The route-map HUD does not show north, current bearing text, or a forward-direction arrow.
2. There is no compact top-left time HUD with a full timestamp format.
3. Default typography does not match the desired visual hierarchy: titles are too large relative to values, units are too detached, and font treatment is too uniform.
4. The current TCX cadence path surfaces values around 90 even though the activity should read around 180.
5. The elapsed widget still shows the `hh:mm:ss` unit suffix even though the formatted value already encodes time.
6. In the editor, widget overlays can move immediately while the live preview lags behind, which makes fixed HUD content feel detached from the drag interaction.

The next revision should treat this as a visual refresh, not a patch release. The goal is to make `broadcast-runner` feel closer to a polished sports-broadcast package while keeping YAML, editor state, and production rendering aligned through the same schema-backed HUD model.

## Goals

- Add route-map navigation affordances: north marker, `degrees + cardinal` bearing text, and a forward arrow driven by the route tangent at the current projected point.
- Add a compact top-left time HUD with default format `YYYY/MM/DD HH:mm:ss`.
- Refresh the default typography so label, value, and unit each have distinct visual roles.
- Normalize cadence for the currently confirmed TCX running case so the rendered HUD shows the expected value range.
- Remove the elapsed widget's redundant `hh:mm:ss` suffix by default.
- Make the editor preview update during drag/resize instead of only after interaction settles.
- Refresh the `broadcast-runner` preset layout and spacing, and migrate existing `broadcast-runner` configs toward the new visual defaults when it is safe.

## Non-Goals

- Introducing a second HUD renderer or editor-only rendering path.
- Building a general geospatial heading engine outside the HUD needs of this project.
- Auto-migrating every custom HUD layout regardless of how heavily the user has already edited it.
- Reworking every preset in the repo; this design focuses on `broadcast-runner`.

## Current Findings

### Cadence root cause

The configured activity file is `activity_22577902433.tcx`. Fresh inspection of the parsed values shows:

- `cadence_count = 9343`
- `avg = 92.52`
- `max = 101`

The TCX file populates `Extensions/TPX/RunCadence` and does not populate `Trackpoint/Cadence`. The reader currently maps `RunCadence` directly to `cadence_spm`, which strongly suggests the loader is exposing half-cadence / per-leg cadence as if it were full steps per minute.

### Editor drag mismatch

The editor overlay box updates immediately on pointer movement, but preview rendering is currently driven by a debounced refresh path. During active drag, repeated pointer events keep resetting the debounce timer, so the image often remains stationary until the interaction pauses or ends. This matches the reported “drag box moves, fixed HUD does not” behavior.

### Current visual limitations

- `stat_block` uses one font scale for title and value, so the hierarchy is weak.
- Units are placed far from values in left-aligned stat blocks.
- `metric_card` compact widgets treat title/value/unit with nearly the same typographic weight.
- `route_map` currently draws only the line and current point; there is no navigation overlay.

## Proposed Approach

Treat this as a schema-first visual refresh with three coordinated layers:

1. **Data normalization**
   - Normalize confirmed cadence anomalies at the activity-reader boundary.
   - Keep elapsed formatting compact and remove the redundant suffix from defaults.

2. **HUD schema + renderer expansion**
   - Extend route-map styling/options to support navigation overlays.
   - Add a timestamp widget path using the existing schema-backed HUD model.
   - Split typography into title/value/unit sizing and weight so the renderer can express a clearer hierarchy.

3. **Preset + editor refresh**
   - Recompose the default `broadcast-runner` layout and spacing.
   - Make the editor preview update while dragging/resizing.
   - Expose the same new controls in editor schema so YAML and UI stay aligned.

## Architecture

### 1. Cadence normalization boundary

Cadence correction belongs in the activity ingestion layer, not in HUD rendering.

Planned behavior:

- For running activities loaded from TCX where cadence is sourced from `RunCadence`, normalize to full steps per minute before the data reaches `HudSample`.
- Do not blindly change FIT behavior in the same pass; only expand normalization there if the repo produces matching evidence.
- Add regression coverage around the current activity semantics so the fix is evidence-backed rather than heuristic guesswork.

This keeps every downstream consumer consistent: live preview, production render, tests, and future widgets all see the same corrected cadence.

### 2. Route-map navigation overlay

The route-map widget will remain a HUD widget, but gain a richer overlay layer:

- `show_north_marker` — default `true`
- `show_bearing_label` — default `true`
- `show_heading_arrow` — default `true`
- `bearing_label_format` — default `degrees_cardinal`

The map remains north-up. The current-motion arrow uses the tangent of the projected route segment at the current point, which is the user-approved direction source. The label renders as text like `220°SW`.

Visually:

- `N` sits near the top of the circular map.
- The arrow is drawn at the current point and rotated to the route tangent.
- The bearing label sits near the bottom edge of the map panel.

### 3. Timestamp HUD

Instead of overloading the existing large context-card presentation, add a compact timestamp-capable widget path that can live in the top-left broadcast cluster.

Default behavior:

- format: `YYYY/MM/DD HH:mm:ss`
- positioned near the top-left, above or alongside the stat cluster
- follows the same typography hierarchy as the refreshed preset

The saved config should carry the format explicitly so editor users can adjust it later without introducing editor-only state.

### 4. Typography hierarchy

The visual refresh needs more than one `font_size_px`.

Add theme-level typography roles, with widget overrides where appropriate:

- title font family / weight / size
- value font family / weight / size
- unit font family / weight / size

The defaults should bias toward:

- smaller labels
- larger, heavier values
- compact, visually attached units

This preserves current font-family selection while letting the default preset look closer to the provided reference.

### 5. Layout and spacing refresh

Refresh `broadcast-runner` so the default composition is more coherent:

- top-left: time HUD + tighter stat blocks
- top-center: ruler remains, but should visually match the refined type scale
- right-side compact metrics: more balanced spacing, no redundant elapsed suffix
- route-map cluster: richer navigation treatment

Specific spacing change:

- left-aligned stat blocks should bring the unit much closer to the rendered value instead of pinning it to the far edge of a wide panel

### 6. Editor live-preview behavior

Replace the “debounce-only while dragging” experience with a two-speed model:

- during drag/resize: throttled preview updates so the rendered HUD keeps following the interaction
- on pointerup: immediate flush to the latest geometry

Save behavior remains explicit. Dragging still edits only local draft state until the user presses **Save YAML**.

## Migration Strategy

The user explicitly wants existing `broadcast-runner` configs to move toward the new visual defaults when possible, but without destroying deliberate customization.

Migration policy:

1. Detect `preset == "broadcast-runner"`.
2. Compare widget geometry/style against the legacy built-in defaults.
3. If a widget still matches or nearly matches the legacy default shape/style, migrate it to the new default values.
4. If a widget has clearly user-edited geometry/style, preserve the user-authored values and only backfill newly required fields with safe defaults.

This makes the migration selective rather than destructive.

## Error Handling

- Invalid new style values still fail validation instead of silently falling back.
- If route-map navigation overlays cannot compute a current direction because there is no usable route segment, the map still renders and only the arrow/label are omitted.
- If timestamp formatting is invalid, validation should fail at config/schema level rather than rendering broken strings.

## Testing Strategy

Add or extend tests for:

- TCX cadence normalization from `RunCadence`
- route-map north marker, bearing text, and heading arrow rendering behavior
- timestamp widget formatting
- typography hierarchy defaults and stat/unit spacing behavior
- elapsed widget default suffix removal
- selective `broadcast-runner` migration behavior
- editor schema exposure for new fields
- editor drag preview behavior / refresh policy

Run the full `uv run pytest -q` suite after implementation.

## Risks and Mitigations

- **Migration risk:** selective migration avoids clobbering heavily customized configs.
- **Heading jitter:** deriving the arrow from the projected route tangent avoids raw GPS noise.
- **Schema sprawl:** keep new controls grouped by clear widget/theme roles instead of adding unrelated one-off flags.
- **Editor churn:** preserve explicit save semantics and local-draft preview flow while improving drag responsiveness.

## Delivery Shape

This work should be implemented as one coordinated effort because the user asked for a single visual refresh and the main seams are shared:

1. activity ingestion / normalized sample values
2. HUD schema and renderer
3. preset defaults and migration
4. editor preview and schema exposure

The implementation plan should therefore split work by seam, not by isolated visual symptom.
