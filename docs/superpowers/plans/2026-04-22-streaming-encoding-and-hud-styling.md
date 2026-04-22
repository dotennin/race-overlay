# Streaming Encoding and HUD Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve source-video encoding as closely as practical, make streaming export the default fast path with automatic cache fallback, and expose richer HUD styling controls in both YAML and the editor.

**Architecture:** Extend the existing `VideoClip` probe result so one `ffprobe` call captures both timing and encoding metadata. Use that metadata to resolve an `OutputEncodingPlan`, drive a streaming-first ffmpeg compose path inside `pipeline.py`, and fall back to the existing cache path only when compatibility requires it. Keep `render_hud_frame` as the single HUD renderer, but expand the HUD schema/theme and editor inspector so font, color, unit, and ruler-display controls share one config model.

**Tech Stack:** Python 3.12, Pillow, ffmpeg/ffprobe, Typer, vanilla JS, pytest, uv

---

## File Map

- `src/race_overlay/models.py` — extend `VideoClip` with optional encoding metadata so callers do not need a second probe object.
- `src/race_overlay/video_probe.py` — request codec/pixel-format/color/audio fields from `ffprobe` and populate the richer `VideoClip`.
- `src/race_overlay/ffmpeg.py` — resolve output encoding from the probed source clip, assemble streaming and cache compose commands, and surface downgrade reasons.
- `src/race_overlay/pipeline.py` — choose the streaming path first, pipe RGBA HUD frames into ffmpeg, emit path/encoding/fallback logs, and reuse the current cache path on recoverable failures.
- `src/race_overlay/hud_schema.py` — add typed theme fields for fonts and unit visibility while keeping existing RGBA conventions.
- `src/race_overlay/hud.py` — consume theme defaults plus widget overrides, hide units when requested, and render the top ruler's current/total distance labels by default.
- `src/race_overlay/hud_presets.py` — seed the new theme defaults and ruler visibility defaults in `broadcast_runner_preset()`.
- `src/race_overlay/editor_preview.py` — expose editor schema metadata for theme controls and keep revision-safe save/load paths aligned with the expanded HUD schema.
- `src/race_overlay/editor_assets/index.html` — add a dedicated theme-controls mount point in the inspector.
- `src/race_overlay/editor_assets/app.js` — render theme controls, wire widget overrides, and round-trip the new style fields through the existing save/preview flow.
- `src/race_overlay/editor_assets/styles.css` — style the extra theme control groups without disturbing the existing layout.
- `tests/test_video_probe.py` — cover richer ffprobe parsing.
- `tests/test_ffmpeg.py` — cover encoding-plan resolution and ffmpeg command construction.
- `tests/test_pipeline.py` — cover streaming selection, automatic fallback, and the new progress logs.
- `tests/test_hud.py` — cover unit visibility, font settings, and ruler current/total labels.
- `tests/test_editor.py` — cover schema metadata exposure and config round-tripping for the new style fields.

### Task 1: Capture source encoding metadata in `VideoClip`

**Files:**
- Modify: `src/race_overlay/models.py`
- Modify: `src/race_overlay/video_probe.py`
- Create: `tests/test_video_probe.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from race_overlay.video_probe import probe_video


def test_probe_video_includes_source_encoding_metadata(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
                "bit_rate": "16000000",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "192000",
            },
        ],
        "format": {
            "duration": "12.5",
            "tags": {"creation_time": "2026-04-19T09:05:59Z"},
        },
    }
    monkeypatch.setattr(
        "race_overlay.video_probe.subprocess.check_output",
        lambda *args, **kwargs: json.dumps(payload),
    )

    clip = probe_video(tmp_path / "clip.MP4")

    assert clip.creation_time == datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc)
    assert clip.video_codec == "h264"
    assert clip.pixel_format == "yuv420p"
    assert clip.video_bitrate == 16_000_000
    assert clip.color_space == "bt709"
    assert clip.color_transfer == "bt709"
    assert clip.color_primaries == "bt709"
    assert clip.audio_codec == "aac"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_video_probe.py::test_probe_video_includes_source_encoding_metadata -v`

Expected: FAIL because `VideoClip` does not have encoding fields yet and `video_probe.py` does not request them from ffprobe.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(slots=True, frozen=True)
class VideoClip:
    path: Path
    creation_time: datetime
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str | None = None
    pixel_format: str | None = None
    video_bitrate: int | None = None
    color_space: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    audio_codec: str | None = None
    audio_bitrate: int | None = None
```

```python
def probe_video(path: Path) -> VideoClip:
    payload = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                (
                    "format=duration:format_tags=creation_time:"
                    "stream=codec_type,codec_name,width,height,avg_frame_rate,"
                    "pix_fmt,bit_rate,color_space,color_transfer,color_primaries"
                ),
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )
    video_stream = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in payload["streams"] if stream["codec_type"] == "audio"), {})
    return VideoClip(
        path=path,
        creation_time=_parse_time(payload["format"]["tags"]["creation_time"]),
        duration_seconds=float(payload["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_parse_rate(video_stream["avg_frame_rate"]),
        video_codec=video_stream.get("codec_name"),
        pixel_format=video_stream.get("pix_fmt"),
        video_bitrate=_parse_optional_int(video_stream.get("bit_rate")),
        color_space=video_stream.get("color_space"),
        color_primaries=video_stream.get("color_primaries"),
        color_transfer=video_stream.get("color_transfer"),
        audio_codec=audio_stream.get("codec_name"),
        audio_bitrate=_parse_optional_int(audio_stream.get("bit_rate")),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_video_probe.py::test_probe_video_includes_source_encoding_metadata -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/models.py src/race_overlay/video_probe.py tests/test_video_probe.py
git commit -m "feat: capture source encoding metadata" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Resolve source-aware output encoding and ffmpeg commands

**Files:**
- Modify: `src/race_overlay/ffmpeg.py`
- Create: `tests/test_ffmpeg.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone
from pathlib import Path

from race_overlay.ffmpeg import build_stream_compose_command, resolve_output_encoding_plan
from race_overlay.models import VideoClip


def test_resolve_output_encoding_plan_preserves_supported_source_settings() -> None:
    clip = VideoClip(
        path=Path("clip.MP4"),
        creation_time=datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc),
        duration_seconds=1.0,
        width=1280,
        height=720,
        fps=29.97,
        video_codec="h264",
        pixel_format="yuv420p",
        video_bitrate=16_000_000,
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
        audio_codec="aac",
        audio_bitrate=192_000,
    )

    plan = resolve_output_encoding_plan(clip)

    assert plan.video_codec == "libx264"
    assert plan.pixel_format == "yuv420p"
    assert plan.audio_args == ("-c:a", "copy")
    assert plan.warnings == ()


def test_resolve_output_encoding_plan_downgrades_unsupported_video_codec() -> None:
    clip = VideoClip(
        path=Path("clip.MOV"),
        creation_time=datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc),
        duration_seconds=1.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="av1",
        pixel_format="yuv444p10le",
        video_bitrate=28_000_000,
        audio_codec="pcm_s16le",
    )

    plan = resolve_output_encoding_plan(clip)

    assert plan.video_codec == "libx264"
    assert plan.pixel_format == "yuv420p"
    assert any("av1" in warning for warning in plan.warnings)


def test_build_stream_compose_command_reads_rgba_frames_from_stdin() -> None:
    clip = VideoClip(
        path=Path("clip.MP4"),
        creation_time=datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc),
        duration_seconds=1.0,
        width=1280,
        height=720,
        fps=30.0,
    )
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=clip.path,
        clip=clip,
        output_path=Path("rendered/clip.MP4"),
        plan=plan,
    )

    assert "-f" in command and "rawvideo" in command
    assert "-pix_fmt" in command and "rgba" in command
    assert "-i" in command and "-" in command
    assert "overlay=0:0" in command
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ffmpeg.py -v`

Expected: FAIL because `ffmpeg.py` only knows how to build a cached `qtrle` overlay and has no output-plan or streaming command helpers.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(slots=True, frozen=True)
class OutputEncodingPlan:
    video_codec: str
    pixel_format: str | None
    video_bitrate: int | None
    color_space: str | None
    color_primaries: str | None
    color_transfer: str | None
    audio_args: tuple[str, ...]
    warnings: tuple[str, ...] = ()
```

```python
SUPPORTED_VIDEO_CODEC_MAP = {
    "h264": "libx264",
    "hevc": "libx265",
    "prores": "prores_ks",
}


def resolve_output_encoding_plan(clip: VideoClip) -> OutputEncodingPlan:
    warnings: list[str] = []
    video_codec = SUPPORTED_VIDEO_CODEC_MAP.get(clip.video_codec or "", "libx264")
    if clip.video_codec and clip.video_codec not in SUPPORTED_VIDEO_CODEC_MAP:
        warnings.append(f"video codec {clip.video_codec} is not supported after overlay; using libx264")
    pixel_format = clip.pixel_format if clip.pixel_format in {"yuv420p", "yuv422p", "yuva444p10le"} else "yuv420p"
    if clip.pixel_format and pixel_format != clip.pixel_format:
        warnings.append(f"pixel format {clip.pixel_format} is not supported after overlay; using {pixel_format}")
    audio_args = ("-c:a", "copy") if clip.audio_codec else ("-an",)
    return OutputEncodingPlan(
        video_codec=video_codec,
        pixel_format=pixel_format,
        video_bitrate=clip.video_bitrate,
        color_space=clip.color_space,
        color_primaries=clip.color_primaries,
        color_transfer=clip.color_transfer,
        audio_args=audio_args,
        warnings=tuple(warnings),
    )
```

```python
def build_stream_compose_command(*, source_path: Path, clip: VideoClip, output_path: Path, plan: OutputEncodingPlan) -> list[str]:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{clip.width}x{clip.height}",
        "-r",
        str(clip.fps),
        "-i",
        "-",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0",
        "-c:v",
        plan.video_codec,
    ]
    if plan.pixel_format:
        command.extend(["-pix_fmt", plan.pixel_format])
    if plan.video_bitrate:
        command.extend(["-b:v", str(plan.video_bitrate)])
    command.extend(plan.audio_args)
    command.append(str(output_path))
    return command
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ffmpeg.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/ffmpeg.py tests/test_ffmpeg.py
git commit -m "feat: plan source-aware output encoding" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Make streaming compose the default render path with automatic cache fallback

**Files:**
- Modify: `src/race_overlay/pipeline.py`
- Modify: `src/race_overlay/ffmpeg.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_pipeline_prefers_streaming_and_reports_encoding_plan(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    messages: list[str] = []
    writes: list[bytes] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = type("Pipe", (), {"write": writes.append, "close": lambda self: None})()

        def wait(self) -> int:
            return 0

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr("race_overlay.pipeline.resolve_output_encoding_plan", lambda clip: resolve_output_encoding_plan(clip))
    monkeypatch.setattr("race_overlay.pipeline.open_stream_compose_process", lambda **kwargs: FakeProcess())

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert any("Render path: streaming" in message for message in messages)
    assert any("Encoding plan:" in message for message in messages)
    assert writes


def test_run_pipeline_falls_back_to_cache_when_streaming_fails(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    messages: list[str] = []
    fallback_called = {"value": False}

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: (_ for _ in ()).throw(OSError("stdin pipe unavailable")),
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: fallback_called.__setitem__("value", True))
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is True
    assert any("falling back to cache" in message for message in messages)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py::test_run_pipeline_prefers_streaming_and_reports_encoding_plan tests/test_pipeline.py::test_run_pipeline_falls_back_to_cache_when_streaming_fails -v`

Expected: FAIL because `run_pipeline()` always writes PNG frames, never opens a streaming ffmpeg process, and never reports encoding-plan/fallback messages.

- [ ] **Step 3: Write the minimal implementation**

```python
def open_stream_compose_process(*, source_path: Path, clip: VideoClip, output_path: Path, plan: OutputEncodingPlan) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        build_stream_compose_command(source_path=source_path, clip=clip, output_path=output_path, plan=plan),
        stdin=subprocess.PIPE,
    )
```

```python
def _render_clip_streaming(..., progress: ProgressReporter | None) -> None:
    plan = resolve_output_encoding_plan(clip)
    _emit(progress, f"Encoding plan: video={plan.video_codec} pix_fmt={plan.pixel_format or 'auto'} audio={' '.join(plan.audio_args)}")
    for warning in plan.warnings:
        _emit(progress, f"Encoding fallback: {warning}")
    process = open_stream_compose_process(source_path=clip.path, clip=clip, output_path=output_path, plan=plan)
    assert process.stdin is not None
    for index in range(int(clip.duration_seconds * clip.fps)):
        image = _render_overlay_frame(...)
        process.stdin.write(image.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode or 1, "ffmpeg")
```

```python
_emit(progress, f"Processing {video_path.name}")
plan = resolve_output_encoding_plan(clip)
try:
    _emit(progress, f"Render path: streaming for {clip.path.name}")
    _render_clip_streaming(..., progress=progress)
except (OSError, subprocess.SubprocessError) as exc:
    _emit(progress, f"Streaming unavailable for {clip.path.name}; falling back to cache: {exc}")
    _render_clip_via_cache(..., progress=progress, plan=plan)
```

- [ ] **Step 4: Run the focused tests, then the full suite**

Run: `uv run pytest tests/test_pipeline.py -v && uv run pytest -q`

Expected: all pipeline tests PASS, then the full suite PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/ffmpeg.py src/race_overlay/pipeline.py tests/test_pipeline.py
git commit -m "feat: stream overlay composition with cache fallback" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Add typed HUD style defaults and default current/total ruler labels

**Files:**
- Modify: `src/race_overlay/hud_schema.py`
- Modify: `src/race_overlay/hud.py`
- Modify: `src/race_overlay/hud_presets.py`
- Modify: `tests/test_hud.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_render_hud_frame_hides_metric_units_when_theme_disables_units(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = broadcast_runner_preset()
    preset.theme.show_units = False

    labels = _rendered_text_labels(monkeypatch, preset)

    assert "KM" not in labels
    assert "BPM" not in labels
    assert "/km" not in labels


def test_render_hud_frame_shows_current_and_total_distance_on_ruler_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    labels: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        labels.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert any("Distance" in label for label in labels)
    assert any("24.60" in label for label in labels)
    assert any("10.00" in label for label in labels)


def test_validate_hud_config_rejects_unknown_font_family() -> None:
    preset = broadcast_runner_preset()
    preset.theme.font_family = "comic-sans"

    with pytest.raises(ValueError, match="font_family"):
        validate_hud_config(preset)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_hides_metric_units_when_theme_disables_units tests/test_hud.py::test_render_hud_frame_shows_current_and_total_distance_on_ruler_by_default tests/test_hud.py::test_validate_hud_config_rejects_unknown_font_family -v`

Expected: FAIL because `HudThemeConfig` has no font/unit fields yet, the renderer always draws units, and the ruler only draws ticks plus the marker.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(slots=True)
class HudThemeConfig:
    panel_rgba: list[int] = field(default_factory=lambda: [12, 18, 28, 168])
    accent_rgba: list[int] = field(default_factory=lambda: [255, 196, 92, 255])
    text_rgba: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    note_text: str = "Race Day"
    font_family: str = "sans"
    font_weight: str = "regular"
    font_size_px: int = 18
    show_units: bool = True
```

```python
def _style_bool(widget: HudWidgetConfig, theme: HudThemeConfig, key: str, default: bool) -> bool:
    value = widget.style.get(key, getattr(theme, key, default))
    return bool(value)


def _style_font_size(widget: HudWidgetConfig, theme: HudThemeConfig, fallback: int) -> int:
    value = widget.style.get("font_size_px", theme.font_size_px or fallback)
    return max(int(value), 8)
```

```python
def _metric_suffix(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    if not _style_bool(widget, theme, "show_unit", theme.show_units):
        return ""
    binding = widget.bindings["value"]
    ...
```

```python
current_label = f"{progress_value_m / 1000:.2f}"
total_label = f"{goal_m / 1000:.2f}"
if _style_bool(widget, theme, "show_current_value", True):
    draw.text((track_left, top + _scale_y(scale, 14)), current_label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, theme.font_size_px))
if _style_bool(widget, theme, "show_total_value", True):
    draw.text((track_right, top + _scale_y(scale, 14)), total_label, fill=tuple(theme.text_rgba), anchor="ra", font=_scaled_font(scale, theme.font_size_px))
```

```python
HudThemeConfig(
    panel_rgba=[12, 18, 28, 148],
    accent_rgba=[26, 230, 198, 255],
    text_rgba=[247, 251, 255, 255],
    font_family="sans",
    font_weight="regular",
    font_size_px=18,
    show_units=True,
)
...
{"label": "Distance", "variant": "ruler", "show_current_value": True, "show_total_value": True}
```

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/test_hud.py -k 'font_family or show_current_and_total_distance_on_ruler or hides_metric_units' -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/hud_schema.py src/race_overlay/hud.py src/race_overlay/hud_presets.py tests/test_hud.py
git commit -m "feat: add typed HUD style defaults" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Expose the new HUD style controls in the editor and preserve round-tripping

**Files:**
- Modify: `src/race_overlay/editor_preview.py`
- Modify: `src/race_overlay/editor_assets/index.html`
- Modify: `src/race_overlay/editor_assets/app.js`
- Modify: `src/race_overlay/editor_assets/styles.css`
- Modify: `tests/test_editor.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_editor_state_exposes_theme_style_schema() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["schema"]["theme"]["font_family"]["options"] == ["sans", "serif", "mono"]
    assert state["schema"]["theme"]["font_weight"]["options"] == ["regular", "medium", "bold"]
    assert state["schema"]["theme"]["show_units"]["type"] == "boolean"


def test_save_editor_payload_round_trips_theme_font_and_ruler_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["font_family"] = "mono"
    payload["theme"]["font_weight"] = "bold"
    payload["theme"]["font_size_px"] = 20
    payload["theme"]["show_units"] = False
    ruler = next(widget for widget in payload["widgets"] if widget["id"] == "distance-ruler")
    ruler["style"]["show_total_value"] = False

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.theme.font_family == "mono"
    assert reloaded.hud.theme.font_weight == "bold"
    assert reloaded.hud.theme.font_size_px == 20
    assert reloaded.hud.theme.show_units is False
    assert next(widget for widget in reloaded.hud.widgets if widget.id == "distance-ruler").style["show_total_value"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_editor.py::test_build_editor_state_exposes_theme_style_schema tests/test_editor.py::test_save_editor_payload_round_trips_theme_font_and_ruler_flags -v`

Expected: FAIL because `build_editor_state()` does not expose theme-control metadata and the saved HUD schema does not yet include the new theme keys.

- [ ] **Step 3: Write the minimal implementation**

```python
def build_editor_state(config: ProjectConfig, width: int, height: int) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "revision": _hud_revision(config.hud),
        "preview": {"width": width, "height": height, "route_points": [[36.0832, 140.2106], [36.0834, 140.2108]]},
        "schema": {
            "theme": {
                "font_family": {"type": "select", "options": ["sans", "serif", "mono"]},
                "font_weight": {"type": "select", "options": ["regular", "medium", "bold"]},
                "font_size_px": {"type": "number", "min": 8, "max": 64},
                "show_units": {"type": "boolean"},
            }
        },
    }
```

```html
<section class="panel-section">
  <div class="section-heading">
    <h2>Theme</h2>
    <span class="section-meta">Shared defaults</span>
  </div>
  <div id="theme-controls"></div>
</section>
```

```javascript
function updateTheme(patch) {
  draftState.theme = { ...draftState.theme, ...patch };
  renderInspector();
  schedulePreviewRefresh();
}

function renderThemeControls() {
  if (!elements.themeControls || !draftState || !savedState?.schema?.theme) {
    return;
  }
  const card = document.createElement("section");
  card.className = "inspector-card";
  const grid = document.createElement("div");
  grid.className = "inspector-grid";
  appendField(grid, "Note", buildTextInput(draftState.theme.note_text ?? "", (value) => updateTheme({ note_text: value })), true);
  appendField(grid, "Font family", buildSelectInput(savedState.schema.theme.font_family.options, draftState.theme.font_family, (value) => updateTheme({ font_family: value })), true);
  appendField(grid, "Font weight", buildSelectInput(savedState.schema.theme.font_weight.options, draftState.theme.font_weight, (value) => updateTheme({ font_weight: value })), false);
  appendField(grid, "Font size", buildNumberInput(draftState.theme.font_size_px, (value) => updateTheme({ font_size_px: value })), false);
  appendToggleField(grid, "Show units", draftState.theme.show_units, (value) => updateTheme({ show_units: value }));
  appendRgbaField(grid, "Text RGBA", draftState.theme.text_rgba, (value) => updateTheme({ text_rgba: value }));
  appendRgbaField(grid, "Accent RGBA", draftState.theme.accent_rgba, (value) => updateTheme({ accent_rgba: value }));
  appendRgbaField(grid, "Panel RGBA", draftState.theme.panel_rgba, (value) => updateTheme({ panel_rgba: value }));
  card.appendChild(grid);
  elements.themeControls.replaceChildren(card);
}
```

- [ ] **Step 4: Run the focused tests, then the full suite**

Run: `uv run pytest tests/test_editor.py -v && uv run pytest -q`

Expected: editor tests PASS, then the full suite PASS

- [ ] **Step 5: Commit**

```bash
git add src/race_overlay/editor_preview.py src/race_overlay/editor_assets/index.html src/race_overlay/editor_assets/app.js src/race_overlay/editor_assets/styles.css tests/test_editor.py
git commit -m "feat: expose HUD style controls in editor" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Spec Coverage Check

- **Preserve source encoding parameters as completely as practical:** Tasks 1-3 capture probe metadata, resolve an output plan, and log any compatibility downgrades.
- **Prefer streaming export and avoid disk-backed cache when possible:** Task 3 makes streaming the default path and keeps the cache path as automatic fallback.
- **Automatic fallback with explanation:** Tasks 2-3 introduce plan warnings and explicit fallback logs.
- **Expand HUD styling in YAML and editor:** Tasks 4-5 extend the HUD schema/theme, renderer, preset defaults, and editor UI.
- **Show current + total distance on the top ruler by default:** Task 4 adds the default ruler labels and widget-level visibility flags.
- **Verify via existing tests:** Every task starts with focused failing tests and ends with focused or full pytest runs.

## Placeholder Scan

- No `TODO`, `TBD`, or "similar to above" shortcuts remain.
- Every code-changing step includes concrete file paths, code shapes, and exact commands.
- The same naming is used throughout: `video_codec`, `pixel_format`, `resolve_output_encoding_plan`, `font_size_px`, `show_units`, `show_current_value`, and `show_total_value`.
