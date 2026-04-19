from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, save_config
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import HudConfig
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

    def fake_run_pipeline(config_path: Path, only: str | None) -> None:
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
        distance_m=12.0,
        speed_mps=3.5,
        pace_seconds_per_km=285.7,
        heart_rate_bpm=150,
        cadence_spm=176,
    )


def test_run_pipeline_passes_loaded_hud_config_to_renderer(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    render_calls: list[HudConfig] = []
    monkeypatch.setattr("race_overlay.pipeline._discover_videos", lambda patterns: [tmp_path / "clip.MP4"])
    monkeypatch.setattr("race_overlay.pipeline.load_activity", lambda path: fake_activity())
    monkeypatch.setattr("race_overlay.pipeline.probe_video", lambda path: fake_clip(path))
    monkeypatch.setattr("race_overlay.pipeline.align_clip", lambda *args, **kwargs: fake_alignment())
    monkeypatch.setattr("race_overlay.pipeline.sample_at", lambda *args, **kwargs: fake_hud_sample())
    monkeypatch.setattr(
        "race_overlay.pipeline.render_hud_frame",
        lambda **kwargs: render_calls.append(kwargs["hud_config"]) or Image.new("RGBA", (1280, 720), (0, 0, 0, 0)),
    )
    monkeypatch.setattr("race_overlay.pipeline.build_overlay_video", lambda *args, **kwargs: None)
    monkeypatch.setattr("race_overlay.pipeline.compose_video", lambda *args, **kwargs: None)

    run_pipeline(config_path, only="clip.MP4")

    assert render_calls[0].preset == "broadcast-runner"
    assert render_calls[0].widgets[0].id == "route-map"
