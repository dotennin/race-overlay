# HUD v2 Designer Redesign

## Goal

Upgrade the local HUD editor from a save-and-reload form editor into a canvas-first designer, and redesign the default running HUD so it feels much closer to the new visual reference while staying practical for repeated production use.

## Current State

- The project already has a schema-driven HUD, a browser editor, and a working production renderer.
- The current editor is still too form-centric and does not feel like a true layout designer.
- Some edits require a save/reload loop instead of showing up immediately.
- The shipped default HUD does not yet match the new reference closely enough in structure, spacing, and hierarchy.

## Approved Design Summary

This redesign keeps the current Python render pipeline as the only production renderer, but upgrades the authoring experience and the default preset in four specific ways:

1. **Default HUD visual redesign**: move the preset closer to the reference image, especially in the top progress treatment, left metric grouping, and lower-left map presence.
2. **Canvas-first editor**: users manipulate HUD blocks directly on the preview canvas instead of mainly through form fields.
3. **Immediate preview**: drag, resize, reorder, show/hide, and style edits update the browser preview immediately.
4. **Explicit persistence**: `overlay.yaml` changes only when the user presses **Save YAML**.

## Visual Direction for the Default Preset

The default preset should remain telemetry-first and should not waste screen space on persistent editor chrome or non-essential decorative branding.

### Layout structure

- A **half-width top distance ruler** sits near the top center.
- The ruler uses **kilometer-based segmentation** with a **checkpoint / ruler** feel rather than a thick continuous bar.
- The ruler background stays **fully transparent** so it reads like an overlay rather than a panel.
- The lower-left **route map becomes larger** and gets more reserved space than before.
- The left-side stat stack keeps **Elevation** and **Distance** prominent, with **Distance** placed slightly higher than in the current build.
- **Elevation**, **Heart rate**, and **Distance** labels should be slightly smaller than the current draft so the numbers stay dominant.
- Unit labels for **Elevation** and **Distance** sit **close to the numeric value**, reading as one compact stat lockup.

### Visual language

- Strong typography hierarchy with large italicized numbers and smaller labels.
- Translucent and lightweight framing where needed, but not heavy boxed panels everywhere.
- Clear negative space around the map and primary metrics.
- Close visual inspiration from the reference image, but still implemented through the existing widget system instead of a one-off hard-coded composition.

## Editor Workspace

The redesigned editor uses a three-pane layout:

1. **Layers panel** on the left for layer order, visibility, and quick selection.
2. **Canvas preview** in the center as the main editing surface.
3. **Inspector** on the right for precise position, size, and style editing.

The canvas is the primary interaction surface. The side panels support it but should not dominate the screen.

## Interaction Model

### Direct manipulation

- Dragging a HUD block on the canvas moves it immediately.
- Resize handles on the selected block change width and height directly on canvas.
- Reordering items in the Layers panel updates z-order immediately.
- Show/hide is controlled from the layer row and reflected immediately in preview.
- Style edits from the Inspector also update preview immediately.

### Help behavior

- The interaction rules are **not** shown as a permanent card or sidebar.
- A compact **Help** entry point, such as a `?` button, is available in the toolbar.
- **Help is hidden by default**.
- Users open Help only when needed, as a popup/modal that does not permanently consume workspace.

### Save behavior

- The editor starts from the currently saved `overlay.yaml`.
- As the user edits, changes are stored in an **in-memory draft state**.
- The preview always reflects the draft state, not only the last saved state.
- `overlay.yaml` is rewritten **only** when the user presses **Save YAML**.
- Reloading the editor without saving discards the unsaved draft and restores the last saved YAML state.

## Shared Data Flow

The editor and the production renderer must use the same core HUD model and the same render path.

### Required rule

The preview image shown in the browser and the final video overlay rendered by the CLI must both come from the same widget schema and the same renderer behavior. The browser editor is an authoring UI, not a second rendering engine with different layout logic.

### Flow

1. Load `overlay.yaml` into the HUD document.
2. Create an in-memory draft copy for the editor session.
3. Re-render preview PNGs from that draft during editing.
4. Serialize the draft back to `overlay.yaml` only on explicit save.
5. The CLI render command consumes that same saved HUD document for final video export.

This guarantees that what the user previews is what lands in the video.

## HUD Schema Impact

The current schema-driven approach stays in place, but the editor now treats widgets as freely positioned canvas objects rather than primarily form-defined entries.

### V1 schema expectations

- Existing widget IDs and widget types remain supported.
- Widgets keep explicit geometry: `x`, `y`, `width`, `height`, `z_index`, `visible`.
- The schema remains YAML-editable by hand.
- Any new editor-specific fields should stay minimal and only be added when the existing widget document cannot express the approved behavior.

The design does **not** require a second independent scene format.

## V1 Scope

### Included

- Drag
- Resize
- Layer ordering
- Visibility toggles
- Style editing
- Immediate preview
- Explicit Save to YAML
- Help popup
- Default preset redesign toward the approved broadcast/reference style

### Excluded from V1

- Automatic snap and advanced alignment systems
- Multi-select batch editing
- Widget grouping
- Undo/redo history
- Timeline animation or keyframe editing
- A visual multi-preset management UI

The first implementation should focus on making the core editing loop feel solid and predictable.

## Error Handling

- Invalid geometry or widget config should still fail clearly through the existing validation path.
- Save should reject invalid draft state rather than silently writing broken YAML.
- Preview errors should surface visibly in the editor instead of silently falling back.

## Testing Strategy

The implementation plan should cover:

- live preview updates after drag/resize/style changes
- YAML remaining unchanged until explicit save
- saved YAML round-tripping cleanly back into editor state
- layer order and visibility being reflected in preview and final render
- default preset layout rendering with the new top ruler and enlarged route map structure
- help popup defaulting to closed

## Implementation Boundary

This redesign is an upgrade to the existing HUD system, not a rewrite into a full design platform. The implementation should improve the shipped preset and editing workflow while preserving the single-renderer architecture that already works in production.
