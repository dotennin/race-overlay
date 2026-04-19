from pathlib import Path
import copy

import yaml
from typer.testing import CliRunner

from race_overlay.cli import app
from race_overlay.config import ProjectConfig, load_config, save_config, write_default_config


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
    assert payload["hud"]["preset"] == "broadcast-runner"
    assert payload["hud"]["theme"]["note_text"] == "Race Day"
    assert any(widget["id"] == "distance-progress" for widget in payload["hud"]["widgets"])


def test_load_config_maps_legacy_fields_to_default_widget_visibility(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": {
                    "fields": {
                        "pace": True,
                        "elapsed": True,
                        "distance": True,
                        "speed": True,
                        "heart_rate": True,
                        "cadence": True,
                        "mini_map": False,
                    }
                },
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    visibility = {widget.id: widget.visible for widget in config.hud.widgets}

    assert config.hud.preset == "broadcast-runner"
    assert visibility["hero-pace"] is True
    assert visibility["route-map"] is False
    assert visibility["metric-heart-rate"] is True


def test_write_default_config_includes_broadcast_runner_schema(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"

    write_default_config(path, "activity_22577902433.tcx")

    payload = yaml.safe_load(path.read_text())
    assert payload["hud"]["preset"] == "broadcast-runner"
    assert payload["hud"]["theme"]["note_text"] == "Race Day"
    assert any(widget["id"] == "distance-progress" for widget in payload["hud"]["widgets"])


def test_resolve_override_prefers_per_video_values() -> None:
    from race_overlay.config import ProjectConfig, resolve_override

    config = ProjectConfig(
        activity_file="activity_22577902433.tcx",
        overrides={"DJI_20260419090559_0002_D.MP4": {"offset_seconds": 1.5, "outside_activity": "skip"}},
    )
    override = resolve_override(config, "DJI_20260419090559_0002_D.MP4")
    assert override.offset_seconds == 1.5
    assert override.outside_activity == "skip"


def test_save_config_uses_hud_serializer_boundary(tmp_path: Path, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("deepcopy should not be used for config serialization")

    monkeypatch.setattr(copy, "deepcopy", boom)

    path = tmp_path / "overlay.yaml"
    config = ProjectConfig(activity_file="activity_22577902433.tcx")

    save_config(path, config)

    payload = yaml.safe_load(path.read_text())
    assert payload["hud"]["preset"] == "broadcast-runner"


def test_project_config_defaults_to_broadcast_runner_hud() -> None:
    config = ProjectConfig(activity_file="activity_22577902433.tcx")

    assert config.hud.preset == "broadcast-runner"
    assert any(widget.id == "distance-progress" for widget in config.hud.widgets)
