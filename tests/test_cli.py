from typer.testing import CliRunner

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
