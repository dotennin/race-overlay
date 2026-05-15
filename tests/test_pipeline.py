from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import build_editor_state, save_editor_payload
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, serialize_hud_config
from race_overlay.models import ActivityLap, ActivitySample, ActivityTrack, ClipAlignment, HudSample, VideoClip
from race_overlay.editor_render import RenderJobCanceledError
from race_overlay.pipeline import FatalStreamingComposeError, run_pipeline
from race_overlay.sampling import LapWaterfallState


def test_render_runs_pipeline_with_config(tmp_path: Path, monkeypatch) -> None:
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

    called = {}

    def fake_run_pipeline(config_path: Path, only: str | None, *, progress=None) -> None:
        called["config_path"] = config_path
        called["only"] = only

    monkeypatch.setattr("race_overlay.cli.run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(app, ["render", "--config-path", str(config_path), "--only", "DJI_20260419090559_0002_D.MP4"])
    assert result.exit_code == 0
    assert called["config_path"] == config_path
    assert called["only"] == "DJI_20260419090559_0002_D.MP4"


def fake_activity() -> ActivityTrack:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    return ActivityTrack(
        sport="running",
        samples=[
            ActivitySample(start, 36.0832, 140.2106, 5.0, 0.0, 3.5, 150, 176),
            ActivitySample(start + timedelta(seconds=10), 36.0834, 140.2108, 5.2, 35.0, 3.6, 152, 178),
        ],
    )


def fake_clip(path: Path, **overrides) -> VideoClip:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    values = {
        "path": path,
        "creation_time": start,
        "duration_seconds": 1.0,
        "width": 1280,
        "height": 720,
        "fps": 1.0,
    }
    values.update(overrides)
    return VideoClip(**values)


def fake_alignment() -> ClipAlignment:
    clip = fake_clip(Path("clip.MP4"))
    return ClipAlignment(
        clip=clip,
        status="inside",
        clip_start=clip.creation_time,
        clip_end=clip.creation_time + timedelta(seconds=clip.duration_seconds),
        overlay_start=clip.creation_time,
        overlay_end=clip.creation_time + timedelta(seconds=clip.duration_seconds),
    )


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


class FakeStreamingPipe:
    def __init__(self, writes: list[bytes], *, write_error: Exception | None = None) -> None:
        self._writes = writes
        self.write_error = write_error
        self.closed = False

    def write(self, data: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self._writes.append(data)
        return len(data)

    def close(self) -> None:
        self.closed = True
        return None


class FakeStreamingProcess:
    def __init__(self, writes: list[bytes], *, returncode: int | None = 0, write_error: Exception | None = None) -> None:
        self.stdin = FakeStreamingPipe(writes, write_error=write_error)
        self.returncode = returncode
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self) -> int:
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


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
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess([]),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4")

    assert captured == [(broadcast_runner_preset(), 35.0)]


def test_run_pipeline_prefers_streaming_and_reports_encoding_plan(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    writes: list[bytes] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert any("Encoding plan:" in message for message in messages)
    assert any("Render path: streaming" in message for message in messages)
    assert writes
    assert any("Finished clip.MP4" in message for message in messages)


def test_run_pipeline_emits_structured_frame_progress_updates(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    updates = []
    writes: list[bytes] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: VideoClip(
            path=path,
            creation_time=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
            duration_seconds=2.0,
            width=1280,
            height=720,
            fps=2.0,
        ),
    )
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append, progress_update=updates.append)

    assert updates
    assert updates[0].clip_name == "clip.MP4"
    assert updates[0].frame_index == 1
    assert updates[-1].percent == 100
    assert updates[-1].frame_total == 4


def test_run_pipeline_passes_encoding_plan_to_cache_compose(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    captured_plan = {}
    process = FakeStreamingProcess([], returncode=None, write_error=BrokenPipeError("broken pipe"))

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: fake_clip(
            path,
            video_codec="hevc",
            pixel_format="yuv420p10le",
            video_bitrate=4_000_000,
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
            audio_codec="mp3",
            audio_bitrate=128_000,
            has_attached_pic=True,
            attached_pic_stream_index=4,
        ),
    )
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: process,
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)

    def fake_compose_video(
        source_path: Path, overlay_path: Path, output_path: Path, *, plan, attached_pic_stream_index
    ) -> None:
        captured_plan["plan"] = plan
        captured_plan["attached_pic_stream_index"] = attached_pic_stream_index

    monkeypatch.setattr("race_overlay.pipeline.compose_video", fake_compose_video)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert captured_plan["plan"].video_codec == "libx265"
    assert captured_plan["plan"].pixel_format == "yuv420p10le"
    assert captured_plan["plan"].video_bitrate == 4_000_000
    assert captured_plan["plan"].audio_args == ("-c:a", "aac", "-b:a", "128000")
    assert captured_plan["attached_pic_stream_index"] == 4
    assert any("falling back to cache" in message for message in messages)


def test_run_pipeline_does_not_fall_back_when_streaming_setup_fails(tmp_path: Path, monkeypatch) -> None:
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
        lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("ffmpeg")),
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.build_overlay_video",
        lambda *args, **kwargs: fallback_called.__setitem__("value", True),
    )
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    with pytest.raises(FatalStreamingComposeError, match="ffmpeg streaming setup failed: ffmpeg"):
        run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is False
    assert all("falling back to cache" not in message for message in messages)


def test_run_pipeline_does_not_fall_back_when_stream_process_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
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
        lambda **kwargs: FakeStreamingProcess([], returncode=1),
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.build_overlay_video",
        lambda *args, **kwargs: fallback_called.__setitem__("value", True),
    )
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    with pytest.raises(FatalStreamingComposeError, match="non-zero status 1"):
        run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is False
    assert all("falling back to cache" not in message for message in messages)


def test_run_pipeline_cleans_up_stream_process_before_cache_fallback(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    fallback_called = {"value": False}
    process = FakeStreamingProcess([], returncode=None, write_error=BrokenPipeError("broken pipe"))

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: process,
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.build_overlay_video",
        lambda *args, **kwargs: fallback_called.__setitem__("value", True),
    )
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is True
    assert process.stdin.closed is True
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls >= 1
    assert any("falling back to cache" in message for message in messages)


def test_run_pipeline_does_not_fall_back_for_render_oserror(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    messages: list[str] = []
    fallback_called = {"value": False}
    process = FakeStreamingProcess([], returncode=None)

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: (_ for _ in ()).throw(OSError("hud asset missing")),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: process,
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.build_overlay_video",
        lambda *args, **kwargs: fallback_called.__setitem__("value", True),
    )
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    with pytest.raises(OSError, match="hud asset missing"):
        run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is False
    assert process.stdin.closed is True
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls >= 1
    assert all("Streaming unavailable" not in message for message in messages)


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


def test_run_pipeline_skipped_outside_clips_do_not_enter_render_path(tmp_path: Path, monkeypatch) -> None:
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

    def fail_if_called(*args, **kwargs) -> None:
        raise AssertionError("skipped clips must not enter any render path")

    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", fail_if_called)
    monkeypatch.setattr("race_overlay.pipeline.open_stream_compose_process", fail_if_called, raising=False)
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", fail_if_called)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", fail_if_called)

    config = load_config(config_path)
    config.timeline.outside_activity = "skip"
    save_config(config_path, config)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert any("Skipping clip.MP4" in message and "outside activity" in message for message in messages)
    assert all("Encoding plan:" not in message for message in messages)
    assert all("Render path:" not in message for message in messages)


def test_editor_saved_hud_config_round_trips_through_pipeline(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Kasumigaura"
    save_editor_payload(config_path, payload)
    (tmp_path / "clip.MP4").write_bytes(b"")

    captured: list[str] = []
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: captured.append(kwargs["hud_config"].theme.note_text)
        or Image.new("RGBA", (1280, 720), (0, 0, 0, 0)),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess([]),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4")

    assert captured == ["Kasumigaura"]


def test_run_pipeline_passes_lap_state_to_renderer(tmp_path: Path, monkeypatch) -> None:
    """render_hud_frame must receive widget-scoped lap_states computed from activity laps."""
    config_path = tmp_path / "overlay.yaml"
    lap_hud = HudConfig(
        preset="lap-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="lap-table",
                type="lap_waterfall",
                bindings={"value": "laps"},
                anchor="top-left",
                x=24,
                y=320,
                width=420,
                height=180,
                style={"visible_rows": 1, "always_show": True},
            )
        ],
    )
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=lap_hud))

    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    activity_with_laps = ActivityTrack(
        sport="running",
        samples=[
            ActivitySample(start, 36.0832, 140.2106, 5.0, 0.0, 3.5, 150, 176),
            ActivitySample(start + timedelta(seconds=10), 36.0834, 140.2108, 5.2, 35.0, 3.6, 152, 178),
        ],
        laps=[
            ActivityLap(
                start_time=start - timedelta(seconds=300),
                total_time_seconds=300.0,
                distance_m=1000.0,
                avg_heart_rate_bpm=None,
                max_heart_rate_bpm=None,
                max_speed_mps=None,
                elevation_delta_m=None,
                calories=None,
            )
        ],
    )

    captured_kwargs: list[dict] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: activity_with_laps)
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: captured_kwargs.append(kwargs) or Image.new("RGBA", (1280, 720), (0, 0, 0, 0)),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess([]),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4")

    assert captured_kwargs, "render_hud_frame was not called"
    kwargs = captured_kwargs[0]
    assert "lap_states" in kwargs, "lap_states kwarg was not passed to render_hud_frame"
    assert isinstance(kwargs["lap_states"], dict)
    assert isinstance(kwargs["lap_states"]["lap-table"], LapWaterfallState)
    assert len(kwargs["lap_states"]["lap-table"].visible_rows) == 1


# ── Render Context ───────────────────────────────────────────────────────────


def test_create_render_context_includes_visible_widgets() -> None:
    """Test that render context filters visible widgets."""
    from dataclasses import replace
    from race_overlay.pipeline import create_render_context
    from race_overlay.hud_schema import HudWidgetConfig
    
    config = broadcast_runner_preset()
    # Make one widget invisible
    modified_widgets = [
        widget if widget.id != "pace" else replace(widget, visible=False)
        for widget in config.widgets
    ]
    config = replace(config, widgets=modified_widgets)
    
    activity = fake_activity()
    context = create_render_context(config, activity.samples, route_points=[], frame_width=1280, frame_height=720)
    
    assert context.hud_config == config
    assert all(w.id != "pace" for w in context.visible_widgets)
    assert all(w.visible for w in context.visible_widgets)
    assert [widget.z_index for widget in context.visible_widgets] == sorted(widget.z_index for widget in context.visible_widgets)


def test_create_render_context_includes_sample_cursor() -> None:
    """Test that render context includes a sample cursor."""
    from race_overlay.pipeline import create_render_context
    from race_overlay.sampling import SampleCursor
    
    config = broadcast_runner_preset()
    activity = fake_activity()
    context = create_render_context(config, activity.samples, route_points=[], frame_width=1280, frame_height=720)
    
    assert isinstance(context.sample_cursor, SampleCursor)
    assert context.sample_cursor.samples is activity.samples


def test_create_render_context_validates_hud_config() -> None:
    """Render context should validate HUD config up front."""
    from dataclasses import replace
    from race_overlay.pipeline import create_render_context

    config = broadcast_runner_preset()
    duplicate = replace(config.widgets[0], id=config.widgets[1].id)
    invalid_config = replace(config, widgets=[duplicate, *config.widgets[1:]])

    with pytest.raises(ValueError, match="duplicate HUD widget id"):
        create_render_context(invalid_config, fake_activity().samples, route_points=[], frame_width=1280, frame_height=720)


def test_create_render_context_primes_route_map_cache() -> None:
    """Render context should prime clip-static route-map cache."""
    from race_overlay import hud as hud_module
    from race_overlay.pipeline import create_render_context

    config = broadcast_runner_preset()
    activity = fake_activity()
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]

    hud_module._clear_route_map_cache()
    context = create_render_context(config, activity.samples, route_points=route_points, frame_width=1280, frame_height=720)

    assert context.route_map_cache_keys
    assert set(context.route_map_cache_keys.values()).issubset(set(hud_module._get_route_map_cache().keys()))


def test_render_overlay_frame_uses_prevalidated_context_without_runtime_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frame rendering should not revalidate HUD config after context creation."""
    from race_overlay.pipeline import _render_overlay_frame, create_render_context

    activity = fake_activity()
    clip = fake_clip(Path("clip.MP4"))
    alignment = fake_alignment()
    config = broadcast_runner_preset()
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    context = create_render_context(
        config,
        activity.samples,
        route_points=route_points,
        frame_width=clip.width,
        frame_height=clip.height,
        total_distance_m=35.0,
    )

    def fail_validate(*args, **kwargs):
        raise AssertionError("validate_hud_config should not run during frame rendering")

    monkeypatch.setattr("race_overlay.hud.validate_hud_config", fail_validate)

    image = _render_overlay_frame(
        activity=activity,
        clip=clip,
        alignment=alignment,
        index=0,
        context=context,
    )

    assert image.size == (clip.width, clip.height)


def test_render_overlay_frame_reuses_precomputed_route_map_cache_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepared frame rendering should not recompute route-map cache keys."""
    from race_overlay.pipeline import _render_overlay_frame, create_render_context

    activity = fake_activity()
    clip = fake_clip(Path("clip.MP4"))
    alignment = fake_alignment()
    config = broadcast_runner_preset()
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    context = create_render_context(
        config,
        activity.samples,
        route_points=route_points,
        frame_width=clip.width,
        frame_height=clip.height,
        total_distance_m=35.0,
    )

    def fail_cache_key(*args, **kwargs):
        raise AssertionError("route-map cache key should not be recomputed during frame rendering")

    monkeypatch.setattr("race_overlay.hud._route_map_cache_key", fail_cache_key)

    image = _render_overlay_frame(
        activity=activity,
        clip=clip,
        alignment=alignment,
        index=0,
        context=context,
    )

    assert image.size == (clip.width, clip.height)


def test_compose_preview_frame_alpha_composites_overlay_over_source() -> None:
    from race_overlay.pipeline import _compose_preview_frame

    source = Image.new("RGB", (2, 1), (10, 20, 30))
    overlay = Image.new("RGBA", (2, 1), (210, 120, 60, 128))

    composed = _compose_preview_frame(source_frame=source, overlay_frame=overlay)

    assert composed.mode == "RGBA"
    assert composed.size == (2, 1)
    assert composed.getpixel((0, 0)) == (110, 70, 45, 255)


def test_run_pipeline_skips_preview_work_when_preview_is_disabled(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    writes: list[bytes] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: fake_clip(path, duration_seconds=2.0, fps=30.0),
    )
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (0, 0, 0, 0)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "race_overlay.pipeline.extract_video_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview extraction should stay disabled")),
        raising=False,
    )

    run_pipeline(config_path, only="clip.MP4")

    assert writes


def test_run_pipeline_allows_preview_after_mid_bucket_enable(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    writes: list[bytes] = []
    preview_updates = []
    extracted_timestamps: list[float] = []
    preview_enabled = {"value": False}

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: fake_clip(path, duration_seconds=0.1, fps=30.0),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.align_clip",
        lambda *args, **kwargs: ClipAlignment(
            clip=fake_clip(tmp_path / "clip.MP4", duration_seconds=0.1, fps=30.0),
            status="inside",
            clip_start=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
            clip_end=datetime(2026, 4, 19, 9, 0, 0, 100000, tzinfo=timezone.utc),
            overlay_start=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
            overlay_end=datetime(2026, 4, 19, 9, 0, 0, 100000, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr("race_overlay.pipeline.render_hud_frame", lambda **kwargs: Image.new("RGBA", (1280, 720), (200, 50, 25, 128)))
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    def fake_extract_video_frame(source_path: Path, *, timestamp_seconds: float) -> Image.Image:
        extracted_timestamps.append(timestamp_seconds)
        return Image.new("RGB", (1280, 720), (25, 50, 200))

    def preview_update(payload) -> bool:
        preview_updates.append(payload)
        if payload is None and not preview_enabled["value"]:
            preview_enabled["value"] = True
            return False
        return True

    monkeypatch.setattr("race_overlay.pipeline.extract_video_frame", fake_extract_video_frame, raising=False)

    run_pipeline(config_path, only="clip.MP4", preview_update=preview_update)

    assert writes
    assert preview_updates[0] is None
    assert preview_updates[1] is None
    assert len([payload for payload in preview_updates if payload is not None]) == 1
    assert [round(update.frame_time_seconds, 3) for update in preview_updates if update is not None] == [0.033]
    assert [round(timestamp, 3) for timestamp in extracted_timestamps] == [0.033]


def test_run_pipeline_emits_throttled_preview_updates_when_enabled(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    writes: list[bytes] = []
    preview_updates = []
    extracted_timestamps: list[float] = []

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: fake_clip(path, duration_seconds=2.0, fps=30.0),
    )
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: Image.new("RGBA", (1280, 720), (200, 50, 25, 128)),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    def fake_extract_video_frame(source_path: Path, *, timestamp_seconds: float) -> Image.Image:
        extracted_timestamps.append(timestamp_seconds)
        return Image.new("RGB", (1280, 720), (25, 50, 200))

    def preview_update(payload) -> bool:
        if payload is None:
            return True
        preview_updates.append(payload)
        return True

    monkeypatch.setattr("race_overlay.pipeline.extract_video_frame", fake_extract_video_frame, raising=False)

    run_pipeline(config_path, only="clip.MP4", preview_update=preview_update)

    assert writes
    assert [update.frame_index for update in preview_updates] == [1, 31]
    assert [round(update.frame_time_seconds, 3) for update in preview_updates] == [0.0, 1.0]
    assert [round(timestamp, 3) for timestamp in extracted_timestamps] == [0.0, 1.0]
    assert all(update.clip_name == "clip.MP4" for update in preview_updates)
    assert all(update.image_bytes.startswith(b"\x89PNG\r\n\x1a\n") for update in preview_updates)


def test_run_pipeline_continues_when_preview_extraction_fails(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    writes: list[bytes] = []
    preview_probes: list[object | None] = []
    messages: list[str] = []

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr(
        "race_overlay.pipeline.probe_video",
        lambda path: fake_clip(path, duration_seconds=2.0, fps=30.0),
    )
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: Image.new("RGBA", (1280, 720), (200, 50, 25, 128)),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess(writes),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "race_overlay.pipeline.extract_video_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("preview extraction failed")),
        raising=False,
    )

    def preview_update(payload) -> bool:
        preview_probes.append(payload)
        return True

    run_pipeline(config_path, only="clip.MP4", progress=messages.append, preview_update=preview_update)

    assert writes
    assert preview_probes == [None, None]
    assert any("Preview unavailable for clip.MP4" in message for message in messages)


def test_preview_bucket_uses_single_bucket_for_non_positive_fps() -> None:
    from race_overlay.pipeline import _preview_bucket

    assert _preview_bucket(index=0, fps=0.0) == 0
    assert _preview_bucket(index=30, fps=0.0) == 0
    assert _preview_bucket(index=30, fps=-24.0) == 0


def test_run_pipeline_skipped_outside_clips_do_not_emit_preview_updates(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    preview_updates = []
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
    monkeypatch.setattr(
        "race_overlay.pipeline.extract_video_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("skipped clips must not extract preview frames")),
        raising=False,
    )

    config = load_config(config_path)
    config.timeline.outside_activity = "skip"
    save_config(config_path, config)

    run_pipeline(config_path, only="clip.MP4", preview_update=lambda payload: preview_updates.append(payload) or True)

    assert preview_updates == []


def test_run_pipeline_cancel_before_render_does_not_emit_preview_updates(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    preview_updates = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path, duration_seconds=2.0, fps=30.0))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: FakeStreamingProcess([], returncode=None),
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.extract_video_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("canceled renders must not extract preview frames")),
        raising=False,
    )

    with pytest.raises(RenderJobCanceledError, match="render canceled"):
        run_pipeline(
            config_path,
            only="clip.MP4",
            preview_update=lambda payload: preview_updates.append(payload) or True,
            cancel_requested=lambda: True,
        )

    assert preview_updates == []


def test_run_pipeline_render_failure_does_not_emit_preview_updates(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    preview_updates = []
    process = FakeStreamingProcess([], returncode=None)

    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: (_ for _ in ()).throw(OSError("hud asset missing")),
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.open_stream_compose_process",
        lambda **kwargs: process,
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.extract_video_frame",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("failed renders must not extract preview frames")),
        raising=False,
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    with pytest.raises(OSError, match="hud asset missing"):
        run_pipeline(
            config_path,
            only="clip.MP4",
            preview_update=lambda payload: preview_updates.append(payload) or True,
        )

    assert preview_updates == []
