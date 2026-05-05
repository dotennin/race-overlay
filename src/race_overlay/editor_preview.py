from dataclasses import replace
import hashlib
import json
import shutil
import tempfile
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock

import yaml

from race_overlay.config import (
    ProjectConfig,
    _load_hud_config,
    _locked_config_save,
    load_config,
    resolve_path_from_config,
    resolve_video_globs_from_config,
    save_config,
)
from race_overlay.hud import render_hud_frame
from race_overlay.hud_schema import HUD_FONT_FAMILY_OPTIONS, HUD_FONT_WEIGHT_OPTIONS, HudConfig, HudWidgetConfig, serialize_hud_config
from race_overlay.models import ActivityLap, HudSample
from race_overlay.sampling import LapWaterfallState, lap_waterfall_state_for_widget

_EDITOR_SAVE_LOCK = Lock()
_EDITOR_REVISION_FIELD = "revision"
_ACTIVITY_FILE_SUFFIXES = {".fit", ".tcx"}
_VIDEO_FILE_SUFFIXES = {".avi", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts"}
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
        "variant": {"kind": "selection", "label": "Variant", "options": ["compact", "speed_gauge"]},
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
        "zoom_percent": {
            "kind": "range",
            "label": "Route scale",
            "min": 70,
            "max": 140,
            "step": 1,
            "suffix": "%",
        },
        "show_panel": {"kind": "boolean", "label": "Show panel"},
        "background_rgba": {"kind": "rgba", "label": "Background RGBA"},
        "completed_rgba": {"kind": "rgba", "label": "Completed RGBA"},
        "remaining_rgba": {"kind": "rgba", "label": "Remaining RGBA"},
        "show_north_marker": {"kind": "boolean", "label": "Show north marker"},
        "show_bearing_label": {"kind": "boolean", "label": "Show bearing label"},
    },
    "lap_waterfall": {
        "visible_rows": {"kind": "integer", "label": "Visible rows", "min": 1},
        "always_show": {"kind": "boolean", "label": "Always show"},
        "fade_after_seconds": {"kind": "integer", "label": "Fade after seconds", "min": 1},
        "show_distance": {"kind": "boolean", "label": "Show distance"},
        "show_time": {"kind": "boolean", "label": "Show time"},
        "show_pace": {"kind": "boolean", "label": "Show pace"},
        "show_elevation": {"kind": "boolean", "label": "Show elevation"},
        "show_heart_rate": {"kind": "boolean", "label": "Show heart rate"},
        "value_font_family": {"kind": "enum", "label": "Value font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "value_font_weight": {"kind": "enum", "label": "Value font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "value_font_size_px": {"kind": "integer", "label": "Value font size", "min": 8},
        "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
        "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
        "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    },
}


class StaleHudSaveError(ValueError):
    """Raised when an editor save is based on outdated HUD state."""


def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.08358,
        longitude=140.20992,
        altitude_m=25.0,
        distance_m=5210.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=133,
        cadence_spm=178,
    )


def _sample_route_points() -> list[tuple[float, float]]:
    return [
        (36.08320, 140.20990),
        (36.08320, 140.21025),
        (36.08326, 140.21042),
        (36.08340, 140.21052),
        (36.08356, 140.21052),
        (36.08370, 140.21042),
        (36.08376, 140.21025),
        (36.08376, 140.20990),
        (36.08370, 140.20973),
        (36.08356, 140.20963),
        (36.08340, 140.20963),
        (36.08326, 140.20973),
        (36.08320, 140.20990),
    ]


def _sample_laps() -> list[ActivityLap]:
    base = datetime(2026, 4, 19, 8, 0, 0, tzinfo=timezone.utc)
    return [
        ActivityLap(
            start_time=base,
            total_time_seconds=360.0,
            distance_m=1000.0,
            avg_heart_rate_bpm=148,
            max_heart_rate_bpm=158,
            max_speed_mps=4.2,
            elevation_delta_m=2.0,
            calories=52,
        ),
        ActivityLap(
            start_time=base + timedelta(seconds=360),
            total_time_seconds=355.0,
            distance_m=1000.0,
            avg_heart_rate_bpm=151,
            max_heart_rate_bpm=161,
            max_speed_mps=4.3,
            elevation_delta_m=-1.0,
            calories=51,
        ),
        ActivityLap(
            start_time=base + timedelta(seconds=715),
            total_time_seconds=350.0,
            distance_m=1000.0,
            avg_heart_rate_bpm=154,
            max_heart_rate_bpm=164,
            max_speed_mps=4.4,
            elevation_delta_m=1.5,
            calories=50,
        ),
    ]


def _sample_lap_waterfall_states(hud_config: HudConfig) -> dict[str, LapWaterfallState]:
    laps = _sample_laps()
    last_lap = laps[-1]
    when = last_lap.start_time + timedelta(seconds=last_lap.total_time_seconds + 1)
    return {
        widget.id: lap_waterfall_state_for_widget(_preview_lap_waterfall_widget(widget), laps, when)
        for widget in hud_config.widgets
        if widget.visible and widget.type == "lap_waterfall"
    }


def _preview_lap_waterfall_widget(widget: HudWidgetConfig) -> HudWidgetConfig:
    return replace(widget, style={**widget.style, "always_show": True})


def _next_overlay_widget_id(base_id: str, existing_ids: set[str]) -> str:
    candidate = base_id
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    existing_ids.add(candidate)
    return candidate


def _overlay_library(hud_config: HudConfig) -> list[dict[str, object]]:
    catalog = json.loads(
        json.dumps(
            [
                {
                    "type": "progress_bar",
                    "label": "Distance ruler",
                    "defaults": {
                        "id": "distance-ruler",
                        "type": "progress_bar",
                        "bindings": {"value": "distance_m"},
                        "anchor": "bottom-left",
                        "x": 40,
                        "y": 56,
                        "width": 420,
                        "height": 72,
                        "z_index": 10,
                        "visible": True,
                        "style": {"label": "Distance", "variant": "ruler"},
                    },
                },
                {
                    "type": "stat_block",
                    "label": "Stat block",
                    "defaults": {
                        "id": "stat-block",
                        "type": "stat_block",
                        "bindings": {"value": "altitude_m"},
                        "anchor": "top-left",
                        "x": 44,
                        "y": 146,
                        "width": 160,
                        "height": 86,
                        "z_index": 30,
                        "visible": True,
                        "style": {"label": "Elevation", "unit": "M"},
                    },
                },
                {
                    "type": "stat_block",
                    "label": "Elevation stat",
                    "defaults": {
                        "id": "elevation-stat",
                        "type": "stat_block",
                        "bindings": {"value": "altitude_m"},
                        "anchor": "top-left",
                        "x": 44,
                        "y": 146,
                        "width": 160,
                        "height": 86,
                        "z_index": 30,
                        "visible": True,
                        "style": {"label": "Elevation", "unit": "M"},
                    },
                },
                {
                    "type": "stat_block",
                    "label": "Distance stat",
                    "defaults": {
                        "id": "distance-stat",
                        "type": "stat_block",
                        "bindings": {"value": "distance_m"},
                        "anchor": "top-left",
                        "x": 44,
                        "y": 320,
                        "width": 210,
                        "height": 88,
                        "z_index": 30,
                        "visible": True,
                        "style": {"label": "Distance", "unit": "KM"},
                    },
                },
                {
                    "type": "stat_block",
                    "label": "Heart rate stat",
                    "defaults": {
                        "id": "heart-rate-stat",
                        "type": "stat_block",
                        "bindings": {"value": "heart_rate_bpm"},
                        "anchor": "top-right",
                        "x": 1100,
                        "y": 132,
                        "width": 138,
                        "height": 82,
                        "z_index": 30,
                        "visible": True,
                        "style": {"label": "Heart rate", "unit": "BPM", "align": "right"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Metric card",
                    "defaults": {
                        "id": "metric-card",
                        "type": "metric_card",
                        "bindings": {"value": "pace_seconds_per_km"},
                        "anchor": "bottom-right",
                        "x": 980,
                        "y": 560,
                        "width": 120,
                        "height": 72,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Pace", "variant": "compact"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Pace chip",
                    "defaults": {
                        "id": "pace-chip",
                        "type": "metric_card",
                        "bindings": {"value": "pace_seconds_per_km"},
                        "anchor": "bottom-right",
                        "x": 980,
                        "y": 560,
                        "width": 120,
                        "height": 72,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Pace", "variant": "compact"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Cadence chip",
                    "defaults": {
                        "id": "cadence-chip",
                        "type": "metric_card",
                        "bindings": {"value": "cadence_spm"},
                        "anchor": "bottom-right",
                        "x": 1110,
                        "y": 560,
                        "width": 120,
                        "height": 72,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Cadence", "variant": "compact"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Elapsed chip",
                    "defaults": {
                        "id": "elapsed-chip",
                        "type": "metric_card",
                        "bindings": {"value": "elapsed_seconds"},
                        "anchor": "bottom-right",
                        "x": 980,
                        "y": 642,
                        "width": 120,
                        "height": 72,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Elapsed", "variant": "compact"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Speed chip",
                    "defaults": {
                        "id": "speed-chip",
                        "type": "metric_card",
                        "bindings": {"value": "speed_mps"},
                        "anchor": "bottom-right",
                        "x": 1110,
                        "y": 642,
                        "width": 120,
                        "height": 120,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Speed", "variant": "speed_gauge"},
                    },
                },
                {
                    "type": "metric_card",
                    "label": "Stride card",
                    "defaults": {
                        "id": "stride-chip",
                        "type": "metric_card",
                        "bindings": {"value": "stride_length_m"},
                        "anchor": "bottom-right",
                        "x": 848,
                        "y": 552,
                        "width": 126,
                        "height": 76,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Stride", "variant": "compact"},
                    },
                },
                {
                    "type": "hero_metric",
                    "label": "Hero metric",
                    "defaults": {
                        "id": "hero-metric",
                        "type": "hero_metric",
                        "bindings": {"value": "pace_seconds_per_km"},
                        "anchor": "bottom-left",
                        "x": 40,
                        "y": 560,
                        "width": 240,
                        "height": 120,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Pace"},
                    },
                },
                {
                    "type": "context_card",
                    "label": "Context card",
                    "defaults": {
                        "id": "context-card",
                        "type": "context_card",
                        "bindings": {"value": "timestamp"},
                        "anchor": "top-left",
                        "x": 44,
                        "y": 40,
                        "width": 292,
                        "height": 56,
                        "z_index": 36,
                        "visible": True,
                        "style": {
                            "variant": "compact",
                            "format": "",
                        },
                    },
                },
                {
                    "type": "context_card",
                    "label": "Time chip",
                    "defaults": {
                        "id": "time-chip",
                        "type": "context_card",
                        "bindings": {"value": "timestamp"},
                        "anchor": "top-left",
                        "x": 44,
                        "y": 40,
                        "width": 292,
                        "height": 56,
                        "z_index": 36,
                        "visible": True,
                        "style": {
                            "variant": "timestamp_chip",
                            "format": "%Y/%m/%d %H:%M:%S",
                        },
                    },
                },
                {
                    "type": "route_map",
                    "label": "Route map",
                    "defaults": {
                        "id": "route-map",
                        "type": "route_map",
                        "bindings": {"value": "route_points"},
                        "anchor": "top-left",
                        "x": 26,
                        "y": 514,
                        "width": 180,
                        "height": 180,
                        "z_index": 20,
                        "visible": True,
                        "style": {"label": "Route map", "shape": "circle", "show_panel": True},
                    },
                },
                {
                    "type": "lap_waterfall",
                    "label": "Lap waterfall",
                    "defaults": {
                        "id": "lap-waterfall",
                        "type": "lap_waterfall",
                        "bindings": {"value": "laps"},
                        "anchor": "bottom-right",
                        "x": 40,
                        "y": 120,
                        "width": 420,
                        "height": 220,
                        "z_index": 30,
                        "visible": True,
                        "style": {"visible_rows": 5},
                    },
                },
            ]
        )
    )
    existing_ids = {widget.id for widget in hud_config.widgets}
    for entry in catalog:
        defaults = entry["defaults"]
        defaults["id"] = _next_overlay_widget_id(defaults["id"], existing_ids)
    return catalog


def build_editor_state(
    config: ProjectConfig,
    width: int,
    height: int,
    *,
    config_path: Path | None = None,
) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "project": _build_project_state(config, config_path),
        "schema": _build_editor_schema(config.hud),
        "overlay_library": _overlay_library(config.hud),
        "revision": _hud_revision(config.hud),
        "preview": {
            "width": width,
            "height": height,
            "route_points": _sample_route_points(),
        },
    }


def _build_project_state(config: ProjectConfig, config_path: Path | None) -> dict[str, object]:
    choices = {
        "activity_files": [],
        "video_files": [],
        "output_dirs": [],
    }
    config_display = {"name": "", "path": ""}
    if config_path is not None:
        config_display = {"name": config_path.name, "path": str(config_path)}
        config_dir = config_path.resolve().parent
        choices = {
            "activity_files": _discover_relative_paths(config_dir, _ACTIVITY_FILE_SUFFIXES, files_only=True),
            "video_files": _discover_relative_paths(config_dir, _VIDEO_FILE_SUFFIXES, files_only=True),
            "output_dirs": _discover_relative_paths(config_dir, set(), directories_only=True),
        }
    return {
        "config_path": config_display,
        "activity_file": config.activity_file,
        "video_globs": list(config.video_globs),
        "output_dir": config.output_dir,
        "choices": choices,
    }


def _discover_relative_paths(
    config_dir: Path,
    suffixes: set[str],
    *,
    files_only: bool = False,
    directories_only: bool = False,
) -> list[str]:
    matches: list[str] = []
    if directories_only:
        for candidate in sorted(config_dir.iterdir()):
            if candidate.is_dir():
                matches.append(candidate.relative_to(config_dir).as_posix())
        return matches
    for candidate in sorted(config_dir.rglob("*")):
        if files_only:
            if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                continue
        else:
            continue
        matches.append(candidate.relative_to(config_dir).as_posix())
    return matches


def _require_project_payload_path(
    config_path: Path,
    value: object,
    *,
    label: str,
    file_kind: str,
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    resolved = resolve_path_from_config(config_path, value)
    if file_kind == "file":
        if not resolved.is_file():
            raise ValueError(f"{label} must point to an existing file")
    elif not resolved.is_dir():
        raise ValueError(f"{label} must point to an existing directory")
    return _record_project_payload_path(config_path, resolved)


def _require_project_payload_video_paths(config_path: Path, value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("video_globs must be a non-empty list")
    normalized: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry:
            raise ValueError("video_globs entries must be non-empty strings")
        normalized.append(entry)
    return normalized


def _path_relative_to_config_dir(config_path: Path, path: Path) -> str:
    config_dir = config_path.resolve().parent
    return path.resolve().relative_to(config_dir).as_posix()


def _record_project_payload_path(config_path: Path, path: Path) -> str:
    resolved = path.resolve()
    config_dir = config_path.resolve().parent
    if resolved.is_relative_to(config_dir):
        return resolved.relative_to(config_dir).as_posix()
    return str(resolved)


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


def save_editor_project_payload(config_path: Path, payload: dict[str, object]) -> None:
    if not isinstance(payload, dict):
        raise TypeError("project config payload must be a JSON object")
    allowed_keys = {"activity_file", "video_globs", "output_dir"}
    unexpected_keys = set(payload) - allowed_keys
    if unexpected_keys:
        raise ValueError(f"project config payload contains unsupported fields: {', '.join(sorted(unexpected_keys))}")
    if not any(key in payload for key in allowed_keys):
        raise ValueError("project config payload requires at least one field")

    latest_config = load_editor_config(config_path)
    if "activity_file" in payload:
        latest_config.activity_file = _require_project_payload_path(
            config_path,
            payload.get("activity_file"),
            label="activity_file",
            file_kind="file",
        )
    if "video_globs" in payload:
        latest_config.video_globs = _require_project_payload_video_paths(config_path, payload.get("video_globs"))
    if "output_dir" in payload:
        output_dir = payload.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a non-empty string")
        latest_config.output_dir = output_dir

    with _EDITOR_SAVE_LOCK:
        with _locked_config_save(config_path):
            save_config(config_path, latest_config)


def render_preview_png(config: ProjectConfig, width: int, height: int) -> bytes:
    _validate_preview_dimensions(width, height)
    lap_states = _sample_lap_waterfall_states(config.hud)
    image = render_hud_frame(
        width,
        height,
        _sample_hud_value(),
        _sample_route_points(),
        config.hud,
        6852,
        total_distance_m=10000.0,
        lap_states=lap_states,
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


@contextmanager
def editor_render_snapshot(config_path: Path, payload: dict[str, object]):
    config = load_editor_config(config_path)
    _validate_complete_hud_payload(config.hud, payload)
    snapshot_hud = _load_hud_config(payload, require_complete=True)
    snapshot_config = ProjectConfig(
        activity_file=str(resolve_path_from_config(config_path, config.activity_file)),
        video_globs=resolve_video_globs_from_config(config_path, config.video_globs),
        output_dir=str(resolve_path_from_config(config_path, config.output_dir)),
        cache_dir=str(resolve_path_from_config(config_path, config.cache_dir)),
        timeline=config.timeline,
        hud=snapshot_hud,
        overrides=dict(config.overrides),
    )
    temp_dir = Path(tempfile.mkdtemp(prefix="race-overlay-editor-render-"))
    snapshot_path = temp_dir / config_path.name
    save_config(snapshot_path, snapshot_config)
    try:
        yield snapshot_path
    finally:
        with suppress(FileNotFoundError):
            shutil.rmtree(temp_dir)


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
    if not isinstance(widgets_payload, list):
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
    
    # Allow empty widgets list only if existing HUD also has no widgets
    if len(widgets_payload) == 0 and len(existing_hud.widgets) > 0:
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")

    payload_widget_ids = [widget.get("id") for widget in widgets_payload if isinstance(widget, dict)]
    if len(payload_widget_ids) != len(widgets_payload):
        raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")

    expected_widgets_by_id = {widget["id"]: widget for widget in expected["widgets"]}
    for widget_payload in widgets_payload:
        if not isinstance(widget_payload, dict) or set(widget_payload) != set(HudWidgetConfig.__dataclass_fields__):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
        expected_widget = expected_widgets_by_id.get(widget_payload.get("id"))
        payload_style = widget_payload.get("style")
        if (
            not isinstance(widget_payload.get("bindings"), dict)
            or not isinstance(payload_style, dict)
        ):
            raise ValueError("editor save requires a complete HUD document with all theme fields and widgets")
        if expected_widget is None:
            continue
        expected_style_keys = set(expected_widget["style"])
        if (
            set(widget_payload["bindings"]) != set(expected_widget["bindings"])
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
    widget_types = {widget.type for widget in hud.widgets} | set(_WIDGET_STYLE_SCHEMA_BY_TYPE)
    return {
        "theme": json.loads(json.dumps(_THEME_FIELD_SCHEMA)),
        "widget_types": {
            widget_type: {
                "type": widget_type,
                "style": _widget_type_style_schema(widget_type),
            }
            for widget_type in sorted(widget_types)
        },
        "widgets": {
            widget.id: {
                "type": widget.type,
                "style": _widget_style_schema(widget),
            }
            for widget in hud.widgets
        },
    }


def _widget_type_style_schema(widget_type: str) -> dict[str, object]:
    return json.loads(json.dumps(dict(_WIDGET_STYLE_SCHEMA_BY_TYPE.get(widget_type, {}))))


def _widget_style_schema(widget: HudWidgetConfig) -> dict[str, object]:
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
