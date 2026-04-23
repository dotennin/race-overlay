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
    save_editor_payload,
)
from race_overlay.editor_server import _ACTIVE_SERVERS, _ACTIVE_THREADS, launch_editor
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
    assert ruler_style["font_family"]["options"] == list(HUD_FONT_FAMILY_OPTIONS)
    assert ruler_style["font_weight"]["options"] == ["regular", "bold"]
    assert ruler_style["font_size_px"]["min"] == 8
    assert ruler_style["show_unit"] == {"kind": "boolean", "label": "Show unit suffix"}
    assert ruler_style["show_current_value"] == {"kind": "boolean", "label": "Show current value"}
    assert ruler_style["show_total_value"] == {"kind": "boolean", "label": "Show total value"}
    assert ruler_style["current_font_size_px"] == {"kind": "integer", "label": "Current font size", "min": 8}
    assert ruler_style["fill_rgba"] == {"kind": "rgba", "label": "Fill RGBA"}
    assert ruler_style["rail_rgba"] == {"kind": "rgba", "label": "Rail RGBA"}
    assert ruler_style["tick_rgba"] == {"kind": "rgba", "label": "Tick RGBA"}

    pace_chip_style = state["schema"]["widgets"]["pace-chip"]["style"]
    assert pace_chip_style["font_family"]["options"] == list(HUD_FONT_FAMILY_OPTIONS)
    assert pace_chip_style["font_weight"]["options"] == ["regular", "bold"]
    assert pace_chip_style["font_size_px"]["min"] == 8
    assert pace_chip_style["show_unit"] == {"kind": "boolean", "label": "Show unit suffix"}


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
    assert route_map_style["show_heading_arrow"] == {"kind": "boolean", "label": "Show heading arrow"}

    time_card_style = state["schema"]["widgets"]["time-card"]["style"]
    assert time_card_style["variant"] == {"kind": "text", "label": "Variant"}
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
    route_map["style"].update(show_north_marker=True, show_bearing_label=False, show_heading_arrow=True)
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
    assert route_map_reloaded.style["show_heading_arrow"] is True
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
    pace_chip["style"].update(font_family="mono", font_weight="bold", font_size_px=26, show_unit=False)
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
    assert reloaded_pace_chip.style["font_family"] == "mono"
    assert reloaded_pace_chip.style["font_weight"] == "bold"
    assert reloaded_pace_chip.style["font_size_px"] == 26
    assert reloaded_pace_chip.style["show_unit"] is False
    assert reloaded_ruler.style["show_current_value"] is False
    assert reloaded_ruler.style["show_total_value"] is False
    assert reloaded_ruler.style["fill_rgba"] == [34, 255, 138, 255]
    assert reloaded_ruler.style["rail_rgba"] == [8, 12, 20, 220]
    assert reloaded_ruler.style["tick_rgba"] == [230, 238, 245, 168]


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
        {
            "preset": "broadcast-runner",
            "theme": serialize_hud_config(broadcast_runner_preset())["theme"],
            "widgets": [serialize_hud_config(broadcast_runner_preset())["widgets"][0]],
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
    assert 'id="theme-controls"' in body


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


def test_editor_shell_contains_two_pane_workspace_and_hidden_help_modal() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")

    assert 'id="canvas-panel"' in html
    assert 'id="inspector-panel"' in html
    assert 'id="widget-list"' not in html
    assert "Widgets" not in html
    assert 'id="help-button"' in html
    assert 'id="help-modal"' in html
    assert "hidden" in html.split('id="help-modal"', 1)[1]


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


def test_editor_asset_uses_color_picker_controls_for_rgba_fields() -> None:
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")

    assert 'input.type = "color"' in app_js
    assert 'className = "color-alpha-input"' in app_js
    assert "function buildRgbaInput(" not in app_js
    assert ".color-alpha-input" in css


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


def test_editor_shell_uses_canvas_first_layout_copy() -> None:
    html = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8")
    css = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8")
    app_js = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8")

    assert "Canvas-first designer" in html
    assert "Selection rail" not in html
    assert "Widgets" not in html
    assert "grid-template-columns: minmax(0, 1fr) 360px;" in css
    assert "function renderWidgetSelection()" in app_js
    assert "layer-item__actions" not in app_js
