# Streaming Encoding and HUD Styling Design

## Problem

The current render pipeline favors correctness and simplicity, but it has three gaps:

1. Final outputs do not preserve source-video encoding characteristics as closely as practical.
2. Rendering is slower than necessary because production output depends on disk-backed frame caches and an intermediate overlay video.
3. HUD styling controls are too limited for both YAML authors and editor users.

The solution must preserve the existing single-renderer rule: `render_hud_frame` remains the only HUD renderer used by both live preview and production export.

## Goals

- Preserve source encoding parameters as completely as practical for final outputs.
- Prefer a fast streaming export path that avoids PNG frame caches and intermediate overlay movies.
- Fall back automatically to a compatible cache-based path when the fast path cannot safely run.
- Expand HUD styling so the same fields are editable in YAML and the visual editor.
- Make the top ruler show current distance and total distance by default, with configurable visibility.
- Add clear stage-level logging so users can see which render path and encoding profile were selected.

## Non-Goals

- Supporting arbitrary user-supplied font files in the first version.
- Replacing the Python HUD renderer with ffmpeg-native drawing filters.
- Building a strict failure mode that aborts when any source encoding parameter cannot be preserved exactly.

## Constraints

- Production output and live preview must continue to share the same HUD rendering logic.
- Incompatible encoder settings must fall back automatically to the nearest safe output configuration and log the reason.
- YAML and editor UI must read and write the same validated configuration model.
- Logging should remain stage-oriented rather than per-frame verbose.

## Proposed Approach

Use a hybrid render architecture with two export paths:

1. **Streaming-first path (default):**
   - Probe each input video before rendering.
   - Derive a `SourceEncodingProfile` that captures the source video and audio characteristics relevant to export decisions.
   - Render HUD frames with the existing Python renderer and stream them directly into ffmpeg for compositing, avoiding disk-backed PNG caches and the intermediate `overlay.mov`.
   - Build the output encoder arguments from the source profile wherever ffmpeg can safely honor them after filtering.

2. **Compatibility fallback path:**
   - If the streaming pipeline cannot be initialized or source settings cannot be applied safely, fall back to the current cache-based export workflow.
   - Reuse the same encoding decision layer so fallback outputs still inherit as much of the source profile as practical.
   - Emit an explicit log entry describing the fallback reason.

For styling, introduce a typed HUD style model with theme defaults plus widget-level overrides. The editor and YAML will both operate on that same schema-backed model.

## Architecture

### 1. Source Encoding Profile

Add a small ffmpeg/probe model that captures:

- video codec
- pixel format
- fps
- bitrate
- colorspace
- color primaries
- transfer characteristics
- audio codec and relevant copy compatibility

This profile becomes the input to output-encoder selection rather than hardcoding the export format in `ffmpeg.py`.

### 2. Output Encoder Resolution

Add an encoder resolution step that turns a `SourceEncodingProfile` into an `OutputEncodingPlan`.

The resolution order is:

1. Try to preserve source video and audio characteristics as-is when they remain valid after overlay compositing.
2. If a source parameter is incompatible with the selected filter/encoder path, reduce only that parameter to the nearest safe equivalent.
3. Log every meaningful downgrade, such as pixel-format coercion or codec substitution.

The system does not silently pretend to preserve unsupported settings.

### 3. Streaming Export Path

In the fast path:

- Python continues generating HUD frames.
- Those frames are sent directly to ffmpeg over a pipe instead of being written as numbered PNG files.
- ffmpeg composites the source video and the incoming HUD stream in a single export command.

This keeps HUD rendering in Python while removing the heaviest disk I/O from normal renders.

### 4. Cache-Based Fallback Path

The current cached render path remains available as an internal fallback for:

- unsupported streaming input/output combinations
- ffmpeg initialization failures for the streaming graph
- environments where direct streaming cannot satisfy the requested export behavior

Fallback remains automatic and is visible in the log output.

## HUD Style Model

### Theme Defaults

Extend the theme/schema model with explicit style fields for:

- `font_family`
- `font_weight`
- `font_size`
- `text_color`
- `accent_color`
- `panel_color`
- `show_unit`

These fields replace the need to overload ad hoc `style` keys for common styling behavior.

### Widget Overrides

Each widget may override any supported theme field locally. Unspecified values inherit from the theme defaults.

This allows coarse project-wide styling with selective local adjustments, while keeping the saved config compact and predictable.

### Top Ruler Defaults

The top-center distance ruler will:

- show current distance by default
- show total distance by default
- follow the global unit-visibility flag by default
- allow widget-local visibility overrides when needed

This makes the default export/editor behavior match the requested information density without forcing it on every project.

## Editor Integration

The editor will expose controls that map one-to-one to the new validated config fields.

Key rules:

- the editor does not maintain editor-only hidden style state
- live preview updates immediately from the same schema-backed values used for export
- saving from the editor round-trips all new style fields back into project config

This keeps YAML and the editor aligned as a single source of truth.

## Logging and UX

Add stage-level render logs for:

- source probe summary
- chosen output encoding plan
- selected render path (`streaming` or `cache`)
- fallback reason when applicable
- clip-level completion messages

The logging remains concise and readable in the terminal and avoids per-frame output.

## Error Handling

- Invalid style values fail schema validation rather than being silently ignored.
- Unrecoverable ffmpeg or input-file failures still stop the affected render.
- Recoverable export incompatibilities trigger automatic fallback to a safe encoding/render path and emit a clear log entry.

## Testing Strategy

Add or extend tests for:

- source-profile parsing and output-plan selection
- streaming-path command construction
- automatic fallback behavior and fallback logging
- style schema validation and inheritance
- widget-level style overrides
- top ruler default visibility behavior
- editor save/load round-tripping for the new style fields

Run the existing full pytest suite after implementation.

## Risks and Mitigations

- **Streaming path complexity:** keep the cache workflow as a proven fallback instead of replacing it outright.
- **Encoder compatibility edge cases:** isolate encoder resolution into a single planning step so compatibility rules are explicit and testable.
- **Config sprawl:** use a typed style model with inheritance rather than adding many unrelated top-level flags.

## Delivery Shape

This work is scoped as a single implementation effort because the three requested improvements meet in two shared seams:

1. the production render/export pipeline
2. the HUD schema/editor contract

The implementation plan should still break the work into focused tasks around:

- encoding/profile resolution
- streaming render path with fallback
- HUD style schema and renderer support
- editor exposure and config round-trip
- logging and regression coverage
