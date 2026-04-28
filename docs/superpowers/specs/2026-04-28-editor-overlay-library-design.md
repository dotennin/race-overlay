# Editor overlay library and collapsible theme defaults

## Problem

The HUD editor currently assumes all editing starts from existing widgets on the canvas or in Layers. Adding new overlays is not surfaced as a first-class workflow, which makes it hard to discover the full set of supported HUD blocks, especially newly added ones such as `lap_waterfall`. The editor also renders theme defaults as always-visible controls, which adds noise when most edits are widget-scoped.

## Goals

- Add a visible overlay library so users can append any supported HUD widget directly from the editor.
- Include **all** supported widget types in that library, including `lap_waterfall`.
- Make theme defaults hidden by default and only expanded when the user explicitly wants global theme edits.
- Preserve the existing canvas-first editing flow and avoid making widget editing harder.

## Non-goals

- Changing the default `broadcast-runner` preset contents.
- Reworking canvas drag/resize behavior.
- Designing a generalized widget templating system beyond sensible per-type defaults for insertion.

## Approaches considered

### 1. Right-panel overlay library inside Inspector

This keeps the shell two-column and minimizes layout churn, but it overloads the right panel with document controls, add-widget actions, theme defaults, and selected-widget editing all in one place. It also weakens the visual separation between “add a new thing” and “edit the selected thing.”

### 2. Left-side add-overlay rail with canvas centered

This creates a clear three-pane shell: add on the left, preview in the middle, edit on the right. It makes discovering available overlays easier, keeps the canvas prominent, and leaves the Inspector focused on the selected widget. This is the approved direction.

### 3. Toolbar-triggered add modal

This keeps the editor visually lighter, but hides the library behind another click and makes exploration of supported HUD types less obvious. It also makes repeated add/edit/add cycles slower than a persistent rail.

## Approved design

### Layout

The editor becomes a three-column shell:

1. **Left rail: Overlay library**
   - Persistent panel dedicated to adding overlays.
   - Shows the full HUD catalog as clickable items/cards.
   - Clicking an item immediately appends that widget to the document, adds it to Layers, selects it, and refreshes preview.

2. **Center: Canvas**
   - Remains the visual focus and keeps current drag/resize affordances.
   - No major workflow change besides preserving enough space after the new left rail is introduced.

3. **Right panel: Inspector**
   - Continues to hold document metadata, layers, and selected-widget controls.
   - `Theme defaults` becomes a collapsed section at the top of the inspector flow, expanding only on demand.

### Overlay library behavior

- The library is populated from a single source of truth for supported widget types rather than a hand-maintained partial list.
- Each catalog entry has:
  - human-friendly label,
  - widget type identifier,
  - stable insertion defaults (anchor, x/y, width/height, z-index, bindings, style defaults).
- Insertion is immediate; there is no second confirmation step.
- New widgets should appear in a predictable location that avoids obvious overlap with the most common existing blocks, while still remaining easy to spot and drag.
- `lap_waterfall` must be present in the library with defaults that make it visible and previewable immediately.

### Theme defaults behavior

- `Theme defaults` is rendered as a collapsed accordion/section in the Inspector.
- The collapsed state is the default on load.
- Expanding the section reveals the existing schema-backed theme controls unchanged.
- Collapsing it again should not discard edits; it only changes visibility.

### Data and code structure

- Add an explicit editor-side widget catalog definition that can drive:
  - add-overlay UI rendering,
  - widget insertion payloads,
  - tests for catalog completeness.
- Keep schema-backed style rendering as-is for per-widget controls; the new library is additive, not a replacement for the existing schema system.
- Continue using the existing widget list/layer order model after insertion so new widgets flow through current save/preview code paths without special cases.

### Error handling

- If insertion defaults are invalid for a widget type, the editor should surface the existing error/status messaging rather than silently failing.
- Unknown widget types must not appear in the library.
- Theme collapse/expand is presentational state only and must not mutate saved HUD data.

### Testing

- Add editor-state tests for overlay library metadata presence, including `lap_waterfall`.
- Add browserless/editor logic tests for widget insertion defaults and selected-widget handoff.
- Add tests ensuring theme defaults are collapsed by default and expandable without changing stored theme values.
- Keep existing preview/save tests intact to confirm the new UI state does not break document serialization.

## Implementation notes

- Reuse the existing visual language from `editor_assets/styles.css`; the left rail should look like part of the same product, not a bolted-on sidebar.
- Prefer concise card/list entries over large previews so the rail remains scannable even as more HUD widget types are added.
- Because the center canvas is the main value of the editor, the left rail should be narrower than the Inspector and should degrade gracefully on smaller widths.
