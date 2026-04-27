# Route-map Editor/Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add route-map progress coloring, a route scale slider with a 90% default, and a track-style editor preview example that makes scale tuning easier.

**Architecture:** Keep the change scoped to the existing route-map path: `hud.py` owns rendering and validation, `hud_presets.py` owns defaults, `editor_preview.py` owns schema + preview fixture data, and `app.js` owns inspector control rendering. Implement in TDD order so the renderer behavior is locked first, then wire the editor schema/preview, then expose the new slider UI and finish with a full regression run.

**Tech Stack:** Python, Pillow, plain browser JavaScript, pytest, uv

---

### Task 1: Lock route-map progress coloring in renderer tests

**Files:**
- Modify: `tests/test_hud.py:1853-1933`
- Modify: `tests/test_hud.py:907-956`
- Modify later: `src/race_overlay/hud.py:862-971`
- Modify later: `src/race_overlay/hud.py:1273-1318`

- [ ] **Step 1: Write the failing tests**

Add these tests next to the existing route-map color coverage in `tests/test_hud.py`:

```python
def test_render_hud_frame_route_map_splits_completed_and_remaining_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=35.5,
            longitude=139.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": "", "shape": "rounded-rect"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert (34, 255, 138, 255) in line_fills
    assert (13, 144, 195, 255) in line_fills


def test_render_hud_frame_route_map_uses_remaining_color_when_gps_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    render_hud_frame(
        width=120,
        height=120,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=None,
            longitude=None,
            altitude_m=None,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=120,
                    height=120,
                    style={"label": "", "shape": "circle"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert (13, 144, 195, 255) in line_fills
    assert (34, 255, 138, 255) not in line_fills
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_hud.py -k "splits_completed_and_remaining_segments or uses_remaining_color_when_gps_is_missing"
```

Expected: FAIL because `_draw_route_map()` still draws the whole route once with a single fill color.

- [ ] **Step 3: Write the minimal renderer implementation**

Update `src/race_overlay/hud.py` inside `_draw_route_map()` and add a helper near `_projected_route_vector()`:

```python
ROUTE_MAP_REMAINING_RGBA = (13, 144, 195, 255)


def _split_route_points(
    route_points: list[tuple[float, float]],
    route_projection: RouteProjection,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    split_point = route_projection.point
    start_index = route_projection.segment_index
    completed = [*route_points[: start_index + 1], split_point]
    remaining = [split_point, *route_points[start_index + 1 :]]
    return completed, remaining
```

```python
completed_rgba = _style_rgba(widget, "completed_rgba", ROUTE_MAP_ROUTE_RGBA)
remaining_rgba = _style_rgba(widget, "remaining_rgba", ROUTE_MAP_REMAINING_RGBA)

if route_projection is None:
    widget_draw.line(projected, fill=remaining_rgba, width=_scale_draw(scale, 4))
else:
    completed_points, remaining_points = _split_route_points(route_points, route_projection)
    completed_projected = [project(point) for point in completed_points]
    remaining_projected = [project(point) for point in remaining_points]
    if len(completed_projected) >= 2:
        widget_draw.line(completed_projected, fill=completed_rgba, width=_scale_draw(scale, 4))
    if len(remaining_projected) >= 2:
        widget_draw.line(remaining_projected, fill=remaining_rgba, width=_scale_draw(scale, 4))
```

Do not change north marker, bearing label, or arrow drawing in this task.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_hud.py -k "splits_completed_and_remaining_segments or uses_remaining_color_when_gps_is_missing"
```

Expected: PASS with both new tests green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_hud.py src/race_overlay/hud.py
git commit -m "feat: split route-map progress colors" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Add route scale default, validation, and inset projection behavior

**Files:**
- Modify: `tests/test_hud.py:1853-1933`
- Modify: `tests/test_hud_presets.py:21-48`
- Modify: `tests/test_hud_presets.py:111-123`
- Modify: `src/race_overlay/hud.py:326-344`
- Modify: `src/race_overlay/hud.py:862-940`
- Modify: `src/race_overlay/hud_presets.py:289-309`

- [ ] **Step 1: Write the failing tests**

Add one renderer test and one preset test:

```python
def test_render_hud_frame_route_map_zoom_percent_insets_route_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_lines: list[list[tuple[float, float]]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill in {(34, 255, 138, 255), (13, 144, 195, 255)}:
            recorded_lines.append([(float(x), float(y)) for x, y in xy])
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    def route_span(zoom_percent: int) -> tuple[float, float]:
        recorded_lines.clear()
        render_hud_frame(
            width=220,
            height=220,
            hud_value=HudSample(
                timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
                latitude=35.5,
                longitude=139.5,
                altitude_m=25.0,
                distance_m=24600.0,
                speed_mps=3.58,
                pace_seconds_per_km=278.0,
                heart_rate_bpm=162,
                cadence_spm=178,
            ),
            route_points=[(35.0, 139.0), (35.4, 139.7), (36.0, 140.0)],
            hud_config=HudConfig(
                preset="route-only",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=0,
                        y=0,
                        width=220,
                        height=220,
                        style={"label": "", "shape": "circle", "zoom_percent": zoom_percent},
                    )
                ],
            ),
            elapsed_seconds=6852,
        )
        points = [point for line in recorded_lines for point in line]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        return (max(xs) - min(xs), max(ys) - min(ys))

    width_100, height_100 = route_span(100)
    width_90, height_90 = route_span(90)

    assert width_90 < width_100
    assert height_90 < height_100
```

```python
def test_broadcast_runner_preset_sets_route_map_zoom_percent_default() -> None:
    route_map = next(widget for widget in broadcast_runner_preset().widgets if widget.id == "route-map")
    assert route_map.style["zoom_percent"] == 90
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_hud.py -k "zoom_percent_insets_route_projection"
uv run pytest -q tests/test_hud_presets.py -k "zoom_percent_default"
```

Expected: FAIL because the preset has no `zoom_percent` and the projection math still fills the current bounds.

- [ ] **Step 3: Implement route scale default and math**

In `src/race_overlay/hud.py`, add a dedicated helper and apply it after projection:

```python
def _route_map_zoom_percent(widget: HudWidgetConfig) -> int:
    value = widget.style.get("zoom_percent", 90)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"widget '{widget.id}' style.zoom_percent must be an integer")
    if value < 1:
        raise ValueError(f"widget '{widget.id}' style.zoom_percent must be at least 1")
    return value
```

```python
zoom_scale = _route_map_zoom_percent(widget) / 100.0
center_x = map_left + inner_width / 2
center_y = map_top + inner_height / 2

def project(point: tuple[float, float]) -> tuple[float, float]:
    lat, lon = point
    raw_x = map_left + ((lon - lon_min) / max(lon_max - lon_min, 1e-9)) * inner_width
    raw_y = map_bottom - ((lat - lat_min) / max(lat_max - lat_min, 1e-9)) * inner_height
    return (
        center_x + (raw_x - center_x) * zoom_scale,
        center_y + (raw_y - center_y) * zoom_scale,
    )
```

Also update `_validate_widget_style()` to validate the new field and set the preset default in `src/race_overlay/hud_presets.py`:

```python
_route_map_zoom_percent(widget)
```

```python
"zoom_percent": 90,
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_hud.py -k "zoom_percent_insets_route_projection"
uv run pytest -q tests/test_hud_presets.py -k "zoom_percent_default"
```

Expected: PASS with the route span shrinking at `90` and the preset exposing the default value.

- [ ] **Step 5: Commit**

```bash
git add tests/test_hud.py tests/test_hud_presets.py src/race_overlay/hud.py src/race_overlay/hud_presets.py
git commit -m "feat: add route-map zoom defaults" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Wire schema, preview fixture data, and save round-trip for route scale

**Files:**
- Modify: `tests/test_editor.py:236-310`
- Modify: `tests/test_editor.py:1439-1457`
- Modify: `src/race_overlay/editor_preview.py:88-98`
- Modify: `src/race_overlay/editor_preview.py:105-129`
- Modify: `src/race_overlay/editor_preview.py:263-295`

- [ ] **Step 1: Write the failing tests**

Update the existing editor tests and add a preview-shape assertion:

```python
def test_build_editor_state_hides_removed_theme_colors_and_exposes_route_map_fields() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    route_map_style = state["schema"]["widgets"]["route-map"]["style"]
    assert route_map_style["zoom_percent"] == {
        "kind": "range",
        "label": "Route scale",
        "min": 70,
        "max": 140,
        "step": 1,
        "suffix": "%",
    }
```

```python
def test_build_editor_state_uses_track_style_route_map_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    route_points = state["preview"]["route_points"]
    assert len(route_points) >= 8
    assert route_points[0] != route_points[1]
    assert len({tuple(point) for point in route_points}) >= 8
```

```python
route_map = next(widget for widget in payload["widgets"] if widget["id"] == "route-map")
route_map["style"].update(show_north_marker=True, show_bearing_label=False, zoom_percent=118)
time_card = next(widget for widget in payload["widgets"] if widget["id"] == "time-card")
time_card["style"].update(variant="timestamp_chip", format="%H:%M")
save_editor_payload(config_path, payload)
reloaded = load_config(config_path)
route_map_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "route-map")
assert route_map_reloaded.style["zoom_percent"] == 118
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_editor.py -k "route_map_fields or track_style_route_map_preview or round_trips_navigation_timestamp_and_typography_fields"
```

Expected: FAIL because `zoom_percent` is absent from the schema/save path and preview still uses a two-point straight line.

- [ ] **Step 3: Implement schema metadata and preview fixture changes**

Update `src/race_overlay/editor_preview.py`:

```python
"zoom_percent": {
    "kind": "range",
    "label": "Route scale",
    "min": 70,
    "max": 140,
    "step": 1,
    "suffix": "%",
},
```

```python
def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.08358,
        longitude=140.20992,
        altitude_m=25.0,
        distance_m=5210.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=133,
        cadence_spm=178,
    )
```

```python
"route_points": [
    [36.08320, 140.20990],
    [36.08320, 140.21025],
    [36.08326, 140.21042],
    [36.08340, 140.21052],
    [36.08356, 140.21052],
    [36.08370, 140.21042],
    [36.08376, 140.21025],
    [36.08376, 140.20990],
    [36.08370, 140.20973],
    [36.08356, 140.20963],
    [36.08340, 140.20963],
    [36.08326, 140.20973],
    [36.08320, 140.20990],
],
```

Keep the preview payload shape the same; only change the fixture content and route-map style schema.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_editor.py -k "route_map_fields or track_style_route_map_preview or round_trips_navigation_timestamp_and_typography_fields"
```

Expected: PASS with schema metadata, preview fixture data, and save round-trip all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_editor.py src/race_overlay/editor_preview.py
git commit -m "feat: add route-map preview schema metadata" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Render the route scale slider in the inspector and finish verification

**Files:**
- Modify: `tests/test_editor.py:1460-1485`
- Modify: `src/race_overlay/editor_assets/app.js:472-589`
- Verify: `tests/test_hud.py`
- Verify: `tests/test_hud_presets.py`
- Verify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing asset test**

Extend the existing asset-level editor test:

```python
def test_editor_asset_uses_slider_controls_for_range_fields() -> None:
    from importlib.resources import files

    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'function buildRangeInput(' in app_js
    assert 'input.type = "range"' in app_js
    assert 'metadata?.kind === "range"' in app_js
    assert 'options.suffix ?? ""' in app_js
```

- [ ] **Step 2: Run the targeted asset test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_editor.py -k "slider_controls_for_range_fields"
```

Expected: FAIL because the inspector only knows about boolean / rgba / enum / integer / text controls.

- [ ] **Step 3: Implement the slider control**

Add a shared helper in `src/race_overlay/editor_assets/app.js` and branch on the new schema kind:

```javascript
function buildRangeInput(value, onChange, options = {}, onInput = null) {
  const wrapper = document.createElement("div");
  const input = document.createElement("input");
  const valueText = document.createElement("span");
  let currentValue = Number(value);

  input.type = "range";
  input.min = String(options.min ?? 0);
  input.max = String(options.max ?? 100);
  input.step = String(options.step ?? 1);
  input.value = String(currentValue);
  valueText.textContent = `${currentValue}${options.suffix ?? ""}`;

  function emit(nextValue, live) {
    currentValue = nextValue;
    valueText.textContent = `${currentValue}${options.suffix ?? ""}`;
    (live ? (onInput ?? onChange) : onChange)(currentValue);
  }

  input.addEventListener("input", () => emit(Number(input.value), true));
  input.addEventListener("change", () => emit(Number(input.value), false));
  wrapper.append(input, valueText);
  return wrapper;
}
```

```javascript
if (metadata?.kind === "range") {
  appendField(parent, fieldLabel, buildRangeInput(value, onChange, metadata, onInput), true);
  return;
}
```

Keep the rest of the inspector wiring unchanged so live preview refresh still flows through the existing `updateWidget(widget.id, patch, { live: true })` call sites.

- [ ] **Step 4: Run focused editor tests and then the full suite**

Run:

```bash
uv run pytest -q tests/test_editor.py -k "route_map_fields or track_style_route_map_preview or slider_controls_for_range_fields"
uv run pytest -q tests/test_hud.py tests/test_hud_presets.py tests/test_editor.py
uv run pytest -q
```

Expected:
- first command PASS
- second command PASS
- full suite PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_editor.py src/race_overlay/editor_assets/app.js
git commit -m "feat: add route-map scale slider" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
