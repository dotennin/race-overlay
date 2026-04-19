from pathlib import Path

import yaml
from typer.testing import CliRunner

from race_overlay.cli import app


def test_init_writes_default_overlay_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init", "--activity-file", "activity_22577902433.tcx"])

    config_path = tmp_path / "overlay.yaml"
    assert result.exit_code == 0
    assert config_path.exists()

    payload = yaml.safe_load(config_path.read_text())
    assert payload["activity_file"] == "activity_22577902433.tcx"
    assert payload["video_globs"] == ["*.MP4", "*.mov"]
    assert payload["timeline"]["global_offset_seconds"] == 0.0
    assert payload["timeline"]["outside_activity"] == "no_data"
    assert payload["hud"]["fields"]["pace"] is True
    assert payload["hud"]["fields"]["mini_map"] is True
