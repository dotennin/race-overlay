# HUD Navigation, Typography, and Editor Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add route-map navigation overlays, a compact timestamp HUD, richer typography hierarchy, cadence normalization, selective `broadcast-runner` migration, and drag-synchronous editor preview behavior.

**Architecture:** Normalize the confirmed cadence issue at activity-ingestion time so every downstream consumer sees corrected values. Extend the existing schema-backed HUD model rather than creating a second renderer path, then refresh `broadcast-runner` defaults and apply selective migration during config load. Keep YAML and editor parity by exposing the same new fields through `editor_preview.py` and the canvas editor.

**Tech Stack:** Python 3.12, Pillow, Typer, vanilla JS, pytest, uv

---

## File Map

- `src/race_overlay/activity/tcx_reader.py` — normalize TCX running cadence sourced from `RunCadence`.
- `tests/test_tcx_reader.py` — prove cadence normalization on TCX input.
- `src/race_overlay/hud_schema.py` — add theme/widget fields for title/value/unit typography, route-map navigation flags, and compact timestamp formatting.
- `tests/test_hud_schema.py` — validate new schema fields and boolean/format constraints.
- `src/race_overlay/hud.py` — render route-map north marker/bearing/arrow, compact timestamp widget behavior, typography hierarchy, tighter unit placement, and default elapsed suffix removal.
- `tests/test_hud.py` — cover rendered labels/formatting and new route-map/timestamp behavior.
- `src/race_overlay/hud_presets.py` — refresh `broadcast-runner` widget defaults and add migration helpers.
- `src/race_overlay/config.py` — run selective migration when loading schema-backed `broadcast-runner` configs.
- `tests/test_hud_presets.py` — assert refreshed preset defaults.
- `tests/test_config.py` — assert selective migration preserves customized values.
- `src/race_overlay/editor_preview.py` — expose new schema fields to the editor.
- `src/race_overlay/editor_assets/app.js` — make preview refresh during drag/resize and surface new inspector controls.
- `tests/test_editor.py` — assert editor schema exposure and round-trip for the new fields.

### Task 1: Normalize TCX running cadence at ingestion

**Files:**
- Modify: `src/race_overlay/activity/tcx_reader.py`
- Modify: `tests/test_tcx_reader.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from race_overlay.activity.loader import load_activity


def test_load_activity_normalizes_running_tcx_run_cadence(tmp_path: Path) -> None:
    tcx_path = tmp_path / "cadence.tcx"
    tcx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:05Z</Time>
            <Extensions><ns3:TPX><ns3:RunCadence>92</ns3:RunCadence></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>""",
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.sport == "Running"
    assert activity.samples[0].cadence_spm == 184
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tcx_reader.py::test_load_activity_normalizes_running_tcx_run_cadence -q`

Expected: FAIL because `tcx_reader.py` currently returns `RunCadence` directly, yielding `92`.

- [ ] **Step 3: Write the minimal implementation**

```python
def _normalize_run_cadence(value: int | None, sport: str) -> int | None:
    if value is None:
        return None
    if sport.lower() != "running":
        return value
    return value * 2


def read_tcx(path: Path) -> ActivityTrack:
    root = ET.parse(path).getroot()
    activity = root.find(".//tcx:Activity", NS)
    sport = activity.attrib["Sport"]
    samples: list[ActivitySample] = []
    for point in root.findall(".//tcx:Trackpoint", NS):
        samples.append(
            ActivitySample(
                timestamp=_parse_time(point.findtext("tcx:Time", namespaces=NS)),
                latitude=_find_float(point, "tcx:Position/tcx:LatitudeDegrees"),
                longitude=_find_float(point, "tcx:Position/tcx:LongitudeDegrees"),
                altitude_m=_find_float(point, "tcx:AltitudeMeters"),
                distance_m=_find_float(point, "tcx:DistanceMeters"),
                speed_mps=_find_float(point, "tcx:Extensions/ns3:TPX/ns3:Speed"),
                heart_rate_bpm=_find_int(point, "tcx:HeartRateBpm/tcx:Value"),
                cadence_spm=_normalize_run_cadence(
                    _find_int(point, "tcx:Extensions/ns3:TPX/ns3:RunCadence"),
                    sport,
                ),
            )
        )
```

- [ ] **Step 4: Run the focused reader tests**

Run: `uv run pytest tests/test_tcx_reader.py tests/test_sampling.py -q`

Expected: PASS. The new TCX test should be green, and interpolation should continue to work with normalized cadence values.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/activity/tcx_reader.py tests/test_tcx_reader.py
git commit -m "fix: normalize TCX running cadence" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Expand schema for route-map navigation, timestamp formatting, and typography roles

**Files:**
- Modify: `src/race_overlay/hud_schema.py`
- Modify: `tests/test_hud_schema.py`
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing schema tests**

```python
import pytest

from race_overlay.config import ProjectConfig
from race_overlay.editor_preview import build_editor_state
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, validate_hud_theme_config


def test_validate_hud_theme_config_accepts_typography_roles() -> None:
    theme = validate_hud_theme_config(
        HudThemeConfig(
            title_font_family="sans",
            title_font_weight="regular",
            title_font_size_px=16,
            value_font_family="serif",
            value_font_weight="bold",
            value_font_size_px=34,
            unit_font_family="sans",
            unit_font_weight="regular",
            unit_font_size_px=14,
        )
    )

    assert theme.value_font_size_px == 34


def test_build_editor_state_exposes_route_map_navigation_and_timestamp_fields() -> None:
    hud = HudConfig(
        preset="broadcast-runner",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=24,
                y=24,
                width=180,
                height=180,
                style={"show_panel": True},
            ),
            HudWidgetConfig(
                id="time-chip",
                type="context_card",
                bindings={"value": "timestamp"},
                anchor="top-left",
                x=24,
                y=24,
                width=220,
                height=48,
                style={"variant": "timestamp"},
            ),
        ],
    )
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=hud),
        width=1280,
        height=720,
    )

    route_map_style = state["schema"]["widgets"]["route-map"]["style"]
    assert route_map_style["show_north_marker"]["kind"] == "boolean"
    assert route_map_style["show_bearing_label"]["kind"] == "boolean"
    assert route_map_style["show_heading_arrow"]["kind"] == "boolean"

    time_style = state["schema"]["widgets"]["time-chip"]["style"]
    assert time_style["format"] == {"kind": "text", "label": "Timestamp format"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud_schema.py tests/test_editor.py -k "typography_roles or route_map_navigation" -q`

Expected: FAIL because the theme dataclass, widget schema, and editor schema do not expose these fields yet.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(slots=True)
class HudThemeConfig:
    panel_rgba: list[int] = field(default_factory=lambda: [12, 18, 28, 168])
    accent_rgba: list[int] = field(default_factory=lambda: [255, 196, 92, 255])
    text_rgba: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    note_text: str = "Race Day"
    title_font_family: str = "sans"
    title_font_weight: str = "regular"
    title_font_size_px: int = 16
    value_font_family: str = "sans"
    value_font_weight: str = "bold"
    value_font_size_px: int = 30
    unit_font_family: str = "sans"
    unit_font_weight: str = "regular"
    unit_font_size_px: int = 14
    show_units: bool = True
```

```python
_WIDGET_STYLE_SCHEMA_BY_TYPE = {
    "route_map": {
        "label": {"kind": "text", "label": "Label"},
        "shape": {"kind": "text", "label": "Shape"},
        "show_panel": {"kind": "boolean", "label": "Show panel"},
        "show_north_marker": {"kind": "boolean", "label": "Show north marker"},
        "show_bearing_label": {"kind": "boolean", "label": "Show bearing label"},
        "show_heading_arrow": {"kind": "boolean", "label": "Show heading arrow"},
    },
    "context_card": {
        "label": {"kind": "text", "label": "Label"},
        "variant": {"kind": "text", "label": "Variant"},
        "format": {"kind": "text", "label": "Timestamp format"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
}
```

- [ ] **Step 4: Run the focused schema/editor tests**

Run: `uv run pytest tests/test_hud_schema.py tests/test_editor.py -q`

Expected: PASS. New fields should validate and surface through the editor schema.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud_schema.py src/race_overlay/editor_preview.py tests/test_hud_schema.py tests/test_editor.py
git commit -m "feat: add HUD navigation and typography schema" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Render route-map navigation overlays, compact timestamp HUD, and refined typography

**Files:**
- Modify: `src/race_overlay/hud.py`
- Modify: `tests/test_hud.py`

- [ ] **Step 1: Write the failing HUD tests**

```python
def test_render_hud_frame_route_map_shows_north_marker_and_bearing(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(monkeypatch, broadcast_runner_preset())

    assert "N" in labels
    assert any(label.endswith(("N", "NE", "E", "SE", "S", "SW", "W", "NW")) and "°" in label for label in labels)


def test_render_hud_frame_time_chip_uses_full_timestamp_format(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(monkeypatch, broadcast_runner_preset())

    assert any(label == "2026/04/19 09:48:10" for label in labels)


def test_metric_suffix_hides_elapsed_unit_by_default() -> None:
    preset = broadcast_runner_preset()
    elapsed_widget = next(widget for widget in preset.widgets if widget.id == "elapsed-chip")

    assert _metric_suffix(elapsed_widget, preset.theme) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py -k "north_marker or full_timestamp or hides_elapsed_unit" -q`

Expected: FAIL because route-map does not draw navigation overlays, the preset has no compact timestamp widget, and elapsed still returns `hh:mm:ss`.

- [ ] **Step 3: Write the minimal implementation**

```python
def _bearing_degrees(start: tuple[float, float], end: tuple[float, float]) -> float:
    delta_lat = end[0] - start[0]
    delta_lon = end[1] - start[1]
    radians = math.atan2(delta_lon, delta_lat)
    return (math.degrees(radians) + 360.0) % 360.0


def _bearing_cardinal(degrees_value: float) -> str:
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[int((degrees_value + 22.5) // 45) % len(directions)]


def _format_bearing_label(degrees_value: float) -> str:
    return f"{degrees_value:.0f}°{_bearing_cardinal(degrees_value)}"
```

```python
if binding == "elapsed_seconds":
    return ""
```

```python
if widget.style.get("variant") == "timestamp":
    text = context_timestamp.strftime(str(widget.style.get("format", "%Y/%m/%d %H:%M:%S")))
    draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 12)), text, fill=tuple(theme.text_rgba), font=value_font)
    return
```

- [ ] **Step 4: Run the focused HUD tests**

Run: `uv run pytest tests/test_hud.py -q`

Expected: PASS. Route-map labels should render, timestamp text should appear, and elapsed should drop the redundant suffix.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud.py tests/test_hud.py
git commit -m "feat: render route-map navigation and time HUD" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Refresh `broadcast-runner` defaults and add selective migration

**Files:**
- Modify: `src/race_overlay/hud_presets.py`
- Modify: `src/race_overlay/config.py`
- Modify: `tests/test_hud_presets.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing preset/migration tests**

```python
def test_broadcast_runner_preset_includes_time_chip_and_route_map_navigation_defaults() -> None:
    config = broadcast_runner_preset()
    ids = [widget.id for widget in config.widgets]

    assert "time-chip" in ids
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")
    assert route_map.style["show_north_marker"] is True
    assert route_map.style["show_bearing_label"] is True
    assert route_map.style["show_heading_arrow"] is True


def test_load_config_migrates_near_default_broadcast_runner_widgets(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    hud_payload = serialize_hud_config(broadcast_runner_preset())
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": hud_payload,
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    assert any(widget.id == "time-chip" for widget in config.hud.widgets)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud_presets.py tests/test_config.py -k "time_chip or migrates_near_default" -q`

Expected: FAIL because the preset has no time widget and config load does not perform selective migration.

- [ ] **Step 3: Write the minimal implementation**

```python
def _legacy_broadcast_runner_geometry() -> dict[str, tuple[int, int, int, int]]:
    legacy = broadcast_runner_preset()
    return {
        widget.id: (widget.x, widget.y, widget.width, widget.height)
        for widget in legacy.widgets
    }


def migrate_broadcast_runner_config(config: HudConfig) -> HudConfig:
    if config.preset != "broadcast-runner":
        return config
    migrated = deepcopy(config)
    defaults = broadcast_runner_preset()
    legacy_geometry_by_id = _legacy_broadcast_runner_geometry()
    existing_by_id = {widget.id: widget for widget in migrated.widgets}
    default_by_id = {widget.id: widget for widget in defaults.widgets}
    for widget_id, default_widget in default_by_id.items():
        existing = existing_by_id.get(widget_id)
        if existing is None:
            migrated.widgets.append(deepcopy(default_widget))
            continue
        if (existing.x, existing.y, existing.width, existing.height) == legacy_geometry_by_id.get(widget_id):
            existing.x, existing.y = default_widget.x, default_widget.y
            existing.width, existing.height = default_widget.width, default_widget.height
        for key, value in default_widget.style.items():
            existing.style.setdefault(key, value)
    return migrated
```

```python
def _load_hud_config(payload: dict[str, object], *, require_complete: bool = False) -> HudConfig:
    config = deserialize_hud_config(payload, require_complete=require_complete)
    return migrate_broadcast_runner_config(config)
```

- [ ] **Step 4: Run the preset/config tests**

Run: `uv run pytest tests/test_hud_presets.py tests/test_config.py -q`

Expected: PASS. The new preset defaults should exist, and schema-backed `broadcast-runner` loads should migrate only where safe.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud_presets.py src/race_overlay/config.py tests/test_hud_presets.py tests/test_config.py
git commit -m "feat: refresh broadcast-runner defaults" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Expose new controls in the editor and make drag preview follow interaction

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing editor tests**

```python
def test_build_editor_state_exposes_time_chip_and_navigation_schema() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert "time-chip" in state["schema"]["widgets"]
    assert state["schema"]["widgets"]["route-map"]["style"]["show_north_marker"]["kind"] == "boolean"
    assert state["schema"]["widgets"]["time-chip"]["style"]["format"]["kind"] == "text"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_editor.py -k "time_chip_and_navigation_schema" -q`

Expected: FAIL because the preset/editor schema do not yet expose the new widget and fields.

- [ ] **Step 3: Write the minimal implementation**

```javascript
let previewRefreshTimer = null;
let lastPreviewRefreshAt = 0;
const PREVIEW_DRAG_THROTTLE_MS = 90;

function schedulePreviewRefresh({ immediate = false } = {}) {
  if (!draftState) return;
  const now = Date.now();
  if (immediate || now - lastPreviewRefreshAt >= PREVIEW_DRAG_THROTTLE_MS) {
    lastPreviewRefreshAt = now;
    void refreshPreview().catch((error) => setStatusMessage(readErrorMessage(error, "Failed to render preview")));
    return;
  }
  clearTimeout(previewRefreshTimer);
  previewRefreshTimer = setTimeout(() => {
    lastPreviewRefreshAt = Date.now();
    void refreshPreview().catch((error) => setStatusMessage(readErrorMessage(error, "Failed to render preview")));
  }, PREVIEW_DRAG_THROTTLE_MS);
}
```

```javascript
function handlePointerMove(event) {
  // existing geometry update...
  schedulePreviewRefresh();
}

function endInteraction() {
  if (!activeInteraction) return;
  activeInteraction = null;
  schedulePreviewRefresh({ immediate: true });
  renderLayers();
  renderInspector();
  renderCanvasOverlays();
}
```

- [ ] **Step 4: Run the focused editor tests**

Run: `uv run pytest tests/test_editor.py -q`

Expected: PASS. New schema-backed controls should be visible and existing editor round-trip tests should stay green.

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_preview.py src/race_overlay/editor_assets/app.js tests/test_editor.py
git commit -m "feat: sync editor preview with HUD refresh" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 6: Full regression and release gate

**Files:**
- Verify: `tests/test_tcx_reader.py`
- Verify: `tests/test_hud_schema.py`
- Verify: `tests/test_hud.py`
- Verify: `tests/test_hud_presets.py`
- Verify: `tests/test_config.py`
- Verify: `tests/test_editor.py`

- [ ] **Step 1: Run focused HUD/editor regressions**

Run: `uv run pytest tests/test_tcx_reader.py tests/test_hud_schema.py tests/test_hud.py tests/test_hud_presets.py tests/test_config.py tests/test_editor.py -q`

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS with the full repository test suite green.

- [ ] **Step 3: Review the final diff**

Run:

```bash
git --no-pager diff --stat HEAD~5..HEAD
git --no-pager status --short
```

Expected: only the planned HUD/activity/editor files are modified or committed.

- [ ] **Step 4: Commit any final fixups**

```bash
git add tests/test_tcx_reader.py tests/test_hud_schema.py tests/test_hud.py tests/test_hud_presets.py tests/test_config.py tests/test_editor.py
git commit -m "test: cover HUD navigation refresh" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
