from pathlib import Path

from typer.testing import CliRunner

import pytest
import yaml

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, save_config
from race_overlay.hud_presets import broadcast_runner_preset


def test_cli_shows_top_level_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "render" in result.stdout


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
