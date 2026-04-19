from typer.testing import CliRunner

import pytest

from race_overlay.cli import app


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


@pytest.mark.parametrize("width,height", [(0, 720), (1280, 0), (-1, 720), (1280, -1)])
def test_edit_hud_rejects_non_positive_preview_dimensions(width: int, height: int) -> None:
    result = CliRunner().invoke(app, ["edit-hud", "--width", str(width), "--height", str(height)])

    assert result.exit_code != 0
    assert "must be greater than 0" in result.output
