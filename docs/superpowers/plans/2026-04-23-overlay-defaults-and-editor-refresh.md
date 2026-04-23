# Overlay Defaults and Editor Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current `overlay.yaml` the new built-in `broadcast-runner` baseline, simplify HUD theme controls, add route-map appearance controls and split-progress coloring, fix progress-bar alignment, and redesign the editor into a quieter canvas-first workflow.

**Architecture:** Keep one schema-backed HUD pipeline from YAML through preview and final rendering. First remove ambiguous theme color knobs while preserving backward-compatible config loading, then refresh the preset and renderer together so the new defaults, route-map behavior, and editor schema stay in sync. Finish by restructuring the editor UI so Layers only selects widgets, all meaningful controls live in the inspector, and retained RGBA fields use color-picker inputs with alpha.

**Tech Stack:** Python 3.12, Pillow, Typer, PyYAML, vanilla JS, pytest, uv

---

## File Map

- `src/race_overlay/hud_schema.py` — define the supported HUD theme/widget schema; remove ambiguous theme colors and validate route-map shapes.
- `src/race_overlay/config.py` — translate legacy configs so old `panel_rgba` / `accent_rgba` keys still load after schema cleanup.
- `src/race_overlay/hud_presets.py` — encode the refreshed `broadcast-runner` defaults that mirror the current checked-in `overlay.yaml`.
- `src/race_overlay/hud.py` — render route-map background + completed/remaining path colors, support the enum-backed map shapes, and align progress-bar values.
- `src/race_overlay/editor_preview.py` — expose the cleaned theme fields and new route-map style fields to the editor schema.
- `src/race_overlay/editor_assets/index.html` — simplify the editor shell into a canvas-first layout.
- `src/race_overlay/editor_assets/styles.css` — restyle the layout, layers rail, inspector sections, and quieter overlay chrome.
- `src/race_overlay/editor_assets/app.js` — remove duplicated layer actions, hide drag titles, render color-picker controls, and group route-map controls semantically.
- `overlay.yaml` — keep the checked-in config aligned with the new default schema/output.
- `tests/test_hud_schema.py` — lock down schema cleanup and route-map shape validation.
- `tests/test_config.py` — prove legacy configs with removed theme keys still load and serialize cleanly.
- `tests/test_hud_presets.py` — prove `broadcast_runner_preset()` matches the new baseline.
- `tests/test_hud.py` — cover route-map segmentation, shape handling, and progress-bar alignment helpers.
- `tests/test_editor.py` — prove editor schema exposure, round-trip persistence, and asset-level UI cleanup.
- `tests/test_cli.py` — prove `init` emits the refreshed default config.

### Task 1: Remove ambiguous theme colors while keeping old configs loadable

**Files:**
- Modify: `src/race_overlay/hud_schema.py`
- Modify: `src/race_overlay/config.py`
- Modify: `tests/test_hud_schema.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
import yaml

from race_overlay.config import load_config
from race_overlay.hud_schema import deserialize_hud_config, serialize_hud_config


def test_deserialize_hud_config_rejects_removed_theme_color_keys() -> None:
    with pytest.raises(ValueError, match="unexpected keys"):
        deserialize_hud_config(
            {
                "preset": "broadcast-runner",
                "theme": {
                    "text_rgba": [247, 251, 255, 255],
                    "panel_rgba": [12, 18, 28, 148],
                },
                "widgets": [],
            },
            require_complete=True,
        )


def test_load_config_strips_legacy_panel_and_accent_theme_keys(tmp_path) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": {
                    "preset": "broadcast-runner",
                    "theme": {
                        "panel_rgba": [12, 18, 28, 148],
                        "accent_rgba": [26, 230, 198, 255],
                        "text_rgba": [247, 251, 255, 255],
                        "note_text": "Race Day",
                        "font_family": "broadcast_ui",
                        "font_weight": "regular",
                        "font_size_px": 18,
                        "title_font_family": "broadcast_ui",
                        "title_font_weight": "regular",
                        "title_font_size_px": 16,
                        "value_font_family": "broadcast_value",
                        "value_font_weight": "bold",
                        "value_font_size_px": 33,
                        "unit_font_family": "broadcast_value",
                        "unit_font_weight": "regular",
                        "unit_font_size_px": 13,
                        "show_units": True,
                    },
                    "widgets": [],
                },
                "overrides": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)
    theme_payload = serialize_hud_config(config.hud)["theme"]

    assert "panel_rgba" not in theme_payload
    assert "accent_rgba" not in theme_payload
    assert theme_payload["text_rgba"] == [247, 251, 255, 255]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud_schema.py tests/test_config.py -k "removed_theme_color_keys or strips_legacy_panel" -q`

Expected: FAIL because `HudThemeConfig` still declares `panel_rgba` and `accent_rgba`, so deserialization accepts them and serialization keeps them.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(slots=True)
class HudThemeConfig:
    text_rgba: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    note_text: str = "Race Day"
    font_family: str = "broadcast_ui"
    font_weight: str = "regular"
    font_size_px: int = 18
    title_font_family: str | None = "broadcast_ui"
    title_font_weight: str | None = None
    title_font_size_px: int | None = None
    value_font_family: str | None = "broadcast_value"
    value_font_weight: str | None = None
    value_font_size_px: int | None = None
    unit_font_family: str | None = "broadcast_ui"
    unit_font_weight: str | None = None
    unit_font_size_px: int | None = None
    show_units: bool = True


def _strip_legacy_theme_keys(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    theme_payload = normalized.get("theme")
    if isinstance(theme_payload, dict):
        normalized["theme"] = {
            key: value
            for key, value in theme_payload.items()
            if key not in {"panel_rgba", "accent_rgba"}
        }
    return normalized


def _load_hud_config(payload: dict[str, object], *, require_complete: bool = False) -> HudConfig:
    normalized_payload = _strip_legacy_theme_keys(payload)
    return migrate_broadcast_runner_config(
        deserialize_hud_config(normalized_payload, require_complete=require_complete)
    )
```

- [ ] **Step 4: Run the focused schema/config tests**

Run: `uv run pytest tests/test_hud_schema.py tests/test_config.py -k "removed_theme_color_keys or strips_legacy_panel" -q`

Expected: PASS. Old configs still load through `config.py`, while direct schema validation rejects the removed keys.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud_schema.py src/race_overlay/config.py tests/test_hud_schema.py tests/test_config.py
git commit -m "refactor: remove ambiguous HUD theme colors" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Add route-map appearance controls and fix progress-bar text alignment

**Files:**
- Modify: `src/race_overlay/hud.py`
- Modify: `tests/test_hud.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from race_overlay.hud import _progress_bar_text_layout, _split_route_segments, validate_hud_config
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig


def test_validate_hud_config_rejects_unknown_route_map_shape() -> None:
    with pytest.raises(ValueError, match="supported shapes: circle, rounded-rect, square"):
        validate_hud_config(
            HudConfig(
                preset="broadcast-runner",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=0,
                        y=0,
                        width=196,
                        height=196,
                        style={"shape": "triangle"},
                    )
                ],
            )
        )


def test_split_route_segments_uses_current_projection_for_completed_and_remaining_paths() -> None:
    projected = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    projection = RouteProjection(
        point=(12.0, 0.0),
        tangent=(1.0, 0.0),
        segment_start=(10.0, 0.0),
        segment_end=(20.0, 0.0),
    )

    completed, remaining = _split_route_segments(projected, projection)

    assert completed == [(0.0, 0.0), (10.0, 0.0), (12.0, 0.0)]
    assert remaining == [(12.0, 0.0), (20.0, 0.0)]


def test_progress_bar_text_layout_aligns_current_and_total_values() -> None:
    layout = _progress_bar_text_layout(left=0, top=0, width=560, height=56, label="Distance")

    assert layout.current_anchor[1] == layout.total_anchor[1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py -k "unknown_route_map_shape or split_route_segments or progress_bar_text_layout" -q`

Expected: FAIL because these helpers and enum-backed validation do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
ROUTE_MAP_SHAPES = ("circle", "rounded-rect", "square")


@dataclass(slots=True, frozen=True)
class ProgressBarTextLayout:
    current_anchor: tuple[int, int]
    total_anchor: tuple[int, int]


def _route_map_shape(widget: HudWidgetConfig) -> str:
    shape = str(widget.style.get("shape", "circle"))
    if shape not in ROUTE_MAP_SHAPES:
        supported = ", ".join(ROUTE_MAP_SHAPES)
        raise ValueError(f"widget '{widget.id}' style.shape must be one of: {supported}")
    return shape


def _split_route_segments(
    projected: list[tuple[float, float]], projection: RouteProjection
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    split_index = projected.index(projection.segment_start)
    completed = projected[: split_index + 1] + [projection.point]
    remaining = [projection.point, projection.segment_end]
    if projection.segment_end in projected[split_index + 1 :]:
        remaining.extend(projected[split_index + 2 :])
    return completed, remaining


def _progress_bar_text_layout(left: int, top: int, width: int, height: int, label: str) -> ProgressBarTextLayout:
    baseline_y = top + 14
    current_x = left + 16 + (80 if label else 0)
    total_x = left + width - 16
    return ProgressBarTextLayout(current_anchor=(current_x, baseline_y), total_anchor=(total_x, baseline_y))
```

```python
shape = _route_map_shape(widget)
background_rgba = _style_rgba(widget, "background_rgba", (6, 10, 18, 148))
completed_rgba = _style_rgba(widget, "completed_rgba", (34, 255, 138, 255))
remaining_rgba = _style_rgba(widget, "remaining_rgba", (13, 144, 195, 255))
```

- [ ] **Step 4: Run the focused HUD tests**

Run: `uv run pytest tests/test_hud.py -k "route_map_shape or split_route_segments or progress_bar_text_layout" -q`

Expected: PASS. The renderer should accept only supported shapes, split route geometry at the current projection, and place current/total distance text on a shared baseline.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud.py tests/test_hud.py
git commit -m "feat: refresh route map and progress bar rendering" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Refresh `broadcast-runner` so it matches the current overlay baseline

**Files:**
- Modify: `src/race_overlay/hud_presets.py`
- Modify: `src/race_overlay/config.py`
- Modify: `overlay.yaml`
- Modify: `tests/test_hud_presets.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
import yaml

from race_overlay.config import write_default_config
from race_overlay.hud_presets import broadcast_runner_preset


def test_broadcast_runner_preset_matches_overlay_refresh_defaults() -> None:
    config = broadcast_runner_preset()
    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert config.theme.text_rgba == [247, 251, 255, 255]
    assert ruler.x == 359
    assert ruler.y == 40
    assert ruler.style["fill_rgba"] == [34, 255, 138, 255]
    assert route_map.x == 21
    assert route_map.style["background_rgba"] == [6, 10, 18, 148]
    assert route_map.style["completed_rgba"] == [34, 255, 138, 255]
    assert route_map.style["remaining_rgba"] == [13, 144, 195, 255]


def test_init_writes_default_overlay_without_removed_theme_colors(tmp_path) -> None:
    config_path = tmp_path / "overlay.yaml"
    write_default_config(config_path, "activity_22577902433.tcx")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    route_map = next(widget for widget in payload["hud"]["widgets"] if widget["id"] == "route-map")

    assert "panel_rgba" not in payload["hud"]["theme"]
    assert "accent_rgba" not in payload["hud"]["theme"]
    assert route_map["style"]["background_rgba"] == [6, 10, 18, 148]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud_presets.py tests/test_cli.py -k "overlay_refresh_defaults or removed_theme_colors" -q`

Expected: FAIL because the preset still uses the older geometry and route-map style shape, and default config generation still serializes the old theme keys.

- [ ] **Step 3: Write the minimal implementation**

```python
def broadcast_runner_preset() -> HudConfig:
    return HudConfig(
        theme=HudThemeConfig(
            text_rgba=[247, 251, 255, 255],
            note_text="My Race config",
            font_family="broadcast_value",
            font_weight="regular",
            font_size_px=18,
            title_font_family="broadcast_value",
            title_font_weight="regular",
            title_font_size_px=16,
            value_font_family="broadcast_value",
            value_font_weight="bold",
            value_font_size_px=33,
            unit_font_family="broadcast_value",
            unit_font_weight="regular",
            unit_font_size_px=13,
            show_units=True,
        ),
        widgets=[
            HudWidgetConfig(... id="distance-ruler", x=359, y=40, width=560, height=56, ...),
            HudWidgetConfig(
                ...,
                id="route-map",
                x=21,
                y=488,
                width=196,
                height=196,
                style={
                    "label": "",
                    "shape": "circle",
                    "show_panel": True,
                    "background_rgba": [6, 10, 18, 148],
                    "completed_rgba": [34, 255, 138, 255],
                    "remaining_rgba": [13, 144, 195, 255],
                    "show_north_marker": True,
                    "show_bearing_label": True,
                    "show_heading_arrow": True,
                },
            ),
        ],
    )
```

```python
config = load_config(Path("overlay.yaml"))
save_config(Path("overlay.yaml"), config)
```

- [ ] **Step 4: Run the focused preset/default tests**

Run: `uv run pytest tests/test_hud_presets.py tests/test_config.py tests/test_cli.py -k "overlay_refresh_defaults or removed_theme_colors or migrates_legacy" -q`

Expected: PASS. The preset becomes the source of truth for the new baseline, and `init` outputs the cleaned schema.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud_presets.py src/race_overlay/config.py overlay.yaml tests/test_hud_presets.py tests/test_config.py tests/test_cli.py
git commit -m "feat: refresh broadcast runner defaults" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Expose only meaningful editor controls and switch RGBA editing to color pickers

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
from race_overlay.config import ProjectConfig
from race_overlay.editor_preview import build_editor_state
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig


def test_build_editor_state_hides_removed_theme_colors_and_exposes_route_map_fields() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=HudConfig(theme=HudThemeConfig())),
        width=1280,
        height=720,
    )

    assert "panel_rgba" not in state["schema"]["theme"]
    assert "accent_rgba" not in state["schema"]["theme"]

    route_map_style = state["schema"]["widgets"]["route-map"]["style"]
    assert route_map_style["shape"] == {
        "kind": "enum",
        "label": "Shape",
        "options": ["circle", "rounded-rect", "square"],
    }
    assert route_map_style["background_rgba"] == {"kind": "rgba", "label": "Background RGBA"}
    assert route_map_style["completed_rgba"] == {"kind": "rgba", "label": "Completed RGBA"}
    assert route_map_style["remaining_rgba"] == {"kind": "rgba", "label": "Remaining RGBA"}


def test_editor_asset_uses_color_picker_controls_for_rgba_fields() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'input.type = "color"' in app_js
    assert 'className = "color-alpha-input"' in app_js
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_editor.py -k "hides_removed_theme_colors or color_picker_controls" -q`

Expected: FAIL because the editor schema still exposes `panel_rgba` / `accent_rgba`, `shape` is still text-backed, and the JS only renders four numeric RGBA channels.

- [ ] **Step 3: Write the minimal implementation**

```python
_THEME_FIELD_SCHEMA = {
    "text_rgba": {"kind": "rgba", "label": "Text RGBA"},
    "note_text": {"kind": "text", "label": "Theme note"},
    ...
}

_WIDGET_STYLE_SCHEMA_BY_TYPE = {
    "route_map": {
        "label": {"kind": "text", "label": "Label"},
        "shape": {"kind": "enum", "label": "Shape", "options": ["circle", "rounded-rect", "square"]},
        "background_rgba": {"kind": "rgba", "label": "Background RGBA"},
        "completed_rgba": {"kind": "rgba", "label": "Completed RGBA"},
        "remaining_rgba": {"kind": "rgba", "label": "Remaining RGBA"},
        "show_panel": {"kind": "boolean", "label": "Show panel"},
        "show_north_marker": {"kind": "boolean", "label": "Show north marker"},
        "show_bearing_label": {"kind": "boolean", "label": "Show bearing label"},
        "show_heading_arrow": {"kind": "boolean", "label": "Show heading arrow"},
    },
}
```

```javascript
function buildColorInput(value, onChange, onInput = null) {
  const rgba = Array.isArray(value) && value.length === 4 ? [...value] : [255, 255, 255, 255];
  const wrapper = document.createElement("div");
  wrapper.className = "color-alpha-input";

  const color = document.createElement("input");
  color.type = "color";
  color.value = rgbToHex(rgba.slice(0, 3));
  color.addEventListener("input", () => emitColorChange());

  const alpha = document.createElement("input");
  alpha.type = "number";
  alpha.min = "0";
  alpha.max = "255";
  alpha.value = String(rgba[3]);
  alpha.addEventListener("input", () => emitColorChange());

  function emitColorChange() {
    const [r, g, b] = hexToRgb(color.value);
    const next = [r, g, b, Number(alpha.value)];
    (onInput ?? onChange)(next);
  }

  wrapper.append(color, alpha);
  return wrapper;
}
```

- [ ] **Step 4: Run the focused editor-schema tests**

Run: `uv run pytest tests/test_editor.py -k "hides_removed_theme_colors or route_map_fields or color_picker_controls" -q`

Expected: PASS. The editor schema only exposes meaningful theme fields, route-map controls are constrained and semantically named, and RGBA editing switches to color-picker-first controls.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_preview.py src/race_overlay/editor_assets/app.js tests/test_editor.py
git commit -m "feat: simplify editor color controls" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Rebuild the editor into a quieter canvas-first workspace

**Files:**
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
from importlib.resources import files


def test_editor_assets_remove_duplicate_layer_actions_and_overlay_titles() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'textContent = "▲"' not in app_js
    assert 'textContent = "▼"' not in app_js
    assert 'widget-overlay__label' not in app_js


def test_editor_shell_uses_canvas_first_layout_copy() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert "Canvas-first designer" not in html
    assert "HUD workspace" not in html
    assert "grid-template-columns: 240px minmax(0, 1fr) 280px;" not in css
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_editor.py -k "duplicate_layer_actions or canvas_first_layout_copy" -q`

Expected: FAIL because the current JS still creates visibility/up/down buttons and overlay labels, while the HTML/CSS still use the older three-column proportions and copy.

- [ ] **Step 3: Write the minimal implementation**

```html
<aside id="layers-panel">
  <div class="panel-header">
    <p class="eyebrow">Layers</p>
    <h1>Selection rail</h1>
    <p class="panel-copy">Choose a widget, then edit it in the inspector.</p>
  </div>
  <div id="widget-list"></div>
</aside>
```

```css
#app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 188px minmax(0, 1fr) 340px;
  gap: 16px;
  padding: 16px;
}

.layer-item__actions,
.widget-overlay__label {
  display: none;
}
```

```javascript
function renderLayers() {
  elements.widgetList.innerHTML = "";
  getWidgetsInLayerOrder().reverse().forEach((widget) => {
    const item = document.createElement("article");
    item.className = `layer-item${widget.id === selectedWidgetId ? " is-selected" : ""}`;

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "layer-select";
    selectButton.addEventListener("click", () => {
      selectedWidgetId = widget.id;
      renderLayers();
      renderInspector();
      renderCanvasOverlays();
    });

    const title = document.createElement("h3");
    title.className = "layer-item__title";
    title.textContent = widget.style.label || widget.id;
    selectButton.appendChild(title);
    item.appendChild(selectButton);
    elements.widgetList.appendChild(item);
  });
}

function renderCanvasOverlays() {
  ...
  // Do not append a floating label; selection lives in Layers + inspector heading.
}
```

- [ ] **Step 4: Run the editor tests and perform one browser smoke check**

Run: `uv run pytest tests/test_editor.py -k "duplicate_layer_actions or canvas_first_layout_copy or build_editor_state" -q`

Expected: PASS.

Run: `uv run race-overlay edit-hud --config-path overlay.yaml`

Expected: prints `HUD editor available at http://127.0.0.1:<port>`; opening the page should show a compact layers rail, larger canvas, no layer action buttons, and no drag-title collision on the preview.

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -q`

Expected: PASS for the full repository test suite.

```bash
git add src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/styles.css src/race_overlay/editor_assets/app.js tests/test_editor.py
git commit -m "feat: redesign canvas-first HUD editor" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
