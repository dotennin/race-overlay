from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import build_editor_state, save_editor_payload
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import HudConfig, serialize_hud_config
from race_overlay.models import ActivitySample, ActivityTrack, ClipAlignment, HudSample, VideoClip
from race_overlay.pipeline import run_pipeline


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


def fake_clip(path: Path) -> VideoClip:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    return VideoClip(path=path, creation_time=start, duration_seconds=1.0, width=1280, height=720, fps=1.0)


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
    def __init__(self, writes: list[bytes]) -> None:
        self._writes = writes

    def write(self, data: bytes) -> int:
        self._writes.append(data)
        return len(data)

    def close(self) -> None:
        return None


class FakeStreamingProcess:
    def __init__(self, writes: list[bytes], *, returncode: int = 0) -> None:
        self.stdin = FakeStreamingPipe(writes)
        self.returncode = returncode

    def wait(self) -> int:
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
        raising=False,
    )
    monkeypatch.setattr(
        "race_overlay.pipeline.build_overlay_video",
        lambda *args, **kwargs: fallback_called.__setitem__("value", True),
    )
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is True
    assert any("falling back to cache" in message for message in messages)


def test_run_pipeline_falls_back_to_cache_when_stream_process_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
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

    run_pipeline(config_path, only="clip.MP4", progress=messages.append)

    assert fallback_called["value"] is True
    assert any("falling back to cache" in message for message in messages)


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
