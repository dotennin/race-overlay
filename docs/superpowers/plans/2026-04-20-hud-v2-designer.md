# HUD v2 Designer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the HUD v2 redesign by adding elevation-aware telemetry, a closer-to-reference default preset, a canvas-first live-preview editor, and explicit save-to-YAML persistence without splitting preview and production rendering into separate engines.

**Architecture:** Keep `render_hud_frame()` as the single drawing path for both preview PNGs and final video frames. Extend the data path so HUD samples include altitude and the renderer knows the activity total distance, then redesign the default preset around that richer data. Upgrade the editor server to preview arbitrary in-memory draft HUD documents, and rebuild the browser assets around a Layers / Canvas / Inspector workspace that only persists on `Save YAML`.

**Tech Stack:** Python 3.12, uv, PyYAML, Pillow, standard-library `http.server`, vanilla HTML/CSS/JavaScript, pytest

---

## File Structure

- Modify: `README.md` — document live-preview editing, hidden Help popup, and explicit save semantics
- Modify: `src/race_overlay/models.py` — add `altitude_m` to `HudSample`
- Modify: `src/race_overlay/sampling.py` — interpolate altitude into HUD samples
- Modify: `src/race_overlay/pipeline.py` — pass activity total distance into the shared renderer
- Modify: `src/race_overlay/editor_preview.py` — build preview PNGs from unsaved draft HUD payloads without persisting
- Modify: `src/race_overlay/editor_server.py` — expose a draft-preview endpoint and keep `/api/config` as the only persistence endpoint
- Modify: `src/race_overlay/hud.py` — support the HUD v2 ruler/stat rendering and keep validation in the shared renderer path
- Modify: `src/race_overlay/hud_presets.py` — redesign `broadcast-runner` around the approved layout and keep legacy field mapping
- Modify: `src/race_overlay/editor_assets/index.html` — three-pane editor shell with hidden-by-default Help modal
- Modify: `src/race_overlay/editor_assets/styles.css` — canvas-first layout, overlays, handles, modal styling
- Modify: `src/race_overlay/editor_assets/app.js` — local draft state, live preview requests, drag/resize/layer ordering/help modal behavior
- Modify: `tests/test_sampling.py` — cover altitude interpolation
- Modify: `tests/test_hud.py` — cover the new preset composition and shared-renderer behavior
- Modify: `tests/test_hud_presets.py` — lock the approved default widget inventory and geometry
- Modify: `tests/test_pipeline.py` — verify the pipeline passes the new telemetry/render inputs
- Modify: `tests/test_editor.py` — verify draft preview, non-persistence before save, and the new editor shell contract

## Notes

- Keep the current schema shape (`preset`, `theme`, `widgets`) and reuse existing widget geometry fields instead of inventing a second scene format.
- Use the shared renderer for both preview and final export; do not add browser-only layout logic that can drift from video output.
- `overlay.yaml` remains the durable source of truth. The browser editor owns an unsaved draft, but the config file changes only on `Save YAML`.
- The approved HUD v2 layout includes a half-width transparent kilometer ruler, larger lower-left route map, prominent Elevation / Distance / Heart rate blocks, and compact support metrics for the legacy fields that still need to map cleanly.

### Task 1: Carry elevation and total-distance data into the shared renderer

**Files:**
- Modify: `src/race_overlay/models.py`
- Modify: `src/race_overlay/sampling.py`
- Modify: `src/race_overlay/pipeline.py`
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `tests/test_sampling.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing telemetry-path tests**

```python
# tests/test_sampling.py
def test_sample_at_interpolates_distance_heart_rate_and_altitude() -> None:
    activity = ActivityTrack(
        sport="Running",
        samples=[
            ActivitySample(datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc), 36.0, 140.0, -1.4, 0.0, 4.0, 120, 90),
            ActivitySample(datetime(2026, 4, 19, 0, 45, 15, tzinfo=timezone.utc), 36.1, 140.1, -1.0, 40.0, 5.0, 130, 92),
        ],
    )

    hud_value = sample_at(activity, datetime(2026, 4, 19, 0, 45, 10, tzinfo=timezone.utc))

    assert round(hud_value.distance_m, 1) == 20.0
    assert hud_value.heart_rate_bpm == 125
    assert round(hud_value.speed_mps, 1) == 4.5
    assert round(hud_value.altitude_m, 2) == -1.2
```

```python
# tests/test_pipeline.py
def fake_hud_sample() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2107,
        altitude_m=5.1,
        distance_m=12.0,
        speed_mps=3.5,
        pace_seconds_per_km=285.7,
        heart_rate_bpm=150,
        cadence_spm=176,
    )


def test_run_pipeline_passes_total_distance_to_renderer(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    captured: list[tuple[HudConfig, float | None]] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: captured.append((kwargs["hud_config"], kwargs["total_distance_m"]))
        or Image.new("RGBA", (1280, 720), (0, 0, 0, 0)),
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4")

    assert captured == [(broadcast_runner_preset(), 35.0)]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_sampling.py tests/test_pipeline.py -v`
Expected: FAIL because `HudSample` has no `altitude_m` field and `render_hud_frame()` is not called with `total_distance_m`

- [ ] **Step 3: Add altitude to `HudSample` and interpolate it**

```python
# src/race_overlay/models.py
@dataclass(slots=True, frozen=True)
class HudSample:
    timestamp: datetime
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    distance_m: float | None
    speed_mps: float | None
    pace_seconds_per_km: float | None
    heart_rate_bpm: int | None
    cadence_spm: int | None
```

```python
# src/race_overlay/sampling.py
return HudSample(
    timestamp=when,
    latitude=_lerp(before.latitude, after.latitude, ratio),
    longitude=_lerp(before.longitude, after.longitude, ratio),
    altitude_m=_lerp(before.altitude_m, after.altitude_m, ratio),
    distance_m=_lerp(before.distance_m, after.distance_m, ratio),
    speed_mps=speed_mps,
    pace_seconds_per_km=(1000.0 / speed_mps) if speed_mps else None,
    heart_rate_bpm=round(_lerp(before.heart_rate_bpm, after.heart_rate_bpm, ratio)),
    cadence_spm=round(_lerp(before.cadence_spm, after.cadence_spm, ratio)),
)
```

- [ ] **Step 4: Thread total distance through pipeline and preview helpers**

```python
# src/race_overlay/pipeline.py
total_distance_m = activity.samples[-1].distance_m if activity.samples else None

image = render_hud_frame(
    width=clip.width,
    height=clip.height,
    hud_value=hud_value,
    route_points=route_points,
    hud_config=config.hud,
    elapsed_seconds=int((when - activity.samples[0].timestamp).total_seconds()),
    total_distance_m=total_distance_m,
)
```

```python
# src/race_overlay/editor_preview.py
def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=5210.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=133,
        cadence_spm=178,
    )


def render_preview_png(config: ProjectConfig, width: int, height: int) -> bytes:
    image = render_hud_frame(
        width,
        height,
        _sample_hud_value(),
        [(36.0832, 140.2106), (36.0834, 140.2108)],
        config.hud,
        6852,
        total_distance_m=10000.0,
    )
```

- [ ] **Step 5: Re-run the targeted tests to verify they pass**

Run: `uv run pytest tests/test_sampling.py tests/test_pipeline.py -v`
Expected: PASS with altitude interpolation and `total_distance_m` captured by the renderer spy

- [ ] **Step 6: Commit the telemetry-path changes**

```bash
git add tests/test_sampling.py tests/test_pipeline.py src/race_overlay/models.py src/race_overlay/sampling.py src/race_overlay/pipeline.py src/race_overlay/editor_preview.py
git commit -m "feat: thread elevation and total distance into HUD rendering"
```

### Task 2: Redesign the shared renderer and default preset for HUD v2

**Files:**
- Modify: `src/race_overlay/hud.py`
- Modify: `src/race_overlay/hud_presets.py`
- Modify: `tests/test_hud.py`
- Modify: `tests/test_hud_presets.py`

- [ ] **Step 1: Write the failing preset and renderer tests**

```python
# tests/test_hud_presets.py
from race_overlay.hud_presets import broadcast_runner_preset


def test_broadcast_runner_preset_matches_hud_v2_widget_inventory() -> None:
    config = broadcast_runner_preset()
    ids = [widget.id for widget in config.widgets]

    assert ids == [
        "distance-ruler",
        "elevation-stat",
        "distance-stat",
        "heart-rate-stat",
        "pace-chip",
        "cadence-chip",
        "elapsed-chip",
        "speed-chip",
        "route-map",
    ]

    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert ruler.width == 560
    assert ruler.y == 28
    assert route_map.width == 140
    assert route_map.height == 140
    assert route_map.y == 554
```

```python
# tests/test_hud.py
def test_render_hud_frame_draws_hud_v2_regions(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(monkeypatch, broadcast_runner_preset())
    image = render_hud_frame(
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
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert "Elevation" in labels
    assert "Distance" in labels
    assert "Heart rate" in labels
    assert image.getpixel((640, 70))[3] > 0
    assert image.getpixel((90, 610))[3] > 0
    assert image.getpixel((80, 210))[3] > 0
    assert image.getpixel((1150, 170))[3] > 0
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_hud_presets.py tests/test_hud.py -v`
Expected: FAIL because the preset still exposes the old widget IDs and the renderer does not draw the new HUD v2 regions

- [ ] **Step 3: Replace the default preset geometry with the approved HUD v2 layout**

```python
# src/race_overlay/hud_presets.py
def broadcast_runner_preset() -> HudConfig:
    return HudConfig(
        theme=HudThemeConfig(panel_rgba=[12, 18, 28, 148], accent_rgba=[26, 230, 198, 255], text_rgba=[247, 251, 255, 255]),
        widgets=[
            HudWidgetConfig("distance-ruler", "progress_bar", {"value": "distance_m"}, "top-left", 360, 28, 560, 56, 40, True, {"label": "Distance", "variant": "ruler", "transparent_panel": True}),
            HudWidgetConfig("elevation-stat", "stat_block", {"value": "altitude_m"}, "top-left", 44, 146, 160, 86, 30, True, {"label": "Elevation", "unit": "M"}),
            HudWidgetConfig("distance-stat", "stat_block", {"value": "distance_m"}, "top-left", 44, 250, 210, 88, 30, True, {"label": "Distance", "unit": "KM", "decimals": 2}),
            HudWidgetConfig("heart-rate-stat", "stat_block", {"value": "heart_rate_bpm"}, "top-right", 1100, 132, 138, 82, 30, True, {"label": "Heart rate", "unit": "BPM", "align": "right"}),
            HudWidgetConfig("pace-chip", "metric_card", {"value": "pace_seconds_per_km"}, "bottom-right", 980, 560, 120, 72, 20, True, {"label": "Pace", "variant": "compact"}),
            HudWidgetConfig("cadence-chip", "metric_card", {"value": "cadence_spm"}, "bottom-right", 1110, 560, 120, 72, 20, True, {"label": "Cadence", "variant": "compact"}),
            HudWidgetConfig("elapsed-chip", "metric_card", {"value": "elapsed_seconds"}, "bottom-right", 980, 642, 120, 72, 20, True, {"label": "Elapsed", "variant": "compact"}),
            HudWidgetConfig("speed-chip", "metric_card", {"value": "speed_mps"}, "bottom-right", 1110, 642, 120, 72, 20, True, {"label": "Speed", "variant": "compact"}),
            HudWidgetConfig("route-map", "route_map", {"value": "route_points"}, "top-left", 26, 554, 140, 140, 20, True, {"label": "", "shape": "circle"}),
        ],
    )
```

```python
# src/race_overlay/hud_presets.py
def apply_legacy_field_visibility(config: HudConfig, fields: dict[str, bool]) -> HudConfig:
    updated = deepcopy(config)
    visibility_map = {
        "distance-ruler": fields.get("distance", True),
        "distance-stat": fields.get("distance", True),
        "heart-rate-stat": fields.get("heart_rate", True),
        "pace-chip": fields.get("pace", True),
        "cadence-chip": fields.get("cadence", True),
        "elapsed-chip": fields.get("elapsed", True),
        "speed-chip": fields.get("speed", True),
        "route-map": fields.get("mini_map", True),
    }
    for widget in updated.widgets:
        if widget.id in visibility_map:
            widget.visible = visibility_map[widget.id]
    return updated
```

- [ ] **Step 4: Teach `hud.py` the new stat block, ruler, and compact chip rendering**

```python
# src/race_overlay/hud.py
def render_hud_frame(
    width: int,
    height: int,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    hud_config: HudConfig | HudLayout | None = None,
    elapsed_seconds: int = 0,
    *,
    layout: HudLayout | None = None,
    total_distance_m: float | None = None,
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    legacy_layout = _resolve_legacy_layout(hud_config, layout)
    if legacy_layout is not None:
        _render_legacy_layout(draw, legacy_layout, hud_value, route_points, elapsed_seconds)
        return image

    resolved_hud_config = validate_hud_config(_resolve_hud_config(hud_config))
    widgets = sorted((widget for widget in resolved_hud_config.widgets if widget.visible), key=lambda item: item.z_index)
    for widget in widgets:
        _render_widget(draw, widget, hud_value, route_points, elapsed_seconds, resolved_hud_config.theme, width, height, total_distance_m)
    return image
```

```python
# src/race_overlay/hud.py
def _render_widget(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    elapsed_seconds: int,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    total_distance_m: float | None,
) -> None:
    if widget.type == "progress_bar":
        _draw_progress_bar(draw, widget, hud_value.distance_m, total_distance_m, theme, frame_width, frame_height)
    elif widget.type == "stat_block":
        _draw_stat_block(draw, widget, hud_value, theme, frame_width, frame_height)
    elif widget.type == "route_map":
        _draw_route_map(draw, widget, route_points, hud_value, theme, frame_width, frame_height)
    elif widget.type == "metric_card":
        _draw_metric_card(draw, widget, hud_value, elapsed_seconds, theme, frame_width, frame_height)
    else:
        raise ValueError(f"unknown widget type '{widget.type}' for widget '{widget.id}'")
```

```python
# src/race_overlay/hud.py
def _draw_stat_block(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
) -> None:
    binding = _require_supported_binding(widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    left, top = _resolve_widget_origin(widget, frame_width, frame_height)
    label = str(widget.style.get("label", "Metric"))
    unit = str(widget.style.get("unit", ""))
    align = str(widget.style.get("align", "left"))
    value_text = _stat_block_value(binding, hud_value, decimals=int(widget.style.get("decimals", 0)))
    if align == "right":
        value_right = left + widget.width
        draw.text((value_right, top), label, fill=tuple(theme.text_rgba), anchor="ra")
        draw.text((value_right, top + 28), value_text, fill=tuple(theme.text_rgba), anchor="ra")
        draw.text((value_right + 8, top + 32), unit, fill=tuple(theme.text_rgba), anchor="la")
        return

    draw.text((left, top), label, fill=tuple(theme.text_rgba))
    draw.text((left, top + 28), value_text, fill=tuple(theme.text_rgba))
    draw.text((left + widget.width - 8, top + 32), unit, fill=tuple(theme.text_rgba), anchor="ra")


def _stat_block_value(binding: str, hud_value: HudSample, decimals: int) -> str:
    if binding == "altitude_m":
        return "--" if hud_value.altitude_m is None else f"{hud_value.altitude_m:.0f}"
    if binding == "distance_m":
        if hud_value.distance_m is None:
            return "--"
        return f"{hud_value.distance_m / 1000:.{decimals}f}"
    if binding == "heart_rate_bpm":
        return "--" if hud_value.heart_rate_bpm is None else str(hud_value.heart_rate_bpm)
    raise AssertionError(f"unsupported stat_block binding '{binding}'")
```

```python
# src/race_overlay/hud.py
def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    distance_m: float | None,
    total_distance_m: float | None,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
) -> None:
    goal_m = max(total_distance_m or distance_m or 1.0, 1.0)
    left, top = _resolve_widget_origin(widget, frame_width, frame_height)
    if not bool(widget.style.get("transparent_panel", False)):
        draw.rounded_rectangle((left, top, left + widget.width, top + widget.height), radius=18, fill=tuple(theme.panel_rgba))
    track_left = left + 16
    track_right = left + widget.width - 16
    track_y = top + 18
    draw.line((track_left, track_y, track_right, track_y), fill=tuple(theme.text_rgba), width=2)
    for kilometer in range(int(goal_m // 1000) + 1):
        ratio = kilometer / max(goal_m / 1000.0, 1.0)
        x = track_left + int((track_right - track_left) * ratio)
        tick_height = 20 if kilometer % 2 == 0 else 14
        draw.line((x, track_y - tick_height // 2, x, track_y + tick_height // 2), fill=tuple(theme.text_rgba), width=2)
    progress_ratio = min(max((distance_m or 0.0) / goal_m, 0.0), 1.0)
    marker_x = track_left + int((track_right - track_left) * progress_ratio)
    draw.ellipse((marker_x - 9, track_y - 9, marker_x + 9, track_y + 9), fill=tuple(theme.accent_rgba), outline=tuple(theme.text_rgba))
```

- [ ] **Step 5: Re-run the renderer tests to verify they pass**

Run: `uv run pytest tests/test_hud_presets.py tests/test_hud.py -v`
Expected: PASS with the new widget inventory, new HUD v2 region checks, and no unknown-widget regressions

- [ ] **Step 6: Commit the HUD v2 renderer and preset changes**

```bash
git add tests/test_hud_presets.py tests/test_hud.py src/race_overlay/hud.py src/race_overlay/hud_presets.py
git commit -m "feat: redesign default HUD for canvas-first editor"
```

### Task 3: Add live draft preview without persisting YAML

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `src/race_overlay/editor_server.py`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing draft-preview tests**

```python
# tests/test_editor.py
def test_render_preview_payload_uses_unsaved_draft_without_touching_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    distance_stat = next(widget for widget in payload["widgets"] if widget["id"] == "distance-stat")
    distance_stat["x"] = 96

    png = render_preview_payload(config_path, payload, width=1280, height=720)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert config_path.read_text() == original_text
    assert next(widget for widget in load_config(config_path).hud.widgets if widget.id == "distance-stat").x == 44
```

```python
# tests/test_editor.py
def test_api_preview_rejects_invalid_draft_payload_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/preview",
                body=json.dumps({"widgets": []}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "complete HUD document" in json.loads(body.decode("utf-8"))["error"]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_editor.py -k "preview_payload or api_preview" -v`
Expected: FAIL because `render_preview_payload()` and `/api/preview` do not exist yet

- [ ] **Step 3: Add a draft-preview helper that validates but does not persist**

```python
# src/race_overlay/editor_preview.py
def render_preview_payload(config_path: Path, payload: dict[str, object], width: int, height: int) -> bytes:
    config = load_editor_config(config_path)
    _validate_complete_hud_payload(config.hud, payload)
    preview_hud = _load_hud_config(payload, require_complete=True)
    preview_config = ProjectConfig(
        activity_file=config.activity_file,
        video_globs=list(config.video_globs),
        output_dir=config.output_dir,
        cache_dir=config.cache_dir,
        timeline=config.timeline,
        hud=preview_hud,
        overrides=dict(config.overrides),
    )
    return render_preview_png(preview_config, width, height)
```

- [ ] **Step 4: Expose `POST /api/preview` in the editor server**

```python
# src/race_overlay/editor_server.py
if request_path == "/api/preview":
    try:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(
            self.rfile.read(content_length) or b"{}",
            parse_constant=_reject_invalid_json_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError("HUD config payload must be a JSON object")
        preview = render_preview_payload(config_path, payload, width, height)
    except JSONDecodeError:
        self._write_json(400, {"error": "invalid JSON payload"})
        return
    except (TypeError, ValueError) as exc:
        self._write_json(400, {"error": str(exc)})
        return

    self.send_response(200)
    self.send_header("Content-Type", "image/png")
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(preview)
    return
```

- [ ] **Step 5: Re-run the draft-preview tests to verify they pass**

Run: `uv run pytest tests/test_editor.py -k "preview_payload or api_preview" -v`
Expected: PASS with preview PNGs generated from unsaved drafts and `overlay.yaml` unchanged until save

- [ ] **Step 6: Commit the live-preview backend changes**

```bash
git add tests/test_editor.py src/race_overlay/editor_preview.py src/race_overlay/editor_server.py
git commit -m "feat: add live draft preview for HUD editor"
```

### Task 4: Rebuild the browser editor as a canvas-first designer

**Files:**
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing editor-shell tests**

```python
# tests/test_editor.py
from importlib.resources import files


def test_editor_shell_contains_three_pane_workspace_and_hidden_help_modal() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")

    assert 'id="layers-panel"' in html
    assert 'id="canvas-panel"' in html
    assert 'id="inspector-panel"' in html
    assert 'id="help-button"' in html
    assert 'id="help-modal"' in html
    assert 'hidden' in html.split('id="help-modal"', 1)[1]
```

```python
# tests/test_editor.py
def test_editor_script_uses_preview_endpoint_for_live_draft_updates() -> None:
    script = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/preview"' in script
    assert "draftState" in script
    assert "help-modal" in script
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_editor.py -k "three_pane_workspace or live_draft_updates" -v`
Expected: FAIL because the current editor shell is still a sidebar form and the script only loads `/api/preview.png`

- [ ] **Step 3: Replace `index.html` with the three-pane shell**

```html
<!-- src/race_overlay/editor_assets/index.html -->
<body>
  <div id="app-shell">
    <aside id="layers-panel"></aside>
    <main id="canvas-panel">
      <header id="toolbar">
        <button id="help-button" type="button" aria-controls="help-modal" aria-expanded="false">?</button>
        <button id="save-button" type="button">Save YAML</button>
      </header>
      <section id="canvas-stage">
        <img id="preview" alt="HUD preview" />
        <div id="widget-overlays" aria-hidden="true"></div>
      </section>
    </main>
    <aside id="inspector-panel"></aside>
  </div>
  <dialog id="help-modal" hidden>
    <h2>Help</h2>
    <p>Drag on canvas to move HUD blocks. Use handles to resize. Save YAML to persist.</p>
    <button id="help-close-button" type="button">Close</button>
  </dialog>
  <script src="/app.js" type="module"></script>
</body>
```

- [ ] **Step 4: Replace `styles.css` with a canvas-first layout**

```css
/* src/race_overlay/editor_assets/styles.css */
body {
  margin: 0;
  min-height: 100vh;
  background: #0b1020;
  color: #f4f7fb;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

#app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 280px;
  gap: 16px;
  padding: 16px;
}

#canvas-stage {
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: #111723;
  overflow: hidden;
}

#widget-overlays {
  position: absolute;
  inset: 16px;
  pointer-events: none;
}

.widget-overlay.is-selected {
  outline: 2px solid #63d6ff;
  box-shadow: 0 0 0 3px rgba(99, 214, 255, 0.28);
}

#help-modal[hidden] {
  display: none;
}
```

- [ ] **Step 5: Replace `app.js` with local-draft, live-preview, drag/resize, layer-order, and help-modal logic**

```javascript
// src/race_overlay/editor_assets/app.js
let savedState = null;
let draftState = null;
let selectedWidgetId = null;
let previewRequest = 0;

function cloneHud(hud) {
  const theme = Object.assign({}, hud.theme);
  const widgets = hud.widgets.map((widget) => ({
    id: widget.id,
    type: widget.type,
    bindings: Object.assign({}, widget.bindings),
    anchor: widget.anchor,
    x: widget.x,
    y: widget.y,
    width: widget.width,
    height: widget.height,
    z_index: widget.z_index,
    visible: widget.visible,
    style: Object.assign({}, widget.style),
  }));
  return {
    preset: hud.preset,
    theme,
    widgets,
  };
}

async function refreshPreview() {
  if (!draftState) return;
  const requestId = ++previewRequest;
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draftState),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error ?? "Failed to render preview");
  }
  if (requestId !== previewRequest) return;
  const blob = await response.blob();
  document.getElementById("preview").src = URL.createObjectURL(blob);
}

function openHelp() {
  const modal = document.getElementById("help-modal");
  modal.hidden = false;
  document.getElementById("help-button").setAttribute("aria-expanded", "true");
}

function closeHelp() {
  const modal = document.getElementById("help-modal");
  modal.hidden = true;
  document.getElementById("help-button").setAttribute("aria-expanded", "false");
}

function updateWidget(widgetId, patch) {
  const widget = draftState.widgets.find((item) => item.id === widgetId);
  Object.assign(widget, patch);
  renderLayers();
  renderInspector();
  renderCanvasOverlays();
  void refreshPreview();
}

document.getElementById("help-button").addEventListener("click", openHelp);
document.getElementById("help-close-button").addEventListener("click", closeHelp);
document.getElementById("save-button").addEventListener("click", saveState);
```

- [ ] **Step 6: Re-run the editor-shell tests to verify they pass**

Run: `uv run pytest tests/test_editor.py -k "three_pane_workspace or live_draft_updates" -v`
Expected: PASS with the new shell contract, hidden Help modal, and `/api/preview` usage locked in

- [ ] **Step 7: Commit the editor UI rewrite**

```bash
git add tests/test_editor.py src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/styles.css src/race_overlay/editor_assets/app.js
git commit -m "feat: rebuild HUD editor as canvas-first workspace"
```

### Task 5: Update docs and run the full regression pass

**Files:**
- Modify: `README.md`
- Modify: `tests/test_editor.py`
- Modify: `tests/test_hud.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing documentation contract test**

```python
# tests/test_editor.py
def test_editor_help_defaults_closed_in_served_html(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            connection.close()

    assert response.status == 200
    assert 'id="help-modal"' in body
    assert "hidden" in body.split('id="help-modal"', 1)[1]
```

- [ ] **Step 2: Run the targeted documentation/smoke test to verify it passes with the new shell**

Run: `uv run pytest tests/test_editor.py -k "help_defaults_closed_in_served_html" -v`
Expected: PASS because the served HTML keeps Help hidden until the user opens it

- [ ] **Step 3: Update the user-facing README workflow**

~~~md
<!-- README.md -->
## Edit the HUD visually

Run the local editor:

```bash
uv run race-overlay edit-hud --config-path overlay.yaml
```

- Drag HUD blocks directly on the canvas to reposition them.
- Resize selected widgets from the canvas handles.
- Use the Layers panel for visibility and z-order changes.
- Use the Inspector for exact geometry and style values.
- Preview updates immediately in the browser, but `overlay.yaml` is unchanged until you click **Save YAML**.
- The Help popup is hidden by default and only opens from the `?` button.
~~~

- [ ] **Step 4: Run the focused regression suite for all touched behavior**

Run: `uv run pytest tests/test_sampling.py tests/test_hud.py tests/test_hud_presets.py tests/test_pipeline.py tests/test_editor.py -q`
Expected: PASS with the new data path, renderer, live preview, and editor shell all covered

- [ ] **Step 5: Run the full repository test suite**

Run: `uv run pytest -q`
Expected: PASS with no regressions outside the HUD/editor changes

- [ ] **Step 6: Commit docs and final polish**

```bash
git add README.md tests/test_editor.py tests/test_hud.py tests/test_pipeline.py
git commit -m "docs: document HUD v2 editor workflow"
```
