# HUD Render Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make final rendered videos match the live preview's visual proportions, make non-map HUD widgets transparent by default, and add concise render progress logs that expose cache generation.

**Architecture:** Keep `render_hud_frame` as the only HUD renderer and fix parity inside it by introducing an internal scaling context plus explicit widget panel defaults. Add render progress reporting as a callback-driven concern in `pipeline.py`, with `cli.py` responsible for sending those messages to the terminal via Typer.

**Tech Stack:** Python 3.12, Pillow, Typer, pytest, uv

---

## File Map

- `src/race_overlay/hud.py` — single HUD renderer; add scaling helpers, scaled font usage, and unified panel-default handling.
- `src/race_overlay/hud_presets.py` — align the shipped preset with the new `show_panel` behavior and remove the legacy transparent-panel-only preset tweak.
- `src/race_overlay/pipeline.py` — emit stage-by-stage progress through a callback without changing render/composition responsibilities.
- `src/race_overlay/cli.py` — pass `typer.echo` into the pipeline and keep the existing command UX small and readable.
- `tests/test_hud.py` — prove scaled layout/font behavior and transparent-by-default widget panels.
- `tests/test_hud_presets.py` — prove the preset now expresses route-map panel intent explicitly.
- `tests/test_pipeline.py` — prove progress messages cover cache generation, compose, and skip paths.
- `tests/test_cli.py` — prove `render` prints pipeline progress and still reports completion.

### Task 1: Scale configurable HUD geometry and text from the 1280×720 reference canvas

**Files:**
- Modify: `src/race_overlay/hud.py:9-379`
- Test: `tests/test_hud.py:16-128`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_hud_frame_scales_widget_regions_for_larger_frames() -> None:
    image = render_hud_frame(
        width=2560,
        height=1440,
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

    assert image.getpixel((1280, 140))[3] > 0
    assert image.getpixel((180, 1220))[3] > 0
    assert image.getpixel((640, 70))[3] == 0
    assert image.getpixel((90, 610))[3] == 0


def test_render_hud_frame_scales_font_sizes_for_larger_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_sizes: list[int] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        if font is not None and getattr(font, "size", None) is not None:
            seen_sizes.append(int(font.size))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)

    render_hud_frame(
        width=2560,
        height=1440,
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

    assert max(seen_sizes) >= 20
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_scales_widget_regions_for_larger_frames tests/test_hud.py::test_render_hud_frame_scales_font_sizes_for_larger_frames -v`

Expected: FAIL because the larger render still draws widgets at the old 1280×720 coordinates and `ImageDraw.text()` receives no scaled font.

- [ ] **Step 3: Write the minimal implementation**

```python
from PIL import Image, ImageDraw, ImageFont


@dataclass(slots=True, frozen=True)
class RenderScale:
    x: float
    y: float
    draw: float


def _render_scale(frame_width: int, frame_height: int) -> RenderScale:
    x_scale = frame_width / HUD_REFERENCE_WIDTH
    y_scale = frame_height / HUD_REFERENCE_HEIGHT
    return RenderScale(x=x_scale, y=y_scale, draw=min(x_scale, y_scale))


def _scale_x(scale: RenderScale, value: int) -> int:
    return int(round(value * scale.x))


def _scale_y(scale: RenderScale, value: int) -> int:
    return int(round(value * scale.y))


def _scale_draw(scale: RenderScale, value: int) -> int:
    return max(int(round(value * scale.draw)), 1)


def _scaled_font(scale: RenderScale, size: int):
    return ImageFont.load_default(size=max(_scale_draw(scale, size), 8))
```
```python
def _resolve_widget_origin(widget: HudWidgetConfig, frame_width: int, frame_height: int, scale: RenderScale) -> tuple[int, int]:
    left = _scale_x(scale, widget.x)
    top = _scale_y(scale, widget.y)
    if "right" in widget.anchor:
        left += frame_width - _scale_x(scale, HUD_REFERENCE_WIDTH)
    if "bottom" in widget.anchor:
        top += frame_height - _scale_y(scale, HUD_REFERENCE_HEIGHT)
    return (max(left, 0), max(top, 0))
```
```python
scale = _render_scale(frame_width, frame_height)
left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
right = left + _scale_x(scale, widget.width)
bottom = top + _scale_y(scale, widget.height)
draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_scales_widget_regions_for_larger_frames tests/test_hud.py::test_render_hud_frame_scales_font_sizes_for_larger_frames -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_hud.py src/race_overlay/hud.py
git commit -m "fix: scale HUD rendering from reference canvas" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Make widget panels transparent by default except for the route map

**Files:**
- Modify: `src/race_overlay/hud.py:187-379`
- Modify: `src/race_overlay/hud_presets.py:6-132`
- Test: `tests/test_hud.py:74-128,455-520`
- Test: `tests/test_hud_presets.py:4-30`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_hud_frame_defaults_non_map_widgets_to_transparent_panels(monkeypatch: pytest.MonkeyPatch) -> None:
    panel_fills: list[tuple[int, int, int, int]] = []
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            panel_fills.append(fill)
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)

    preset = broadcast_runner_preset()
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
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert tuple(preset.theme.panel_rgba) not in panel_fills


def test_render_hud_frame_keeps_route_map_panel_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ellipse_fills: list[tuple[int, int, int, int]] = []
    original_ellipse = ImageDraw.ImageDraw.ellipse

    def record_ellipse(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            ellipse_fills.append(fill)
        return original_ellipse(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "ellipse", record_ellipse)

    preset = broadcast_runner_preset()
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
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert tuple(preset.theme.panel_rgba) in ellipse_fills


def test_render_hud_frame_honors_explicit_show_panel_override(monkeypatch: pytest.MonkeyPatch) -> None:
    panel_fills: list[tuple[int, int, int, int]] = []
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            panel_fills.append(fill)
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)

    hud_config = HudConfig(
        preset="panel-opt-in",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="pace-chip",
                type="metric_card",
                bindings={"value": "pace_seconds_per_km"},
                anchor="top-left",
                x=24,
                y=24,
                width=160,
                height=96,
                style={"label": "Pace", "show_panel": True},
            )
        ],
    )

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
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert tuple(hud_config.theme.panel_rgba) in panel_fills


def test_broadcast_runner_preset_uses_explicit_route_map_panel_toggle() -> None:
    config = broadcast_runner_preset()
    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert "transparent_panel" not in ruler.style
    assert route_map.style["show_panel"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_defaults_non_map_widgets_to_transparent_panels tests/test_hud.py::test_render_hud_frame_keeps_route_map_panel_by_default tests/test_hud.py::test_render_hud_frame_honors_explicit_show_panel_override tests/test_hud_presets.py::test_broadcast_runner_preset_uses_explicit_route_map_panel_toggle -v`

Expected: FAIL because metric/stat/context widgets still draw `theme.panel_rgba`, the preset still uses `transparent_panel`, and there is no `show_panel` override behavior.

- [ ] **Step 3: Write the minimal implementation**

```python
def _widget_panel_enabled(widget: HudWidgetConfig) -> bool:
    show_panel = widget.style.get("show_panel")
    if isinstance(show_panel, bool):
        return show_panel
    if bool(widget.style.get("transparent_panel", False)):
        return False
    return widget.type == "route_map"
```
```python
if _widget_panel_enabled(widget):
    draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 20), fill=tuple(theme.panel_rgba))
```
```python
HudWidgetConfig(
    "distance-ruler",
    "progress_bar",
    {"value": "distance_m"},
    "top-left",
    360,
    28,
    560,
    56,
    40,
    True,
    {"label": "Distance", "variant": "ruler"},
)
```
```python
HudWidgetConfig(
    "route-map",
    "route_map",
    {"value": "route_points"},
    "top-left",
    26,
    514,
    180,
    180,
    20,
    True,
    {"label": "", "shape": "circle", "show_panel": True},
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_defaults_non_map_widgets_to_transparent_panels tests/test_hud.py::test_render_hud_frame_keeps_route_map_panel_by_default tests/test_hud.py::test_render_hud_frame_honors_explicit_show_panel_override tests/test_hud_presets.py::test_broadcast_runner_preset_uses_explicit_route_map_panel_toggle -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_hud.py tests/test_hud_presets.py src/race_overlay/hud.py src/race_overlay/hud_presets.py
git commit -m "fix: default HUD widgets to transparent panels" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Report render progress and cache generation through the CLI

**Files:**
- Modify: `src/race_overlay/pipeline.py:1-80`
- Modify: `src/race_overlay/cli.py:23-30`
- Test: `tests/test_pipeline.py:16-132`
- Test: `tests/test_cli.py:13-88`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_pipeline_reports_progress_for_cache_and_compose(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert any("Generating frame cache" in message for message in messages)
    assert any("Building overlay cache" in message for message in messages)
    assert any("Composing final video" in message for message in messages)
    assert any("Finished clip.MP4" in message for message in messages)


def test_run_pipeline_reports_skipped_outside_clips(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    outside_alignment = ClipAlignment(
        clip=fake_clip(tmp_path / "clip.MP4"),
        status="outside",
        clip_start=fake_clip(tmp_path / "clip.MP4").creation_time,
        clip_end=fake_clip(tmp_path / "clip.MP4").creation_time + timedelta(seconds=1),
        overlay_start=None,
        overlay_end=None,
    )

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: outside_alignment)

    config = load_config(config_path)
    config.timeline.outside_activity = "skip"
    save_config(config_path, config)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert any("Skipping clip.MP4" in message and "outside activity" in message for message in messages)


def test_render_command_prints_pipeline_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.write_text(
        "activity_file: activity_22577902433.tcx\n"
        "video_globs:\n  - '*.MP4'\n"
        "output_dir: rendered\n"
        "cache_dir: cache\n"
        "timeline:\n  global_offset_seconds: 0.0\n  outside_activity: no_data\n"
        "hud:\n  fields:\n    pace: true\n    elapsed: true\n    distance: true\n    speed: true\n    heart_rate: true\n    cadence: true\n    mini_map: true\n"
        "overrides: {}\n"
    )

    def fake_run_pipeline(config_path: Path, only: str | None, *, progress) -> None:
        progress("Generating frame cache at cache/clip/frames")
        progress("Finished clip.MP4")

    monkeypatch.setattr("race_overlay.cli.run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(app, ["render", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert "Generating frame cache at cache/clip/frames" in result.stdout
    assert "Finished clip.MP4" in result.stdout
    assert "Render completed" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py::test_run_pipeline_reports_progress_for_cache_and_compose tests/test_pipeline.py::test_run_pipeline_reports_skipped_outside_clips tests/test_cli.py::test_render_command_prints_pipeline_progress -v`

Expected: FAIL because `run_pipeline()` has no `progress` callback, skip messages are silent, and the CLI never prints intermediate pipeline progress.

- [ ] **Step 3: Write the minimal implementation**

```python
from collections.abc import Callable

ProgressReporter = Callable[[str], None]


def _emit(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def run_pipeline(config_path: Path, only: str | None = None, *, progress: ProgressReporter | None = None) -> None:
    _emit(progress, f"Loading config from {config_path}")
    config = load_config(config_path)
    activity_path = resolve_path_from_config(config_path, config.activity_file)
    _emit(progress, f"Loading activity from {activity_path}")
    activity = load_activity(activity_path)
    total_distance_m = activity.samples[-1].distance_m if activity.samples else None
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    output_dir = resolve_path_from_config(config_path, config.output_dir)
    cache_dir = resolve_path_from_config(config_path, config.cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for video_path in _discover_videos(resolve_video_globs_from_config(config_path, config.video_globs)):
        if only and video_path.name != only:
            continue
        _emit(progress, f"Processing {video_path.name}")
        clip = probe_video(video_path)
        override = resolve_override(config, clip.path.name)
        alignment = align_clip(
            activity,
            clip,
            global_offset_seconds=config.timeline.global_offset_seconds,
            per_video_offset_seconds=override.offset_seconds,
        )
        outside_policy = override.outside_activity or config.timeline.outside_activity
        frame_dir = cache_dir / clip.path.stem / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        _emit(progress, f"Generating frame cache at {frame_dir}")
        for index in range(int(clip.duration_seconds * clip.fps)):
            when = alignment.clip_start + timedelta(seconds=index / clip.fps)
            if alignment.overlay_start is None or when < alignment.overlay_start or when > alignment.overlay_end:
                image = Image.new("RGBA", (clip.width, clip.height), (0, 0, 0, 0))
            else:
                hud_value = sample_at(activity, when)
                image = render_hud_frame(
                    width=clip.width,
                    height=clip.height,
                    hud_value=hud_value,
                    route_points=route_points,
                    hud_config=config.hud,
                    elapsed_seconds=int((when - activity.samples[0].timestamp).total_seconds()),
                    total_distance_m=total_distance_m,
                )
            image.save(frame_dir / f"{index:06d}.png")

        overlay_path = cache_dir / clip.path.stem / "overlay.mov"
        output_path = output_dir / clip.path.name
        _emit(progress, f"Building overlay cache at {overlay_path}")
        build_overlay_video(frame_dir, clip.fps, overlay_path)
        _emit(progress, f"Composing final video at {output_path}")
        compose_video(clip.path, overlay_path, output_path)
        _emit(progress, f"Finished {clip.path.name}")
```
```python
if alignment.status == "outside" and outside_policy == "skip":
    _emit(progress, f"Skipping {clip.path.name}: outside activity window and policy=skip")
    continue
```
```python
def render(
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
    only: str | None = typer.Option(None, "--only"),
) -> None:
    run_pipeline(config_path, only, progress=typer.echo)
    typer.echo("Render completed")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py::test_run_pipeline_reports_progress_for_cache_and_compose tests/test_pipeline.py::test_run_pipeline_reports_skipped_outside_clips tests/test_cli.py::test_render_command_prints_pipeline_progress -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline.py tests/test_cli.py src/race_overlay/pipeline.py src/race_overlay/cli.py
git commit -m "feat: log render pipeline progress" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Run the combined regression set before handing the branch back

**Files:**
- Test: `tests/test_hud.py`
- Test: `tests/test_hud_presets.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_cli.py`
- Inspect: `src/race_overlay/hud.py`
- Inspect: `src/race_overlay/hud_presets.py`
- Inspect: `src/race_overlay/pipeline.py`
- Inspect: `src/race_overlay/cli.py`

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_hud.py tests/test_hud_presets.py tests/test_pipeline.py tests/test_cli.py -q`

Expected: PASS

- [ ] **Step 2: Run the full repository test suite**

Run: `uv run pytest -q`

Expected: PASS

- [ ] **Step 3: Inspect the diff before handoff**

Run:

```bash
git --no-pager diff -- src/race_overlay/hud.py src/race_overlay/hud_presets.py src/race_overlay/pipeline.py src/race_overlay/cli.py tests/test_hud.py tests/test_hud_presets.py tests/test_pipeline.py tests/test_cli.py
```

Expected: only the planned scaling, panel-default, and progress-logging changes are present.
