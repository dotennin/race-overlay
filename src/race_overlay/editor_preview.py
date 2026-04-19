from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from race_overlay.config import ProjectConfig, _load_hud_config, load_config, save_config
from race_overlay.hud import render_hud_frame
from race_overlay.hud_schema import HudConfig, serialize_hud_config
from race_overlay.models import HudSample


def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )


def build_editor_state(config: ProjectConfig, width: int, height: int) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "preview": {
            "width": width,
            "height": height,
            "route_points": [[36.0832, 140.2106], [36.0834, 140.2108]],
        },
    }


def save_editor_payload(config_path: Path, payload: dict[str, object]) -> None:
    config = load_config(config_path)
    _validate_complete_hud_payload(config.hud, payload)
    config.hud = _load_hud_config(payload, require_complete=True)
    save_config(config_path, config)


def render_preview_png(config: ProjectConfig, width: int, height: int) -> bytes:
    _validate_preview_dimensions(width, height)
    image = render_hud_frame(
        width,
        height,
        _sample_hud_value(),
        [(36.0832, 140.2106), (36.0834, 140.2108)],
        config.hud,
        6852,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _validate_preview_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("preview width and height must be greater than 0")


def _validate_complete_hud_payload(existing_hud: HudConfig, payload: dict[str, object]) -> None:
    expected = serialize_hud_config(existing_hud)
    if set(payload) != set(expected):
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
    expected_theme_keys = set(expected["theme"])
    theme_payload = payload.get("theme")
    if not isinstance(theme_payload, dict) or set(theme_payload) != expected_theme_keys:
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")

    widgets_payload = payload.get("widgets")
    expected_widget_ids = [widget["id"] for widget in expected["widgets"]]
    if not isinstance(widgets_payload, list):
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")

    payload_widget_ids = [widget.get("id") for widget in widgets_payload if isinstance(widget, dict)]
    if (
        len(widgets_payload) != len(expected_widget_ids)
        or len(payload_widget_ids) != len(expected_widget_ids)
        or set(payload_widget_ids) != set(expected_widget_ids)
    ):
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")

    expected_widgets_by_id = {widget["id"]: widget for widget in expected["widgets"]}
    for widget_payload in widgets_payload:
        if not isinstance(widget_payload, dict):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
        widget_id = widget_payload.get("id")
        expected_widget = expected_widgets_by_id.get(widget_id)
        if expected_widget is None or set(widget_payload) != set(expected_widget):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
        if (
            not isinstance(widget_payload.get("bindings"), dict)
            or set(widget_payload["bindings"]) != set(expected_widget["bindings"])
            or not isinstance(widget_payload.get("style"), dict)
            or set(widget_payload["style"]) != set(expected_widget["style"])
        ):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
