from pathlib import Path
import copy

import pytest
import yaml
from typer.testing import CliRunner

from race_overlay.cli import app
from race_overlay.config import (
    ProjectConfig,
    load_config,
    resolve_path_from_config,
    resolve_video_globs_from_config,
    save_config,
    write_default_config,
)
from race_overlay.hud_presets import _legacy_broadcast_runner_preset, broadcast_runner_preset
from race_overlay.hud_schema import serialize_hud_config


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
    assert any(widget["id"] == "distance-ruler" for widget in payload["hud"]["widgets"])


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
    assert visibility["time-chip"] is True
    assert visibility["pace-chip"] is True
    assert visibility["route-map"] is False
    assert visibility["heart-rate-stat"] is True


def test_load_config_legacy_only_fields_disable_context_card(tmp_path: Path) -> None:
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
                        "pace": False,
                        "elapsed": False,
                        "distance": False,
                        "speed": False,
                        "heart_rate": False,
                        "cadence": False,
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
    assert visibility["elevation-stat"] is False
    assert visibility["distance-ruler"] is False
    assert visibility["distance-stat"] is False
    assert visibility["time-chip"] is False
    assert visibility["heart-rate-stat"] is False
    assert visibility["pace-chip"] is False
    assert visibility["cadence-chip"] is False
    assert visibility["elapsed-chip"] is False
    assert visibility["speed-chip"] is False
    assert visibility["route-map"] is False


def test_load_config_prefers_schema_widgets_when_legacy_fields_are_also_present(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    schema_hud = broadcast_runner_preset()
    schema_hud.theme.note_text = "Custom schema HUD"
    route_map = next(widget for widget in schema_hud.widgets if widget.id == "route-map")
    pace_chip = next(widget for widget in schema_hud.widgets if widget.id == "pace-chip")
    route_map.visible = True
    pace_chip.visible = False
    pace_chip.x = 944
    schema_payload = serialize_hud_config(schema_hud)
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
                    },
                    **schema_payload,
                },
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    route_map_loaded = next(widget for widget in config.hud.widgets if widget.id == "route-map")
    pace_chip_loaded = next(widget for widget in config.hud.widgets if widget.id == "pace-chip")

    assert config.hud.theme.note_text == "Custom schema HUD"
    assert route_map_loaded.visible is True
    assert pace_chip_loaded.visible is False
    assert pace_chip_loaded.x == 944


def test_load_config_migrates_legacy_broadcast_runner_schema_defaults(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    legacy_payload = serialize_hud_config(_legacy_broadcast_runner_preset())
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": legacy_payload,
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    widget_ids = [widget.id for widget in config.hud.widgets]
    time_chip = next(widget for widget in config.hud.widgets if widget.id == "time-chip")
    route_map = next(widget for widget in config.hud.widgets if widget.id == "route-map")
    elevation = next(widget for widget in config.hud.widgets if widget.id == "elevation-stat")

    assert "time-chip" in widget_ids
    assert config.hud.theme.title_font_size_px == 16
    assert config.hud.theme.unit_font_size_px == 13
    assert config.hud.theme.value_font_family == "broadcast_value"
    assert time_chip.style["variant"] == "timestamp_chip"
    assert route_map.style["show_north_marker"] is True
    assert route_map.style["show_bearing_label"] is True
    assert route_map.style["show_heading_arrow"] is True
    assert route_map.x == 21
    assert route_map.y == 488
    assert elevation.y == 122


def test_load_config_preserves_customized_broadcast_runner_geometry_and_legacy_theme(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    legacy_hud = _legacy_broadcast_runner_preset()
    legacy_hud.theme.font_family = "mono"
    legacy_hud.theme.font_size_px = 24
    pace_chip = next(widget for widget in legacy_hud.widgets if widget.id == "pace-chip")
    pace_chip.x = 990
    pace_chip.z_index = 999
    route_map = next(widget for widget in legacy_hud.widgets if widget.id == "route-map")
    route_map.style["shape"] = "rect"
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": serialize_hud_config(legacy_hud),
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    loaded_pace_chip = next(widget for widget in config.hud.widgets if widget.id == "pace-chip")
    loaded_route_map = next(widget for widget in config.hud.widgets if widget.id == "route-map")

    assert config.hud.theme.font_family == "mono"
    assert config.hud.theme.font_size_px == 24
    assert config.hud.theme.title_font_family is None
    assert config.hud.theme.value_font_size_px is None
    assert loaded_pace_chip.x == 990
    assert loaded_pace_chip.z_index == 999
    assert loaded_route_map.style["shape"] == "rect"
    assert loaded_route_map.style["show_north_marker"] is True


def test_load_config_only_backfills_broadcast_runner_defaults_for_explicit_legacy_values(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    legacy_hud = _legacy_broadcast_runner_preset()
    legacy_theme = _legacy_broadcast_runner_preset().theme
    legacy_hud.theme.title_font_family = "mono"
    legacy_hud.theme.title_font_weight = "bold"
    legacy_hud.theme.title_font_size_px = 22
    legacy_hud.theme.value_font_family = legacy_theme.font_family
    legacy_hud.theme.value_font_weight = legacy_theme.font_weight
    legacy_hud.theme.value_font_size_px = legacy_theme.font_size_px
    legacy_hud.theme.unit_font_family = "serif"
    legacy_hud.theme.unit_font_weight = "bold"
    legacy_hud.theme.unit_font_size_px = 11
    distance_ruler = next(widget for widget in legacy_hud.widgets if widget.id == "distance-ruler")
    distance_ruler.style["fill_rgba"] = [200, 10, 20, 255]
    route_map = next(widget for widget in legacy_hud.widgets if widget.id == "route-map")
    route_map.x = 96
    route_map.width = 244
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": serialize_hud_config(legacy_hud),
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    loaded_ruler = next(widget for widget in config.hud.widgets if widget.id == "distance-ruler")
    loaded_route_map = next(widget for widget in config.hud.widgets if widget.id == "route-map")

    assert config.hud.theme.title_font_family == "mono"
    assert config.hud.theme.title_font_weight == "bold"
    assert config.hud.theme.title_font_size_px == 22
    assert config.hud.theme.value_font_family == "broadcast_value"
    assert config.hud.theme.value_font_weight == "bold"
    assert config.hud.theme.value_font_size_px == 32
    assert config.hud.theme.unit_font_family == "serif"
    assert config.hud.theme.unit_font_weight == "bold"
    assert config.hud.theme.unit_font_size_px == 11
    assert loaded_ruler.style["fill_rgba"] == [200, 10, 20, 255]
    assert loaded_ruler.style["rail_rgba"] == [8, 12, 20, 220]
    assert loaded_route_map.x == 96
    assert loaded_route_map.width == 244
    assert loaded_route_map.style["show_north_marker"] is True


def test_load_config_does_not_reintroduce_removed_legacy_widgets(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    legacy_hud = _legacy_broadcast_runner_preset()
    legacy_hud.widgets = [widget for widget in legacy_hud.widgets if widget.id not in {"route-map", "pace-chip"}]
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": serialize_hud_config(legacy_hud),
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    config = load_config(path)
    widget_ids = [widget.id for widget in config.hud.widgets]

    assert "time-chip" in widget_ids
    assert "route-map" not in widget_ids
    assert "pace-chip" not in widget_ids


def test_load_config_rejects_duplicate_widget_ids(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"
    hud_payload = serialize_hud_config(broadcast_runner_preset())
    duplicated_widget = dict(hud_payload["widgets"][0])
    duplicated_widget["bindings"] = dict(duplicated_widget["bindings"])
    duplicated_widget["style"] = dict(duplicated_widget["style"])
    hud_payload["widgets"].append(duplicated_widget)
    path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": hud_payload,
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    with pytest.raises(ValueError, match="duplicate HUD widget id"):
        load_config(path)


def test_write_default_config_includes_broadcast_runner_schema(tmp_path: Path) -> None:
    path = tmp_path / "overlay.yaml"

    write_default_config(path, "activity_22577902433.tcx")

    payload = yaml.safe_load(path.read_text())
    assert payload["hud"]["preset"] == "broadcast-runner"
    assert payload["hud"]["theme"]["note_text"] == "Race Day"
    assert any(widget["id"] == "distance-ruler" for widget in payload["hud"]["widgets"])


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


def test_save_config_is_atomic_when_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "overlay.yaml"
    original = ProjectConfig(activity_file="activity_22577902433.tcx")
    save_config(path, original)
    original_text = path.read_text()

    updated = ProjectConfig(activity_file="activity_22577902433.tcx")
    updated.hud.theme.note_text = "Kasumigaura"

    def fail_after_partial_write(target: Path, data: str, *args, **kwargs) -> int:
        with target.open("w", encoding=kwargs.get("encoding", "utf-8")) as handle:
            handle.write("hud:\n  theme:\n")
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail_after_partial_write)

    with pytest.raises(OSError, match="disk full"):
        save_config(path, updated)

    assert path.read_text() == original_text
    assert load_config(path).hud.theme.note_text == "Race Day"


def test_project_config_defaults_to_broadcast_runner_hud() -> None:
    config = ProjectConfig(activity_file="activity_22577902433.tcx")

    assert config.hud.preset == "broadcast-runner"
    assert any(widget.id == "distance-ruler" for widget in config.hud.widgets)


def test_load_config_rejects_non_finite_style_values(tmp_path: Path) -> None:
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
                    "preset": "broadcast-runner",
                    "theme": {
                        "panel_rgba": [12, 18, 28, 168],
                        "accent_rgba": [255, 196, 92, 255],
                        "text_rgba": [255, 255, 255, 255],
                        "note_text": "Race Day",
                    },
                    "widgets": [
                        {
                            "id": "hero-pace",
                            "type": "hero_metric",
                            "bindings": {"value": "pace_seconds_per_km"},
                            "anchor": "top-left",
                            "x": 24,
                            "y": 172,
                            "width": 336,
                            "height": 116,
                            "z_index": 20,
                            "visible": True,
                            "style": {"label": float("nan")},
                        }
                    ],
                },
                "overrides": {},
            },
            sort_keys=False,
        )
    )

    with pytest.raises(ValueError, match="finite"):
        load_config(path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda hud: hud.update(unknown_top_level=True),
            "unexpected hud key",
        ),
        (
            lambda hud: hud["theme"].update(unknown_theme=True),
            "unexpected hud.theme key",
        ),
        (
            lambda hud: hud["widgets"][0].update(unknown_widget=True),
            "unexpected hud.widgets",
        ),
    ],
)
def test_load_config_rejects_unknown_hud_keys(tmp_path: Path, mutate, message: str) -> None:
    path = tmp_path / "overlay.yaml"
    save_config(path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    payload = yaml.safe_load(path.read_text())
    mutate(payload["hud"])
    path.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match=message):
        load_config(path)


def test_resolve_path_from_config_uses_config_directory_for_relative_values(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "overlay.yaml"
    config_path.parent.mkdir()

    resolved = resolve_path_from_config(config_path, "cache")

    assert resolved == config_path.parent / "cache"


def test_resolve_video_globs_from_config_uses_config_directory_for_relative_patterns(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "overlay.yaml"
    config_path.parent.mkdir()

    resolved = resolve_video_globs_from_config(config_path, ["*.MP4", "/already/absolute.mov"])

    assert resolved == [str(config_path.parent / "*.MP4"), "/already/absolute.mov"]


def test_load_config_strips_legacy_panel_and_accent_theme_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "activity_file": "activity_22577902433.tcx",
                "video_globs": ["*.MP4", "*.mov"],
                "output_dir": "rendered",
                "cache_dir": "cache",
                "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
                "hud": {
                    "preset": "broadcast-runner",
                    "theme": {
                        "panel_rgba": [12, 18, 28, 148],
                        "accent_rgba": [26, 230, 198, 255],
                        "text_rgba": [247, 251, 255, 255],
                        "note_text": "Race Day",
                        "font_family": "broadcast_ui",
                        "font_weight": "regular",
                        "font_size_px": 18,
                        "title_font_family": "broadcast_ui",
                        "title_font_weight": "regular",
                        "title_font_size_px": 16,
                        "value_font_family": "broadcast_value",
                        "value_font_weight": "bold",
                        "value_font_size_px": 33,
                        "unit_font_family": "broadcast_value",
                        "unit_font_weight": "regular",
                        "unit_font_size_px": 13,
                        "show_units": True,
                    },
                    "widgets": [],
                },
                "overrides": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)
    theme_payload = serialize_hud_config(config.hud)["theme"]

    assert "panel_rgba" not in theme_payload
    assert "accent_rgba" not in theme_payload
    assert theme_payload["text_rgba"] == [247, 251, 255, 255]
