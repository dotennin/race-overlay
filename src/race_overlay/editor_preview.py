import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock

import yaml

from race_overlay.config import ProjectConfig, _load_hud_config, _locked_config_save, load_config, save_config
from race_overlay.hud import render_hud_frame
from race_overlay.hud_schema import HUD_FONT_FAMILY_OPTIONS, HUD_FONT_WEIGHT_OPTIONS, HudConfig, serialize_hud_config
from race_overlay.models import HudSample

_EDITOR_SAVE_LOCK = Lock()
_EDITOR_REVISION_FIELD = "revision"
_THEME_FIELD_SCHEMA = {
    "text_rgba": {"kind": "rgba", "label": "Text RGBA"},
    "note_text": {"kind": "text", "label": "Theme note"},
    "font_family": {"kind": "enum", "label": "Font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "font_weight": {"kind": "enum", "label": "Font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "font_size_px": {"kind": "integer", "label": "Font size", "min": 8},
    "title_font_family": {"kind": "enum", "label": "Title font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "title_font_weight": {"kind": "enum", "label": "Title font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "title_font_size_px": {"kind": "integer", "label": "Title font size", "min": 8},
    "value_font_family": {"kind": "enum", "label": "Value font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "value_font_weight": {"kind": "enum", "label": "Value font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "value_font_size_px": {"kind": "integer", "label": "Value font size", "min": 8},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "show_units": {"kind": "boolean", "label": "Show units"},
}
_WIDGET_STYLE_SCHEMA_BY_TYPE = {
    "progress_bar": {
        "label": {"kind": "text", "label": "Label"},
        "variant": {"kind": "selection", "label": "Variant", "options": ["ruler"]},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
        "current_font_size_px": {"kind": "integer", "label": "Current font size", "min": 8},
        "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
        "show_current_value": {"kind": "boolean", "label": "Show current value"},
        "show_total_value": {"kind": "boolean", "label": "Show total value"},
        "fill_rgba": {"kind": "rgba", "label": "Fill RGBA"},
        "rail_rgba": {"kind": "rgba", "label": "Rail RGBA"},
        "tick_rgba": {"kind": "rgba", "label": "Tick RGBA"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
    "stat_block": {
        "label": {"kind": "text", "label": "Label"},
        "unit": {"kind": "text", "label": "Unit", "hidden": True},
        "variant": {"kind": "selection", "label": "Variant", "options": ["standard", "compact"]},
        "align": {"kind": "selection", "label": "Align", "options": ["left", "right"]},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
        "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
    "metric_card": {
        "label": {"kind": "text", "label": "Label"},
        "variant": {"kind": "selection", "label": "Variant", "options": ["compact"]},
        "align": {"kind": "selection", "label": "Align", "options": ["left", "right"]},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
        "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
    "hero_metric": {
        "label": {"kind": "text", "label": "Label"},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
        "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
    "context_card": {
        "label": {"kind": "text", "label": "Label", "hidden": True},
        "variant": {"kind": "selection", "label": "Variant", "options": ["compact", "timestamp_chip"]},
        "format": {"kind": "text", "label": "Format"},
        "value_font_family": {"kind": "enum", "label": "Value font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "value_font_weight": {"kind": "enum", "label": "Value font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "value_font_size_px": {"kind": "integer", "label": "Value font size", "min": 8},
        "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
    },
    "route_map": {
        "label": {"kind": "text", "label": "Label"},
        "shape": {"kind": "enum", "label": "Shape", "options": ["circle", "rounded-rect", "square"]},
        "show_panel": {"kind": "boolean", "label": "Show panel"},
        "background_rgba": {"kind": "rgba", "label": "Background RGBA"},
        "completed_rgba": {"kind": "rgba", "label": "Completed RGBA"},
        "remaining_rgba": {"kind": "rgba", "label": "Remaining RGBA"},
        "show_north_marker": {"kind": "boolean", "label": "Show north marker"},
        "show_bearing_label": {"kind": "boolean", "label": "Show bearing label"},
        "show_heading_arrow": {"kind": "boolean", "label": "Show heading arrow"},
    },
}


class StaleHudSaveError(ValueError):
    """Raised when an editor save is based on outdated HUD state."""


def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=5210.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=133,
        cadence_spm=178,
    )


def build_editor_state(config: ProjectConfig, width: int, height: int) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "schema": _build_editor_schema(config.hud),
        "revision": _hud_revision(config.hud),
        "preview": {
            "width": width,
            "height": height,
            "route_points": [[36.0832, 140.2106], [36.0834, 140.2108]],
        },
    }


def load_editor_config(config_path: Path) -> ProjectConfig:
    try:
        return load_config(config_path)
    except FileNotFoundError as exc:
        raise ValueError(f"config file not found: {config_path}") from exc
    except IsADirectoryError as exc:
        raise ValueError(f"config file is not a readable file: {config_path}") from exc
    except OSError as exc:
        raise ValueError(f"config file is not readable: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"config file is not valid YAML: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"config file is invalid: {exc}") from exc


def save_editor_payload(config_path: Path, payload: dict[str, object]) -> None:
    config = load_editor_config(config_path)
    hud_payload = _hud_payload_from_editor_save(payload)
    _validate_complete_hud_payload(config.hud, hud_payload)
    updated_hud = _load_hud_config(hud_payload, require_complete=True)
    expected_revision = _editor_payload_revision(payload)

    with _EDITOR_SAVE_LOCK:
        with _locked_config_save(config_path):
            latest_config = load_editor_config(config_path)
            if _hud_revision(latest_config.hud) != expected_revision:
                raise StaleHudSaveError("stale HUD save rejected; reload the editor state and try again")
            latest_config.hud = updated_hud
            save_config(config_path, latest_config)


def render_preview_png(config: ProjectConfig, width: int, height: int) -> bytes:
    _validate_preview_dimensions(width, height)
    image = render_hud_frame(
        width,
        height,
        _sample_hud_value(),
        [(36.0832, 140.2106), (36.0834, 140.2108)],
        config.hud,
        6852,
        total_distance_m=10000.0,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_preview_payload(config_path: Path, payload: dict[str, object], width: int, height: int) -> bytes:
    config = load_editor_config(config_path)
    _validate_complete_hud_payload(config.hud, payload)
    preview_hud = _load_hud_config(payload, require_complete=True)
    preview_config = ProjectConfig(
        activity_file=config.activity_file,
        video_globs=list(config.video_globs),
        output_dir=config.output_dir,
        cache_dir=config.cache_dir,
        timeline=config.timeline,
        hud=preview_hud,
        overrides=dict(config.overrides),
    )
    return render_preview_png(preview_config, width, height)


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
        expected_style_keys = set(expected_widget["style"])
        payload_style = widget_payload.get("style")
        if (
            not isinstance(widget_payload.get("bindings"), dict)
            or set(widget_payload["bindings"]) != set(expected_widget["bindings"])
            or not isinstance(payload_style, dict)
            or (
                not expected_style_keys.issubset(set(payload_style))
                and not (
                    "label" not in expected_style_keys
                    and expected_style_keys | {"label"} <= set(payload_style)
                )
            )
        ):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")


def _hud_payload_from_editor_save(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != _EDITOR_REVISION_FIELD}


def _editor_payload_revision(payload: dict[str, object]) -> str:
    revision = payload.get(_EDITOR_REVISION_FIELD)
    if not isinstance(revision, str) or not revision:
        raise ValueError("editor save requires a revision from /api/state")
    return revision


def _hud_revision(hud: HudConfig) -> str:
    payload = json.dumps(serialize_hud_config(hud), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_editor_schema(hud: HudConfig) -> dict[str, object]:
    return {
        "theme": json.loads(json.dumps(_THEME_FIELD_SCHEMA)),
        "widgets": {
            widget.id: {
                "type": widget.type,
                "style": _widget_style_schema(widget),
            }
            for widget in hud.widgets
        },
    }


def _widget_style_schema(widget) -> dict[str, object]:
    schema = dict(_WIDGET_STYLE_SCHEMA_BY_TYPE.get(widget.type, {}))
    for key, value in widget.style.items():
        schema.setdefault(key, _infer_style_field_schema(key, value))
    return json.loads(json.dumps(schema))


def _infer_style_field_schema(key: str, value: object) -> dict[str, object]:
    if isinstance(value, bool):
        return {"kind": "boolean", "label": _humanize_field_name(key)}
    if isinstance(value, int):
        return {"kind": "integer", "label": _humanize_field_name(key)}
    if isinstance(value, list) and len(value) == 4 and all(isinstance(channel, int) for channel in value):
        return {"kind": "rgba", "label": _humanize_field_name(key).replace("Rgba", "RGBA")}
    return {"kind": "text", "label": _humanize_field_name(key)}


def _humanize_field_name(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()
