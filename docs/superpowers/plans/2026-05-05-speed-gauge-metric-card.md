# Speed Gauge Metric Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dashboard-style circular speed HUD as a new `metric_card` variant that can be applied to `speed-chip` through YAML and the editor.

**Architecture:** Keep `metric_card` as the only widget type and add a `speed_gauge` rendering branch inside `hud.py`. Expose the variant through the editor schema in `editor_preview.py`, keep saved configs backward compatible, and verify the new variant with targeted HUD and editor tests before running the full suite.

**Tech Stack:** Python 3.12, Pillow, vanilla JS-backed editor schema, pytest, uv

---

## File Map

- `src/race_overlay/hud.py` — render the new `metric_card` variant and keep compact/default paths unchanged.
- `src/race_overlay/editor_preview.py` — expose `speed_gauge` in the metric-card variant schema.
- `tests/test_hud.py` — cover the new render path, text output, and placeholder/clamping behavior.
- `tests/test_editor.py` — cover editor schema exposure for the new variant.

### Task 1: Expose `speed_gauge` in the editor schema

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_editor_state_exposes_speed_gauge_metric_card_variant() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    pace_chip_style = state["schema"]["widgets"]["pace-chip"]["style"]

    assert pace_chip_style["variant"] == {
        "kind": "selection",
        "label": "Variant",
        "options": ["compact", "speed_gauge"],
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_editor.py::test_build_editor_state_exposes_speed_gauge_metric_card_variant -v`

Expected: FAIL because `metric_card` currently only exposes `["compact"]`.

- [ ] **Step 3: Write the minimal implementation**

```python
    "metric_card": {
        "label": {"kind": "text", "label": "Label"},
        "variant": {"kind": "selection", "label": "Variant", "options": ["compact", "speed_gauge"]},
        "align": {"kind": "selection", "label": "Align", "options": ["left", "right"]},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
        "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_editor.py::test_build_editor_state_exposes_speed_gauge_metric_card_variant -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_preview.py tests/test_editor.py
git commit -m "feat: expose speed gauge metric card variant" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Render the `speed_gauge` metric-card variant

**Files:**
- Modify: `src/race_overlay/hud.py`
- Test: `tests/test_hud.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = HudWidgetConfig(
        id="speed-chip",
        type="metric_card",
        bindings={"value": "speed_mps"},
        anchor="bottom-right",
        x=1100,
        y=620,
        width=160,
        height=120,
        style={"label": "Speed", "variant": "speed_gauge"},
    )
    hud_config = HudConfig(preset="custom", theme=HudThemeConfig(), widgets=[widget])

    labels = _rendered_text_labels(
        monkeypatch,
        hud_config,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=6.94,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
    )

    assert "25" in labels
    assert "KM/H" in labels
    assert "Speed" not in labels


def test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = HudWidgetConfig(
        id="speed-chip",
        type="metric_card",
        bindings={"value": "speed_mps"},
        anchor="bottom-right",
        x=1100,
        y=620,
        width=160,
        height=120,
        style={"label": "Speed", "variant": "speed_gauge"},
    )
    hud_config = HudConfig(preset="custom", theme=HudThemeConfig(), widgets=[widget])

    labels = _rendered_text_labels(
        monkeypatch,
        hud_config,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=None,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
    )

    assert "--" in labels
    assert "KM/H" in labels
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed -v`

Expected: FAIL because `speed_gauge` has no special rendering path yet and still renders the standard card layout.

- [ ] **Step 3: Write the minimal implementation**

```python
def _speed_gauge_value_text(hud_value: HudSample) -> str:
    if hud_value.speed_mps is None:
        return "--"
    return f"{round(hud_value.speed_mps * 3.6):.0f}"


def _draw_metric_card(...):
    ...
    variant = str(widget.style.get("variant", "standard"))
    if variant == "speed_gauge":
        _draw_speed_gauge_metric_card(
            draw,
            widget,
            hud_value,
            theme,
            frame_width,
            frame_height,
            scale,
        )
        return
    if variant == "compact":
        ...


def _draw_speed_gauge_metric_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    value_text = _speed_gauge_value_text(hud_value)

    # draw panel, rim, segmented arc, and pointer here
    draw.text((left + w * 0.5, top + h * 0.54), value_text, fill=tuple(theme.text_rgba), anchor="mm", font=value_font)
    draw.text((left + w * 0.62, top + h * 0.76), "KM/H", fill=tuple(theme.text_rgba), anchor="mm", font=unit_font)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed -v`

Expected: PASS

- [ ] **Step 5: Add one image-region regression test**

```python
def test_render_hud_frame_speed_gauge_metric_card_draws_visible_pixels() -> None:
    widget = HudWidgetConfig(
        id="speed-chip",
        type="metric_card",
        bindings={"value": "speed_mps"},
        anchor="bottom-right",
        x=1100,
        y=600,
        width=160,
        height=120,
        style={"label": "Speed", "variant": "speed_gauge"},
    )
    hud_config = HudConfig(preset="custom", theme=HudThemeConfig(), widgets=[widget])

    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=6.94,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert _region_has_alpha(image, _widget_bounds(widget, 1280, 720))
```

- [ ] **Step 6: Run the focused HUD tests**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_draws_visible_pixels -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/race_overlay/hud.py tests/test_hud.py
git commit -m "feat: render speed gauge metric card" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Run regression coverage for the feature

**Files:**
- Modify: none
- Test: `tests/test_editor.py`
- Test: `tests/test_hud.py`

- [ ] **Step 1: Run the focused feature tests together**

Run: `uv run pytest tests/test_editor.py::test_build_editor_state_exposes_speed_gauge_metric_card_variant tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed tests/test_hud.py::test_render_hud_frame_speed_gauge_metric_card_draws_visible_pixels -v`

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-05-speed-gauge-metric-card-design.md docs/superpowers/plans/2026-05-05-speed-gauge-metric-card.md
git commit -m "docs: add speed gauge metric card design and plan" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
