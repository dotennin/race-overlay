import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from http.client import HTTPConnection
from importlib.resources import files
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlparse

import pytest
import yaml

from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import (
    build_editor_state,
    load_editor_config,
    render_preview_payload,
    save_editor_preset_payload,
    save_editor_project_payload,
    save_editor_payload,
    select_editor_preset,
)
from race_overlay.editor_render import EditorRenderJobManager, RenderJobCanceledError
from race_overlay.editor_server import (
    NativePickerUnavailableError,
    _ACTIVE_SERVERS,
    _ACTIVE_THREADS,
    launch_editor,
)
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import (
    HUD_FONT_FAMILY_OPTIONS,
    HUD_FONT_WEIGHT_OPTIONS,
    HudConfig,
    HudThemeConfig,
    HudWidgetConfig,
    serialize_hud_config,
)


def test_build_editor_state_exposes_widgets_for_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["hud"]["preset"] == "broadcast-runner"
    assert any(widget["id"] == "time-chip" for widget in state["hud"]["widgets"])
    assert any(widget["id"] == "pace-chip" for widget in state["hud"]["widgets"])
    assert state["preview"]["width"] == 1280
    assert isinstance(state["revision"], str)
    assert state["revision"]


def test_build_editor_state_exposes_project_config_context_and_candidates(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "rendered").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "activities" / "backup.fit").write_bytes(b"FIT")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    config_path = tmp_path / "overlay.yaml"
    config = ProjectConfig(
        activity_file="activities/race.tcx",
        video_globs=["videos/clip-a.MP4", "videos/clip-b.mov"],
        output_dir="rendered",
        hud=broadcast_runner_preset(),
    )
    save_config(config_path, config)

    state = build_editor_state(config=config, width=1280, height=720, config_path=config_path)

    assert state["project"]["config_path"] == {"name": "overlay.yaml", "path": str(config_path)}
    assert state["project"]["activity_file"] == "activities/race.tcx"
    assert state["project"]["video_globs"] == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert state["project"]["output_dir"] == "rendered"
    assert state["project"]["choices"]["activity_files"] == ["activities/backup.fit", "activities/race.tcx"]
    assert state["project"]["choices"]["video_files"] == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert "rendered" in state["project"]["choices"]["output_dirs"]
    assert "exports" in state["project"]["choices"]["output_dirs"]


def test_build_editor_state_exposes_named_presets_and_active_preset(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    active_hud = broadcast_runner_preset()
    night_hud = broadcast_runner_preset()
    night_hud.preset = "night-run"
    night_hud.theme.note_text = "Night race"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=active_hud,
            hud_presets={
                "broadcast-runner": active_hud,
                "night-run": night_hud,
            },
        ),
    )

    state = build_editor_state(config=load_config(config_path), width=1280, height=720, config_path=config_path)

    assert state["presets"] == {
        "active": "broadcast-runner",
        "names": ["broadcast-runner", "night-run"],
    }


def test_build_editor_state_exposes_overlay_library_with_lap_waterfall() -> None:
    config = ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset())
    state = build_editor_state(
        config=config,
        width=1280,
        height=720,
    )

    catalog = state["overlay_library"]
    widget_types = {item["type"] for item in catalog}
    existing_ids = {widget.id for widget in config.hud.widgets}
    catalog_ids = {item["defaults"]["id"] for item in catalog}

    assert widget_types == {
        "progress_bar",
        "stat_block",
        "metric_card",
        "hero_metric",
        "context_card",
        "route_map",
        "lap_waterfall",
    }
    assert catalog_ids.isdisjoint(existing_ids)

    for entry in catalog:
        assert isinstance(entry["label"], str) and entry["label"]
        defaults = entry["defaults"]
        assert defaults["type"] == entry["type"]
        assert defaults["id"]
        assert defaults["bindings"]
        assert defaults["anchor"]
        assert isinstance(defaults["x"], int)
        assert isinstance(defaults["y"], int)
        assert isinstance(defaults["width"], int)
        assert isinstance(defaults["height"], int)
        assert isinstance(defaults["z_index"], int)
        assert isinstance(defaults["visible"], bool)
        assert isinstance(defaults["style"], dict)

    lap_entry = next(item for item in catalog if item["type"] == "lap_waterfall")
    assert lap_entry["defaults"]["bindings"] == {"value": "laps"}
    assert lap_entry["defaults"]["style"]["visible_rows"] == 5
    assert state["schema"]["widget_types"]["lap_waterfall"]["style"]["visible_rows"] == {
        "kind": "integer",
        "label": "Visible rows",
        "min": 1,
    }


def test_build_editor_state_exposes_stride_card_overlay_library_entry() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    stride_entry = next(item for item in state["overlay_library"] if item["defaults"]["id"] == "stride-chip")
    assert stride_entry["type"] == "metric_card"
    assert stride_entry["defaults"]["bindings"] == {"value": "stride_length_m"}
    assert stride_entry["defaults"]["style"] == {"label": "Stride", "variant": "compact"}


def test_build_editor_state_exposes_speed_chip_overlay_library_entry_with_speed_gauge_variant() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    speed_entry = next(item for item in state["overlay_library"] if item["label"] == "Speed chip")

    assert speed_entry["type"] == "metric_card"
    assert speed_entry["defaults"]["bindings"] == {"value": "speed_mps"}
    assert speed_entry["defaults"]["style"] == {"label": "Speed", "variant": "speed_gauge"}


def test_build_editor_state_exposes_square_speed_chip_overlay_library_entry() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    speed_entry = next(item for item in state["overlay_library"] if item["label"] == "Speed chip")

    assert speed_entry["defaults"]["width"] == speed_entry["defaults"]["height"]


def test_build_editor_state_exposes_speed_chip_value_font_schema() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    speed_chip_style = state["schema"]["widgets"]["speed-chip"]["style"]

    assert speed_chip_style["value_font_family"] == {
        "kind": "enum",
        "label": "Value font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert speed_chip_style["value_font_weight"] == {
        "kind": "enum",
        "label": "Value font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert speed_chip_style["value_font_size_px"] == {"kind": "integer", "label": "Value font size", "min": 8}


def test_build_editor_state_exposes_theme_and_widget_style_schema() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["schema"]["theme"]["font_family"] == {
        "kind": "enum",
        "label": "Font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert state["schema"]["theme"]["font_weight"] == {
        "kind": "enum",
        "label": "Font weight",
        "options": ["regular", "bold"],
    }
    assert state["schema"]["theme"]["font_size_px"] == {"kind": "integer", "label": "Font size", "min": 8}
    assert state["schema"]["theme"]["show_units"] == {"kind": "boolean", "label": "Show units"}

    ruler_style = state["schema"]["widgets"]["distance-ruler"]["style"]
    assert ruler_style["unit_font_family"]["options"] == list(HUD_FONT_FAMILY_OPTIONS)
    assert ruler_style["unit_font_weight"]["options"] == ["regular", "bold"]
    assert ruler_style["unit_font_size_px"]["min"] == 8
    assert ruler_style["show_unit"] == {"kind": "boolean", "label": "Show unit suffix"}
    assert ruler_style["show_current_value"] == {"kind": "boolean", "label": "Show current value"}
    assert ruler_style["show_total_value"] == {"kind": "boolean", "label": "Show total value"}
    assert ruler_style["current_font_size_px"] == {"kind": "integer", "label": "Current font size", "min": 8}
    assert ruler_style["fill_rgba"] == {"kind": "rgba", "label": "Fill RGBA"}
    assert ruler_style["rail_rgba"] == {"kind": "rgba", "label": "Rail RGBA"}
    assert ruler_style["tick_rgba"] == {"kind": "rgba", "label": "Tick RGBA"}

    pace_chip_style = state["schema"]["widgets"]["pace-chip"]["style"]
    assert pace_chip_style["unit_font_family"]["options"] == list(HUD_FONT_FAMILY_OPTIONS)
    assert pace_chip_style["unit_font_weight"]["options"] == ["regular", "bold"]
    assert pace_chip_style["unit_font_size_px"]["min"] == 8
    assert pace_chip_style["show_unit"] == {"kind": "boolean", "label": "Show unit suffix"}


def test_build_editor_state_exposes_speed_gauge_metric_card_variant() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    pace_chip_style = state["schema"]["widgets"]["pace-chip"]["style"]

    assert pace_chip_style["variant"] == {
        "kind": "selection",
        "label": "Variant",
        "options": ["compact", "speed_gauge"],
    }


def test_build_editor_state_exposes_broadcast_font_families_in_schema() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    font_family_options = state["schema"]["theme"]["font_family"]["options"]
    assert "broadcast_ui" in font_family_options
    assert "broadcast_value" in font_family_options
    assert "sans" in font_family_options
    assert "serif" in font_family_options
    assert "mono" in font_family_options


def test_build_editor_state_exposes_navigation_timestamp_and_typography_role_schema() -> None:
    config = ProjectConfig(
        activity_file="activity_22577902433.tcx",
        hud=HudConfig(
            preset="custom",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": "", "shape": "circle", "show_panel": True},
                ),
                HudWidgetConfig(
                    id="time-card",
                    type="context_card",
                    bindings={"value": "timestamp"},
                    anchor="top-right",
                    x=24,
                    y=24,
                    width=240,
                    height=128,
                    style={"label": "Context"},
                ),
            ],
        ),
    )

    state = build_editor_state(config=config, width=1280, height=720)

    assert state["schema"]["theme"]["title_font_family"] == {
        "kind": "enum",
        "label": "Title font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert state["schema"]["theme"]["title_font_weight"] == {
        "kind": "enum",
        "label": "Title font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert state["schema"]["theme"]["title_font_size_px"] == {
        "kind": "integer",
        "label": "Title font size",
        "min": 8,
    }
    assert state["schema"]["theme"]["value_font_family"] == {
        "kind": "enum",
        "label": "Value font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert state["schema"]["theme"]["value_font_weight"] == {
        "kind": "enum",
        "label": "Value font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert state["schema"]["theme"]["value_font_size_px"] == {
        "kind": "integer",
        "label": "Value font size",
        "min": 8,
    }
    assert state["schema"]["theme"]["unit_font_family"] == {
        "kind": "enum",
        "label": "Unit font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert state["schema"]["theme"]["unit_font_weight"] == {
        "kind": "enum",
        "label": "Unit font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert state["schema"]["theme"]["unit_font_size_px"] == {
        "kind": "integer",
        "label": "Unit font size",
        "min": 8,
    }

    route_map_style = state["schema"]["widgets"]["route-map"]["style"]
    assert route_map_style["show_north_marker"] == {"kind": "boolean", "label": "Show north marker"}
    assert route_map_style["show_bearing_label"] == {"kind": "boolean", "label": "Show bearing label"}

    time_card_style = state["schema"]["widgets"]["time-card"]["style"]
    assert time_card_style["variant"] == {"kind": "selection", "label": "Variant", "options": ["compact", "timestamp_chip"]}
    assert time_card_style["format"] == {"kind": "text", "label": "Format"}


def test_build_editor_state_exposes_time_chip_and_navigation_schema_for_broadcast_runner() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert "time-chip" in state["schema"]["widgets"]
    assert state["schema"]["widgets"]["route-map"]["style"]["show_north_marker"] == {
        "kind": "boolean",
        "label": "Show north marker",
    }
    assert state["schema"]["widgets"]["time-chip"]["style"]["format"] == {"kind": "text", "label": "Format"}


def test_build_editor_state_exposes_lap_waterfall_schema() -> None:
    config = ProjectConfig(
        activity_file="activity_22577902433.tcx",
        hud=HudConfig(
            preset="lap-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="lap-table",
                    type="lap_waterfall",
                    bindings={"value": "laps"},
                    anchor="top-left",
                    x=24,
                    y=400,
                    width=400,
                    height=200,
                    style={},
                )
            ],
        ),
    )

    state = build_editor_state(config=config, width=1280, height=720)
    lap_style = state["schema"]["widgets"]["lap-table"]["style"]

    assert lap_style["visible_rows"] == {"kind": "integer", "label": "Visible rows", "min": 1}
    assert lap_style["always_show"] == {"kind": "boolean", "label": "Always show"}
    assert lap_style["fade_after_seconds"] == {"kind": "integer", "label": "Fade after seconds", "min": 1}
    assert lap_style["show_distance"] == {"kind": "boolean", "label": "Show distance"}
    assert lap_style["show_time"] == {"kind": "boolean", "label": "Show time"}
    assert lap_style["show_pace"] == {"kind": "boolean", "label": "Show pace"}
    assert lap_style["show_elevation"] == {"kind": "boolean", "label": "Show elevation"}
    assert lap_style["show_heart_rate"] == {"kind": "boolean", "label": "Show heart rate"}
    assert lap_style["value_font_family"] == {
        "kind": "enum",
        "label": "Value font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert lap_style["value_font_weight"] == {
        "kind": "enum",
        "label": "Value font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert lap_style["value_font_size_px"] == {"kind": "integer", "label": "Value font size", "min": 8}
    assert lap_style["unit_font_family"] == {
        "kind": "enum",
        "label": "Unit font family",
        "options": list(HUD_FONT_FAMILY_OPTIONS),
    }
    assert lap_style["unit_font_weight"] == {
        "kind": "enum",
        "label": "Unit font weight",
        "options": list(HUD_FONT_WEIGHT_OPTIONS),
    }
    assert lap_style["unit_font_size_px"] == {"kind": "integer", "label": "Unit font size", "min": 8}


def test_time_chip_widget_has_value_font_fields_not_unit_font() -> None:
    """Verify time-chip uses value_font_* fields (not unit_font_*) in editor schema."""
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    time_chip_style = state["schema"]["widgets"]["time-chip"]["style"]

    # Verify value_font fields are exposed
    assert "value_font_family" in time_chip_style
    assert time_chip_style["value_font_family"]["kind"] == "enum"
    assert "value_font_weight" in time_chip_style
    assert time_chip_style["value_font_weight"]["kind"] == "enum"
    assert "value_font_size_px" in time_chip_style
    assert time_chip_style["value_font_size_px"]["kind"] == "integer"

    # Verify unit_font fields are NOT exposed for time-chip
    assert "unit_font_family" not in time_chip_style
    assert "unit_font_weight" not in time_chip_style
    assert "unit_font_size_px" not in time_chip_style

    # Verify label is hidden
    assert time_chip_style.get("label", {}).get("hidden") is True


def test_save_editor_payload_round_trips_navigation_timestamp_and_typography_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=HudConfig(
                preset="custom",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=176,
                        height=128,
                        style={"label": "", "shape": "circle", "show_panel": True},
                    ),
                    HudWidgetConfig(
                        id="time-card",
                        type="context_card",
                        bindings={"value": "timestamp"},
                        anchor="top-right",
                        x=24,
                        y=24,
                        width=240,
                        height=128,
                        style={"label": "Context"},
                    ),
                ],
            ),
        ),
    )

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"].update(
        title_font_family="serif",
        title_font_weight="bold",
        title_font_size_px=20,
        value_font_family="mono",
        value_font_weight="regular",
        value_font_size_px=28,
        unit_font_family="sans",
        unit_font_weight="bold",
        unit_font_size_px=14,
    )
    route_map = next(widget for widget in payload["widgets"] if widget["id"] == "route-map")
    route_map["style"].update(show_north_marker=True, show_bearing_label=False, zoom_percent=118)
    time_card = next(widget for widget in payload["widgets"] if widget["id"] == "time-card")
    time_card["style"].update(variant="timestamp_chip", format="%H:%M")

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    route_map_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "route-map")
    time_card_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "time-card")

    assert reloaded.hud.theme.title_font_family == "serif"
    assert reloaded.hud.theme.title_font_weight == "bold"
    assert reloaded.hud.theme.title_font_size_px == 20
    assert reloaded.hud.theme.value_font_family == "mono"
    assert reloaded.hud.theme.value_font_weight == "regular"
    assert reloaded.hud.theme.value_font_size_px == 28
    assert reloaded.hud.theme.unit_font_family == "sans"
    assert reloaded.hud.theme.unit_font_weight == "bold"
    assert reloaded.hud.theme.unit_font_size_px == 14
    assert route_map_reloaded.style["show_north_marker"] is True
    assert route_map_reloaded.style["show_bearing_label"] is False
    assert route_map_reloaded.style["zoom_percent"] == 118

    assert time_card_reloaded.style["variant"] == "timestamp_chip"
    assert time_card_reloaded.style["format"] == "%H:%M"


def test_save_editor_payload_updates_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Kasumigaura"
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip["x"] = 48

    save_editor_payload(config_path, payload)
    reloaded = load_config(config_path)

    assert reloaded.hud.theme.note_text == "Kasumigaura"
    pace_widget = next(widget for widget in reloaded.hud.widgets if widget.id == "pace-chip")
    assert pace_widget.x == 48
    assert len(reloaded.hud.widgets) == len(broadcast_runner_preset().widgets)


def test_save_editor_payload_updates_active_named_preset(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    active_hud = broadcast_runner_preset()
    night_hud = broadcast_runner_preset()
    night_hud.preset = "night-run"
    night_hud.theme.note_text = "Night race"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=active_hud,
            hud_presets={
                "broadcast-runner": active_hud,
                "night-run": night_hud,
            },
        ),
    )

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Updated active preset"

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)

    assert reloaded.hud.theme.note_text == "Updated active preset"
    assert reloaded.hud_presets["broadcast-runner"].theme.note_text == "Updated active preset"
    assert reloaded.hud_presets["night-run"].theme.note_text == "Night race"


def test_save_editor_preset_payload_persists_named_preset_and_activates_it(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["theme"]["note_text"] = "Saved as night"
    revision = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]

    save_editor_preset_payload(
        config_path,
        {
            "name": "night-run",
            "hud": payload,
            "revision": revision,
        },
    )

    reloaded = load_config(config_path)

    assert reloaded.hud.preset == "night-run"
    assert reloaded.hud.theme.note_text == "Saved as night"
    assert set(reloaded.hud_presets) == {"broadcast-runner", "night-run"}
    assert reloaded.hud_presets["night-run"].theme.note_text == "Saved as night"


def test_select_editor_preset_loads_saved_preset_into_active_hud(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    active_hud = broadcast_runner_preset()
    night_hud = broadcast_runner_preset()
    night_hud.preset = "night-run"
    night_hud.theme.note_text = "Night race"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=active_hud,
            hud_presets={
                "broadcast-runner": active_hud,
                "night-run": night_hud,
            },
        ),
    )

    select_editor_preset(config_path, {"name": "night-run"})

    reloaded = load_config(config_path)

    assert reloaded.hud.preset == "night-run"
    assert reloaded.hud.theme.note_text == "Night race"


def test_save_editor_project_payload_updates_activity_video_paths_and_output_dir(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "rendered").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "activities" / "backup.fit").write_bytes(b"FIT")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["videos/clip-a.MP4"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    save_editor_project_payload(
        config_path,
        {
            "activity_file": "activities/backup.fit",
            "video_globs": ["videos/clip-a.MP4", "videos/clip-b.mov"],
            "output_dir": "exports",
        },
    )

    reloaded = load_config(config_path)

    assert reloaded.activity_file == "activities/backup.fit"
    assert reloaded.video_globs == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert reloaded.output_dir == "exports"


def test_save_editor_project_payload_preserves_absolute_native_picker_paths(tmp_path: Path) -> None:
    external_dir = tmp_path.parent / f"{tmp_path.name}-native-picker"
    external_dir.mkdir()
    activity_path = external_dir / "race.tcx"
    video_a_path = external_dir / "clip-a.MP4"
    video_b_path = external_dir / "clip-b.mov"
    output_dir = external_dir / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_a_path.write_bytes(b"video-a")
    video_b_path.write_bytes(b"video-b")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["videos/clip-a.MP4"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    save_editor_project_payload(
        config_path,
        {
            "activity_file": str(activity_path),
            "video_globs": [str(video_a_path), str(video_b_path)],
            "output_dir": str(output_dir),
        },
    )

    reloaded = load_config(config_path)

    assert reloaded.activity_file == str(activity_path)
    assert reloaded.video_globs == [str(video_a_path), str(video_b_path)]
    assert reloaded.output_dir == str(output_dir)


def test_save_editor_payload_round_trips_theme_and_widget_style_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"].update(
        text_rgba=[70, 80, 90, 255],
        font_family="serif",
        font_weight="bold",
        font_size_px=24,
        show_units=False,
    )
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip["style"].update(unit_font_family="mono", unit_font_weight="bold", unit_font_size_px=26, show_unit=False)
    distance_ruler = next(widget for widget in payload["widgets"] if widget["id"] == "distance-ruler")
    distance_ruler["style"].update(
        show_current_value=False,
        show_total_value=False,
        fill_rgba=[34, 255, 138, 255],
        rail_rgba=[8, 12, 20, 220],
        tick_rgba=[230, 238, 245, 168],
    )

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    reloaded_pace_chip = next(widget for widget in reloaded.hud.widgets if widget.id == "pace-chip")
    reloaded_ruler = next(widget for widget in reloaded.hud.widgets if widget.id == "distance-ruler")

    assert reloaded.hud.theme.text_rgba == [70, 80, 90, 255]
    assert reloaded.hud.theme.font_family == "serif"
    assert reloaded.hud.theme.font_weight == "bold"
    assert reloaded.hud.theme.font_size_px == 24
    assert reloaded.hud.theme.show_units is False
    assert reloaded_pace_chip.style["unit_font_family"] == "mono"
    assert reloaded_pace_chip.style["unit_font_weight"] == "bold"
    assert reloaded_pace_chip.style["unit_font_size_px"] == 26
    assert reloaded_pace_chip.style["show_unit"] is False
    assert reloaded_ruler.style["show_current_value"] is False
    assert reloaded_ruler.style["show_total_value"] is False
    assert reloaded_ruler.style["fill_rgba"] == [34, 255, 138, 255]
    assert reloaded_ruler.style["rail_rgba"] == [8, 12, 20, 220]
    assert reloaded_ruler.style["tick_rgba"] == [230, 238, 245, 168]


def test_save_editor_payload_round_trips_time_chip_value_font_fields(tmp_path: Path) -> None:
    """Verify time-chip value_font_* fields are persisted correctly through save/load cycle."""
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    
    # Update time-chip with custom value_font settings
    time_chip = next(widget for widget in payload["widgets"] if widget["id"] == "time-chip")
    time_chip["style"].update(
        value_font_family="mono",
        value_font_weight="regular",
        value_font_size_px=22,
    )

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    reloaded_time_chip = next(widget for widget in reloaded.hud.widgets if widget.id == "time-chip")

    # Verify value_font fields were persisted
    assert reloaded_time_chip.style["value_font_family"] == "mono"
    assert reloaded_time_chip.style["value_font_weight"] == "regular"
    assert reloaded_time_chip.style["value_font_size_px"] == 22


def test_save_editor_payload_preserves_schema_when_legacy_fields_are_also_present(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    schema_hud = broadcast_runner_preset()
    schema_hud.theme.note_text = "Schema wins"
    route_map = next(widget for widget in schema_hud.widgets if widget.id == "route-map")
    pace_chip = next(widget for widget in schema_hud.widgets if widget.id == "pace-chip")
    route_map.visible = True
    pace_chip.visible = False
    pace_chip.x = 944
    mixed_payload = {
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
            **serialize_hud_config(schema_hud),
        },
        "overrides": {},
    }
    config_path.write_text(yaml.safe_dump(mixed_payload, sort_keys=False))

    editor_state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = json.loads(json.dumps(editor_state["hud"]))
    payload["revision"] = editor_state["revision"]
    payload["theme"]["note_text"] = "Saved schema HUD"

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    saved_payload = yaml.safe_load(config_path.read_text())
    route_map_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "route-map")
    pace_chip_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "pace-chip")

    assert reloaded.hud.theme.note_text == "Saved schema HUD"
    assert route_map_reloaded.visible is True
    assert pace_chip_reloaded.visible is False
    assert pace_chip_reloaded.x == 944
    assert "fields" not in saved_payload["hud"]


def test_save_editor_payload_allows_missing_widget_label(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=HudConfig(
                preset="route-only",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=176,
                        height=128,
                    )
                ],
            ),
        ),
    )

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["widgets"][0]["style"]["label"] = ""

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.widgets[0].style == {"label": ""}


def test_save_editor_payload_allows_empty_widget_list_when_existing_hud_is_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=HudConfig(
                preset="empty",
                theme=HudThemeConfig(),
                widgets=[],
            ),
        ),
    )

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "No widgets"

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.theme.note_text == "No widgets"
    assert reloaded.hud.widgets == []


def test_save_editor_payload_does_not_run_two_load_modify_write_cycles_concurrently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    original_save_config = save_editor_payload.__globals__["save_config"]
    first_save_entered = Event()
    release_first_save = Event()
    second_save_entered = Event()
    call_count = 0

    def blocking_save_config(path: Path, config: ProjectConfig) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_save_entered.set()
            release_first_save.wait(timeout=1)
        else:
            second_save_entered.set()
        original_save_config(path, config)

    monkeypatch.setattr("race_overlay.editor_preview.save_config", blocking_save_config)

    payload_one = serialize_hud_config(broadcast_runner_preset())
    payload_one["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload_one["theme"]["note_text"] = "first"
    payload_two = serialize_hud_config(broadcast_runner_preset())
    payload_two["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload_two["theme"]["note_text"] = "second"

    errors: list[BaseException] = []

    def save_payload(payload: dict[str, object]) -> None:
        try:
            save_editor_payload(config_path, payload)
        except BaseException as exc:  # pragma: no cover - captured for assertion
            errors.append(exc)

    first_thread = Thread(target=save_payload, args=(payload_one,))
    second_thread = Thread(target=save_payload, args=(payload_two,))
    first_thread.start()
    assert first_save_entered.wait(timeout=1)
    second_thread.start()

    assert not second_save_entered.wait(timeout=0.1)
    release_first_save.set()
    first_thread.join(timeout=1)
    second_thread.join(timeout=1)

    assert second_save_entered.is_set() is False
    assert len(errors) == 1
    assert "stale HUD" in str(errors[0])


def test_save_editor_payload_preserves_newer_non_hud_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Kasumigaura"

    original_validate = save_editor_payload.__globals__["_validate_complete_hud_payload"]

    def validate_then_apply_external_non_hud_changes(existing_hud: HudConfig, candidate_payload: dict[str, object]) -> None:
        original_validate(existing_hud, candidate_payload)
        updated = load_config(config_path)
        updated.timeline.global_offset_seconds = 12.5
        updated.overrides["clip.mp4"] = {"offset_seconds": 3.0, "outside_activity": "freeze"}
        save_config(config_path, updated)

    monkeypatch.setattr(
        "race_overlay.editor_preview._validate_complete_hud_payload",
        validate_then_apply_external_non_hud_changes,
    )

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.theme.note_text == "Kasumigaura"
    assert reloaded.timeline.global_offset_seconds == 12.5
    assert reloaded.overrides == {"clip.mp4": {"offset_seconds": 3.0, "outside_activity": "freeze"}}


def test_save_editor_payload_rejects_stale_hud_revision(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    initial_state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = dict(initial_state["hud"])
    payload["theme"] = dict(initial_state["hud"]["theme"])
    payload["widgets"] = [
        {**widget, "bindings": dict(widget["bindings"]), "style": dict(widget["style"])}
        for widget in initial_state["hud"]["widgets"]
    ]
    payload["revision"] = initial_state["revision"]

    updated = load_config(config_path)
    updated.hud.theme.note_text = "newer edit"
    save_config(config_path, updated)

    payload["theme"]["note_text"] = "older edit"

    with pytest.raises(ValueError, match="stale HUD"):
        save_editor_payload(config_path, payload)

    assert load_config(config_path).hud.theme.note_text == "newer edit"


def test_save_editor_payload_rejects_external_concurrent_save_from_another_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload_one = json.loads(json.dumps(state["hud"]))
    payload_one["revision"] = state["revision"]
    payload_one["theme"]["note_text"] = "first"
    payload_two = json.loads(json.dumps(state["hud"]))
    payload_two["revision"] = state["revision"]
    payload_two["theme"]["note_text"] = "second"

    original_save_config = save_editor_payload.__globals__["save_config"]
    first_save_entered = Event()
    release_first_save = Event()
    errors: list[BaseException] = []

    def blocking_save_config(path: Path, config: ProjectConfig) -> None:
        first_save_entered.set()
        assert release_first_save.wait(timeout=5)
        original_save_config(path, config)

    monkeypatch.setattr("race_overlay.editor_preview.save_config", blocking_save_config)

    def save_first_payload() -> None:
        try:
            save_editor_payload(config_path, payload_one)
        except BaseException as exc:  # pragma: no cover - captured for assertion
            errors.append(exc)

    first_thread = Thread(target=save_first_payload)
    first_thread.start()
    assert first_save_entered.wait(timeout=1)

    payload_path = tmp_path / "payload-two.json"
    payload_path.write_text(json.dumps(payload_two))

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import json, sys\n"
                "from pathlib import Path\n"
                "from race_overlay.editor_preview import save_editor_payload\n"
                "config_path = Path(sys.argv[1])\n"
                "payload = json.loads(Path(sys.argv[2]).read_text())\n"
                "save_editor_payload(config_path, payload)\n"
            ),
            str(config_path),
            str(payload_path),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(0.2)
    assert process.poll() is None

    release_first_save.set()
    stdout, stderr = process.communicate(timeout=5)
    first_thread.join(timeout=5)

    assert not errors
    assert process.returncode != 0
    assert "stale HUD save rejected" in stderr
    assert stdout == ""
    assert load_config(config_path).hud.theme.note_text == "first"


def test_save_editor_payload_rejects_invalid_numeric_widget_values(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip["x"] = None

    with pytest.raises(ValueError, match="x must be a finite integer"):
        save_editor_payload(config_path, payload)

    pace_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "pace-chip")
    expected_pace_widget = next(widget for widget in broadcast_runner_preset().widgets if widget.id == "pace-chip")
    assert pace_widget.x == expected_pace_widget.x


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"preset": "broadcast-runner"},
        {"theme": {"note_text": "Kasumigaura"}},
        {"preset": "broadcast-runner", "theme": serialize_hud_config(broadcast_runner_preset())["theme"], "widgets": []},
        {
            "preset": "broadcast-runner",
            "theme": {"note_text": "Kasumigaura"},
            "widgets": serialize_hud_config(broadcast_runner_preset())["widgets"],
        },
    ],
)
def test_save_editor_payload_rejects_incomplete_hud_documents(tmp_path: Path, payload: dict[str, object]) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert len(reloaded.hud.widgets) == len(broadcast_runner_preset().widgets)


def test_save_editor_payload_rejects_invalid_theme_values(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["text_rgba"] = "oops"
    payload["theme"]["note_text"] = "Kasumigaura"

    with pytest.raises(ValueError, match="text_rgba must be a list of 4 integers"):
        save_editor_payload(config_path, payload)

    assert load_config(config_path).hud.theme.text_rgba == [247, 251, 255, 255]


def test_save_editor_payload_allows_partial_widgets_removal(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    # Keep only the first widget, removing all others
    payload["widgets"] = [payload["widgets"][0]]

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert len(reloaded.hud.widgets) == 1
    assert reloaded.hud.widgets[0].id == payload["widgets"][0]["id"]


def test_save_editor_payload_rejects_partial_widget_objects(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip.pop("visible")

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    pace_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "pace-chip")
    assert pace_widget.visible is True


def test_save_editor_payload_rejects_partial_widget_bindings(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip["bindings"] = {}

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    pace_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "pace-chip")
    assert pace_widget.bindings == {"value": "pace_seconds_per_km"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip").update(anchor="center"),
            "unsupported anchor",
        ),
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "distance-ruler").update(width=160),
            "minimum width",
        ),
    ],
)
def test_save_editor_payload_rejects_renderer_invalid_widgets_before_persisting(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        save_editor_payload(config_path, payload)

    assert config_path.read_text() == original_text
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_save_editor_payload_allows_appending_overlay_library_widget(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = json.loads(json.dumps(state["hud"]))
    payload["revision"] = state["revision"]
    overlay_entry = next(item for item in state["overlay_library"] if item["type"] == "lap_waterfall")
    payload["widgets"].append(json.loads(json.dumps(overlay_entry["defaults"])))

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    appended = next(widget for widget in reloaded.hud.widgets if widget.id == overlay_entry["defaults"]["id"])

    assert appended.type == "lap_waterfall"
    assert appended.bindings == {"value": "laps"}
    assert appended.style["visible_rows"] == 5


def test_render_preview_payload_uses_unsaved_draft_without_touching_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    distance_stat = next(widget for widget in payload["widgets"] if widget["id"] == "distance-stat")
    distance_stat["x"] = 96

    png = render_preview_payload(config_path, payload, width=1280, height=720)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert config_path.read_text() == original_text
    assert next(widget for widget in load_config(config_path).hud.widgets if widget.id == "distance-stat").x == 44


def test_render_preview_payload_allows_appended_overlay_library_widget(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = json.loads(json.dumps(state["hud"]))
    overlay_entry = next(item for item in state["overlay_library"] if item["type"] == "lap_waterfall")
    payload["widgets"].append(json.loads(json.dumps(overlay_entry["defaults"])))

    png = render_preview_payload(config_path, payload, width=1280, height=720)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert config_path.read_text() == original_text


def test_editor_render_snapshot_uses_unsaved_draft_without_touching_overlay_yaml(tmp_path: Path) -> None:
    import race_overlay.editor_preview as ep

    external_dir = tmp_path.parent / f"{tmp_path.name}-render-snapshot"
    external_dir.mkdir()
    activity_path = external_dir / "race.tcx"
    video_path = external_dir / "clip-a.MP4"
    output_dir = external_dir / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["theme"]["note_text"] = "snapshot draft"
    distance_stat = next(widget for widget in payload["widgets"] if widget["id"] == "distance-stat")
    distance_stat["x"] = 96

    snapshot_path: Path | None = None
    with ep.editor_render_snapshot(config_path, payload) as built_snapshot_path:
        snapshot_path = built_snapshot_path
        snapshot = load_config(snapshot_path)
        assert snapshot.activity_file == str(activity_path)
        assert snapshot.video_globs == [str(video_path)]
        assert snapshot.output_dir == str(output_dir)
        assert snapshot.hud.theme.note_text == "snapshot draft"
        assert next(widget for widget in snapshot.hud.widgets if widget.id == "distance-stat").x == 96
        assert snapshot_path != config_path
        assert snapshot_path.exists()

    assert snapshot_path is not None
    assert not snapshot_path.exists()
    assert config_path.read_text() == original_text
    assert load_config(config_path).hud.theme.note_text != "snapshot draft"
    assert next(widget for widget in load_config(config_path).hud.widgets if widget.id == "distance-stat").x == 44


def test_editor_render_snapshot_resolves_relative_project_paths_to_absolute(tmp_path: Path) -> None:
    import race_overlay.editor_preview as ep

    activity_path = tmp_path / "activity_22577902433.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            video_globs=["clip-a.MP4"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    payload = serialize_hud_config(broadcast_runner_preset())

    with ep.editor_render_snapshot(config_path, payload) as snapshot_path:
        snapshot = load_config(snapshot_path)
        assert snapshot.activity_file == str(activity_path)
        assert snapshot.video_globs == [str(video_path)]
        assert snapshot.output_dir == str(output_dir)
        assert snapshot.cache_dir == str(tmp_path / "cache")


def test_render_preview_png_passes_lap_states_to_render_hud_frame(monkeypatch, tmp_path: Path) -> None:
    """editor_preview.render_preview_png must pass widget-scoped lap_states to render_hud_frame."""
    from race_overlay.editor_preview import render_preview_png
    from race_overlay.sampling import LapWaterfallState

    config = ProjectConfig(
        activity_file="activity_22577902433.tcx",
        hud=HudConfig(
            preset="lap-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="lap-table",
                    type="lap_waterfall",
                    bindings={"value": "laps"},
                    anchor="top-left",
                    x=24,
                    y=400,
                    width=400,
                    height=200,
                    style={"visible_rows": 2, "always_show": True},
                )
            ],
        ),
    )

    captured_kwargs: list[dict] = []

    original_render = __import__("race_overlay.hud", fromlist=["render_hud_frame"]).render_hud_frame

    def capturing_render(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return original_render(*args, **kwargs)

    monkeypatch.setattr("race_overlay.editor_preview.render_hud_frame", capturing_render)

    render_preview_png(config, width=1280, height=720)

    assert captured_kwargs, "render_hud_frame was not called"
    assert "lap_states" in captured_kwargs[0], "lap_states was not passed to render_hud_frame"
    assert isinstance(captured_kwargs[0]["lap_states"]["lap-table"], LapWaterfallState)
    assert len(captured_kwargs[0]["lap_states"]["lap-table"].visible_rows) == 2


def test_sample_lap_waterfall_states_use_widget_helper(monkeypatch) -> None:
    """_sample_lap_waterfall_states must delegate to lap_waterfall_state_for_widget()."""
    import race_overlay.editor_preview as ep
    from race_overlay.sampling import LapWaterfallState

    call_args: list[tuple] = []
    original = __import__("race_overlay.sampling", fromlist=["lap_waterfall_state_for_widget"]).lap_waterfall_state_for_widget

    def capturing(*args, **kwargs):
        call_args.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr("race_overlay.editor_preview.lap_waterfall_state_for_widget", capturing)

    config = HudConfig(
        preset="lap-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="lap-table",
                type="lap_waterfall",
                bindings={"value": "laps"},
                anchor="top-left",
                x=24,
                y=400,
                width=400,
                height=200,
                style={"visible_rows": 2},
            )
        ],
    )

    result = ep._sample_lap_waterfall_states(config)

    assert call_args, "lap_waterfall_state_for_widget() was not called"
    assert isinstance(result["lap-table"], LapWaterfallState)
    preview_widget, laps_arg, _when = call_args[0]
    assert preview_widget.style["always_show"] is True
    assert "always_show" not in config.widgets[0].style
    assert len(laps_arg) > 0, "no ActivityLap values passed to lap_waterfall_state_for_widget"


@contextmanager
def running_editor(config_path: Path) -> str:
    base_url = launch_editor(config_path, width=1280, height=720)
    server = _ACTIVE_SERVERS[-1]
    thread = _ACTIVE_THREADS[-1]
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _ACTIVE_SERVERS.remove(server)
        _ACTIVE_THREADS.remove(thread)


def test_editor_help_defaults_closed_in_served_html(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            connection.close()

    assert response.status == 200
    assert 'id="help-modal"' in body
    assert "hidden" in body.split('id="help-modal"', 1)[1]


def test_editor_shell_exposes_theme_controls_container(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            connection.close()

    assert response.status == 200
    assert "Theme defaults" in body
    assert 'id="theme-defaults-toggle"' in body
    assert 'id="theme-defaults-panel"' in body
    assert 'id="theme-controls"' in body
    assert 'id="overlay-library-panel"' in body
    assert 'id="overlay-library-list"' in body


def test_editor_app_asset_uses_schema_driven_theme_controls(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/app.js")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
        finally:
            connection.close()

    assert response.status == 200
    assert "themeControls" in body
    assert "themeDefaultsToggle" in body
    assert "themeDefaultsPanel" in body
    assert "renderOverlayLibrary" in body
    assert "overlayLibraryList" in body
    assert "savedState.schema" in body
    assert "font_size_px" in body


def test_api_config_rejects_malformed_json_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=b"{",
                headers={"Content-Type": "application/json", "Content-Length": "1"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert json.loads(body.decode("utf-8"))["error"] == "invalid JSON payload"


def test_api_config_rejects_partial_payload_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps({"preset": "broadcast-runner"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "complete HUD document" in json.loads(body.decode("utf-8"))["error"]
    assert len(load_config(config_path).hud.widgets) == len(broadcast_runner_preset().widgets)


def test_api_preview_rejects_invalid_draft_payload_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/preview",
                body=json.dumps({"widgets": []}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "complete HUD document" in json.loads(body.decode("utf-8"))["error"]


def test_api_preview_renders_unsaved_draft_without_touching_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    distance_stat = next(widget for widget in payload["widgets"] if widget["id"] == "distance-stat")
    distance_stat["x"] = 96

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/preview",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 200
    assert response.getheader("Content-Type") == "image/png"
    assert response.getheader("Cache-Control") == "no-store"
    assert body.startswith(b"\x89PNG\r\n\x1a\n")
    assert config_path.read_text() == original_text
    assert next(widget for widget in load_config(config_path).hud.widgets if widget.id == "distance-stat").x == 44


def test_api_render_runs_pipeline_from_unsaved_draft_and_reports_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    original_text = config_path.read_text()
    captured: dict[str, object] = {}

    def fake_run_pipeline(snapshot_path: Path, only=None, *, progress=None) -> None:
        snapshot = load_config(snapshot_path)
        captured["snapshot_path"] = snapshot_path
        captured["note_text"] = snapshot.hud.theme.note_text
        captured["distance_x"] = next(widget for widget in snapshot.hud.widgets if widget.id == "distance-stat").x
        if progress is not None:
            progress("Loading config from snapshot")
            progress("Finished clip-a.MP4")

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", fake_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["theme"]["note_text"] = "render draft"
    next(widget for widget in payload["widgets"] if widget["id"] == "distance-stat")["x"] = 96

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            start_response = connection.getresponse()
            start_body = json.loads(start_response.read().decode("utf-8"))
        finally:
            connection.close()

        status_payload = {}
        deadline = time.time() + 5
        while time.time() < deadline:
            connection = HTTPConnection(parts.hostname, parts.port)
            try:
                connection.request("GET", "/api/render")
                response = connection.getresponse()
                status_payload = json.loads(response.read().decode("utf-8"))
            finally:
                connection.close()
            if status_payload.get("status") == "succeeded":
                break
            time.sleep(0.05)

    assert start_response.status == 202
    assert start_body["status"] == "running"
    assert status_payload["status"] == "succeeded"
    assert status_payload["error"] is None
    assert "Loading config from snapshot" in status_payload["logs"]
    assert "Finished clip-a.MP4" in status_payload["logs"]
    assert captured["note_text"] == "render draft"
    assert captured["distance_x"] == 96
    assert captured["snapshot_path"] != config_path
    assert config_path.read_text() == original_text


def test_api_render_rejects_second_start_while_job_is_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    release_render = Event()

    def blocking_run_pipeline(_snapshot_path: Path, only=None, *, progress=None) -> None:
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", blocking_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        first_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            first_connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            first_response = first_connection.getresponse()
            first_response.read()
        finally:
            first_connection.close()

        second_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            second_connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            second_response = second_connection.getresponse()
            second_body = json.loads(second_response.read().decode("utf-8"))
        finally:
            second_connection.close()

        release_render.set()

        deadline = time.time() + 5
        final_status = {}
        while time.time() < deadline:
            status_connection = HTTPConnection(parts.hostname, parts.port)
            try:
                status_connection.request("GET", "/api/render")
                status_response = status_connection.getresponse()
                final_status = json.loads(status_response.read().decode("utf-8"))
            finally:
                status_connection.close()
            if final_status.get("status") == "succeeded":
                break
            time.sleep(0.05)

    assert first_response.status == 202
    assert second_response.status == 409
    assert second_body == {"error": "render already in progress"}
    assert final_status["status"] == "succeeded"


def test_api_render_cancel_marks_job_canceled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    release_render = Event()
    render_entered = Event()

    def cancelable_run_pipeline(_snapshot_path: Path, only=None, *, progress=None, cancel_requested=None) -> None:
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        while cancel_requested is not None and not cancel_requested():
            if release_render.wait(timeout=0.05):
                break
        if cancel_requested is not None and cancel_requested():
            raise RenderJobCanceledError("render canceled")

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", cancelable_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        start_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            start_connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            start_response = start_connection.getresponse()
            start_body = json.loads(start_response.read().decode("utf-8"))
        finally:
            start_connection.close()

        assert start_response.status == 202
        assert start_body["status"] == "running"
        assert render_entered.wait(timeout=5)

        cancel_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            cancel_connection.request("POST", "/api/render/cancel")
            cancel_response = cancel_connection.getresponse()
            cancel_body = json.loads(cancel_response.read().decode("utf-8"))
        finally:
            cancel_connection.close()

        final_status = {}
        deadline = time.time() + 5
        while time.time() < deadline:
            status_connection = HTTPConnection(parts.hostname, parts.port)
            try:
                status_connection.request("GET", "/api/render")
                status_response = status_connection.getresponse()
                final_status = json.loads(status_response.read().decode("utf-8"))
            finally:
                status_connection.close()
            if final_status.get("status") == "canceled":
                break
            time.sleep(0.05)

    assert cancel_response.status == 200
    assert cancel_body["cancel_requested"] is True
    assert final_status["status"] == "canceled"
    assert final_status["cancel_requested"] is True
    assert final_status["error"] == "render canceled"
    assert "Loading config from snapshot" in final_status["logs"]


def test_api_render_reports_failed_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )

    def failing_run_pipeline(_snapshot_path: Path, only=None, *, progress=None) -> None:
        if progress is not None:
            progress("Loading config from snapshot")
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", failing_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            start_response = connection.getresponse()
            start_response.read()
        finally:
            connection.close()

        deadline = time.time() + 5
        status_payload = {}
        while time.time() < deadline:
            status_connection = HTTPConnection(parts.hostname, parts.port)
            try:
                status_connection.request("GET", "/api/render")
                status_response = status_connection.getresponse()
                status_payload = json.loads(status_response.read().decode("utf-8"))
            finally:
                status_connection.close()
            if status_payload.get("status") == "failed":
                break
            time.sleep(0.05)

    assert start_response.status == 202
    assert status_payload["status"] == "failed"
    assert status_payload["error"] == "ffmpeg exploded"
    assert "Loading config from snapshot" in status_payload["logs"]


def test_render_job_clears_preview_enabled_when_canceled_after_preview_publish(tmp_path: Path) -> None:
    manager = EditorRenderJobManager()
    render_entered = Event()
    release_render = Event()
    captured: dict[str, object] = {}

    @contextmanager
    def build_snapshot(_payload: dict[str, object]):
        snapshot_path = tmp_path / "snapshot.yaml"
        snapshot_path.write_text("snapshot", encoding="utf-8")
        yield snapshot_path

    def cancelable_run_pipeline(_snapshot_path: Path, only=None, *, progress=None, preview_update=None, cancel_requested=None) -> None:
        captured["preview_update"] = preview_update
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)
        if cancel_requested is not None and cancel_requested():
            raise RenderJobCanceledError("render canceled")

    manager.start({}, build_snapshot=build_snapshot, run_pipeline=cancelable_run_pipeline)
    assert render_entered.wait(timeout=5)

    preview_update = captured["preview_update"]
    assert callable(preview_update)
    assert manager.set_preview_enabled(True)["preview"]["enabled"] is True
    assert preview_update(b"published-preview") is True
    assert manager.cancel()["cancel_requested"] is True
    release_render.set()

    deadline = time.time() + 5
    final_status: dict[str, object] = {}
    while time.time() < deadline:
        final_status = manager.snapshot()
        if final_status.get("status") == "canceled":
            break
        time.sleep(0.05)

    assert final_status["status"] == "canceled"
    assert final_status["preview"]["enabled"] is False
    assert final_status["preview"]["available"] is True
    assert final_status["preview"]["version"] == 1


def test_render_job_clears_preview_enabled_when_failed_after_preview_publish(tmp_path: Path) -> None:
    manager = EditorRenderJobManager()
    render_entered = Event()
    release_render = Event()
    captured: dict[str, object] = {}

    @contextmanager
    def build_snapshot(_payload: dict[str, object]):
        snapshot_path = tmp_path / "snapshot.yaml"
        snapshot_path.write_text("snapshot", encoding="utf-8")
        yield snapshot_path

    def failing_run_pipeline(_snapshot_path: Path, only=None, *, progress=None, preview_update=None) -> None:
        captured["preview_update"] = preview_update
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)
        raise RuntimeError("ffmpeg exploded")

    manager.start({}, build_snapshot=build_snapshot, run_pipeline=failing_run_pipeline)
    assert render_entered.wait(timeout=5)

    preview_update = captured["preview_update"]
    assert callable(preview_update)
    assert manager.set_preview_enabled(True)["preview"]["enabled"] is True
    assert preview_update(b"published-preview") is True
    release_render.set()

    deadline = time.time() + 5
    final_status: dict[str, object] = {}
    while time.time() < deadline:
        final_status = manager.snapshot()
        if final_status.get("status") == "failed":
            break
        time.sleep(0.05)

    assert final_status["status"] == "failed"
    assert final_status["preview"]["enabled"] is False
    assert final_status["preview"]["available"] is True
    assert final_status["preview"]["version"] == 1


def test_render_job_clears_preview_enabled_when_succeeded_after_preview_publish(tmp_path: Path) -> None:
    manager = EditorRenderJobManager()
    render_entered = Event()
    release_render = Event()
    captured: dict[str, object] = {}

    @contextmanager
    def build_snapshot(_payload: dict[str, object]):
        snapshot_path = tmp_path / "snapshot.yaml"
        snapshot_path.write_text("snapshot", encoding="utf-8")
        yield snapshot_path

    def previewable_run_pipeline(_snapshot_path: Path, only=None, *, progress=None, preview_update=None) -> None:
        captured["preview_update"] = preview_update
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)

    manager.start({}, build_snapshot=build_snapshot, run_pipeline=previewable_run_pipeline)
    assert render_entered.wait(timeout=5)

    preview_update = captured["preview_update"]
    assert callable(preview_update)
    assert manager.set_preview_enabled(True)["preview"]["enabled"] is True
    assert preview_update(b"published-preview") is True
    release_render.set()

    deadline = time.time() + 5
    final_status: dict[str, object] = {}
    while time.time() < deadline:
        final_status = manager.snapshot()
        if final_status.get("status") == "succeeded":
            break
        time.sleep(0.05)

    assert final_status["status"] == "succeeded"
    assert final_status["preview"]["enabled"] is False
    assert final_status["preview"]["available"] is True
    assert final_status["preview"]["version"] == 1


def test_api_render_preview_toggle_and_fetches_latest_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    release_render = Event()
    render_entered = Event()
    captured: dict[str, object] = {}

    def previewable_run_pipeline(
        _snapshot_path: Path,
        only=None,
        *,
        progress=None,
        preview_update=None,
    ) -> None:
        captured["preview_update"] = preview_update
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", previewable_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        start_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            start_connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            start_response = start_connection.getresponse()
            start_body = json.loads(start_response.read().decode("utf-8"))
        finally:
            start_connection.close()

        assert start_response.status == 202
        assert start_body["status"] == "running"
        assert render_entered.wait(timeout=5)

        toggle_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            toggle_connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps({"enabled": True}),
                headers={"Content-Type": "application/json"},
            )
            toggle_response = toggle_connection.getresponse()
            toggle_body = json.loads(toggle_response.read().decode("utf-8"))
        finally:
            toggle_connection.close()

        status_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            status_connection.request("GET", "/api/render")
            status_response = status_connection.getresponse()
            status_body = json.loads(status_response.read().decode("utf-8"))
        finally:
            status_connection.close()

        preview_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            preview_connection.request("GET", "/api/render/preview.png")
            preview_response = preview_connection.getresponse()
            preview_body = preview_response.read()
        finally:
            preview_connection.close()

        preview_update = captured["preview_update"]
        assert callable(preview_update)
        preview_update(b"first-preview")

        refreshed_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            refreshed_connection.request("GET", "/api/render")
            refreshed_response = refreshed_connection.getresponse()
            refreshed_body = json.loads(refreshed_response.read().decode("utf-8"))
        finally:
            refreshed_connection.close()

        image_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            image_connection.request("GET", "/api/render/preview.png")
            image_response = image_connection.getresponse()
            image_body = image_response.read()
        finally:
            image_connection.close()

        disable_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            disable_connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps({"enabled": False}),
                headers={"Content-Type": "application/json"},
            )
            disable_response = disable_connection.getresponse()
            disable_body = json.loads(disable_response.read().decode("utf-8"))
        finally:
            disable_connection.close()

        preview_update(b"second-preview")

        disabled_status_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            disabled_status_connection.request("GET", "/api/render")
            disabled_status_response = disabled_status_connection.getresponse()
            disabled_status_body = json.loads(disabled_status_response.read().decode("utf-8"))
        finally:
            disabled_status_connection.close()

        disabled_image_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            disabled_image_connection.request("GET", "/api/render/preview.png")
            disabled_image_response = disabled_image_connection.getresponse()
            disabled_image_body = disabled_image_response.read()
        finally:
            disabled_image_connection.close()

        release_render.set()

        final_status = {}
        deadline = time.time() + 5
        while time.time() < deadline:
            final_connection = HTTPConnection(parts.hostname, parts.port)
            try:
                final_connection.request("GET", "/api/render")
                final_response = final_connection.getresponse()
                final_status = json.loads(final_response.read().decode("utf-8"))
            finally:
                final_connection.close()
            if final_status.get("status") == "succeeded":
                break
            time.sleep(0.05)

        final_image_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            final_image_connection.request("GET", "/api/render/preview.png")
            final_image_response = final_image_connection.getresponse()
            final_image_body = final_image_response.read()
        finally:
            final_image_connection.close()

    assert toggle_response.status == 200
    assert toggle_body["preview"] == {
        "enabled": True,
        "available": False,
        "version": 0,
        "updated_at": None,
    }
    assert status_body["preview"] == {
        "enabled": True,
        "available": False,
        "version": 0,
        "updated_at": None,
    }
    assert preview_response.status == 204
    assert preview_body == b""
    assert refreshed_body["preview"]["enabled"] is True
    assert refreshed_body["preview"]["available"] is True
    assert refreshed_body["preview"]["version"] == 1
    assert "seq" not in refreshed_body["preview"]
    assert isinstance(refreshed_body["preview"]["updated_at"], str)
    assert image_response.status == 200
    assert image_response.getheader("Content-Type") == "image/png"
    assert image_body == b"first-preview"
    assert disable_response.status == 200
    assert disable_body["preview"]["enabled"] is False
    assert disable_body["preview"]["available"] is True
    assert disable_body["preview"]["version"] == 1
    assert "seq" not in disable_body["preview"]
    assert isinstance(disable_body["preview"]["updated_at"], str)
    assert disabled_status_body["preview"]["enabled"] is False
    assert disabled_status_body["preview"]["available"] is True
    assert disabled_status_body["preview"]["version"] == 1
    assert "seq" not in disabled_status_body["preview"]
    assert isinstance(disabled_status_body["preview"]["updated_at"], str)
    assert disabled_image_response.status == 200
    assert disabled_image_body == b"first-preview"
    assert final_status["status"] == "succeeded"
    assert final_status["preview"]["enabled"] is False
    assert final_status["preview"]["available"] is True
    assert final_status["preview"]["version"] == 1
    assert "seq" not in final_status["preview"]
    assert isinstance(final_status["preview"]["updated_at"], str)
    assert final_image_response.status == 200
    assert final_image_body == b"first-preview"


def test_api_render_preview_toggle_rejects_missing_active_render(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps({"enabled": True}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    assert response.status == 409
    assert body == {"error": "no render is currently running"}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "preview payload must be a JSON object"),
        ({"enabled": "true"}, "preview enabled flag must be a boolean"),
    ],
)
def test_api_render_preview_rejects_malformed_payload_with_400(
    tmp_path: Path,
    payload,
    message: str,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    assert response.status == 400
    assert body == {"error": message}


def test_api_render_preview_allows_disable_after_render_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_path = tmp_path / "race.tcx"
    video_path = tmp_path / "clip-a.MP4"
    output_dir = tmp_path / "rendered"
    activity_path.write_text("<TrainingCenterDatabase />", encoding="utf-8")
    video_path.write_bytes(b"video-a")
    output_dir.mkdir()

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file=str(activity_path),
            video_globs=[str(video_path)],
            output_dir=str(output_dir),
            hud=broadcast_runner_preset(),
        ),
    )
    release_render = Event()
    render_entered = Event()

    def previewable_run_pipeline(
        _snapshot_path: Path,
        only=None,
        *,
        progress=None,
        preview_update=None,
    ) -> None:
        render_entered.set()
        if progress is not None:
            progress("Loading config from snapshot")
        release_render.wait(timeout=5)

    monkeypatch.setattr("race_overlay.editor_server.run_pipeline", previewable_run_pipeline, raising=False)

    payload = serialize_hud_config(broadcast_runner_preset())

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        start_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            start_connection.request(
                "POST",
                "/api/render",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            start_response = start_connection.getresponse()
            start_response.read()
        finally:
            start_connection.close()

        assert start_response.status == 202
        assert render_entered.wait(timeout=5)

        enable_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            enable_connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps({"enabled": True}),
                headers={"Content-Type": "application/json"},
            )
            enable_response = enable_connection.getresponse()
            enable_body = json.loads(enable_response.read().decode("utf-8"))
        finally:
            enable_connection.close()

        release_render.set()

        final_status = {}
        deadline = time.time() + 5
        while time.time() < deadline:
            status_connection = HTTPConnection(parts.hostname, parts.port)
            try:
                status_connection.request("GET", "/api/render")
                status_response = status_connection.getresponse()
                final_status = json.loads(status_response.read().decode("utf-8"))
            finally:
                status_connection.close()
            if final_status.get("status") == "succeeded":
                break
            time.sleep(0.05)

        disable_connection = HTTPConnection(parts.hostname, parts.port)
        try:
            disable_connection.request(
                "POST",
                "/api/render/preview",
                body=json.dumps({"enabled": False}),
                headers={"Content-Type": "application/json"},
            )
            disable_response = disable_connection.getresponse()
            disable_body = json.loads(disable_response.read().decode("utf-8"))
        finally:
            disable_connection.close()

    assert enable_response.status == 200
    assert enable_body["preview"] == {
        "enabled": True,
        "available": False,
        "version": 0,
        "updated_at": None,
    }
    assert final_status["status"] == "succeeded"
    assert disable_response.status == 200
    assert disable_body["preview"] == {
        "enabled": False,
        "available": False,
        "version": 0,
        "updated_at": None,
    }


def test_api_config_rejects_stale_hud_save_with_409(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            state_response = connection.getresponse()
            state = json.loads(state_response.read().decode("utf-8"))
        finally:
            connection.close()

        updated = load_config(config_path)
        updated.hud.theme.note_text = "newer edit"
        save_config(config_path, updated)

        stale_payload = dict(state["hud"])
        stale_payload["theme"] = dict(state["hud"]["theme"])
        stale_payload["widgets"] = [
            {**widget, "bindings": dict(widget["bindings"]), "style": dict(widget["style"])}
            for widget in state["hud"]["widgets"]
        ]
        stale_payload["revision"] = state["revision"]
        stale_payload["theme"]["note_text"] = "older edit"

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(stale_payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 409
    assert "stale HUD" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.theme.note_text == "newer edit"


def test_api_state_exposes_project_config_context_and_candidates(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "rendered").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["videos/clip-a.MP4", "videos/clip-b.mov"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    assert response.status == 200
    assert body["project"]["config_path"] == {"name": "overlay.yaml", "path": str(config_path)}
    assert body["project"]["activity_file"] == "activities/race.tcx"
    assert body["project"]["video_globs"] == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert body["project"]["output_dir"] == "rendered"
    assert body["project"]["choices"]["activity_files"] == ["activities/race.tcx"]
    assert body["project"]["choices"]["video_files"] == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert "rendered" in body["project"]["choices"]["output_dirs"]
    assert "exports" in body["project"]["choices"]["output_dirs"]


def test_api_state_exposes_named_presets(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    active_hud = broadcast_runner_preset()
    night_hud = broadcast_runner_preset()
    night_hud.preset = "night-run"
    night_hud.theme.note_text = "Night race"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=active_hud,
            hud_presets={
                "broadcast-runner": active_hud,
                "night-run": night_hud,
            },
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    assert response.status == 200
    assert body["presets"] == {
        "active": "broadcast-runner",
        "names": ["broadcast-runner", "night-run"],
    }


def test_api_presets_save_and_select_persist_named_presets(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            state_response = connection.getresponse()
            state = json.loads(state_response.read().decode("utf-8"))
        finally:
            connection.close()

        save_payload = dict(state["hud"])
        save_payload["theme"] = dict(state["hud"]["theme"])
        save_payload["widgets"] = [
            {**widget, "bindings": dict(widget["bindings"]), "style": dict(widget["style"])}
            for widget in state["hud"]["widgets"]
        ]
        save_payload["theme"]["note_text"] = "Night race"

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/presets/save",
                body=json.dumps(
                    {
                        "name": "night-run",
                        "hud": save_payload,
                        "revision": state["revision"],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            save_response = connection.getresponse()
            save_response.read()
        finally:
            connection.close()

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/presets/select",
                body=json.dumps({"name": "broadcast-runner"}),
                headers={"Content-Type": "application/json"},
            )
            select_response = connection.getresponse()
            select_response.read()
        finally:
            connection.close()

    reloaded = load_config(config_path)

    assert save_response.status == 204
    assert select_response.status == 204
    assert set(reloaded.hud_presets) == {"broadcast-runner", "night-run"}
    assert reloaded.hud_presets["night-run"].theme.note_text == "Night race"
    assert reloaded.hud.preset == "broadcast-runner"


def test_api_project_updates_activity_video_paths_and_output_dir(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "rendered").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "activities" / "backup.fit").write_bytes(b"FIT")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["videos/clip-a.MP4"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project",
                body=json.dumps(
                    {
                        "activity_file": "activities/backup.fit",
                        "video_globs": ["videos/clip-a.MP4", "videos/clip-b.mov"],
                        "output_dir": "exports",
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    assert response.status == 204
    reloaded = load_config(config_path)
    assert reloaded.activity_file == "activities/backup.fit"
    assert reloaded.video_globs == ["videos/clip-a.MP4", "videos/clip-b.mov"]
    assert reloaded.output_dir == "exports"


def test_api_project_accepts_partial_updates_without_revalidating_untouched_fields(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "activities" / "backup.fit").write_bytes(b"FIT")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["*.MP4", "*.mov"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project",
                body=json.dumps({"activity_file": "activities/backup.fit"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    assert response.status == 204
    reloaded = load_config(config_path)
    assert reloaded.activity_file == "activities/backup.fit"
    assert reloaded.video_globs == ["*.MP4", "*.mov"]
    assert reloaded.output_dir == "rendered"


def test_api_project_accepts_browser_selected_video_names_without_config_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")
    (tmp_path / "videos" / "clip-b.mov").write_bytes(b"video-b")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["*.MP4", "*.mov"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project",
                body=json.dumps({"video_globs": ["clip-a.MP4", "clip-b.mov"]}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    assert response.status == 204
    reloaded = load_config(config_path)
    assert reloaded.video_globs == ["clip-a.MP4", "clip-b.mov"]


def test_api_project_accepts_browser_selected_output_dir_without_config_relative_path(tmp_path: Path) -> None:
    (tmp_path / "activities").mkdir()
    (tmp_path / "videos").mkdir()
    (tmp_path / "activities" / "race.tcx").write_text("<TrainingCenterDatabase />", encoding="utf-8")
    (tmp_path / "videos" / "clip-a.MP4").write_bytes(b"video-a")

    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activities/race.tcx",
            video_globs=["clip-a.MP4"],
            output_dir="rendered",
            hud=broadcast_runner_preset(),
        ),
    )

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project",
                body=json.dumps({"output_dir": "chosen-output"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    assert response.status == 204
    reloaded = load_config(config_path)
    assert reloaded.output_dir == "chosen-output"


@pytest.mark.parametrize(
    ("field", "picked_value"),
    [
        ("activity_file", "/Users/dotennin-mac14/Downloads/runs/race.tcx"),
        ("video_globs", ["/Users/dotennin-mac14/Movies/clip-a.MP4", "/Users/dotennin-mac14/Movies/clip-b.mov"]),
        ("output_dir", "/Users/dotennin-mac14/Downloads/rendered"),
    ],
)
def test_api_project_picker_returns_native_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    picked_value: str | list[str],
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    def fake_picker(requested_field: str) -> dict[str, object]:
        assert requested_field == field
        return {"field": field, "value": picked_value}

    monkeypatch.setattr("race_overlay.editor_server.pick_project_config_value", fake_picker, raising=False)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project/picker",
                body=json.dumps({"field": field}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 200
    assert json.loads(body.decode("utf-8")) == {"field": field, "value": picked_value}


def test_api_project_picker_returns_structured_error_when_native_picker_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    def raise_unavailable(_field: str) -> dict[str, object]:
        raise NativePickerUnavailableError("native picker is unavailable in this environment")

    monkeypatch.setattr("race_overlay.editor_server.pick_project_config_value", raise_unavailable, raising=False)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/project/picker",
                body=json.dumps({"field": "output_dir"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 501
    assert json.loads(body.decode("utf-8")) == {"error": "native picker is unavailable in this environment"}


def test_pick_project_config_value_uses_external_native_picker_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from race_overlay import editor_server as es

    class FakeCompletedProcess:
        returncode = 0
        stdout = '"/Users/dotennin-mac14/Downloads/runs/race.tcx"\n'
        stderr = ""

    recorded_commands: list[list[str]] = []

    def fake_run(command, *, capture_output, text, check):
        recorded_commands.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr(es.subprocess, "run", fake_run)

    selection = es.pick_project_config_value("activity_file")

    assert selection == {
        "field": "activity_file",
        "value": "/Users/dotennin-mac14/Downloads/runs/race.tcx",
    }
    assert recorded_commands and recorded_commands[0][0] == "osascript"


def test_api_config_returns_structured_error_when_save_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    def raise_permission_error(*args, **kwargs) -> None:
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr("race_overlay.editor_preview.save_config", raise_permission_error)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(
                    {
                        **serialize_hud_config(broadcast_runner_preset()),
                        "revision": build_editor_state(load_config(config_path), width=1280, height=720)["revision"],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 500
    assert "read-only filesystem" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_api_config_returns_structured_error_when_save_reload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_load_config = load_config
    call_count = 0

    def raise_yaml_error(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise yaml.YAMLError("concurrent write truncated file")
        return original_load_config(*args, **kwargs)

    monkeypatch.setattr("race_overlay.editor_preview.load_config", raise_yaml_error)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(
                    {
                        **serialize_hud_config(broadcast_runner_preset()),
                        "revision": build_editor_state(load_config(config_path), width=1280, height=720)["revision"],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config file is not valid YAML" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_api_config_rejects_nan_values_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    pace_chip = next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip")
    pace_chip["style"]["label"] = float("nan")

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert json.loads(body.decode("utf-8"))["error"] == "invalid JSON payload"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "pace-chip").update(anchor="center"),
            "unsupported anchor",
        ),
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "distance-ruler").update(width=160),
            "minimum width",
        ),
    ],
)
def test_api_config_rejects_renderer_invalid_widgets_with_400(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    mutate(payload)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert message in json.loads(body.decode("utf-8"))["error"]
    assert config_path.read_text() == original_text

def test_api_config_rejects_invalid_content_length_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        with socket.create_connection((parts.hostname, parts.port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/config HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: abc\r\n"
                b"Connection: close\r\n\r\n"
                b"{}"
            )
            response = b""
            while chunk := connection.recv(4096):
                response += chunk

    assert b" 400 " in response.splitlines()[0]
    assert b'"error": "invalid Content-Length header"' in response


def test_api_config_rejects_negative_content_length_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        with socket.create_connection((parts.hostname, parts.port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/config HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: -1\r\n"
                b"Connection: close\r\n\r\n"
                b"{}"
            )
            response = b""
            while chunk := connection.recv(4096):
                response += chunk

    assert b" 400 " in response.splitlines()[0]
    assert b'"error": "invalid Content-Length header"' in response


def test_api_state_returns_structured_error_when_config_becomes_malformed(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        config_path.write_text("hud: [\n")
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config" in json.loads(body.decode("utf-8"))["error"]


def test_launch_editor_rejects_directory_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.mkdir()

    with pytest.raises(ValueError, match="config file"):
        launch_editor(config_path, width=1280, height=720)


def test_editor_shell_contains_overlay_library_rail_and_hidden_help_modal() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")

    assert 'id="overlay-library-panel"' in html
    assert 'id="canvas-panel"' in html
    assert 'id="inspector-panel"' in html
    assert 'id="overlay-library-list"' in html
    assert 'id="widget-list"' in html
    assert "Layers" in html
    assert 'id="theme-defaults-toggle"' in html
    assert 'id="theme-defaults-panel"' in html
    assert 'id="help-button"' in html
    assert 'id="help-modal"' in html
    assert "hidden" in html.split('id="help-modal"', 1)[1]


def test_editor_shell_contains_project_config_section_and_left_accordions() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")

    assert 'id="project-config-panel"' in html
    assert 'id="project-activity-file"' in html
    assert 'id="project-video-globs"' in html
    assert 'id="project-output-dir"' in html
    assert 'id="browse-toggle"' in html
    assert 'id="browse-panel"' in html
    assert 'id="layers-toggle"' in html
    assert 'id="layers-panel"' in html


def test_editor_script_uses_preview_endpoint_for_live_draft_updates() -> None:
    script = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/preview"' in script
    assert "draftState" in script
    assert "help-modal" in script


def test_editor_script_refreshes_preview_from_active_input_events() -> None:
    script = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    text_builder = script.split("function buildTextInput", 1)[1].split("function buildNumberInput", 1)[0]
    number_builder = script.split("function buildNumberInput", 1)[1].split("function buildCheckbox", 1)[0]
    select_builder = script.split("function buildSelectInput", 1)[1].split("function buildRgbaInput", 1)[0]

    assert 'addEventListener("input"' in text_builder
    assert 'addEventListener("input"' in number_builder
    assert 'addEventListener("input"' in select_builder
    assert 'addEventListener("change"' in number_builder


def test_editor_script_throttles_preview_during_drag_and_flushes_on_pointerup() -> None:
    script = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "const PREVIEW_DRAG_THROTTLE_MS = 90;" in script
    assert "let dragPreviewTimer = null;" in script
    assert "let lastPreviewRefreshAt = 0;" in script
    assert "let dragPreviewDirty = false;" in script
    assert "function schedulePreviewRefresh({ immediate = false, drag = false } = {})" in script
    assert "lastPreviewRefreshAt = Date.now();" in script
    assert "schedulePreviewRefresh({ drag: true });" in script
    assert "widget.x === nextPatch.x" in script
    assert "moved: false," in script
    assert "if (interaction.moved && (dragPreviewTimer || dragPreviewDirty)) {" in script
    assert "Math.max(PREVIEW_DRAG_THROTTLE_MS - (now - lastPreviewRefreshAt), 0)" in script
    assert "schedulePreviewRefresh({ immediate: true });" in script


def test_api_state_returns_structured_error_when_config_path_becomes_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        config_path.unlink()
        config_path.mkdir()
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config file" in json.loads(body.decode("utf-8"))["error"]


def test_editor_app_surfaces_api_state_errors_without_throwing() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    app_path = repo_root / "src" / "race_overlay" / "editor_assets" / "app.js"
    script = f"""
import fs from "node:fs";
import vm from "node:vm";

const elements = new Map();

function createElement(id) {{
  return {{
    id,
    value: "",
    checked: false,
    hidden: true,
    disabled: false,
    innerHTML: "",
    textContent: "",
    src: "",
    className: "",
    dataset: {{}},
    appendChild() {{}},
    addEventListener() {{}},
    removeAttribute(name) {{
      this[name] = "";
    }},
  }};
}}

const document = {{
  createElement(tagName) {{
    return createElement(tagName);
  }},
  getElementById(id) {{
    if (!elements.has(id)) {{
      elements.set(id, createElement(id));
    }}
    return elements.get(id);
  }},
  querySelectorAll() {{
    return [];
  }},
}};

let unhandled = null;
process.on("unhandledRejection", (error) => {{
  unhandled = error instanceof Error ? error.message : String(error);
}});

globalThis.document = document;
globalThis.window = {{ alert() {{}} }};
globalThis.fetch = async () => ({{
  ok: false,
  async json() {{
    return {{ error: "config file is not readable: permission denied" }};
  }},
}});

const source = fs.readFileSync({json.dumps(str(app_path))}, "utf8");
vm.runInThisContext(source, {{ filename: {json.dumps(str(app_path))} }});
await new Promise((resolve) => setTimeout(resolve, 0));

console.log(JSON.stringify({{
  statusText: document.getElementById("status-message").textContent,
  statusHidden: document.getElementById("status-message").hidden,
  previewSrc: document.getElementById("preview").src,
  widgetList: document.getElementById("widget-list").innerHTML,
  saveDisabled: document.getElementById("save-button").disabled,
  unhandled,
}}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    payload = json.loads(result.stdout.strip())

    assert payload["unhandled"] is None
    assert payload["statusText"] == "config file is not readable: permission denied"
    assert payload["statusHidden"] is False
    assert payload["previewSrc"] == ""
    assert payload["widgetList"] == ""
    assert payload["saveDisabled"] is True


def test_build_editor_state_hides_removed_theme_colors_and_exposes_route_map_fields() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert "panel_rgba" not in state["schema"]["theme"]
    assert "accent_rgba" not in state["schema"]["theme"]

    route_map_style = state["schema"]["widgets"]["route-map"]["style"]
    assert route_map_style["shape"] == {
        "kind": "enum",
        "label": "Shape",
        "options": ["circle", "rounded-rect", "square"],
    }
    assert route_map_style["background_rgba"] == {"kind": "rgba", "label": "Background RGBA"}
    assert route_map_style["completed_rgba"] == {"kind": "rgba", "label": "Completed RGBA"}
    assert route_map_style["remaining_rgba"] == {"kind": "rgba", "label": "Remaining RGBA"}
    assert route_map_style["zoom_percent"] == {
        "kind": "range",
        "label": "Route scale",
        "min": 70,
        "max": 140,
        "step": 1,
        "suffix": "%",
    }


def test_build_editor_state_uses_track_style_route_map_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    route_points = state["preview"]["route_points"]
    assert len(route_points) >= 8
    assert route_points[0] != route_points[1]
    assert len({tuple(point) for point in route_points}) >= 8
    turn_cross_products = [
        (mid[0] - start[0]) * (end[1] - mid[1]) - (mid[1] - start[1]) * (end[0] - mid[0])
        for start, mid, end in zip(route_points, route_points[1:], route_points[2:])
    ]
    assert any(cross != 0 for cross in turn_cross_products), "expected a non-straight track-style route preview"


def test_editor_asset_uses_color_picker_controls_for_rgba_fields() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert 'input.type = "color"' in app_js
    assert 'className = "color-alpha-input"' in app_js
    assert "function buildRgbaInput(" not in app_js
    assert ".color-alpha-input" in css


def test_editor_asset_uses_slider_controls_for_range_fields() -> None:
    from importlib.resources import files

    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert "function buildRangeInput(" in app_js
    assert 'className = "range-input"' in app_js
    assert 'input.type = "range"' in app_js
    assert 'metadata?.kind === "range"' in app_js
    assert "buildRangeInput(value, onChange, {" in app_js
    assert "buildRangeInput(value, onChange, metadata, onInput)" not in app_js
    assert 'options.suffix ?? ""' in app_js
    assert ".range-input" in css


def test_editor_assets_remove_duplicate_layer_actions_and_overlay_titles() -> None:
    from importlib.resources import files

    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert 'textContent = "▲"' not in app_js
    assert 'textContent = "▼"' not in app_js
    assert 'widget-overlay__label' not in app_js


def test_editor_asset_defines_drag_snapping_helpers() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "const GRID_SNAP_SIZE = 8" in app_js
    assert "function collectSnapGuides(" in app_js
    assert "function snapRectToGuides(" in app_js
    assert "function renderSnapGuides(" in app_js


def test_editor_assets_support_project_saves_shared_accordions_and_style_first_inspector() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert 'fetch("/api/project"' in app_js
    assert 'fetch("/api/project/picker"' in app_js
    assert "function renderProjectControls()" in app_js
    assert "function saveProjectState(" in app_js
    assert "function pickProjectPath(" in app_js
    assert "function syncAccordionPanels(" in app_js
    assert 'setStatusMessage("Saved project settings.", "info")' in app_js
    assert 'buildProjectPickerButton("Choose activity file", "activity_file"' in app_js
    assert 'buildProjectPickerButton("Choose video files", "video_globs"' in app_js
    assert 'buildProjectPickerButton("Choose output folder", "output_dir"' in app_js
    assert 'input.type = "file"' not in app_js
    assert "showDirectoryPicker" not in app_js
    assert 'setAttribute("webkitdirectory", "")' not in app_js
    assert app_js.index('elements.inspectorContent.appendChild(styleCard);') < app_js.index(
        'elements.inspectorContent.appendChild(geometryCard);'
    )
    assert 'class="accordion-panel"' in html
    assert ".accordion-panel" in css
    assert "max-height" in css
    assert "overflow-x: hidden;" in css
    assert "project-config-path" not in html


def test_editor_assets_expose_render_panel_controls() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert 'id="render-button"' in html
    assert 'id="render-panel"' in html
    assert 'id="render-minimize-button"' in html
    assert 'id="render-drawer-tab"' in html
    assert 'id="render-status"' in html
    assert 'id="render-stage"' in html
    assert 'id="render-console"' in html
    assert 'id="render-progress"' in html
    assert 'id="render-cancel-button"' in html
    assert html.index('id="canvas-stage"') < html.index('id="render-panel"')
    assert 'fetch("/api/render"' in app_js
    assert 'fetch("/api/render/cancel"' in app_js
    assert "function startRenderJob(" in app_js
    assert "function pollRenderStatus(" in app_js
    assert "function cancelRenderJob(" in app_js
    assert "renderButton" in app_js
    assert "renderCancelButton" in app_js
    assert "renderProgress" in app_js
    assert "renderPercent" in app_js
    assert "renderMinimizeButton" in app_js
    assert "renderDrawerTab" in app_js
    assert "window.confirm(\"Cancel current render? Partial output will be kept.\")" in app_js
    assert "renderPanel" in app_js
    assert "#render-panel" in css
    assert ".render-bottom-sheet__minimize" in css
    assert ".render-drawer-tab" in css
    assert ".render-console" in css
    assert "#render-progress" in css
    assert "#render-cancel-button" in css


def test_editor_assets_expose_render_preview_controls() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert 'id="render-preview-toggle"' in html
    assert 'class="render-preview-controls"' in html
    assert 'class="render-preview-toggle"' in html
    assert 'id="render-preview-modal"' in html
    assert 'id="render-preview-close-button"' in html
    assert 'id="render-preview-image"' in html
    assert 'id="render-preview-status"' in html
    assert 'Show preview' in html
    assert 'fetch("/api/render/preview"' in app_js
    assert 'fetch(`/api/render/preview.png?v=${version}`)' in app_js
    assert "renderPreviewOpen" in app_js
    assert "renderPreviewVersion" in app_js
    assert "renderPreviewObjectUrl" in app_js
    assert "showModal()" in app_js
    assert "closeRenderPreview()" in app_js
    assert "clearRenderPreviewPoll()" in app_js
    assert "URL.revokeObjectURL(renderPreviewObjectUrl)" in app_js
    assert ".render-preview-controls" in css
    assert ".render-preview-toggle" in css
    assert ".render-preview-modal" in css
    assert ".render-preview-modal__image" in css
    assert ".render-preview-modal__status" in css


def test_editor_app_closes_render_preview_popup_on_escape() -> None:
    app_js_path = files("race_overlay.editor_assets").joinpath("app.js")
    script = f"""
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync({json.dumps(str(app_js_path))}, "utf8")
  .split("updateSaveButtonState();\\nupdateRenderButtonState();")[0]
  + '\\n;globalThis.__test = {{\\n'
  + '  openRenderPreview,\\n'
  + '  closeRenderPreview,\\n'
  + '  isRenderPreviewOpen() {{ return renderPreviewOpen; }},\\n'
  + '  getDialog() {{ return elements.renderPreviewModal; }},\\n'
  + '}};';

function makeElement(id) {{
  return {{
    id,
    hidden: false,
    dataset: {{}},
    style: {{}},
    textContent: "",
    open: false,
    addEventListener(type, handler) {{
      this._handlers ??= {{}};
      this._handlers[type] = handler;
    }},
    dispatch(type, event) {{
      if (this._handlers && this._handlers[type]) {{
        this._handlers[type](event);
      }}
    }},
    setAttribute() {{}},
    removeAttribute() {{}},
    appendChild() {{}},
    append() {{}},
    replaceChildren() {{}},
    showModal() {{ this.open = true; }},
    close() {{ this.open = false; }},
    getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 100, height: 100 }}; }},
  }};
}}

const elements = new Map();
const listeners = {{}};
const stub = new Proxy({{}}, {{
  get(_, prop) {{
    if (!elements.has(prop)) {{
      elements.set(prop, makeElement(prop));
    }}
    return elements.get(prop);
  }},
}});

const context = {{
  console,
  URL: {{ createObjectURL() {{ return "blob://frame"; }}, revokeObjectURL() {{}} }},
  Blob,
  Date,
  setTimeout,
  clearTimeout,
  window: {{
    setTimeout,
    clearTimeout,
    addEventListener(type, handler) {{
      listeners[type] = handler;
    }},
    confirm() {{ return true; }},
  }},
  document: {{
    getElementById(id) {{
      return stub[id];
    }},
    addEventListener(type, handler) {{
      listeners[`document:${{type}}`] = handler;
    }},
  }},
  fetch: async () => ({{ ok: true, status: 200, json: async () => ({{ preview: {{ enabled: false, available: false, version: 0 }} }}) }}),
}};

vm.createContext(context);
vm.runInContext(source, context);

context.__test.openRenderPreview();
if (!context.__test.isRenderPreviewOpen() || !context.__test.getDialog().open) {{
  throw new Error("preview did not open");
}}

listeners["document:keydown"]({{ key: "Escape", preventDefault() {{}} }});

if (context.__test.isRenderPreviewOpen() || context.__test.getDialog().open) {{
  throw new Error("preview did not close on escape");
}}
"""

    completed = subprocess.run(["node", "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_editor_app_keeps_previous_render_preview_visible_when_render_restarts() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    start_block = app_js.split("async function startRenderJob()", 1)[1].split("async function cancelRenderJob()", 1)[0]

    assert "renderPreviewVersion = 0;" in start_block
    assert "clearRenderPreviewPoll();" in start_block
    assert "clearRenderPreviewUrl();" not in start_block


def test_editor_app_discards_stale_render_preview_response_after_invalidation() -> None:
    app_js_path = files("race_overlay.editor_assets").joinpath("app.js")
    script = f"""
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync({json.dumps(str(app_js_path))}, "utf8")
  .split("updateSaveButtonState();\\nupdateRenderButtonState();")[0]
  + '\\n;globalThis.__test = {{\\n'
  + '  refreshRenderPreview,\\n'
  + '  clearRenderPreviewPoll,\\n'
  + '  setState(next) {{\\n'
  + '    if ("renderState" in next) renderState = next.renderState;\\n'
  + '    if ("renderPreviewOpen" in next) renderPreviewOpen = next.renderPreviewOpen;\\n'
  + '    if ("renderPanelMinimized" in next) renderPanelMinimized = next.renderPanelMinimized;\\n'
  + '    if ("renderPreviewVersion" in next) renderPreviewVersion = next.renderPreviewVersion;\\n'
  + '    if ("renderPreviewObjectUrl" in next) renderPreviewObjectUrl = next.renderPreviewObjectUrl;\\n'
  + '  }},\\n'
  + '  getImage() {{ return elements.renderPreviewImage; }},\\n'
  + '  getVersion() {{ return renderPreviewVersion; }},\\n'
  + '}};';

function makeElement(id) {{
  return {{
    id,
    hidden: false,
    dataset: {{}},
    style: {{}},
    textContent: "",
    value: "",
    src: "initial://frame",
    addEventListener() {{}},
    setAttribute() {{}},
    removeAttribute() {{}},
    appendChild() {{}},
    append() {{}},
    replaceChildren() {{}},
    getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 100, height: 100 }}; }},
  }};
}}

const elements = new Map();
const stub = new Proxy({{}}, {{
  get(_, prop) {{
    if (!elements.has(prop)) {{
      elements.set(prop, makeElement(prop));
    }}
    return elements.get(prop);
  }},
}});

let createCalls = 0;
let releaseFetch;
const context = {{
  console,
  URL: {{
    createObjectURL() {{
      createCalls += 1;
      return `blob://frame-${{createCalls}}`;
    }},
    revokeObjectURL() {{}},
  }},
  Blob,
  Date,
  setTimeout,
  clearTimeout,
  window: {{ setTimeout, clearTimeout, addEventListener() {{}}, confirm() {{ return true; }} }},
  document: {{
    getElementById(id) {{
      return stub[id];
    }},
    addEventListener() {{}},
  }},
  confirm() {{ return true; }},
  fetch: () => new Promise((resolve) => {{
    releaseFetch = () => resolve({{
      ok: true,
      status: 200,
      blob: async () => new Blob(["frame"]),
    }});
  }}),
}};

vm.createContext(context);
vm.runInContext(source, context);

context.__test.setState({{
  renderState: {{ status: "running", preview: {{ available: true, version: 7 }}, logs: [] }},
  renderPreviewOpen: true,
  renderPanelMinimized: false,
  renderPreviewVersion: 6,
  renderPreviewObjectUrl: "",
}});

(async () => {{
  const request = context.__test.refreshRenderPreview(7);
  context.__test.clearRenderPreviewPoll();
  releaseFetch();
  await request;
  const result = {{
    src: context.__test.getImage().src,
    version: context.__test.getVersion(),
    createCalls,
  }};
  if (result.src !== "initial://frame" || result.version !== 6 || result.createCalls !== 0) {{
    throw new Error(JSON.stringify(result));
  }}
  console.log(JSON.stringify(result));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""

    completed = subprocess.run(["node", "-e", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_load_state_reenables_render_button_after_hud_load() -> None:
    from importlib.resources import files

    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    success_block = app_js.split("async function loadState()", 1)[1].split("catch (error)", 1)[0]
    assert "updateRenderButtonState();" in success_block


def test_editor_shell_uses_canvas_first_layout_copy() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "Canvas-first designer" in html
    assert "Add overlay" in html
    assert "Layers" in html
    assert "Theme defaults" in html
    assert "grid-template-columns: 280px minmax(0, 1fr) 360px;" in css
    assert "function renderWidgetSelection()" in app_js
    assert "function renderOverlayLibrary()" in app_js
    assert "function toggleThemeDefaults(" in app_js
    assert "layer-item__actions" not in app_js
