from copy import deepcopy

from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig


def _legacy_broadcast_runner_preset() -> HudConfig:
    return HudConfig(
        theme=HudThemeConfig(
            text_rgba=[247, 251, 255, 255],
            font_family="sans",
            font_weight="regular",
            font_size_px=18,
            title_font_family=None,
            value_font_family=None,
            unit_font_family=None,
            show_units=True,
        ),
        widgets=[
            HudWidgetConfig(
                "distance-ruler",
                "progress_bar",
                {"value": "distance_m"},
                "top-left",
                360,
                28,
                560,
                56,
                40,
                True,
                {
                    "label": "Distance",
                    "variant": "ruler",
                    "show_current_value": True,
                    "show_total_value": True,
                },
            ),
            HudWidgetConfig(
                "elevation-stat",
                "stat_block",
                {"value": "altitude_m"},
                "top-left",
                44,
                146,
                160,
                86,
                30,
                True,
                {"label": "Elevation", "unit": "M"},
            ),
            HudWidgetConfig(
                "distance-stat",
                "stat_block",
                {"value": "distance_m"},
                "top-left",
                44,
                320,
                210,
                88,
                30,
                True,
                {"label": "Distance", "unit": "KM", "decimals": 2},
            ),
            HudWidgetConfig(
                "heart-rate-stat",
                "stat_block",
                {"value": "heart_rate_bpm"},
                "top-right",
                1100,
                132,
                138,
                82,
                30,
                True,
                {"label": "Heart rate", "unit": "BPM", "align": "right"},
            ),
            HudWidgetConfig(
                "pace-chip",
                "metric_card",
                {"value": "pace_seconds_per_km"},
                "bottom-right",
                980,
                560,
                120,
                72,
                20,
                True,
                {"label": "Pace", "variant": "compact"},
            ),
            HudWidgetConfig(
                "cadence-chip",
                "metric_card",
                {"value": "cadence_spm"},
                "bottom-right",
                1110,
                560,
                120,
                72,
                20,
                True,
                {"label": "Cadence", "variant": "compact"},
            ),
            HudWidgetConfig(
                "elapsed-chip",
                "metric_card",
                {"value": "elapsed_seconds"},
                "bottom-right",
                980,
                642,
                120,
                72,
                20,
                True,
                {"label": "Elapsed", "variant": "compact"},
            ),
            HudWidgetConfig(
                "speed-chip",
                "metric_card",
                {"value": "speed_mps"},
                "bottom-right",
                1110,
                642,
                120,
                72,
                20,
                True,
                {"label": "Speed", "variant": "speed_gauge"},
            ),
            HudWidgetConfig(
                "route-map",
                "route_map",
                {"value": "route_points"},
                "top-left",
                26,
                514,
                180,
                180,
                20,
                True,
                {"label": "", "shape": "circle", "show_panel": True},
            ),
        ],
    )


def broadcast_runner_preset() -> HudConfig:
    return HudConfig(
        theme=HudThemeConfig(
            text_rgba=[247, 251, 255, 255],
            font_family="broadcast_value",
            font_weight="regular",
            font_size_px=18,
            title_font_family="broadcast_value",
            title_font_weight="regular",
            title_font_size_px=16,
            value_font_family="broadcast_value",
            value_font_weight="bold",
            value_font_size_px=32,
            unit_font_family="broadcast_value",
            unit_font_weight="regular",
            unit_font_size_px=13,
            show_units=True,
        ),
        widgets=[
            HudWidgetConfig(
                "time-chip",
                "context_card",
                {"value": "timestamp"},
                "top-left",
                44,
                40,
                292,
                56,
                36,
                True,
                {"variant": "timestamp_chip", "format": "%Y/%m/%d %H:%M:%S"},
            ),
            HudWidgetConfig(
                "distance-ruler",
                "progress_bar",
                {"value": "distance_m"},
                "top-left",
                359,
                40,
                560,
                56,
                40,
                True,
                {
                    "label": "Distance",
                    "variant": "ruler",
                    "show_current_value": True,
                    "show_total_value": True,
                    "fill_rgba": [34, 255, 138, 255],
                    "rail_rgba": [8, 12, 20, 220],
                    "tick_rgba": [230, 238, 245, 168],
                },
            ),
            HudWidgetConfig(
                "elevation-stat",
                "stat_block",
                {"value": "altitude_m"},
                "top-left",
                44,
                122,
                152,
                82,
                30,
                True,
                {"label": "Elevation", "unit": "M"},
            ),
            HudWidgetConfig(
                "distance-stat",
                "stat_block",
                {"value": "distance_m"},
                "top-left",
                44,
                208,
                196,
                84,
                30,
                True,
                {"label": "Distance", "unit": "KM", "decimals": 2},
            ),
            HudWidgetConfig(
                "heart-rate-stat",
                "stat_block",
                {"value": "heart_rate_bpm"},
                "top-right",
                1092,
                118,
                152,
                82,
                30,
                True,
                {"label": "Heart rate", "unit": "BPM", "align": "right"},
            ),
            HudWidgetConfig(
                "pace-chip",
                "metric_card",
                {"value": "pace_seconds_per_km"},
                "bottom-right",
                978,
                552,
                126,
                76,
                20,
                True,
                {"label": "Pace", "variant": "compact"},
            ),
            HudWidgetConfig(
                "cadence-chip",
                "metric_card",
                {"value": "cadence_spm"},
                "bottom-right",
                1110,
                552,
                126,
                76,
                20,
                True,
                {"label": "Cadence", "variant": "compact"},
            ),
            HudWidgetConfig(
                "elapsed-chip",
                "metric_card",
                {"value": "elapsed_seconds"},
                "bottom-right",
                978,
                636,
                126,
                76,
                20,
                True,
                {"label": "Elapsed", "variant": "compact"},
            ),
            HudWidgetConfig(
                "speed-chip",
                "metric_card",
                {"value": "speed_mps"},
                "bottom-right",
                1110,
                636,
                126,
                76,
                20,
                True,
                {"label": "Speed", "variant": "speed_gauge"},
            ),
            HudWidgetConfig(
                "route-map",
                "route_map",
                {"value": "route_points"},
                "top-left",
                21,
                488,
                196,
                196,
                20,
                True,
                {
                    "label": "",
                    "shape": "circle",
                    "zoom_percent": 90,
                    "show_panel": True,
                    "show_north_marker": True,
                    "show_bearing_label": True,
                    "background_rgba": [6, 10, 18, 148],
                    "completed_rgba": [34, 255, 138, 255],
                    "remaining_rgba": [13, 144, 195, 255],
                },
            ),
        ],
    )


def migrate_broadcast_runner_config(config: HudConfig) -> HudConfig:
    if config.preset != "broadcast-runner":
        return config

    migrated = deepcopy(config)
    legacy = _legacy_broadcast_runner_preset()
    refreshed = broadcast_runner_preset()

    _migrate_broadcast_runner_theme(migrated.theme, legacy.theme, refreshed.theme)

    legacy_by_id = {widget.id: widget for widget in legacy.widgets}
    refreshed_by_id = {widget.id: widget for widget in refreshed.widgets}
    existing_by_id = {widget.id: widget for widget in migrated.widgets}

    for widget_id, default_widget in refreshed_by_id.items():
        existing = existing_by_id.get(widget_id)
        if existing is None:
            if widget_id == "time-chip":
                migrated.widgets.append(deepcopy(default_widget))
            continue

        legacy_widget = legacy_by_id.get(widget_id)
        if legacy_widget is not None and _geometry_nearly_matches(existing, legacy_widget):
            existing.x = default_widget.x
            existing.y = default_widget.y
            existing.width = default_widget.width
            existing.height = default_widget.height
            existing.z_index = default_widget.z_index

        _migrate_widget_style(existing, legacy_widget, default_widget)

    return migrated


def _migrate_broadcast_runner_theme(
    theme: HudThemeConfig,
    legacy_theme: HudThemeConfig,
    refreshed_theme: HudThemeConfig,
) -> None:
    legacy_font_family = theme.font_family == legacy_theme.font_family
    legacy_font_weight = theme.font_weight == legacy_theme.font_weight
    legacy_font_size = theme.font_size_px == legacy_theme.font_size_px

    if legacy_font_family:
        theme.font_family = refreshed_theme.font_family

    if legacy_font_family and _should_backfill_theme_role(theme.title_font_family, legacy_theme.font_family):
        theme.title_font_family = refreshed_theme.title_font_family
    if legacy_font_weight and _should_backfill_theme_role(theme.title_font_weight, legacy_theme.font_weight):
        theme.title_font_weight = refreshed_theme.title_font_weight
    if legacy_font_size and _should_backfill_theme_role(theme.title_font_size_px, legacy_theme.font_size_px):
        theme.title_font_size_px = refreshed_theme.title_font_size_px

    if legacy_font_family and _should_backfill_theme_role(theme.value_font_family, legacy_theme.font_family):
        theme.value_font_family = refreshed_theme.value_font_family
    if legacy_font_weight and _should_backfill_theme_role(theme.value_font_weight, legacy_theme.font_weight):
        theme.value_font_weight = refreshed_theme.value_font_weight
    if legacy_font_size and _should_backfill_theme_role(theme.value_font_size_px, legacy_theme.font_size_px):
        theme.value_font_size_px = refreshed_theme.value_font_size_px

    if legacy_font_family and _should_backfill_theme_role(theme.unit_font_family, legacy_theme.font_family):
        theme.unit_font_family = refreshed_theme.unit_font_family
    if legacy_font_weight and _should_backfill_theme_role(theme.unit_font_weight, legacy_theme.font_weight):
        theme.unit_font_weight = refreshed_theme.unit_font_weight
    if legacy_font_size and _should_backfill_theme_role(theme.unit_font_size_px, legacy_theme.font_size_px):
        theme.unit_font_size_px = refreshed_theme.unit_font_size_px


def _should_backfill_theme_role(value: str | int | None, legacy_value: str | int) -> bool:
    return value is None or value == legacy_value


def _geometry_nearly_matches(widget: HudWidgetConfig, reference: HudWidgetConfig) -> bool:
    return (
        widget.x,
        widget.y,
        widget.width,
        widget.height,
        widget.z_index,
    ) == (
        reference.x,
        reference.y,
        reference.width,
        reference.height,
        reference.z_index,
    )


def _migrate_widget_style(
    widget: HudWidgetConfig,
    legacy_widget: HudWidgetConfig | None,
    default_widget: HudWidgetConfig,
) -> None:
    legacy_style = legacy_widget.style if legacy_widget is not None else {}
    for key, value in default_widget.style.items():
        if key not in widget.style:
            widget.style[key] = deepcopy(value)
            continue
        if key in legacy_style and widget.style[key] == legacy_style[key]:
            widget.style[key] = deepcopy(value)


def apply_legacy_field_visibility(config: HudConfig, fields: dict[str, bool]) -> HudConfig:
    updated = deepcopy(config)
    legacy_field_keys = ("pace", "elapsed", "distance", "speed", "heart_rate", "cadence", "mini_map")
    show_any_field = any(fields.get(key, True) for key in legacy_field_keys)
    visibility_map = {
        "time-chip": show_any_field,
        "distance-ruler": fields.get("distance", True),
        "elevation-stat": fields.get("distance", True),
        "distance-stat": fields.get("distance", True),
        "heart-rate-stat": fields.get("heart_rate", True),
        "pace-chip": fields.get("pace", True),
        "cadence-chip": fields.get("cadence", True),
        "elapsed-chip": fields.get("elapsed", True),
        "speed-chip": fields.get("speed", True),
        "route-map": fields.get("mini_map", True),
    }
    for widget in updated.widgets:
        if widget.id in visibility_map:
            widget.visible = visibility_map[widget.id]
    return updated
