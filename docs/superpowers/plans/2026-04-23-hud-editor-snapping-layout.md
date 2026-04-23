# HUD Editor Snapping and Canvas Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship route-map split coloring, color-picker RGBA editing, aligned progress-bar labels, drag snapping, and a two-column canvas-first editor layout.

**Architecture:** Keep renderer behavior in `src/race_overlay/hud.py`, keep editor schema/serialization in the Python editor layer, and keep all browser/editor interaction logic in `editor_assets/app.js` + `index.html` + `styles.css`. Use small shared helpers for color picking and snapping so the editor stays schema-driven and the drag math stays testable.

**Tech Stack:** Python, Pillow, YAML, pytest, browser automation with agent-browser, vanilla JS/CSS.

---

## File Map

- `src/race_overlay/hud.py` — route-map segment splitting, route-map fill colors, progress-bar text layout.
- `src/race_overlay/editor_assets/app.js` — color-picker controls, snap helpers, widget selection rendering, drag interaction updates.
- `src/race_overlay/editor_assets/index.html` — two-column shell and inspector placement for document/widgets.
- `src/race_overlay/editor_assets/styles.css` — color-picker styling, snap-guide styling, two-column layout.
- `tests/test_hud.py` — renderer and layout tests.
- `tests/test_editor.py` — editor schema/source-layout tests.

## Notes

- Do **not** touch `overlay.yaml` in this pass; the current request is about renderer/editor behavior, not the checked-in baseline file.
- The left layer rail is removed from the primary workspace; widget selection moves into the inspector as a selection-only list.
- All RGBA fields should use the shared color-picker control; no user-facing per-channel RGBA editor should remain.

### Task 1: Split route-map rendering into completed and remaining colors

**Files:**
- Modify: `src/race_overlay/hud.py`
- Modify: `tests/test_hud.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_hud_frame_route_map_uses_completed_and_remaining_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    rectangle_fills: list[tuple[int, int, int, int]] = []

    original_line = ImageDraw.ImageDraw.line
    original_round = ImageDraw.ImageDraw.rounded_rectangle

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    def record_round(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            rectangle_fills.append(fill)
        return original_round(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)
    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_round)

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0833, 140.2107), (36.0834, 140.2108)],
        hud=HudConfig(
            preset="custom",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=240,
                    height=240,
                    style={
                        "label": "",
                        "shape": "rounded-rect",
                        "show_panel": True,
                        "background_rgba": [6, 10, 18, 148],
                        "completed_rgba": [34, 255, 138, 255],
                        "remaining_rgba": [13, 144, 195, 255],
                        "show_north_marker": False,
                        "show_bearing_label": False,
                        "show_heading_arrow": False,
                    },
                ),
            ],
        ),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert (6, 10, 18, 148) in rectangle_fills
    assert (34, 255, 138, 255) in line_fills
    assert (13, 144, 195, 255) in line_fills
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_hud.py -k "route_map_uses_completed_and_remaining_colors" -q`

Expected: FAIL because `_draw_route_map()` still draws one polyline color.

- [ ] **Step 3: Write the minimal implementation**

```python
ROUTE_MAP_BACKGROUND_RGBA = (6, 10, 18, 148)
ROUTE_MAP_COMPLETED_RGBA = (34, 255, 138, 255)
ROUTE_MAP_REMAINING_RGBA = (13, 144, 195, 255)


def _split_route_segments(
    projected: list[tuple[float, float]], projection: RouteProjection
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    split_index = projected.index(projection.segment_start)
    completed = projected[: split_index + 1] + [projection.point]
    remaining = [projection.point] + projected[split_index + 1 :]
    return completed, remaining
```

```python
background_rgba = _style_rgba(widget, "background_rgba", ROUTE_MAP_BACKGROUND_RGBA)
completed_rgba = _style_rgba(widget, "completed_rgba", ROUTE_MAP_COMPLETED_RGBA)
remaining_rgba = _style_rgba(widget, "remaining_rgba", ROUTE_MAP_REMAINING_RGBA)

if _widget_panel_enabled(widget):
    widget_draw.rounded_rectangle((0, 0, w, h), radius=_scale_draw(scale, 16), fill=background_rgba, outline=ROUTE_MAP_PANEL_OUTLINE_RGBA)
completed_points, remaining_points = _split_route_segments(projected, route_projection)
if len(completed_points) >= 2:
    widget_draw.line(completed_points, fill=completed_rgba, width=_scale_draw(scale, 4))
if len(remaining_points) >= 2:
    widget_draw.line(remaining_points, fill=remaining_rgba, width=_scale_draw(scale, 4))
```

- [ ] **Step 4: Run the focused renderer tests**

Run: `uv run pytest tests/test_hud.py -k "route_map_uses_completed_and_remaining_colors or route_map" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud.py tests/test_hud.py
git commit -m "feat: split route-map rendering colors"
```

### Task 2: Align distance progress-bar current and total labels

**Files:**
- Modify: `src/race_overlay/hud.py`
- Modify: `tests/test_hud.py`

- [ ] **Step 1: Write the failing test**

```python
def test_progress_bar_text_layout_aligns_current_and_total_values() -> None:
    layout = _progress_bar_text_layout(left=0, top=0, width=560, height=56, label="Distance")

    assert layout.current_anchor[1] == layout.total_anchor[1]
    assert layout.total_anchor[0] > layout.current_anchor[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_hud.py -k "progress_bar_text_layout_aligns_current_and_total_values" -q`

Expected: FAIL because `_draw_progress_bar()` still offsets total distance separately.

- [ ] **Step 3: Write the minimal implementation**

```python
def _progress_bar_text_layout(left: int, top: int, width: int, height: int, label: str) -> ProgressBarTextLayout:
    baseline_y = top + 12
    current_x = left + 12 + (len(label) * 8 if label else 0)
    total_x = left + width - 12
    return ProgressBarTextLayout(current_anchor=(current_x, baseline_y), total_anchor=(total_x, baseline_y))
```

```python
layout = _progress_bar_text_layout(track_left, top, track_right - track_left, track_bottom - track_top, label)
if label:
    draw.text((track_left, layout.current_anchor[1]), label, fill=tuple(theme.text_rgba), font=title_font)
if show_current_value:
    draw.text(layout.current_anchor, _distance_label(progress_value_m, show_units), fill=tuple(theme.text_rgba), font=value_font)
if show_total_value:
    draw.text(layout.total_anchor, _distance_label(goal_m, show_units), fill=tuple(theme.text_rgba), anchor="ra", font=value_font)
```

- [ ] **Step 4: Run the focused renderer tests**

Run: `uv run pytest tests/test_hud.py -k "progress_bar_text_layout_aligns_current_and_total_values or draw_progress_bar" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud.py tests/test_hud.py
git commit -m "feat: align progress bar distance labels"
```

### Task 3: Replace RGBA channel inputs with color-picker controls

**Files:**
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editor_asset_uses_color_picker_controls_for_rgba_fields() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert "function buildColorInput(" in app_js
    assert 'className = "color-alpha-input"' in app_js
    assert "function buildRgbaInput(" not in app_js
    assert ".color-alpha-input" in css
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_editor.py -k "color_picker_controls_for_rgba_fields" -q`

Expected: FAIL because RGBA controls are still rendered as channel-by-channel inputs.

- [ ] **Step 3: Write the minimal implementation**

```javascript
function buildColorInput(value, onChange, onInput = null) {
  const rgba = Array.isArray(value) && value.length === 4 ? [...value] : [255, 255, 255, 255];
  const wrapper = document.createElement("div");
  wrapper.className = "color-alpha-input";

  const color = document.createElement("input");
  color.type = "color";
  color.value = rgbToHex(rgba.slice(0, 3));

  const alpha = document.createElement("input");
  alpha.type = "number";
  alpha.min = "0";
  alpha.max = "255";
  alpha.value = String(rgba[3]);

  function emitColorChange() {
    const [r, g, b] = hexToRgb(color.value);
    const next = [r, g, b, Number(alpha.value)];
    (onInput ?? onChange)(next);
  }

  color.addEventListener("input", emitColorChange);
  alpha.addEventListener("input", emitColorChange);
  wrapper.append(color, alpha);
  return wrapper;
}
```

```javascript
if (metadata?.kind === "rgba") {
  appendField(parent, fieldLabel, buildColorInput(value, onChange, onInput), true);
  return;
}
```

```css
.color-alpha-input {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) 84px;
  align-items: end;
}

.color-alpha-input input[type="color"] {
  height: 42px;
  padding: 4px;
}
```

- [ ] **Step 4: Run the focused editor tests**

Run: `uv run pytest tests/test_editor.py -k "color_picker_controls_for_rgba_fields or exposes_theme_and_widget_style_schema" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_assets/app.js src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: switch RGBA fields to color pickers"
```

### Task 4: Add drag and resize snapping to grid and guides

**Files:**
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editor_asset_defines_drag_snapping_helpers() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "const GRID_SNAP_SIZE = 8" in app_js
    assert "function collectSnapGuides(" in app_js
    assert "function snapRectToGuides(" in app_js
    assert "function renderSnapGuides(" in app_js
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_editor.py -k "drag_snapping_helpers" -q`

Expected: FAIL because the editor still applies raw drag deltas without snap candidates.

- [ ] **Step 3: Write the minimal implementation**

```javascript
const GRID_SNAP_SIZE = 8;
const SNAP_THRESHOLD = 6;

function collectSnapGuides(widgetId) {
  const canvas = getPreviewDimensions();
  const widgets = getWidgetsInLayerOrder().filter((widget) => widget.id !== widgetId && widget.visible);
  return {
    x: [0, canvas.width / 2, canvas.width, ...widgets.flatMap((widget) => [widget.x, widget.x + widget.width / 2, widget.x + widget.width])],
    y: [0, canvas.height / 2, canvas.height, ...widgets.flatMap((widget) => [widget.y, widget.y + widget.height / 2, widget.y + widget.height])],
  };
}

function snapValue(value, candidates, gridSize) {
  const grid = Math.round(value / gridSize) * gridSize;
  let best = { value: grid, delta: Math.abs(grid - value), kind: "grid" };
  candidates.forEach((candidate) => {
    const delta = Math.abs(candidate - value);
    if (delta <= SNAP_THRESHOLD && delta < best.delta) {
      best = { value: candidate, delta, kind: "guide" };
    }
  });
  return best;
}

function snapRectToGuides(rect, widgetId) {
  const guides = collectSnapGuides(widgetId);
  const left = snapValue(rect.left, guides.x, GRID_SNAP_SIZE);
  const top = snapValue(rect.top, guides.y, GRID_SNAP_SIZE);
  return {
    rect: { ...rect, left: left.value, top: top.value },
    guides: [left.kind === "guide" ? left.value : null, top.kind === "guide" ? top.value : null].filter((value) => value !== null),
  };
}
```

```javascript
const snapped = snapRectToGuides(nextRect, activeInteraction.widgetId);
nextRect = snapped.rect;
activeSnapGuides = snapped.guides;
renderSnapGuides(activeSnapGuides);
```

```html
<div id="snap-guides" aria-hidden="true"></div>
```

```css
#snap-guides {
  position: absolute;
  inset: 16px;
  pointer-events: none;
}

.snap-guide {
  position: absolute;
  background: rgba(99, 214, 255, 0.72);
}
```

- [ ] **Step 4: Run the focused editor tests**

Run: `uv run pytest tests/test_editor.py -k "drag_snapping_helpers or build_editor_state_exposes_widgets_for_preview" -q`

Expected: PASS. Then run the browser smoke check:

```bash
uv run race-overlay edit-hud --config-path overlay.yaml
agent-browser open http://127.0.0.1:<port>
agent-browser snapshot -i
```

Expected: the canvas shows snap guides when a widget is dragged near grid/guide thresholds.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_assets/app.js src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: add drag snapping to editor"
```

### Task 5: Move widget selection into the inspector and remove the left rail

**Files:**
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editor_shell_uses_two_column_canvas_first_layout() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "Selection rail" not in html
    assert "Widgets" in html
    assert "grid-template-columns: minmax(0, 1fr) 360px;" in css
    assert "function renderWidgetSelection()" in app_js
    assert "layer-item__actions" not in app_js
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_editor.py -k "two_column_canvas_first_layout" -q`

Expected: FAIL because the editor still renders the old left-side selection rail and grid columns.

- [ ] **Step 3: Write the minimal implementation**

```html
<div id="app-shell">
  <main id="canvas-panel">
    <header id="toolbar">
      <div>
        <p class="eyebrow">Live preview</p>
        <h2>Canvas</h2>
      </div>
      <div class="toolbar-actions">
        <button id="help-button" type="button" aria-controls="help-modal" aria-expanded="false">?</button>
        <button id="save-button" type="button">Save YAML</button>
      </div>
    </header>
    <section id="canvas-stage">
      <img id="preview" alt="HUD preview" />
      <div id="widget-overlays" aria-hidden="true"></div>
      <div id="snap-guides" aria-hidden="true"></div>
    </section>
  </main>

  <aside id="inspector-panel">
    <div class="panel-header">
      <p class="eyebrow">Inspector</p>
      <h2>Widget details</h2>
    </div>
    <section class="panel-section">
      <div class="section-heading">
        <h2>Document</h2>
        <span class="section-meta">Preset and activity</span>
      </div>
      <label class="field">
        <span>Preset</span>
        <input id="preset" type="text" readonly />
      </label>
    </section>
    <section class="panel-section">
      <div class="section-heading">
        <h2>Widgets</h2>
        <span class="section-meta">Selection only</span>
      </div>
      <div id="widget-list"></div>
    </section>
    <section class="panel-section">
      <div class="section-heading">
        <h2>Theme defaults</h2>
        <span class="section-meta">Schema-backed</span>
      </div>
      <div id="theme-controls"></div>
    </section>
    <div id="inspector-content"></div>
  </aside>
</div>
```

```javascript
function renderWidgetSelection() {
  elements.widgetList.innerHTML = "";
  getWidgetsInLayerOrder().reverse().forEach((widget) => {
    const item = document.createElement("article");
    item.className = `layer-item${widget.id === selectedWidgetId ? " is-selected" : ""}${widget.visible ? "" : " is-hidden"}`;

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "layer-select";
    selectButton.addEventListener("click", () => {
      selectedWidgetId = widget.id;
      renderWidgetSelection();
      renderInspector();
      renderCanvasOverlays();
    });

    const title = document.createElement("h3");
    title.className = "layer-item__title";
    title.textContent = widget.style.label || widget.id;
    selectButton.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "layer-item__meta";
    meta.textContent = `${widget.type} · z ${widget.z_index}`;
    selectButton.appendChild(meta);

    item.appendChild(selectButton);
    elements.widgetList.appendChild(item);
  });
}
```

```css
#app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  padding: 16px;
}
```

- [ ] **Step 4: Run the focused editor tests and browser smoke check**

Run: `uv run pytest tests/test_editor.py -k "two_column_canvas_first_layout or build_editor_state_hides_removed_theme_colors" -q`

Expected: PASS.

Then run:

```bash
uv run race-overlay edit-hud --config-path overlay.yaml
agent-browser open http://127.0.0.1:<port>
agent-browser screenshot
```

Expected: no left rail, widget selection lives in the inspector, and the center canvas feels wider and less visually cramped.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/app.js src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: redesign editor into two-column canvas-first layout"
```
