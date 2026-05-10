from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

import pytest
import yaml

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, save_config, write_default_config
from race_overlay.models import ActivitySample, ActivityTrack
from race_overlay.hud_presets import broadcast_runner_preset


def test_cli_shows_top_level_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "render" in result.stdout


def test_cli_shows_benchmark_render_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "benchmark-render" in result.stdout


def test_cli_shows_edit_hud_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "edit-hud" in result.stdout


def test_edit_hud_rejects_missing_config_path(tmp_path) -> None:
    result = CliRunner().invoke(app, ["edit-hud", "--config-path", str(tmp_path / "missing.yaml")])

    assert result.exit_code != 0
    assert "HUD editor available at" not in result.stdout


def test_init_rewrites_relative_paths_for_nested_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    config_path = Path("configs/overlay.yaml")
    config_path.parent.mkdir()

    result = runner.invoke(
        app,
        ["init", "--config-path", str(config_path), "--activity-file", "activity.tcx"],
    )

    assert result.exit_code == 0
    assert config_path.exists()

    payload = yaml.safe_load(config_path.read_text())
    assert payload["activity_file"] == "../activity.tcx"
    assert payload["video_globs"] == ["../*.MP4", "../*.mov"]


def test_edit_hud_rejects_directory_config_path(tmp_path) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.mkdir()

    result = CliRunner().invoke(app, ["edit-hud", "--config-path", str(config_path)])

    assert result.exit_code != 0
    assert "HUD editor available at" not in result.stdout
    assert "config file" in result.output


def test_edit_hud_rejects_unreadable_config_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    original_read_text = type(config_path).read_text

    def reject_read(path, *args, **kwargs) -> str:
        if path == config_path:
            raise PermissionError("permission denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(config_path), "read_text", reject_read)

    result = CliRunner().invoke(app, ["edit-hud", "--config-path", str(config_path)])

    assert result.exit_code != 0
    assert "HUD editor available at" not in result.stdout
    assert "permission denied" in result.output


@pytest.mark.parametrize("width,height", [(0, 720), (1280, 0), (-1, 720), (1280, -1)])
def test_edit_hud_rejects_non_positive_preview_dimensions(width: int, height: int) -> None:
    result = CliRunner().invoke(app, ["edit-hud", "--width", str(width), "--height", str(height)])

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output


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

    def fake_run_pipeline(config_path: Path, only: str | None, *, progress=None) -> None:
        progress("Generating frame cache at cache/clip/frames")
        progress("Finished clip.MP4")

    monkeypatch.setattr("race_overlay.cli.run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(app, ["render", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert "Generating frame cache at cache/clip/frames" in result.stdout
    assert "Finished clip.MP4" in result.stdout
    assert "Render completed" in result.stdout


def test_init_writes_default_overlay_without_removed_theme_colors(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    write_default_config(config_path, "activity_22577902433.tcx")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    route_map = next(widget for widget in payload["hud"]["widgets"] if widget["id"] == "route-map")

    assert "panel_rgba" not in payload["hud"]["theme"]
    assert "accent_rgba" not in payload["hud"]["theme"]
    assert route_map["style"]["background_rgba"] == [6, 10, 18, 148]


def test_benchmark_render_outputs_multi_variant_comparison(tmp_path: Path) -> None:
    """Benchmark command should output baseline and variant comparisons."""
    from race_overlay.hud_schema import HudConfig, HudWidgetConfig
    import shutil
    
    config_path = tmp_path / "overlay.yaml"
    activity_src = next(
        parent / "activity_22577902433.tcx"
        for parent in Path(__file__).resolve().parents
        if (parent / "activity_22577902433.tcx").exists()
    )
    activity_path = tmp_path / "activity.tcx"
    
    # Copy existing activity file
    shutil.copy(activity_src, activity_path)
    
    save_config(
        config_path,
        ProjectConfig(
            activity_file=activity_path.name,
            hud=HudConfig(
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=0,
                        y=0,
                        width=200,
                        height=200,
                        visible=True,
                    ),
                    HudWidgetConfig(
                        id="lap-waterfall",
                        type="lap_waterfall",
                        bindings={"value": "laps"},
                        anchor="bottom-left",
                        x=0,
                        y=0,
                        width=300,
                        height=150,
                        visible=True,
                    ),
                ]
            ),
        ),
    )
    
    result = CliRunner().invoke(
        app,
        ["benchmark-render", "--config-path", str(config_path), "--num-frames", "10"],
    )
    
    assert result.exit_code == 0
    # Should show baseline
    assert "baseline" in result.stdout.lower()
    # Should show at least one variant
    assert "no-route-map" in result.stdout.lower() or "no-lap-waterfall" in result.stdout.lower()
    # Should show comparison percentages
    assert "%" in result.stdout


def test_benchmark_render_profile_outputs_cumulative_stats(tmp_path: Path) -> None:
    from race_overlay.hud_schema import HudConfig
    import shutil

    config_path = tmp_path / "overlay.yaml"
    activity_src = next(
        parent / "activity_22577902433.tcx"
        for parent in Path(__file__).resolve().parents
        if (parent / "activity_22577902433.tcx").exists()
    )
    activity_path = tmp_path / "activity.tcx"
    shutil.copy(activity_src, activity_path)
    save_config(
        config_path,
        ProjectConfig(
            activity_file=activity_path.name,
            hud=HudConfig(widgets=[]),
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "benchmark-render",
            "--config-path",
            str(config_path),
            "--num-frames",
            "10",
            "--profile",
            "--path",
            "prepared",
        ],
    )

    assert result.exit_code == 0
    assert "function calls" in result.stdout
    assert "Ordered by: cumulative time" in result.stdout


def test_benchmark_render_rejects_single_sample_activity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from race_overlay.hud_schema import HudConfig, HudWidgetConfig

    config_path = tmp_path / "overlay.yaml"
    activity_path = tmp_path / "activity.tcx"
    activity_path.write_text("<TrainingCenterDatabase/>", encoding="utf-8")
    save_config(
        config_path,
        ProjectConfig(
            activity_file=activity_path.name,
            hud=HudConfig(
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=0,
                        y=0,
                        width=200,
                        height=200,
                        visible=True,
                    ),
                ]
            ),
        ),
    )
    monkeypatch.setattr(
        "race_overlay.cli.load_activity",
        lambda path: ActivityTrack(
            sport="Running",
            samples=[
                ActivitySample(
                    datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
                    36.0,
                    140.0,
                    10.0,
                    0.0,
                    4.0,
                    120,
                    90,
                )
            ],
        ),
    )

    result = CliRunner().invoke(
        app,
        ["benchmark-render", "--config-path", str(config_path), "--num-frames", "10"],
    )

    assert result.exit_code != 0
    assert "at least 2 samples" in result.output.lower()
