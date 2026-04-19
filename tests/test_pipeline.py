from pathlib import Path

from typer.testing import CliRunner

from race_overlay.cli import app


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
