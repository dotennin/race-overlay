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


def test_edit_hud_rejects_missing_config_path(tmp_path) -> None:
    result = CliRunner().invoke(app, ["edit-hud", "--config-path", str(tmp_path / "missing.yaml")])

    assert result.exit_code != 0
    assert "HUD editor available at" not in result.stdout
