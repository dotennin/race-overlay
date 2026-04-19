from pathlib import Path

from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import build_editor_state, save_editor_payload
from race_overlay.hud_presets import broadcast_runner_preset


def test_build_editor_state_exposes_widgets_for_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["hud"]["preset"] == "broadcast-runner"
    assert any(widget["id"] == "hero-pace" for widget in state["hud"]["widgets"])
    assert state["preview"]["width"] == 1280


def test_save_editor_payload_updates_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = {
        "preset": "broadcast-runner",
        "theme": {"note_text": "Kasumigaura"},
        "widgets": [
            {
                "id": "hero-pace",
                "type": "hero_metric",
                "bindings": {"value": "pace_seconds_per_km"},
                "anchor": "top-left",
                "x": 48,
                "y": 180,
                "width": 336,
                "height": 116,
                "z_index": 20,
                "visible": True,
                "style": {"label": "Pace"},
            }
        ],
    }

    save_editor_payload(config_path, payload)
    reloaded = load_config(config_path)

    assert reloaded.hud.theme.note_text == "Kasumigaura"
    assert reloaded.hud.widgets[0].x == 48
